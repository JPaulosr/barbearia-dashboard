import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# Carregar nome do cliente vindo da outra página
cliente = st.session_state.get("cliente", None)
if not cliente:
    st.error("Nenhum cliente selecionado.")
    st.stop()

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.strftime('%b')
    return df

df = carregar_dados()
df_cliente = df[df["Cliente"].str.lower() == cliente.lower()]

st.header(f"📋 Dados do cliente: {cliente}")

# Tabela detalhada dos atendimentos
st.subheader("📆 Histórico de Atendimentos")
st.dataframe(df_cliente.sort_values(by="Data", ascending=False), use_container_width=True)

# Receita por mês
st.subheader("📈 Receita Mensal")
receita_mensal = df_cliente.groupby("Mês_Nome")["Valor"].sum().reindex(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
).dropna()
fig_mensal = px.bar(receita_mensal, x=receita_mensal.index, y="Valor", text_auto=True, labels={"Valor": "Receita (R$)"})
st.plotly_chart(fig_mensal, use_container_width=True)

# Receita por serviço
st.subheader("💇 Receita por Tipo de Serviço")
receita_servico = df_cliente.groupby("Serviço")["Valor"].sum().sort_values(ascending=False)
fig_servico = px.bar(receita_servico, x=receita_servico.index, y="Valor", text_auto=True, labels={"Valor": "Receita (R$)"})
st.plotly_chart(fig_servico, use_container_width=True)

# Atendimentos por funcionário
st.subheader("👨‍🔧 Atendimentos por Funcionário")
funcionarios = df_cliente["Funcionário"].value_counts()
fig_func = px.pie(values=funcionarios.values, names=funcionarios.index, title="Distribuição de Atendimentos")
st.plotly_chart(fig_func, use_container_width=True)

st.caption("🔙 Volte para a página anterior para selecionar outro cliente.")

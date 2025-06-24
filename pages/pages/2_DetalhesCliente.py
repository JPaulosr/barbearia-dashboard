import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🔍 Detalhamento do Cliente")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Ano"] = df["Data"].dt.strftime("%Y-%m")
    return df

df = carregar_dados()
cliente = st.session_state.get("cliente", None)

if not cliente:
    st.warning("Nenhum cliente selecionado.")
    st.stop()

st.header(f"👤 Cliente: {cliente}")
df_cliente = df[df["Cliente"] == cliente]

# 📅 Histórico de atendimentos
st.subheader("📅 Histórico de atendimentos")
st.dataframe(df_cliente.sort_values("Data", ascending=False), use_container_width=True)

# 📊 Receita mensal por mês e ano
st.subheader("📊 Receita mensal por mês e ano")
receita_mensal = df_cliente.groupby("Mês_Ano")["Valor"].sum().reset_index()
fig_receita = px.bar(receita_mensal, x="Mês_Ano", y="Valor", labels={"Valor": "Receita (R$)", "Mês_Ano": "Mês/Ano"})
st.plotly_chart(fig_receita, use_container_width=True)

# 🥧 Receita por tipo (Produto ou Serviço)
st.subheader("🥧 Receita por tipo (Produto ou Serviço)")
por_tipo = df_cliente.groupby("Tipo")["Valor"].sum().reset_index()
fig_tipo = px.pie(por_tipo, names="Tipo", values="Valor", hole=0.4)
st.plotly_chart(fig_tipo, use_container_width=True)

# 🧑‍🔧 Distribuição de atendimentos por funcionário
st.subheader("🧑‍🔧 Distribuição de atendimentos por funcionário")
atend_func = df_cliente.groupby("Funcionário")["Data"].nunique().reset_index()
atend_func.columns = ["Funcionário", "Atendimentos"]
fig_func = px.pie(atend_func, names="Funcionário", values="Atendimentos")
st.plotly_chart(fig_func, use_container_width=True)

# 📋 Total de atendimentos, combos e simples
st.subheader("📋 Totais")
agrupar = df_cliente.groupby(["Cliente", "Data"]).agg(
    Qtd_Serviços=('Serviço', 'count')
).reset_index()
agrupar["Combo"] = agrupar["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
agrupar["Simples"] = agrupar["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

total_atend = len(agrupar)
total_combo = agrupar["Combo"].sum()
total_simples = agrupar["Simples"].sum()

st.dataframe(pd.DataFrame({
    "Total Atendimentos": [total_atend],
    "Qtd Combos": [total_combo],
    "Qtd Simples": [total_simples]
}), use_container_width=True)

st.success("✅ Detalhamento concluído com sucesso!")

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🔎 Detalhamento do Cliente")

@st.cache_data

def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    df["Mes"] = df["Data"].dt.month
    df["MesNome"] = df["Data"].dt.strftime('%b')
    return df

df = carregar_dados()

if "cliente" not in st.session_state:
    st.error("Nenhum cliente selecionado. Volte para a página anterior e selecione um cliente.")
    st.stop()

cliente = st.session_state["cliente"]
st.header(f"📋 Detalhes do cliente: {cliente}")
df_cliente = df[df["Cliente"] == cliente]

# 📅 Histórico de atendimentos
st.subheader("📅 Histórico de atendimentos")
st.dataframe(df_cliente.sort_values("Data", ascending=False)[["Data", "Serviço", "Tipo", "Valor", "Funcionário"]], use_container_width=True)

# 📊 Receita mensal por mês e ano
st.subheader("📊 Receita mensal por mês e ano")
df_mensal = df_cliente.groupby(["Ano", "MesNome"])['Valor'].sum().reset_index()
fig_mensal = px.bar(df_mensal, x="MesNome", y="Valor", color="Ano", barmode="group", text_auto=True)
st.plotly_chart(fig_mensal, use_container_width=True)

# 🥧 Receita por tipo (Produto ou Serviço)
st.subheader("🥧 Receita por tipo (Produto ou Serviço)")
df_tipo = df_cliente.groupby("Tipo")["Valor"].sum().reset_index()
fig_tipo = px.pie(df_tipo, names="Tipo", values="Valor", hole=0.4)
st.plotly_chart(fig_tipo, use_container_width=True)

# 🧑‍🔧 Distribuição de atendimentos por funcionário (gráfico de pizza)
st.subheader("🧑‍🔧 Distribuição de atendimentos por funcionário")
df_func = df_cliente.groupby("Funcionário")["Data"].nunique().reset_index(name="Atendimentos")
fig_func = px.pie(df_func, names="Funcionário", values="Atendimentos", hole=0.4)
st.plotly_chart(fig_func, use_container_width=True)

# 📋 Tabela com total de atendimentos, combos e simples
st.subheader("📋 Resumo do cliente")
df_agrupado = df_cliente.groupby("Data").agg(
    qtd_servicos=('Serviço', 'count')
).reset_index()
df_agrupado['Combo'] = df_agrupado['qtd_servicos'].apply(lambda x: 1 if x > 1 else 0)
df_agrupado['Simples'] = df_agrupado['qtd_servicos'].apply(lambda x: 1 if x == 1 else 0)

resumo = {
    "Total Atendimentos": len(df_agrupado),
    "Qtd Combos": df_agrupado['Combo'].sum(),
    "Qtd Simples": df_agrupado['Simples'].sum(),
    "Receita Total": f"R$ {df_cliente['Valor'].sum():,.2f}".replace(',', 'v').replace('.', ',').replace('v', '.')
}
st.dataframe(pd.DataFrame([resumo]), use_container_width=True)

if st.button("⬅ Voltar"):
    st.switch_page("pages/1_Clientes.py")

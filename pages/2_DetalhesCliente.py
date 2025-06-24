import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Mês_Ano"] = df["Data"].dt.strftime("%Y-%m")
    return df

df = carregar_dados()

# Filtro de cliente na própria página
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente = st.selectbox("👤 Escolha um cliente para detalhar", clientes_disponiveis)

if not cliente:
    st.warning("Selecione um cliente para continuar.")
    st.stop()

df_cliente = df[df["Cliente"] == cliente]

# 📅 Histórico
st.subheader(f"📅 Histórico de atendimentos - {cliente}")
st.dataframe(df_cliente.sort_values("Data", ascending=False), use_container_width=True)

# 📊 Receita mensal por tipo (Serviço vs Produto)
st.subheader("📊 Receita mensal por tipo de receita")

receita_tipo = (
    df_cliente.groupby(["Mês_Ano", "Tipo"])["Valor"]
    .sum()
    .reset_index()
)
receita_tipo["Mês_Ano"] = receita_tipo["Mês_Ano"].astype(str)  # força como texto no eixo

fig_receita = px.bar(
    receita_tipo,
    x="Mês_Ano",
    y="Valor",
    color="Tipo",
    text_auto=".2s",
    labels={"Valor": "Receita (R$)", "Mês_Ano": "Mês"},
    barmode="group"
)
fig_receita.update_layout(height=400)
st.plotly_chart(fig_receita, use_container_width=True)

# 🧑‍🔧 Distribuição por funcionário
st.subheader("🧑‍🔧 Atendimentos por Funcionário")
por_func = df_cliente["Funcionário"].value_counts().reset_index()
por_func.columns = ["Funcionário", "Atendimentos"]
fig_func = px.bar(
    por_func,
    x="Funcionário",
    y="Atendimentos",
    text_auto=True
)
fig_func.update_layout(height=350)
st.plotly_chart(fig_func, use_container_width=True)

# 📋 Tabela resumo
st.subheader("📋 Resumo de Atendimentos")
resumo = df_cliente.groupby("Data").agg(
    Qtd_Serviços=("Serviço", "count"),
    Qtd_Produtos=("Tipo", lambda x: (x == "Produto").sum())
).reset_index()

resumo["Qtd_Combo"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
resumo["Qtd_Simples"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

resumo_final = pd.DataFrame({
    "Total Atendimentos": [resumo.shape[0]],
    "Qtd Combos": [resumo["Qtd_Combo"].sum()],
    "Qtd Simples": [resumo["Qtd_Simples"].sum()]
})

st.dataframe(resumo_final, use_container_width=True)

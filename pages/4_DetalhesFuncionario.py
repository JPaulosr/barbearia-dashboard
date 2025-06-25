import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧑‍💼 Detalhamento do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.strftime('%b')
    return df

df = carregar_dados()

# Filtro por ano
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("Selecione o Ano", anos, index=0)
df = df[df["Ano"] == ano]

# Receita mensal por funcionário (ordenado de Jan a Jun)
st.subheader("📈 Receita Mensal por Funcionário")

receita_mensal = df.groupby(["Funcionário", "Mês", "Mês_Nome"])["Valor"].sum().reset_index()
receita_mensal = receita_mensal.sort_values("Mês")

fig = px.bar(
    receita_mensal,
    x="Mês_Nome",
    y="Valor",
    color="Funcionário",
    barmode="group",
    text_auto=True,
    category_orders={"Mês_Nome": ["Jan", "Feb", "Mar", "Apr", "May", "Jun"]}
)
st.plotly_chart(fig, use_container_width=True)

# Total de atendimentos por funcionário
st.subheader("📋 Total de Atendimentos por Funcionário")
atendimentos = df.groupby("Funcionário")["Data"].count().reset_index().rename(columns={"Data": "Qtd Atendimentos"})
st.dataframe(atendimentos, use_container_width=True)

# Distribuição entre combo e simples
st.subheader("🔀 Distribuição de Atendimentos: Combo vs Simples")
agrupado = df.groupby(["Cliente", "Data", "Funcionário"]).agg(
    Qtd_Serviços=("Serviço", "count")
).reset_index()
agrupado["Combo"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
agrupado["Simples"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

combo_simples = agrupado.groupby("Funcionário").agg(
    Total_Atendimentos=("Data", "count"),
    Qtd_Combo=("Combo", "sum"),
    Qtd_Simples=("Simples", "sum")
).reset_index()

st.dataframe(combo_simples, use_container_width=True)

st.markdown("""
---
⬅️ Volte para o menu lateral para acessar outras páginas.
""")

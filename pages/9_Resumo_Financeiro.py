import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("📊 Resumo Financeiro do Salão")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    return df

df = carregar_dados()

anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos, index=0)
df_ano = df[df["Ano"] == ano]

# Separação por fases
data_corte = pd.to_datetime("2025-05-11")
df_fase1 = df_ano[df_ano["Data"] < data_corte]
df_fase2 = df_ano[df_ano["Data"] >= data_corte]

st.header("📘 Fase 1 – JPaulo como prestador de serviço")
receita_fase1 = df_fase1[df_fase1["Funcionário"] == "JPaulo"]["Valor"].sum()
despesas_fase1 = df_fase1[df_fase1["Tipo"] == "Despesa"]["Valor"].sum()
lucro_fase1 = receita_fase1 - despesas_fase1

col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas (comissão paga)", f"R$ {despesas_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Líquido", f"R$ {lucro_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

st.header("📙 Fase 2 – JPaulo como dono do salão")

receita_jpaulo = df_fase2[df_fase2["Funcionário"] == "JPaulo"]["Valor"].sum()
receita_vinicius = df_fase2[df_fase2["Funcionário"] == "Vinicius"]["Valor"].sum() * 0.5
receita_total_salao = receita_jpaulo + receita_vinicius

st.subheader("💵 Receita do Salão")
col1, col2, col3 = st.columns(3)
col1.metric("Receita JPaulo (100%)", f"R$ {receita_jpaulo:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Receita Vinicius (50%)", f"R$ {receita_vinicius:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Receita Total", f"R$ {receita_total_salao:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.subheader("💸 Despesas do Salão")
with st.form("despesas_fixas"):
    col1, col2, col3, col4 = st.columns(4)
    aluguel = col1.number_input("Aluguel", min_value=0.0, value=1200.0, step=50.0)
    agua = col2.number_input("Água", min_value=0.0, value=200.0, step=10.0)
    luz = col3.number_input("Luz", min_value=0.0, value=300.0, step=10.0)
    produtos = col4.number_input("Produtos", min_value=0.0, value=400.0, step=10.0)
    submit = st.form_submit_button("Atualizar valores")

total_despesas_fase2 = aluguel + agua + luz + produtos
lucro_fase2 = receita_total_salao - total_despesas_fase2

col1, col2 = st.columns(2)
col1.metric("Total de Despesas", f"R$ {total_despesas_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Lucro do Salão", f"R$ {lucro_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

st.header("📌 Consolidado do Ano")
receita_total_ano = receita_fase1 + receita_total_salao
despesas_total_ano = despesas_fase1 + total_despesas_fase2
lucro_total_ano = receita_total_ano - despesas_total_ano

col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

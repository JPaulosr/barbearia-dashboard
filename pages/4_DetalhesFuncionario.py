
import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("🏦 Resumo Financeiro do Salão")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    return df

df = carregar_dados()

# === Filtro por ano ===
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos)
df_ano = df[df["Ano"] == ano]

# === Corte entre Fases ===
data_corte = pd.to_datetime("2025-05-11")
fase1 = df_ano[df_ano["Data"] < data_corte]
fase2 = df_ano[df_ano["Data"] >= data_corte]

# === Fase 1: Prestador de Serviço ===
st.header("📘 Fase 1 — JPaulo como prestador (antes de 11/05/2025)")

receita_f1 = fase1[fase1["Funcionário"] == "JPaulo"]["Valor"].sum()

# Buscar despesas na Fase 1
despesas_f1 = fase1[fase1["Tipo"].str.lower().str.contains("despesa", na=False)]
total_despesas_f1 = despesas_f1["Valor"].sum()

st.markdown(f"- Receita bruta JPaulo: **R$ {receita_f1:,.2f}**".replace(",", "v").replace(".", ",").replace("v", "."))
st.markdown(f"- Comissão paga ao dono (despesas): **R$ {total_despesas_f1:,.2f}**".replace(",", "v").replace(".", ",").replace("v", "."))
st.markdown(f"**➡️ Resultado líquido Fase 1:** R$ {(receita_f1 - total_despesas_f1):,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === Fase 2: Dono do salão ===
st.header("📙 Fase 2 — JPaulo como dono (a partir de 11/05/2025)")

receita_jpaulo_f2 = fase2[fase2["Funcionário"] == "JPaulo"]["Valor"].sum()
receita_vinicius_f2 = fase2[fase2["Funcionário"] == "Vinicius"]["Valor"].sum()

receita_salao_f2 = receita_jpaulo_f2 + (receita_vinicius_f2 * 0.5)

st.subheader("📥 Receita do Salão (Fase 2)")
st.markdown(f"- Receita JPaulo (100%): **R$ {receita_jpaulo_f2:,.2f}**".replace(",", "v").replace(".", ",").replace("v", "."))
st.markdown(f"- Receita Vinicius (50%): **R$ {receita_vinicius_f2 * 0.5:,.2f}**".replace(",", "v").replace(".", ",").replace("v", "."))
st.markdown(f"**➡️ Receita total salão:** R$ {receita_salao_f2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === Despesas fixas fase 2 ===
st.subheader("📤 Despesas Fixas (Fase 2)")
col1, col2, col3 = st.columns(3)
aluguel = col1.number_input("Aluguel", min_value=0.0, value=800.0, step=50.0)
agua = col2.number_input("Água", min_value=0.0, value=120.0, step=10.0)
luz = col3.number_input("Luz", min_value=0.0, value=200.0, step=10.0)
produtos = st.number_input("Produtos e materiais", min_value=0.0, value=300.0, step=50.0)

total_despesas_f2 = aluguel + agua + luz + produtos

# === Lucro final Fase 2 ===
st.subheader("📈 Resultado Financeiro (Fase 2)")
lucro_f2 = receita_salao_f2 - total_despesas_f2
st.metric("Lucro do Salão", f"R$ {lucro_f2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === Total geral consolidado ===
st.header("📊 Consolidado do Ano")
receita_total = receita_f1 + receita_salao_f2
despesas_total = total_despesas_f1 + total_despesas_f2
lucro_total = receita_total - despesas_total

st.markdown(f"**Receita Total do Ano:** R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.markdown(f"**Despesas Totais do Ano:** R$ {despesas_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.markdown(f"**Lucro Líquido do Ano:** R$ {lucro_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

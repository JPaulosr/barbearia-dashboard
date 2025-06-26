import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📊 Resumo Financeiro do Salão")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    df = get_as_dataframe(conectar_sheets().worksheet(BASE_ABA)).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    return df

df = carregar_dados()

# === FILTRO POR ANO ===
anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos, index=0)
df_ano = df[df["Ano"] == ano]

# === SEPARAÇÃO POR FASES
data_corte = pd.to_datetime("2025-05-11")
df_fase1 = df_ano[df_ano["Data"] < data_corte]
df_fase2 = df_ano[df_ano["Data"] >= data_corte]

# === FASE 1: JPAULO COMO PRESTADOR
st.header("📘 Fase 1 – JPaulo como prestador de serviço")
receita_fase1 = df_fase1[df_fase1["Funcionário"] == "JPaulo"]["Valor"].sum()
despesas_fase1 = df_fase1[
    (df_fase1["Tipo"] == "Despesa") &
    (df_fase1["Descrição"].str.lower().str.contains("neto"))
]["Valor"].sum()
lucro_fase1 = receita_fase1 - despesas_fase1

col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão paga ao Neto", f"R$ {despesas_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Líquido", f"R$ {lucro_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === FASE 2: JPAULO COMO DONO DO SALÃO
st.header("📙 Fase 2 – JPaulo como dono do salão")

receita_jpaulo = df_fase2[df_fase2["Funcionário"] == "JPaulo"]["Valor"].sum()

# Puxar comissão real do Vinicius
comissao_vinicius = df_fase2[
    (df_fase2["Tipo"] == "Despesa") &
    (df_fase2["Descrição"].str.lower().str.contains("vinicius"))
]["Valor"].sum()

receita_total_salao = receita_jpaulo + comissao_vinicius

st.subheader("💵 Receita do Salão")
col1, col2, col3 = st.columns(3)
col1.metric("Receita JPaulo (100%)", f"R$ {receita_jpaulo:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão paga ao Vinicius", f"R$ {comissao_vinicius:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Receita Total", f"R$ {receita_total_salao:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === DESPESAS FIXAS
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

# === CONSOLIDADO DO ANO
st.header("📌 Consolidado do Ano")
receita_total_ano = receita_fase1 + receita_total_salao
despesas_total_ano = despesas_fase1 + total_despesas_fase2
lucro_total_ano = receita_total_ano - despesas_total_ano

col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.markdown("---")
st.caption("Criado por JPaulo ✨ | Estrutura financeira anual por fase do salão")

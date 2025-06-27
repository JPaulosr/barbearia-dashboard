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
DESPESAS_ABA = "Despesas"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_bases():
    planilha = conectar_sheets()
    base = get_as_dataframe(planilha.worksheet(BASE_ABA)).dropna(how="all")
    despesas = get_as_dataframe(planilha.worksheet(DESPESAS_ABA)).dropna(how="all")

    base.columns = [col.strip() for col in base.columns]
    despesas.columns = [col.strip() for col in despesas.columns]

    base["Data"] = pd.to_datetime(base["Data"], errors="coerce")
    despesas["Data"] = pd.to_datetime(despesas["Data"], errors="coerce")

    base = base.dropna(subset=["Data"])
    despesas = despesas.dropna(subset=["Data"])

    base["Ano"] = base["Data"].dt.year
    despesas["Ano"] = despesas["Data"].dt.year

    return base, despesas

base, despesas = carregar_bases()

anos_disponiveis = sorted(base["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("🗓️ Selecione o Ano", anos_disponiveis, index=0)

base_ano = base[base["Ano"] == ano]
despesas_ano = despesas[despesas["Ano"] == ano]

# === FASE 1: Autônomo (prestador) ===
df_fase1 = base_ano[base_ano["Fase"] == "Autônomo (prestador)"]
df_desp1 = despesas_ano[despesas_ano["Data"] <= df_fase1["Data"].max()]

receita_fase1 = df_fase1[df_fase1["Funcionário"] == "JPaulo"]["Valor"].sum()
despesas_fase1 = df_desp1["Valor"].sum()
lucro_fase1 = receita_fase1 - despesas_fase1

# === FASE 2: Dono Salão (sozinho) ===
df_fase2 = base_ano[base_ano["Fase"] == "Dono Salão"]
df_desp2 = despesas_ano[
    (despesas_ano["Data"] >= df_fase2["Data"].min()) &
    (despesas_ano["Data"] < pd.to_datetime("2025-01-25"))
]
receita_fase2 = df_fase2[df_fase2["Funcionário"] == "JPaulo"]["Valor"].sum()
despesas_fase2 = df_desp2["Valor"].sum()
lucro_fase2 = receita_fase2 - despesas_fase2

# === FASE 3: Dono com Funcionário ===
df_fase3 = base_ano[base_ano["Fase"] == "Funcionário"]
df_desp3 = despesas_ano[despesas_ano["Data"] >= df_fase3["Data"].min()]

receita_jp3 = df_fase3[df_fase3["Funcionário"] == "JPaulo"]["Valor"].sum()
receita_vini3 = df_fase3[df_fase3["Funcionário"] == "Vinicius"]["Valor"].sum()
receita_fase3 = receita_jp3 + receita_vini3
despesas_fase3 = df_desp3["Valor"].sum()
lucro_fase3 = receita_fase3 - despesas_fase3

# === EXIBIÇÃO ===
st.header("📘 Fase 1 – Prestador de Serviço")
col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro", f"R$ {lucro_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()
st.header("📙 Fase 2 – Dono sem Funcionário")
col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro", f"R$ {lucro_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()
st.header("📜 Fase 3 – Dono com Funcionário")
col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_fase3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_fase3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro", f"R$ {lucro_fase3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === CONSOLIDADO ===
st.divider()
st.header("📊 Consolidado do Ano")
receita_total = receita_fase1 + receita_fase2 + receita_fase3
despesas_total = despesas_fase1 + despesas_fase2 + despesas_fase3
lucro_total = receita_total - despesas_total

col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.caption("Criado por JPaulo ✨ | Financeiro segmentado por fase e ano")

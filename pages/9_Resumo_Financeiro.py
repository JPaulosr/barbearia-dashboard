import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📊 Resumo Financeiro do Salão")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

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
    df_base = get_as_dataframe(planilha.worksheet("Base de Dados")).dropna(how="all")
    df_desp = get_as_dataframe(planilha.worksheet("Despesas")).dropna(how="all")

    df_base.columns = df_base.columns.str.strip()
    df_base["Data"] = pd.to_datetime(df_base["Data"], errors="coerce")
    df_base = df_base.dropna(subset=["Data"])
    df_base["Ano"] = df_base["Data"].dt.year

    df_desp.columns = df_desp.columns.str.strip()
    df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce")
    df_desp = df_desp.dropna(subset=["Data"])
    df_desp["Ano"] = df_desp["Data"].dt.year

    return df_base, df_desp

df, df_despesas = carregar_bases()

anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("🗓️ Selecione o Ano", anos)

df_ano = df[df["Ano"] == ano]
df_desp_ano = df_despesas[df_despesas["Ano"] == ano]

# === FASE 1 – AUTÔNOMO / PRESTADOR
fase1 = df_ano[df_ano["Fase"] == "Autônomo (prestador)"]
desp1 = df_desp_ano[df_desp_ano["Descrição"].str.lower().str.contains("neto", na=False) |
                    df_desp_ano["Descrição"].str.lower().str.contains("produto", na=False)]

receita1 = fase1[fase1["Funcionário"] == "JPaulo"]["Valor"].sum()
despesas1 = desp1["Valor"].sum()
lucro1 = receita1 - despesas1

st.subheader("🧊 Fase 1 – Prestador de Serviço")
col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro", f"R$ {lucro1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === FASE 2 – DONO SOZINHO
fase2 = df_ano[df_ano["Fase"] == "Dono Salão"]
desp2 = df_desp_ano[~df_desp_ano["Descrição"].str.lower().str.contains("vinicius", na=False)]

receita2 = fase2[fase2["Funcionário"] == "JPaulo"]["Valor"].sum()
despesas2 = desp2["Valor"].sum()
lucro2 = receita2 - despesas2

st.subheader("🧡 Fase 2 – Dono sem Funcionário")
col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro", f"R$ {lucro2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === FASE 3 – DONO COM FUNCIONÁRIO
fase3 = df_ano[df_ano["Fase"] == "Funcionário"]
desp3 = df_desp_ano[df_desp_ano["Descrição"].str.lower().str.contains("vinicius", na=False)]

receita_jpaulo = fase3[fase3["Funcionário"] == "JPaulo"]["Valor"].sum()
receita_vinicius = fase3[fase3["Funcionário"] == "Vinicius"]["Valor"].sum()
receita3 = receita_jpaulo + receita_vinicius

despesas3 = desp3["Valor"].sum()
lucro3 = receita3 - despesas3

st.subheader("📜 Fase 3 – Dono com Funcionário")
col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro", f"R$ {lucro3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

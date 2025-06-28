
import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="centered")
st.title("🔍 Diagnóstico - Valores Crus das Horas")

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
def carregar_raw():
    aba = conectar_sheets().worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [col.strip() for col in df.columns]
    df = df.dropna(subset=["Data"])
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    return df

df = carregar_raw()

# Filtrar data
df_sel = df[df["Data"].dt.date == pd.to_datetime("2025-06-27").date()]

st.write(f"### Registros do dia 27/06/2025: {len(df_sel)}")
st.dataframe(df_sel[["Cliente", "Funcionário", "Hora Chegada", "Hora Início", "Hora Saída"]])

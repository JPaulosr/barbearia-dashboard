import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(layout="wide")
st.title("📋 Ranking dos Clientes com Maior Tempo de Ausência")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

# === CONEXÃO COM GOOGLE SHEETS ===
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [col.strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data", "Cliente"])
    return df

@st.cache_data
def carregar_status():
    try:
        planilha = conectar_sheets()
        aba = planilha.worksheet(STATUS_ABA)
        status = get_as_dataframe(aba).dropna(how="all")
        status.columns = [col.strip() for col in status.columns]
        return status[["Cliente", "Status"]]
    except:
        return pd.DataFrame(columns=["Cliente", "Status"])

# === PRÉ-PROCESSAMENTO ===
df = carregar_dados()
status_df = carregar_status()

# Remove clientes sem nome
df = df[df["Cliente"].notna() & (df["Cliente"].str.strip() != "")]

# Usa último atendimento por cliente
ultimos = df.groupby("Cliente")["Data"].max().reset_index()
ultimos.columns = ["Cliente", "Data"]

# Calcula dias sem vir
hoje = pd.Timestamp.today().normalize()
ultimos["Dias sem vir"] = (hoje - ultimos["Data"]).dt.days

# Junta com status
ultimos = ultimos.merge(status_df, on="Cliente", how="left")

# Ranking top 20 ausentes
ranking = ultimos.sort_values(by="Dias sem vir", ascending=False).head(20)

# Formata data
ranking["Data"] = ranking["Data"].dt.strftime("%d/%m/%Y")

# Mostra resultado
st.dataframe(ranking, use_container_width=True)

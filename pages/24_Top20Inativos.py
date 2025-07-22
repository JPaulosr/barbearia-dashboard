import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(layout="wide")
st.title("🕒 Top 20 Clientes com Mais Tempo Sem Visitar")

# === CONFIG GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

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
    df = df.dropna(subset=["Data"])
    return df

@st.cache_data
def carregar_status():
    planilha = conectar_sheets()
    aba = planilha.worksheet(STATUS_ABA)
    df_status = get_as_dataframe(aba).dropna(how="all")
    df_status.columns = [col.strip() for col in df_status.columns]
    return df_status[["Cliente", "Status"]]

df = carregar_dados()
df_status = carregar_status()

# === Filtra últimos atendimentos ===
df_ultimos = df.sort_values("Data").drop_duplicates(subset=["Cliente"], keep="last")

# === Cálculo de tempo sem vir ===
hoje = pd.Timestamp.today().normalize()
df_ultimos["Dias sem vir"] = (hoje - df_ultimos["Data"]).dt.days
df_ultimos = df_ultimos.merge(df_status, on="Cliente", how="left")

# === Remove nomes genéricos ===
nomes_ignorar = ["boliviano", "brasileiro", "menino", "menino boliviano"]
df_ultimos = df_ultimos[~df_ultimos["Cliente"].str.lower().isin(nomes_ignorar)]

# === Top 20 mais ausentes ===
top20 = df_ultimos.sort_values(by="Dias sem vir", ascending=False).head(20)

# === Exibição ===
st.markdown("### 📋 Ranking dos Clientes com Maior Tempo de Ausência")
st.dataframe(
    top20[["Cliente", "Data", "Dias sem vir", "Status"]],
    use_container_width=True,
    hide_index=True
)

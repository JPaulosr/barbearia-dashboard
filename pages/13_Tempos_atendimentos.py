
import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import time

st.set_page_config(layout="centered")
st.title("⏱️ Teste de Leitura de Horários - Barbearia")

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
def carregar_base():
    aba = conectar_sheets().worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [col.strip() for col in df.columns]
    df = df.dropna(subset=["Data"])
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")

    def converter_hora(valor):
        if pd.isna(valor):
            return None
        if isinstance(valor, (int, float)):
            hora = int(valor * 24)
            minuto = int((valor * 24 - hora) * 60)
            return time(hour=hora, minute=minuto)
        if isinstance(valor, str) and ":" in valor:
            try:
                return pd.to_datetime(valor, format="%H:%M").time()
            except:
                return None
        return None

    for col in ["Hora Chegada", "Hora Início", "Hora Saída"]:
        df[col] = df[col].apply(converter_hora)

    for col in ["Hora Chegada", "Hora Início", "Hora Saída"]:
        df[col] = pd.to_datetime(df["Data"].dt.strftime("%Y-%m-%d") + " " + df[col].astype(str), format="%Y-%m-%d %H:%M", errors="coerce")

    return df

df = carregar_base()

# Filtro de data
data_unicas = df["Data"].dropna().dt.date.unique()
data_sel = st.date_input("Selecione a data", value=max(data_unicas), min_value=min(data_unicas), max_value=max(data_unicas))

df_dia = df[df["Data"].dt.date == data_sel]

st.write("### Registros encontrados:", len(df_dia))

if not df_dia.empty:
    df_dia["Espera (min)"] = (df_dia["Hora Início"] - df_dia["Hora Chegada"]).dt.total_seconds() / 60
    df_dia["Atendimento (min)"] = (df_dia["Hora Saída"] - df_dia["Hora Início"]).dt.total_seconds() / 60
    df_dia["Tempo Total (min)"] = (df_dia["Hora Saída"] - df_dia["Hora Chegada"]).dt.total_seconds() / 60
    st.dataframe(df_dia[["Data", "Cliente", "Funcionário", "Hora Chegada", "Hora Início", "Hora Saída", "Espera (min)", "Atendimento (min)", "Tempo Total (min)"]])
else:
    st.warning("Nenhum atendimento encontrado para a data selecionada.")

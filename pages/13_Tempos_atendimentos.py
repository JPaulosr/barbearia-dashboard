
import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🐞 Debug - Filtro de Data no Painel de Horários")

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

    for col in ["Hora Chegada", "Hora Início", "Hora Saída"]:
        df[col] = pd.to_datetime(df[col], format="%H:%M:%S", errors="coerce").dt.time

    for col in ["Hora Chegada", "Hora Início", "Hora Saída"]:
        df[col] = pd.to_datetime(df["Data"].dt.strftime("%Y-%m-%d") + " " + df[col].astype(str), format="%Y-%m-%d %H:%M:%S", errors="coerce")

    return df

df = carregar_base()

# Filtro de data com inspeção
data_unicas = df["Data"].dropna().dt.date.unique()
data_sel = st.date_input("Selecione uma data", value=max(data_unicas))

st.write("🗓️ **Data selecionada:**", data_sel)
st.write("📆 **Exemplo de datas no DataFrame:**", df["Data"].dt.date.unique()[:5])
st.write("📋 DataFrame original (amostra):")
st.dataframe(df[["Data", "Cliente", "Hora Chegada", "Hora Início", "Hora Saída"]].head(10))

# Aplicar filtro
df_filtrado = df[df["Data"].dt.date == data_sel]

st.write("✅ **Registros filtrados:**", len(df_filtrado))
st.dataframe(df_filtrado[["Data", "Cliente", "Hora Chegada", "Hora Início", "Hora Saída"]])

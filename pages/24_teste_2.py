# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import datetime
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

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
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month

    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)

    # Cálculo da duração em minutos de forma robusta
    def calcular_duracao(row):
        h1 = row.get("Hora Chegada")
        h2 = row.get("Hora Saída do Salão")
        try:
            h1 = pd.to_datetime(str(h1), errors="coerce").time()
            h2 = pd.to_datetime(str(h2), errors="coerce").time()
            if pd.isna(h1) or pd.isna(h2):
                return None
            dt1 = datetime.datetime.combine(datetime.date.today(), h1)
            dt2 = datetime.datetime.combine(datetime.date.today(), h2)
            return (dt2 - dt1).total_seconds() / 60 if dt2 > dt1 else None
        except:
            return None

    if {"Hora Chegada", "Hora Saída do Salão"}.issubset(df.columns):
        df["Duração (min)"] = df.apply(calcular_duracao, axis=1)

    return df

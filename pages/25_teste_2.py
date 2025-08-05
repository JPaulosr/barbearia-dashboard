import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos por Atendimento")

@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"

    df = pd.read_csv(url, skiprows=1)  # Pula a primeira linha visual
    df.columns = df.columns.str.strip()

    # Remove linhas com valores inválidos ou agrupadores (ex: "2023", "2024" etc. em todas as colunas vazias)
    df = df[~df["Data"].astype(str).str.fullmatch(r"\d{4}")].copy()

    st.write("🔍 Colunas encontradas:", df.columns.tolist())

    if "Data" not in df.columns:
        st.error("❌ A coluna 'Data' não foi encontrada. Verifique a planilha.")
        st.stop()

    # Conversão da coluna Data
    df["Data_convertida"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df[df["Data_convertida"].notna()].copy()
    df["Data"] = df["Data_convertida"].dt.date
    df.drop(columns=["Data_convertida"], inplace=True)

    # Conversão de horários
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')

    return df

df = carregar_dados_google_sheets()

# Verificação das colunas obrigatórias
colunas_necessarias = ["Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão", "Cliente", "Funcionário", "Tipo", "Combo", "Data"]
faltando = [col for col in colunas_necessarias if col not in df.columns]
if faltando:
    st.error(f"❌ As colunas obrigatórias estão faltando: {', '.join(faltando)}")
    st.stop()

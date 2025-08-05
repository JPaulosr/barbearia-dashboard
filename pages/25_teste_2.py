
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos por Atendimento")

@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"

    # Pula a primeira linha (que contém os agrupamentos visuais) e usa a segunda como cabeçalho
    df = pd.read_csv(url, skiprows=1)

    df.columns = df.columns.str.strip()
    st.write("🔍 Colunas encontradas:", df.columns.tolist())

    if "Data" not in df.columns:
        st.error("❌ A coluna 'Data' não foi encontrada. Verifique a planilha.")
        st.stop()

    df["Data_convertida"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df[df["Data_convertida"].notna()].copy()
    df["Data"] = df["Data_convertida"].dt.date
    df.drop(columns=["Data_convertida"], inplace=True)

    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')

    return df

df = carregar_dados_google_sheets()

colunas_necessarias = ["Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão", "Cliente", "Funcionário", "Tipo", "Combo", "Data"]
faltando = [col for col in colunas_necessarias if col not in df.columns]
if faltando:
    st.error(f"As colunas obrigatórias estão faltando: {', '.join(faltando)}")
    st.stop()

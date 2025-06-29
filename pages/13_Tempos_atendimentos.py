import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos por Atendimento")

# Função para carregar os dados diretamente do Google Sheets com cache
@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    return df

# Carregar dados
df = carregar_dados_google_sheets()

# Agrupar por Cliente + Data para evitar duplicações de combos
combo_grouped = df.dropna(subset=["Hora Início", "Hora Saída", "Hora Chegada"]).copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data"]).agg({
    "Hora Chegada": "min",
    "Hora Início": "min",
    "Hora Saída": "max",
    "Funcionário": "first",
    "Tipo": lambda x: ', '.join(sorted(set(x))),
}).reset_index()

# Calcular duração do atendimento
combo_grouped["Duração (min)"] = (combo_grouped["Hora Saída"] - combo_grouped["Hora Início"]).dt.total_seconds() / 60
combo_grouped["Duração formatada"] = combo_grouped["Duração (min)"].apply(
    lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else "")
combo_grouped["Espera (min)"] = (combo_grouped["Hora Início"] - combo_grouped["Hora Chegada"]).dt.total_seconds() / 60
combo_grouped["Tempo no Salão (min)"] = (combo_grouped["Hora Saída"] - combo_grouped["Hora Chegada"]).dt.total_seconds() / 60

# Categorizar combos e simples
combo_grouped["Categoria"] = combo_grouped["Tipo"].apply(lambda x: "Combo" if "," in x else "Simples")

# Filtrar apenas registros válidos e a partir de junho de 2025
df_tempo = combo_grouped.dropna(subset=["Duração (min)", "Tempo no Salão (min)"])
df_tempo = df_tempo[df_tempo["Data"] >= pd.to_datetime("2025-06-01")]

# Exibir dados de base (opcional)
with st.expander("📋 Visualizar dados consolidados"):
    st.dataframe(df_tempo, use_container_width=True)

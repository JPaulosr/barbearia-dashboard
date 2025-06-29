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
    df["Hora Saída do Salão"] = pd.to_datetime(df.get("Hora Saída do Salão"), errors='coerce')
    return df

# Carregar dados
df = carregar_dados_google_sheets()

# Agrupar por Cliente + Data para evitar duplicações de combos
combo_grouped = df.dropna(subset=["Hora Início", "Hora Saída"]).copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data"]).agg({
    "Hora Chegada": "min",
    "Hora Início": "min",
    "Hora Saída": "max",
    "Hora Saída do Salão": "max",
    "Funcionário": "first",
    "Tipo": lambda x: ', '.join(sorted(set(x))),
}).reset_index()

# Calcular duração do atendimento e tempo no salão
def calcular_duracao(row):
    try:
        return (row["Hora Saída"] - row["Hora Início"]).total_seconds() / 60
    except:
        return None

def calcular_tempo_salao(row):
    try:
        fim = row["Hora Saída do Salão"] if pd.notnull(row["Hora Saída do Salão"]) else row["Hora Saída"]
        return (fim - row["Hora Chegada"]).total_seconds() / 60
    except:
        return None

def calcular_espera(row):
    try:
        return (row["Hora Início"] - row["Hora Chegada"]).total_seconds() / 60
    except:
        return None

combo_grouped["Duração (min)"] = combo_grouped.apply(calcular_duracao, axis=1)
combo_grouped["Tempo no salão (min)"] = combo_grouped.apply(calcular_tempo_salao, axis=1)
combo_grouped["Espera (min)"] = combo_grouped.apply(calcular_espera, axis=1)
combo_grouped["Duração formatada"] = combo_grouped["Duração (min)"].apply(
    lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else "")
combo_grouped["Categoria"] = combo_grouped["Tipo"].apply(lambda x: "Combo" if "," in x else "Simples")

df_tempo = combo_grouped.dropna(subset=["Duração (min)"])

# Visualizações e painéis seguem iguais, você pode agora usar "Tempo no salão (min)" para novos gráficos ou comparações.

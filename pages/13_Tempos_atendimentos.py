import streamlit as st import pandas as pd import plotly.express as px import gspread from gspread_dataframe import get_as_dataframe from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide") st.title("⏱️ Tempos por Atendimento")

=== CONFIGURAÇÃO GOOGLE SHEETS ===

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE" BASE_ABA = "Base de Dados"

@st.cache_resource def conectar_sheets(): info = st.secrets["GCP_SERVICE_ACCOUNT"] escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"] credenciais = Credentials.from_service_account_info(info, scopes=escopo) cliente = gspread.authorize(credenciais) return cliente.open_by_key(SHEET_ID)

@st.cache_data def carregar_dados(): planilha = conectar_sheets() aba = planilha.worksheet(BASE_ABA) df = get_as_dataframe(aba).dropna(how="all") df.columns = [col.strip() for col in df.columns] df = df.dropna(subset=["Data"]) df["Data"] = pd.to_datetime(df["Data"], errors="coerce") for col in ["Hora Chegada", "Hora Início", "Hora Saída"]: if col in df.columns: df[col] = pd.to_datetime(df[col], format="%H:%M:%S", errors="coerce") return df

df = carregar_dados()

=== Calcular tempos ===

df_hora = df.dropna(subset=["Hora Chegada", "Hora Início", "Hora Saída"], how="all").copy() df_hora["Espera (min)"] = (df_hora["Hora Início"] - df_hora["Hora Chegada"]).dt.total_seconds() / 60 df_hora["Atendimento (min)"] = (df_hora["Hora Saída"] - df_hora["Hora Início"]).dt.total_seconds() / 60 df_hora["Tempo Total (min)"] = (df_hora["Hora Saída"] - df_hora["Hora Chegada"]).dt.total_seconds() / 60 df_hora = df_hora.round({"Espera (min)": 1, "Atendimento (min)": 1, "Tempo Total (min)": 1})

=== Insights por atendimento ===

def gerar_insight(row): if row["Tempo Total (min)"] >= 70: return "🔥 Muito Demorado" elif row["Tempo Total (min)"] >= 50: return "⏳ Demorado" elif row["Tempo Total (min)"] >= 30: return "✅ Normal" else: return "⚡ Rápido"

df_hora["Insight"] = df_hora.apply(gerar_insight, axis=1)

=== Filtros ===

col1, col2, col3 = st.columns(3) clientes = sorted(df_hora["Cliente"].dropna().unique().tolist()) funcionarios = sorted(df_hora["Funcion


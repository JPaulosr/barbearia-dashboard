
import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import time

# === CONFIG ===
st.set_page_config(layout="wide")
st.title("⏱️ Tempos por Atendimento")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

# === Funções auxiliares ===
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

    colunas_esperadas = ["Data", "Cliente", "Funcionário", "Hora Chegada", "Hora Início", "Hora Saída"]
    for col in colunas_esperadas:
        if col not in df.columns:
            df[col] = pd.NaT if 'Hora' in col else None

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

    return df

df = carregar_dados()

# === Calcular tempos ===
df_hora = df.dropna(subset=["Hora Chegada", "Hora Início", "Hora Saída"], how="any").copy()

# Concatena a data com a hora para cálculo correto
for col in ["Hora Chegada", "Hora Início", "Hora Saída"]:
    df_hora[col] = pd.to_datetime(df_hora["Data"].dt.strftime("%Y-%m-%d") + " " + df_hora[col].astype(str), format="%Y-%m-%d %H:%M", errors="coerce")

df_hora["Espera (min)"] = (df_hora["Hora Início"] - df_hora["Hora Chegada"]).dt.total_seconds() / 60
df_hora["Atendimento (min)"] = (df_hora["Hora Saída"] - df_hora["Hora Início"]).dt.total_seconds() / 60
df_hora["Tempo Total (min)"] = (df_hora["Hora Saída"] - df_hora["Hora Chegada"]).dt.total_seconds() / 60
df_hora = df_hora.round({"Espera (min)": 1, "Atendimento (min)": 1, "Tempo Total (min)": 1})

# === Insights ===
def gerar_insight(row):
    if row["Tempo Total (min)"] >= 70:
        return "🔥 Muito Demorado"
    elif row["Tempo Total (min)"] >= 50:
        return "⏳ Demorado"
    elif row["Tempo Total (min)"] >= 30:
        return "✅ Normal"
    else:
        return "⚡ Rápido"

df_hora["Insight"] = df_hora.apply(gerar_insight, axis=1)

# === Filtros ===
st.sidebar.header("🔍 Filtros")
data_sel = st.sidebar.date_input("Selecionar data", value=pd.to_datetime("today"))
df_hora = df_hora[df_hora["Data"] == pd.to_datetime(data_sel)]

clientes = sorted(df_hora["Cliente"].dropna().unique().tolist())
funcionarios = sorted(df_hora["Funcionário"].dropna().unique().tolist())

cliente_sel = st.sidebar.selectbox("👤 Cliente", ["Todos"] + clientes)
func_sel = st.sidebar.selectbox("✂️ Funcionário", ["Todos"] + funcionarios)

if cliente_sel != "Todos":
    df_hora = df_hora[df_hora["Cliente"] == cliente_sel]
if func_sel != "Todos":
    df_hora = df_hora[df_hora["Funcionário"] == func_sel]

# === Indicadores ===
st.subheader("📊 Indicadores do Dia")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Clientes atendidos", len(df_hora))
col2.metric("Média de Espera", f"{df_hora['Espera (min)'].mean():.1f} min" if not df_hora.empty else "-")
col3.metric("Média Atendimento", f"{df_hora['Atendimento (min)'].mean():.1f} min" if not df_hora.empty else "-")
col4.metric("Tempo Total Médio", f"{df_hora['Tempo Total (min)'].mean():.1f} min" if not df_hora.empty else "-")

# === Gráfico ===
st.subheader("🕒 Gráfico - Tempo de Espera por Cliente")
if not df_hora.empty:
    fig = px.bar(df_hora, x="Cliente", y="Espera (min)", color="Funcionário", text="Espera (min)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nenhum atendimento registrado nesta data.")

# === Tabela ===
st.subheader("📋 Atendimentos do Dia")
st.dataframe(
    df_hora[[
        "Cliente", "Funcionário", "Hora Chegada", "Hora Início", "Hora Saída",
        "Espera (min)", "Atendimento (min)", "Tempo Total (min)", "Insight"
    ]],
    use_container_width=True
)

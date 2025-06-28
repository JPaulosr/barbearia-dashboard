import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📊 Controle de Fila e Fluxo no Salão")

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
    df.columns = [col.strip() for col in df.columns]
    df = df.dropna(subset=["Data"])
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    for col in ["Hora Chegada", "Hora Início", "Hora Saída"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%H:%M:%S", errors="coerce")
    return df

df = carregar_dados()

# === Filtros ===
st.sidebar.header("🔍 Filtros")
datas = sorted(df["Data"].dropna().dt.date.unique(), reverse=True)
data_sel = st.sidebar.selectbox("📅 Escolha a data", datas, index=0)
funcionarios = sorted(df["Funcionário"].dropna().unique().tolist())
func_sel = st.sidebar.selectbox("💈 Filtrar por Funcionário", ["Todos"] + funcionarios)

# === Aplicar filtros ===
df_dia = df[df["Data"].dt.date == data_sel].copy()
if func_sel != "Todos":
    df_dia = df_dia[df_dia["Funcionário"] == func_sel]

df_dia = df_dia.dropna(subset=["Hora Chegada", "Hora Início", "Hora Saída"], how="any")

# === Cálculo dos tempos ===
df_dia["Espera (min)"] = (df_dia["Hora Início"] - df_dia["Hora Chegada"]).dt.total_seconds() / 60
df_dia["Atendimento (min)"] = (df_dia["Hora Saída"] - df_dia["Hora Início"]).dt.total_seconds() / 60
df_dia["Tempo Total (min)"] = (df_dia["Hora Saída"] - df_dia["Hora Chegada"]).dt.total_seconds() / 60
df_dia = df_dia.round({"Espera (min)": 1, "Atendimento (min)": 1, "Tempo Total (min)": 1})

# === Indicadores gerais ===
st.subheader("📈 Indicadores do Dia")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Clientes atendidos", len(df_dia))
col2.metric("Média de Espera", f"{df_dia['Espera (min)'].mean():.1f} min")
col3.metric("Média Atendimento", f"{df_dia['Atendimento (min)'].mean():.1f} min")
col4.metric("Tempo Total Médio", f"{df_dia['Tempo Total (min)'].mean():.1f} min")

# === Gráfico de Espera ===
st.subheader("🕒 Gráfico - Tempo de Espera por Cliente")
fig = px.bar(df_dia.sort_values("Espera (min)", ascending=False),
             x="Cliente", y="Espera (min)", color="Espera (min)", text_auto=True)
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

# === Tabela detalhada ===
st.subheader("📋 Atendimentos do Dia")
st.dataframe(df_dia[["Cliente", "Funcionário", "Hora Chegada", "Hora Início", "Hora Saída",
                    "Espera (min)", "Atendimento (min)", "Tempo Total (min)"]], use_container_width=True)

# === Rodapé ===
st.markdown("---")
st.markdown("Esses dados ajudam a entender a real dinâmica do salão e melhorar decisões no dia a dia.")

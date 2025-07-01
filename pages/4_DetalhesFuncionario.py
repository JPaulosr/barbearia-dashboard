import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from utils.utils import aplicar_filtros

st.set_page_config(layout="wide")
st.title("👨‍💼 Detalhes do Funcionário")

@st.cache_data
def carregar_dados_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credenciais.json", scope)
    client = gspread.authorize(creds)

    url_planilha = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/edit?usp=sharing"
    planilha = client.open_by_url(url_planilha)

    df = pd.DataFrame(planilha.worksheet("Base de Dados").get_all_records())
    df_despesas = pd.DataFrame(planilha.worksheet("Despesas").get_all_records())

    return df, df_despesas

df, df_despesas = carregar_dados_google_sheets()
df["Data"] = pd.to_datetime(df["Data"])
df_despesas["Data"] = pd.to_datetime(df_despesas["Data"])
df["Ano"] = df["Data"].dt.year
df["Mes"] = df["Data"].dt.month
df["Dia"] = df["Data"].dt.day
df["DiaSemana"] = df["Data"].dt.strftime("%a")
df["Semana"] = df["Data"].dt.isocalendar().week

df["DiaSemana"] = df["DiaSemana"].map({
    "Mon": "Seg",
    "Tue": "Ter",
    "Wed": "Qua",
    "Thu": "Qui",
    "Fri": "Sex",
    "Sat": "Sáb",
    "Sun": "Dom"
})

anos_disponiveis = sorted(df["Ano"].unique(), reverse=True)
ano_escolhido = st.selectbox("🗕️ Filtrar por ano", anos_disponiveis)
meses_disponiveis = ["Todos"] + sorted(df[df["Ano"] == ano_escolhido]["Mes"].unique())
mes_filtro = st.selectbox("🕖️ Filtrar por mês", meses_disponiveis)
dias_disponiveis = ["Todos"] + sorted(df[df["Ano"] == ano_escolhido]["Dia"].unique())
dia_filtro = st.selectbox("🗕️ Filtrar por dia", dias_disponiveis)
semanas_disponiveis = df[df["Ano"] == ano_escolhido]["Semana"].unique().tolist()
semanas_disponiveis.sort()
semana_filtro = st.selectbox("📈 Filtrar por semana", ["Todos"] + semanas_disponiveis)
funcionarios_disponiveis = sorted(df["Profissional"].dropna().unique())
funcionario_escolhido = st.selectbox("🧕‍♂️ Escolha um funcionário", funcionarios_disponiveis)

...

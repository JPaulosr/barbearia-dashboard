import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
from google.oauth2.service_account import Credentials
import gspread
from gspread_dataframe import get_as_dataframe

st.set_page_config(page_title="Receita Mensal por Mês e Ano", layout="wide")
st.title("📊 Receita Mensal por Mês e Ano")

# === CONEXÃO COM GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Valor"] = pd.to_numeric(df["Valor"], errors='coerce')
    return df

# === CARREGAR BASE ===
base = carregar_base()

# === FILTRAR JPAULO ===
df_jpaulo = base[base["Funcionário"] == "JPaulo"].copy()
df_jpaulo["MesNome"] = df_jpaulo["Data"].dt.strftime('%B %Y')
df_jpaulo["MesNum"] = df_jpaulo["Data"].dt.month
df_jpaulo["Ano"] = df_jpaulo["Data"].dt.year

receita_jpaulo = df_jpaulo.groupby(["Ano", "MesNome", "MesNum"])["Valor"].sum().reset_index()

# === COMISSÕES PAGAS AO VINICIUS ===
comissoes = base[(base["Funcionário"] == "Vinicius") & (base["Tipo"] == "Despesa")].copy()
comissoes["MesNome"] = comissoes["Data"].dt.strftime('%B %Y')
comissoes["MesNum"] = comissoes["Data"].dt.month
comissoes["Ano"] = comissoes["Data"].dt.year

comissoes_mes = comissoes.groupby(["Ano", "MesNome", "MesNum"])["Valor"].sum().reset_index()

# === JUNÇÃO E CÁLCULO ===
receita_total = receita_jpaulo.merge(comissoes_mes, on=["Ano", "MesNome", "MesNum"], how="outer", suffixes=("_JPaulo", "_ComVinicius"))
receita_total = receita_total.fillna(0)
receita_total["Receita Real do Salão"] = receita_total["Valor_JPaulo"] + receita_total["Valor_ComVinicius"]

# === ORDENAR ===
receita_total = receita_total.sort_values(["Ano", "MesNum"])

# === GRÁFICO ===
fig = px.bar(receita_total,
             x="MesNome",
             y=["Valor_JPaulo", "Valor_ComVinicius"],
             barmode="group",
             labels={"value": "Receita (R$)", "MesNome": "Mês"},
             height=450)

st.plotly_chart(fig, use_container_width=True)

# === TABELA ===
st.dataframe(
    receita_total[["MesNome", "Valor_JPaulo", "Valor_ComVinicius", "Receita Real do Salão"]]
    .rename(columns={
        "MesNome": "Mês",
        "Valor_JPaulo": "Receita JPaulo",
        "Valor_ComVinicius": "Comissão paga ao Vinicius"
    }),
    use_container_width=True
)

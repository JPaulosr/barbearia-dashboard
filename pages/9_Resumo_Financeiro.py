import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("\ud83d\udcca Resumo Financeiro do Sal\u00e3o")

# === CONFIGURA\u00c7\u00c3O GOOGLE SHEETS ===
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
    df = get_as_dataframe(conectar_sheets().worksheet(BASE_ABA)).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    return df

df = carregar_dados()

# === FILTRO POR ANO ===
anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("\ud83d\uddd3\ufe0f Selecione o Ano", anos, index=0)
df_ano = df[df["Ano"] == ano]

# === SEPARA\u00c7\u00c3O POR FASES
data_corte = pd.to_datetime("2025-05-11")
df_fase1 = df_ano[df_ano["Data"] < data_corte]
df_fase2 = df_ano[df_ano["Data"] >= data_corte]

# === FASE 1: JPAULO COMO PRESTADOR
st.header("\ud83d\udcd8 Fase 1 \u2013 JPaulo como prestador de servi\u00e7o")
receita_fase1 = df_fase1[df_fase1["Funcion\u00e1rio"] == "JPaulo"]["Valor"].sum()

if "Descri\u00e7\u00e3o" in df_fase1.columns:
    despesas_fase1 = df_fase1[
        (df_fase1["Tipo"] == "Despesa") &
        (df_fase1["Descri\u00e7\u00e3o"].str.lower().str.contains("neto"))
    ]["Valor"].sum()
else:
    despesas_fase1 = 0.0

lucro_fase1 = receita_fase1 - despesas_fase1

col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas (comiss\u00e3o paga)", f"R$ {despesas_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro L\u00edquido", f"R$ {lucro_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === FASE 2: JPAULO COMO DONO DO SAL\u00c3O
st.header("\ud83d\udcd9 Fase 2 \u2013 JPaulo como dono do sal\u00e3o")

receita_jpaulo = df_fase2[df_fase2["Funcion\u00e1rio"] == "JPaulo"]["Valor"].sum()
comissao_vinicius = df_fase2[
    (df_fase2["Tipo"] == "Despesa") &
    (df_fase2["Descri\u00e7\u00e3o"].str.lower().str.contains("vinicius"))
]["Valor"].sum()
receita_total_salao = receita_jpaulo + comissao_vinicius

st.subheader("\ud83d\udcb5 Receita do Sal\u00e3o")
col1, col2, col3 = st.columns(3)
col1.metric("Receita JPaulo (100%)", f"R$ {receita_jpaulo:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comiss\u00e3o paga ao Vinicius", f"R$ {comissao_vinicius:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Receita Total", f"R$ {receita_total_salao:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === DESPESAS FIXAS
st.subheader("\ud83d\udcb8 Despesas do Sal\u00e3o")
with st.form("despesas_fixas"):
    col1, col2, col3, col4 = st.columns(4)
    aluguel = col1.number_input("Aluguel", min_value=0.0, value=1200.0, step=50.0)
    agua = col2.number_input("\u00c1gua", min_value=0.0, value=200.0, step=10.0)
    luz = col3.number_input("Luz", min_value=0.0, value=300.0, step=10.0)
    produtos = col4.number_input("Produtos", min_value=0.0, value=400.0, step=10.0)
    submit = st.form_submit_button("Atualizar valores")

total_despesas_fase2 = aluguel + agua + luz + produtos
lucro_fase2 = receita_total_salao - total_despesas_fase2

col1, col2 = st.columns(2)
col1.metric("Total de Despesas", f"R$ {total_despesas_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Lucro do Sal\u00e3o", f"R$ {lucro_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === CONSOLIDADO DO ANO
st.header("\ud83d\udccc Consolidado do Ano")
receita_total_ano = receita_fase1 + receita_total_salao
despesas_total_ano = despesas_fase1 + total_despesas_fase2
lucro_total_ano = receita_total_ano - despesas_total_ano

col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.markdown("---")
st.caption("Criado por JPaulo \u2728 | Estrutura financeira anual por fase do sal\u00e3o")

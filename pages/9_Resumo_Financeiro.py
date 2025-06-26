import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📊 Resumo Financeiro do Salão")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
DESPESAS_ABA = "Despesas"

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
    df_base = get_as_dataframe(planilha.worksheet(BASE_ABA)).dropna(how="all")
    df_base.columns = [str(col).strip() for col in df_base.columns]
    df_base["Data"] = pd.to_datetime(df_base["Data"], errors='coerce')
    df_base = df_base.dropna(subset=["Data"])
    df_base["Ano"] = df_base["Data"].dt.year

    df_despesas = get_as_dataframe(planilha.worksheet(DESPESAS_ABA)).dropna(how="all")
    df_despesas.columns = [str(col).strip() for col in df_despesas.columns]
    df_despesas["Data"] = pd.to_datetime(df_despesas["Data"], errors='coerce')
    df_despesas = df_despesas.dropna(subset=["Data"])
    df_despesas["Ano"] = df_despesas["Data"].dt.year

    return df_base, df_despesas

df, despesas = carregar_dados()

anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos, index=0)
df_ano = df[df["Ano"] == ano]
despesas_ano = despesas[despesas["Ano"] == ano]

data_corte = pd.to_datetime("2025-05-11")
df_fase1 = df_ano[df_ano["Data"] < data_corte]
df_fase2 = df_ano[df_ano["Data"] >= data_corte]
despesas_fase1 = despesas_ano[despesas_ano["Data"] < data_corte]
despesas_fase2 = despesas_ano[despesas_ano["Data"] >= data_corte]

# === FASE 1 ===
st.header("📘 Fase 1 – JPaulo como prestador de serviço")
receita_fase1 = df_fase1[df_fase1["Funcionário"] == "JPaulo"]["Valor"].sum()
comissoes_neto = despesas_fase1[despesas_fase1["Descrição"].str.lower().str.contains("neto")]["Valor"].sum()
lucro_fase1 = receita_fase1 - comissoes_neto

col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão paga ao Neto", f"R$ {comissoes_neto:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Líquido", f"R$ {lucro_fase1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === FASE 2 ===
st.header("📙 Fase 2 – JPaulo como dono do salão")
receita_jpaulo = df_fase2[df_fase2["Funcionário"] == "JPaulo"]["Valor"].sum()
comissao_vinicius = despesas_fase2[despesas_fase2["Descrição"].str.lower().str.contains("vinicius")]["Valor"].sum()
receita_total_salao = receita_jpaulo + comissao_vinicius

st.subheader("💵 Receita do Salão")
col1, col2, col3 = st.columns(3)
col1.metric("Receita JPaulo (100%)", f"R$ {receita_jpaulo:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão paga ao Vinicius", f"R$ {comissao_vinicius:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Receita Total", f"R$ {receita_total_salao:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === Despesas fixas
st.subheader("💸 Despesas do Salão")
with st.form("despesas_fixas"):
    col1, col2, col3, col4 = st.columns(4)
    aluguel = col1.number_input("Aluguel", min_value=0.0, value=1200.0, step=50.0)
    agua = col2.number_input("Água", min_value=0.0, value=200.0, step=10.0)
    luz = col3.number_input("Luz", min_value=0.0, value=300.0, step=10.0)
    produtos = col4.number_input("Produtos", min_value=0.0, value=400.0, step=10.0)
    submit = st.form_submit_button("Atualizar valores")

total_despesas_fase2 = aluguel + agua + luz + produtos
lucro_fase2 = receita_total_salao - total_despesas_fase2

col1, col2 = st.columns(2)
col1.metric("Total de Despesas", f"R$ {total_despesas_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Lucro do Salão", f"R$ {lucro_fase2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === Consolidado
st.divider()
st.header("📌 Consolidado do Ano")
receita_total_ano = receita_fase1 + receita_total_salao
despesas_total_ano = comissoes_neto + comissao_vinicius + total_despesas_fase2
lucro_total_ano = receita_total_ano - despesas_total_ano

col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total_ano:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.markdown("---")
st.caption("Criado por JPaulo ✨ | Estrutura financeira anual por fase do salão")

import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📊 Resumo Financeiro do Salão")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
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
    df_base["Data"] = pd.to_datetime(df_base["Data"], errors="coerce")
    df_base = df_base.dropna(subset=["Data"])
    df_base["Ano"] = df_base["Data"].dt.year

    df_despesas = get_as_dataframe(planilha.worksheet(DESPESAS_ABA)).dropna(how="all")
    df_despesas.columns = [str(col).strip() for col in df_despesas.columns]
    df_despesas["Data"] = pd.to_datetime(df_despesas["Data"], errors="coerce")
    df_despesas = df_despesas.dropna(subset=["Data"])
    df_despesas["Ano"] = df_despesas["Data"].dt.year

    return df_base, df_despesas

df, df_despesas = carregar_dados()

anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos, index=0)
df_ano = df[df["Ano"] == ano]
df_despesas_ano = df_despesas[df_despesas["Ano"] == ano]

# === Fase 1: Autônomo (prestador) ===
st.header("📘 Fase 1 – JPaulo como prestador de serviço")
df_f1 = df_ano[df_ano["Fase"] == "Autônomo (prestador)"]
df_desp_f1 = df_despesas_ano[df_despesas_ano["Descrição"].str.lower().str.contains("neto")]

receita_f1 = df_f1[df_f1["Funcionário"] == "JPaulo"]["Valor"].sum()
comissao_neto = df_desp_f1["Valor"].sum()
lucro_f1 = receita_f1 - comissao_neto

col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_f1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão paga ao Neto", f"R$ {comissao_neto:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Líquido", f"R$ {lucro_f1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === Fase 2: Dono sozinho ===
st.header("📙 Fase 2 – JPaulo como dono do salão (sem funcionário)")
df_f2 = df_ano[df_ano["Fase"] == "Dono (sozinho)"]
receita_f2 = df_f2[df_f2["Funcionário"] == "JPaulo"]["Valor"].sum()

st.subheader("💵 Receita do Salão")
col1, col2 = st.columns(2)
col1.metric("Receita JPaulo (100%)", f"R$ {receita_f2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão paga", "R$ 0,00")

# === Despesas fixas (definidas pelo usuário)
st.subheader("💸 Despesas do Salão")
with st.form("despesas_fixas"):
    col1, col2, col3, col4 = st.columns(4)
    aluguel = col1.number_input("Aluguel", min_value=0.0, value=1200.0, step=50.0)
    agua = col2.number_input("Água", min_value=0.0, value=200.0, step=10.0)
    luz = col3.number_input("Luz", min_value=0.0, value=300.0, step=10.0)
    produtos = col4.number_input("Produtos", min_value=0.0, value=400.0, step=10.0)
    submit = st.form_submit_button("Atualizar valores")

despesas_f2 = aluguel + agua + luz + produtos
lucro_f2 = receita_f2 - despesas_f2

col1, col2 = st.columns(2)
col1.metric("Total de Despesas", f"R$ {despesas_f2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Lucro do Salão", f"R$ {lucro_f2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === Fase 3: Dono com funcionário ===
st.header("📗 Fase 3 – Dono com funcionário (Vinicius)")
df_f3 = df_ano[df_ano["Fase"] == "Dono + funcionário"]
df_desp_f3 = df_despesas_ano[df_despesas_ano["Descrição"].str.lower().str.contains("vinicius")]

receita_jp3 = df_f3[df_f3["Funcionário"] == "JPaulo"]["Valor"].sum()
comissao_vinicius = df_desp_f3["Valor"].sum()
receita_total_f3 = receita_jp3 + comissao_vinicius
lucro_f3 = receita_total_f3 - despesas_f2 - comissao_vinicius

col1, col2, col3 = st.columns(3)
col1.metric("Receita JPaulo", f"R$ {receita_jp3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão Vinicius", f"R$ {comissao_vinicius:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Receita Total", f"R$ {receita_total_f3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

col1, col2 = st.columns(2)
col1.metric("Despesas Fixas", f"R$ {despesas_f2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Lucro Líquido", f"R$ {lucro_f3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === Consolidado ===
st.divider()
st.header("📌 Consolidado do Ano")
receita_total = receita_f1 + receita_f2 + receita_total_f3
despesas_total = comissao_neto + despesas_f2 + comissao_vinicius
lucro_total = receita_total - despesas_total

col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.markdown("---")
st.caption("Criado por JPaulo ✨ | Estrutura financeira anual segmentada por fase")

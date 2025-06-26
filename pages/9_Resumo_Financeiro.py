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
    df_despesas = get_as_dataframe(planilha.worksheet(DESPESAS_ABA)).dropna(how="all")

    for df in [df_base, df_despesas]:
        df.columns = [str(col).strip() for col in df.columns]

    df_base["Data"] = pd.to_datetime(df_base["Data"], errors='coerce')
    df_base = df_base.dropna(subset=["Data"])
    df_base["Ano"] = df_base["Data"].dt.year
    df_base["Fase"] = df_base["Fase"].fillna("")

    df_despesas["Data"] = pd.to_datetime(df_despesas["Data"], errors='coerce')
    df_despesas = df_despesas.dropna(subset=["Data"])
    df_despesas["Ano"] = df_despesas["Data"].dt.year
    df_despesas["Valor"] = df_despesas["Valor"].astype(str).str.replace("R\$", "").str.replace(".", "").str.replace(",", ".").astype(float)

    return df_base, df_despesas

df, despesas = carregar_dados()

anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos, index=0)

df_ano = df[df["Ano"] == ano]
despesas_ano = despesas[despesas["Ano"] == ano]

# =====================
# FASE 1 – Prestador de Serviço
# =====================
st.header("📘 Fase 1 – JPaulo como prestador de serviço")

fase1 = df_ano[df_ano["Fase"] == "Autônomo (prestador)"]
despesas_f1 = despesas_ano[despesas_ano["Descrição"].str.lower().str.contains("neto")]

receita_f1 = fase1[fase1["Funcionário"] == "JPaulo"]["Valor"].sum()
comissao_neto = despesas_f1["Valor"].sum()
lucro_f1 = receita_f1 - comissao_neto

col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_f1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão paga ao Neto", f"R$ {comissao_neto:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Líquido", f"R$ {lucro_f1:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# =====================
# FASE 2 – Dono sem Funcionário
# =====================
st.header("📙 Fase 2 – JPaulo como dono do salão (sem funcionário)")

fase2 = df_ano[df_ano["Fase"] == "Dono (sozinho)"]
despesas_f2 = despesas_ano[despesas_ano["Descrição"].str.lower().str.contains("produto|água|agua|luz|aluguel")]

receita_f2 = fase2[fase2["Funcionário"] == "JPaulo"]["Valor"].sum()
despesas_fixas = despesas_f2["Valor"].sum()
lucro_f2 = receita_f2 - despesas_fixas

col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_f2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas fixas", f"R$ {despesas_fixas:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro do Salão", f"R$ {lucro_f2:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# =====================
# FASE 3 – Dono com Funcionário
# =====================
st.header("📒 Fase 3 – JPaulo com funcionário (Vinicius)")

fase3 = df_ano[df_ano["Fase"] == "Dono + funcionário"]
despesas_vinicius = despesas_ano[despesas_ano["Descrição"].str.lower().str.contains("vinicius")]
despesas_outros = despesas_ano[~despesas_ano["Descrição"].str.lower().str.contains("vinicius|neto")]

receita_jp3 = fase3[fase3["Funcionário"] == "JPaulo"]["Valor"].sum()
comissao_vinicius = despesas_vinicius["Valor"].sum()
despesas_fixas3 = despesas_outros["Valor"].sum()
receita_total3 = receita_jp3
lucro_f3 = receita_total3 - comissao_vinicius - despesas_fixas3

col1, col2, col3 = st.columns(3)
col1.metric("Receita (JPaulo)", f"R$ {receita_jp3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Comissão Vinicius", f"R$ {comissao_vinicius:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Despesas fixas", f"R$ {despesas_fixas3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

col4, col5 = st.columns(2)
col4.metric("Receita Total", f"R$ {receita_total3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col5.metric("Lucro Líquido", f"R$ {lucro_f3:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# =====================
# CONSOLIDADO DO ANO
# =====================
st.header("📌 Consolidado do Ano")
receita_total = receita_f1 + receita_f2 + receita_total3
despesas_total = comissao_neto + despesas_fixas + comissao_vinicius + despesas_fixas3
lucro_total = receita_total - despesas_total

col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.caption("Painel atualizado com base em fases e despesas reais registradas na planilha ✅")

import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import matplotlib.pyplot as plt

st.set_page_config(layout="wide")
st.title("📊 Resultado Financeiro Total do Salão")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_bases():
    planilha = conectar_sheets()
    df_base = get_as_dataframe(planilha.worksheet("Base de Dados")).dropna(how="all")
    df_desp = get_as_dataframe(planilha.worksheet("Despesas")).dropna(how="all")

    df_base.columns = df_base.columns.str.strip()
    df_base["Data"] = pd.to_datetime(df_base["Data"], errors="coerce")
    df_base = df_base.dropna(subset=["Data"])
    df_base["Ano"] = df_base["Data"].dt.year
    df_base["Mês"] = df_base["Data"].dt.month

    df_desp.columns = df_desp.columns.str.strip()
    df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce")
    df_desp = df_desp.dropna(subset=["Data"])
    df_desp["Ano"] = df_desp["Data"].dt.year
    df_desp["Mês"] = df_desp["Data"].dt.month

    return df_base, df_desp

# === CARREGAR DADOS
df, df_despesas = carregar_bases()

anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("🗓️ Selecione o Ano", anos)

df_ano = df[df["Ano"] == ano]
df_desp_ano = df_despesas[df_despesas["Ano"] == ano]

# === CÁLCULOS GERAIS
receita_total = df_ano["Valor"].sum()
despesas_total = df_desp_ano["Valor"].sum()
lucro_total = receita_total - despesas_total

st.subheader("📊 Resultado Consolidado do Salão")
col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === RECEITA POR FUNCIONÁRIO
st.subheader("👤 Receita por Funcionário")
df_func = df_ano.groupby("Funcionário")["Valor"].sum().reset_index().sort_values(by="Valor", ascending=False)

st.dataframe(df_func.rename(columns={"Valor": "Receita (R$)"}), use_container_width=True)

# === GRÁFICO DE BARRAS – Receita por Funcionário
fig, ax = plt.subplots()
ax.bar(df_func["Funcionário"], df_func["Valor"])
ax.set_title("Receita por Funcionário")
ax.set_ylabel("Receita (R$)")
ax.set_xlabel("Funcionário")
ax.tick_params(axis='x', rotation=0)
st.pyplot(fig)

st.divider()

# === GRÁFICO MENSAL – Receita e Despesas
st.subheader("📅 Evolução Mensal de Receita e Despesas")

# Receita mensal
receita_mensal = df_ano.groupby("Mês")["Valor"].sum().reset_index(name="Receita")
# Despesa mensal
despesa_mensal = df_desp_ano.groupby("Mês")["Valor"].sum().reset_index(name="Despesa")

# Juntar as duas bases
df_mensal = pd.merge(receita_mensal, despesa_mensal, on="Mês", how="outer").fillna(0).sort_values("Mês")

fig2, ax2 = plt.subplots()
ax2.plot(df_mensal["Mês"], df_mensal["Receita"], marker='o', label="Receita")
ax2.plot(df_mensal["Mês"], df_mensal["Despesa"], marker='o', label="Despesa", color="red")
ax2.set_title("Evolução Mensal")
ax2.set_xlabel("Mês")
ax2.set_ylabel("R$")
ax2.legend()
ax2.grid(True)
st.pyplot(fig2)

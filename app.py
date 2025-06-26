import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📊 Dashboard da Barbearia")

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
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Ano-Mês"] = df["Data"].dt.to_period("M").astype(str)
    return df

df = carregar_dados()

# === Sidebar: Filtros por Ano e Meses múltiplos ===
st.sidebar.header("🎛️ Filtros")
anos_disponiveis = sorted(df["Ano"].dropna().unique(), reverse=True)
ano_escolhido = st.sidebar.selectbox("🗓️ Escolha o Ano", anos_disponiveis)

meses_pt = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

meses_disponiveis = sorted(df[df["Ano"] == ano_escolhido]["Mês"].dropna().unique())
mes_opcoes = [meses_pt[m] for m in meses_disponiveis]
meses_selecionados = st.sidebar.multiselect("📆 Selecione os Meses (opcional)", mes_opcoes, default=mes_opcoes)

# === Aplicar filtros ===
if meses_selecionados:
    meses_numeros = [k for k, v in meses_pt.items() if v in meses_selecionados]
    df = df[(df["Ano"] == ano_escolhido) & (df["Mês"].isin(meses_numeros))]
else:
    df = df[df["Ano"] == ano_escolhido]

# === Indicadores principais ===
receita_total = df["Valor"].sum()
total_atendimentos = len(df)

data_limite = pd.to_datetime("2025-05-11")
antes = df[df["Data"] < data_limite]
depois = df[df["Data"] >= data_limite].drop_duplicates(subset=["Cliente", "Data"])
clientes_unicos = pd.concat([antes, depois])["Cliente"].nunique()
ticket_medio = receita_total / total_atendimentos if total_atendimentos else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 Receita Total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("📅 Total de Atendimentos", total_atendimentos)
col3.metric("🎯 Ticket Médio", f"R$ {ticket_medio:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col4.metric("🟢 Clientes Ativos", clientes_unicos)

# === Receita por Funcionário ===
st.markdown("### 📊 Receita por Funcionário")
df_func = df.groupby("Funcionário")["Valor"].sum().reset_index()
fig_func = px.bar(df_func, x="Funcionário", y="Valor", text_auto=True)
fig_func.update_traces(marker_color=["#5179ff", "#33cc66", "#ff9933"])
fig_func.update_layout(height=400, yaxis_title="Receita (R$)", showlegend=False)
st.plotly_chart(fig_func, use_container_width=True)

# === Receita por Tipo ===
st.markdown("### 🧾 Receita por Tipo")
df_tipo = df.copy()
df_tipo["Tipo"] = df_tipo["Serviço"].apply(
    lambda x: "Combo" if "combo" in str(x).lower() else "Produto" if "gel" in str(x).lower() or "produto" in str(x).lower() else "Serviço"
)
df_pizza = df_tipo.groupby("Tipo")["Valor"].sum().reset_index()
fig_pizza = px.pie(df_pizza, values="Valor", names="Tipo", title="Distribuição de Receita")
fig_pizza.update_traces(textinfo='percent+label')
st.plotly_chart(fig_pizza, use_container_width=True)

# === Top 10 Clientes (excluindo nomes genéricos) ===
st.markdown("### 🥇 Top 10 Clientes")
nomes_excluir = ["boliviano", "brasileiro", "menino"]
df_top = df.groupby("Cliente").agg({"Serviço": "count", "Valor": "sum"}).reset_index()
df_top.columns = ["Cliente", "Qtd_Serviços", "Valor"]
df_top = df_top[~df_top["Cliente"].str.lower().isin(nomes_excluir)]
df_top = df_top.sort_values(by="Valor", ascending=False).head(10)
df_top["Valor Formatado"] = df_top["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(df_top[["Cliente", "Qtd_Serviços", "Valor Formatado"]], use_container_width=True)

st.markdown("---")
st.caption("Criado por JPaulo ✨ | Versão principal do painel consolidado")

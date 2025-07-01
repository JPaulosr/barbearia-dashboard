import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode
from io import BytesIO
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🧑‍💼 Detalhes do Funcionário")

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
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    return df

df = carregar_dados()

@st.cache_data
def carregar_despesas():
    planilha = conectar_sheets()
    aba_desp = planilha.worksheet("Despesas")
    df_desp = get_as_dataframe(aba_desp).dropna(how="all")
    df_desp.columns = [str(col).strip() for col in df_desp.columns]
    df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce")
    df_desp = df_desp.dropna(subset=["Data"])
    df_desp["Ano"] = df_desp["Data"].dt.year.astype(int)
    return df_desp

df_despesas = carregar_despesas()

# === Lista de funcionários ===
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

# === Filtro por ano ===
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("🗕️ Filtrar por ano", anos)

# === Seleção de funcionário ===
funcionario_escolhido = st.selectbox("📋 Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionário"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)].copy()

# === Filtro por tipo de serviço ===
tipos_servico = df_func["Serviço"].dropna().unique().tolist()
tipo_selecionado = st.multiselect("Filtrar por tipo de serviço", tipos_servico)
if tipo_selecionado:
    df_func = df_func[df_func["Serviço"].isin(tipo_selecionado)]

# === Insights do Funcionário ===
st.subheader("📌 Insights do Funcionário")

# KPIs
col1, col2, col3, col4 = st.columns(4)
total_atendimentos = df_func.shape[0]
clientes_unicos = df_func["Cliente"].nunique()
total_receita = df_func["Valor"].sum()
ticket_medio_geral = df_func["Valor"].mean()

col1.metric("🔢 Total de atendimentos", total_atendimentos)
col2.metric("👥 Clientes únicos", clientes_unicos)
col3.metric("💰 Receita total", f"R$ {total_receita:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col4.metric("🎫 Ticket médio", f"R$ {ticket_medio_geral:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# Dia mais cheio
dia_mais_cheio = df_func.groupby(df_func["Data"].dt.date).size().reset_index(name="Atendimentos").sort_values("Atendimentos", ascending=False).head(1)
if not dia_mais_cheio.empty:
    data_cheia = pd.to_datetime(dia_mais_cheio.iloc[0, 0]).strftime("%d/%m/%Y")
    qtd_atend = int(dia_mais_cheio.iloc[0, 1])
    st.info(f"📅 Dia com mais atendimentos: **{data_cheia}** com **{qtd_atend} atendimentos**")

# Gráfico: Distribuição por dia da semana
st.markdown("### 📆 Atendimentos por dia da semana")
dias_semana = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
df_func["DiaSemana"] = df_func["Data"].dt.dayofweek.map(dias_semana)
grafico_semana = df_func.groupby("DiaSemana").size().reset_index(name="Qtd Atendimentos")
fig_dias = px.bar(grafico_semana, x="DiaSemana", y="Qtd Atendimentos", text_auto=True, template="plotly_white")
st.plotly_chart(fig_dias, use_container_width=True)

# Média de atendimentos por dia do mês
st.markdown("### 🗓️ Média de atendimentos por dia do mês")
df_func["Dia"] = df_func["Data"].dt.day
media_por_dia = df_func.groupby("Dia").size().reset_index(name="Média por dia")
fig_dia_mes = px.line(media_por_dia, x="Dia", y="Média por dia", markers=True, template="plotly_white")
st.plotly_chart(fig_dia_mes, use_container_width=True)

# Comparativo com outros funcionários
st.markdown("### ⚖️ Comparativo com a média dos outros funcionários")
todos_func_mesmo_ano = df[df["Ano"] == ano_escolhido].copy()
media_geral = todos_func_mesmo_ano.groupby("Funcionário")["Valor"].mean().reset_index(name="Ticket Médio")
media_geral["Ticket Médio Formatado"] = media_geral["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(media_geral[["Funcionário", "Ticket Médio Formatado"]].sort_values("Ticket Médio", ascending=False), use_container_width=True)

# (restante do seu código continua aqui... como receitas mensais etc.)

import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import datetime
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

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
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month

    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)

    # Verifica se coluna de duração está vazia
    if "Duração (min)" not in df.columns or df["Duração (min)"].isna().all():
        if set(["Hora Chegada", "Hora Saída do Salão", "Hora Saída"]).intersection(df.columns):
            def calcular_duracao(row):
                try:
                    h1 = pd.to_datetime(row["Hora Chegada"], format="%H:%M:%S", errors="coerce")
                    h2 = pd.to_datetime(row.get("Hora Saída do Salão", None), format="%H:%M:%S", errors="coerce")
                    h3 = pd.to_datetime(row.get("Hora Saída", None), format="%H:%M:%S", errors="coerce")
                    fim = h2 if pd.notnull(h2) else h3
                    return (fim - h1).total_seconds() / 60 if pd.notnull(fim) and pd.notnull(h1) and fim > h1 else None
                except Exception as e:
                    return None
            df["Duração (min)"] = df.apply(calcular_duracao, axis=1)

    return df

# === TENTATIVA DE CARREGAR DADOS COM PROTEÇÃO ===
try:
    df = carregar_dados()
except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    st.stop()

if df.empty:
    st.error("Erro: A base de dados está vazia ou não foi carregada.")
    st.stop()

# == CONTINUA A LÓGICA NORMAL ===
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = (
    st.session_state.get("cliente") 
    if "cliente" in st.session_state and st.session_state["cliente"] in clientes_disponiveis
    else clientes_disponiveis[0]
)
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

st.success("Dados carregados com sucesso e cliente selecionado!")
df_cliente = df[df["Cliente"] == cliente].sort_values("Data", ascending=False)

if df_cliente.empty:
    st.warning("Nenhum atendimento encontrado para esse cliente.")
    st.stop()

# Último atendimento
ultimo = df_cliente["Data"].max()
dias_desde = (pd.Timestamp.today() - ultimo).days
frequencia = df_cliente["Data"].diff().dt.days.dropna().mean()
intervalo_medio = round(df_cliente["Data"].diff().dt.days.dropna().mean(), 1)

# Status
status = "🟢 Em dia"
if dias_desde > frequencia * 1.5:
    status = "🔴 Muito atrasado"
elif dias_desde > frequencia:
    status = "🟡 Pouco atrasado"

# Mais atendido por
mais_atendido = df_cliente["Funcionário"].value_counts().idxmax()

# VIP
vip = "Sim" if df_cliente["Cliente VIP"].astype(str).str.lower().str.contains("sim").any() else "Não"

# Ticket médio
ticket = df_cliente["Valor"].mean()

# Tempo total no salão (se houver duração)
tempo_total = df_cliente["Duração (min)"].sum() if "Duração (min)" in df_cliente.columns else None
tempo_txt = f"{int(tempo_total)} min" if tempo_total else "Indisponível"

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.subheader("📅 Último Atendimento")
    st.markdown(f"<h3>{ultimo.strftime('%d/%m/%Y')}</h3>", unsafe_allow_html=True)
with col2:
    st.subheader("📊 Frequência Média")
    st.markdown(f"<h3>{frequencia:.1f} dias</h3>", unsafe_allow_html=True)
with col3:
    st.subheader("🕒 Dias Desde Último")
    st.markdown(f"<h3>{dias_desde}</h3>", unsafe_allow_html=True)
with col4:
    st.subheader("📌 Status")
    st.markdown(f"<h3>{status}</h3>", unsafe_allow_html=True)

st.markdown("---")
st.subheader("💡 Insights Adicionais do Cliente")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("🧡 **Cliente VIP**")
    st.markdown(f"<h3>{vip} ⭐</h3>", unsafe_allow_html=True)
    st.markdown("🪙 **Ticket Médio**")
    st.markdown(f"<h3>R$ {ticket:.2f}</h3>", unsafe_allow_html=True)

with col2:
    st.markdown("🧑‍🦱 **Mais atendido por**")
    st.markdown(f"<h3>{mais_atendido}</h3>", unsafe_allow_html=True)
    st.markdown("📆 **Intervalo Médio**")
    st.markdown(f"<h3>{intervalo_medio} dias</h3>", unsafe_allow_html=True)

with col3:
    st.markdown("⏱️ **Tempo Total no Salão**")
    st.markdown(f"<h3>{tempo_txt}</h3>", unsafe_allow_html=True)

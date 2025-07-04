import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from urllib.parse import quote
from PIL import Image
import requests
from io import BytesIO
import re

st.set_page_config(layout="wide")
st.title("📅 Frequência dos Clientes")

# === CONFIG GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

# === Funções auxiliares ===
def padronizar_link(link):
    if not isinstance(link, str) or link.strip() == "":
        return ""
    match = re.search(r"[-\w]{25,}", link)
    if match:
        file_id = match.group(0)
        return f"https://drive.google.com/uc?export=view&id={file_id}"
    return ""

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
    return df

@st.cache_data
def carregar_status():
    try:
        planilha = conectar_sheets()
        aba_status = planilha.worksheet(STATUS_ABA)
        status = get_as_dataframe(aba_status).dropna(how="all")
        status.columns = [str(col).strip() for col in status.columns]

        colunas = status.columns.tolist()
        coluna_imagem = next((col for col in colunas if col.strip().lower() in ["linkimagem", "imagem cliente", "foto", "imagem"]), None)

        if coluna_imagem:
            status = status.rename(columns={coluna_imagem: "Imagem"})
        else:
            status["Imagem"] = ""

        status["Imagem"] = status["Imagem"].fillna("").apply(padronizar_link)
        return status[["Cliente", "Status", "Imagem"]]
    except:
        return pd.DataFrame(columns=["Cliente", "Status", "Imagem"])

# === PRÉ-PROCESSAMENTO ===
df = carregar_dados()
df_status = carregar_status()
clientes_validos = df_status[~df_status["Status"].isin(["Inativo", "Ignorado"])]
clientes_validos = clientes_validos["Cliente"].unique().tolist()
df = df[df["Cliente"].isin(clientes_validos)]
atendimentos = df.drop_duplicates(subset=["Cliente", "Data"])

# === CÁLCULO DE FREQUÊNCIA ===
frequencia_clientes = []
hoje = pd.Timestamp.today().normalize()

for cliente, grupo in atendimentos.groupby("Cliente"):
    datas = grupo.sort_values("Data")["Data"].tolist()
    if len(datas) < 2:
        continue
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media_freq = sum(diffs) / len(diffs)
    ultimo_atendimento = datas[-1]
    dias_desde_ultimo = (hoje - ultimo_atendimento).days

    if dias_desde_ultimo <= media_freq:
        status = ("🟢 Em dia", "Em dia")
    elif dias_desde_ultimo <= media_freq * 1.5:
        status = ("🟠 Pouco atrasado", "Pouco atrasado")
    else:
        status = ("🔴 Muito atrasado", "Muito atrasado")

    frequencia_clientes.append({
        "Status": status[0],
        "Cliente": cliente,
        "Último Atendimento": ultimo_atendimento.date(),
        "Qtd Atendimentos": len(datas),
        "Frequência Média (dias)": round(media_freq, 1),
        "Dias Desde Último": dias_desde_ultimo,
        "Status_Label": status[1]
    })

freq_df = pd.DataFrame(frequencia_clientes)
freq_df = freq_df.merge(df_status[["Cliente", "Imagem"]], on="Cliente", how="left")

# === INDICADORES ===
st.markdown("### 📊 Indicadores")
col1, col2, col3, col4 = st.columns(4)
col1.metric("👥 Clientes ativos", freq_df["Cliente"].nunique())
col2.metric("🟢 Em dia", freq_df[freq_df["Status_Label"] == "Em dia"]["Cliente"].nunique())
col3.metric("🟠 Pouco atrasado", freq_df[freq_df["Status_Label"] == "Pouco atrasado"]["Cliente"].nunique())
col4.metric("🔴 Muito atrasado", freq_df[freq_df["Status_Label"] == "Muito atrasado"]["Cliente"].nunique())

# === TABELA COM IMAGEM E FILTRO POR STATUS ===
def gerar_tabela_com_imagens(df_input, titulo, cor_status="🔴"):
    st.markdown(titulo)

    nome_filtrado = st.text_input(f"🔍 Filtrar {titulo.replace('#', '').strip()} por nome", key=titulo).strip().lower()
    if nome_filtrado:
        df_input = df_input[df_input["Cliente"].str.lower().str.contains(nome_filtrado)]

    if df_input.empty:
        st.warning("Nenhum cliente encontrado com esse filtro.")
        return

    df_tabela = df_input.copy()
    df_tabela["Foto"] = df_tabela["Imagem"].apply(
        lambda x: f'<img src="{x}" width="40">' if isinstance(x, str) and x.startswith("http") else "📷❌"
    )

    df_tabela["Cliente"] = df_tabela["Cliente"].apply(lambda x: f"<b>{x}</b>")
    df_tabela = df_tabela[[
        "Foto", "Cliente", "Último Atendimento", "Qtd Atendimentos",
        "Frequência Média (dias)", "Dias Desde Último", "Status_Label"
    ]].rename(columns={
        "Foto": "Foto",
        "Cliente": "Cliente",
        "Último Atendimento": "Último",
        "Qtd Atendimentos": "Atendimentos",
        "Frequência Média (dias)": "Freq. Média",
        "Dias Desde Último": "Ausência (dias)",
        "Status_Label": "Status"
    })

    st.markdown(df_tabela.to_html(escape=False, index=False), unsafe_allow_html=True)

# === EXIBIÇÃO DAS TABELAS COM FILTRO E FOTO ===
st.divider()
gerar_tabela_com_imagens(freq_df[freq_df["Status_Label"] == "Muito atrasado"], "## 🔴 Muito Atrasados")
st.divider()
gerar_tabela_com_imagens(freq_df[freq_df["Status_Label"] == "Pouco atrasado"], "## 🟠 Pouco Atrasados")
st.divider()
gerar_tabela_com_imagens(freq_df[freq_df["Status_Label"] == "Em dia"], "## 🟢 Em Dia")

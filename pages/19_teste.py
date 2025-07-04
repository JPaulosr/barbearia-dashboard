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
st.title("\U0001F4C6 Frequência dos Clientes")

# === CONFIG GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

# === Funções auxiliares ===
def carregar_imagem(link):
    try:
        response = requests.get(link)
        if response.status_code == 200:
            return Image.open(BytesIO(response.content))
    except:
        return None

def verificar_status_imagem(link):
    if not link:
        return "❌ Vazio"
    try:
        response = requests.get(link)
        if response.status_code == 200:
            return "✅ OK"
        else:
            return f"⚠️ {response.status_code}"
    except:
        return "❌ Erro"

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

        # Diagnóstico e ajuste de coluna de imagem
        colunas = status.columns.tolist()
        if "LinkImagem" in colunas:
            status = status.rename(columns={"LinkImagem": "Imagem"})
        elif "Imagem cliente" in colunas:
            status = status.rename(columns={"Imagem cliente": "Imagem"})
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

# === FILTRO POR TEXTO ===
st.markdown("### 🎯 Filtro de Cliente")
nome_busca = st.text_input("🔍 Digite parte do nome").strip().lower()
if nome_busca:
    freq_df = freq_df[freq_df["Cliente"].str.lower().str.contains(nome_busca)]

# === INDICADORES ===
st.markdown("### 📊 Indicadores")
col1, col2, col3, col4 = st.columns(4)
col1.metric("👥 Clientes ativos", freq_df["Cliente"].nunique())
col2.metric("🟢 Em dia", freq_df[freq_df["Status_Label"] == "Em dia"]["Cliente"].nunique())
col3.metric("🟠 Pouco atrasado", freq_df[freq_df["Status_Label"] == "Pouco atrasado"]["Cliente"].nunique())
col4.metric("🔴 Muito atrasado", freq_df[freq_df["Status_Label"] == "Muito atrasado"]["Cliente"].nunique())

# === TABELAS COM IMAGEM ===
def mostrar_tabela_com_imagem(df_input, titulo):
    st.markdown(titulo)
    for _, row in df_input.iterrows():
        col1, col2, col3 = st.columns([1, 3, 6])
        imagem = carregar_imagem(row["Imagem"])
        if imagem:
            col1.image(imagem, width=50)
        else:
            col1.markdown("📷❌")
        col2.markdown(f"**{row['Cliente']}**")
        col3.markdown(
            f"Último: {row['Último Atendimento']} — "
            f"{row['Qtd Atendimentos']} atendimentos — "
            f"Freq: {row['Frequência Média (dias)']}d — "
            f"{row['Dias Desde Último']} dias sem vir"
        )

st.divider()
mostrar_tabela_com_imagem(freq_df[freq_df["Status_Label"] == "Muito atrasado"], "## 🔴 Muito Atrasados")
mostrar_tabela_com_imagem(freq_df[freq_df["Status_Label"] == "Pouco atrasado"], "## 🟠 Pouco Atrasados")
mostrar_tabela_com_imagem(freq_df[freq_df["Status_Label"] == "Em dia"], "## 🟢 Em Dia")

# === GRÁFICO: TOP 20 CLIENTES AUSENTES ===
st.divider()
st.subheader("📊 Top 20 Clientes com mais dias sem vir")
top_grafico = freq_df.sort_values("Dias Desde Último", ascending=False).head(20)
fig = px.bar(
    top_grafico,
    x="Cliente",
    y="Dias Desde Último",
    color="Status_Label",
    text="Dias Desde Último",
    labels={"Dias Desde Último": "Dias de ausência", "Status_Label": "Status"}
)
fig.update_layout(xaxis_tickangle=-45, height=500)
fig.update_traces(textposition="outside")
st.plotly_chart(fig, use_container_width=True)

# === RANKING DE FREQUÊNCIA COM FOTO ===
st.divider()
st.subheader("🏆 Ranking por Frequência Média")
col5, col6 = st.columns(2)

with col5:
    st.markdown("### ✅ Top 5 Clientes com Melhor Frequência")
    melhores = freq_df.sort_values("Frequência Média (dias)").head(5)
    for _, row in melhores.iterrows():
        img = carregar_imagem(row["Imagem"])
        col_a, col_b = st.columns([1, 5])
        if img:
            col_a.image(img, width=50)
        else:
            col_a.markdown("📷❌")
        col_b.markdown(f"**{row['Cliente']}** — {row['Frequência Média (dias)']} dias")

with col6:
    st.markdown("### ⚠️ Top 5 Clientes com Pior Frequência")
    piores = freq_df.sort_values("Frequência Média (dias)", ascending=False).head(5)
    for _, row in piores.iterrows():
        img = carregar_imagem(row["Imagem"])
        col_a, col_b = st.columns([1, 5])
        if img:
            col_a.image(img, width=50)
        else:
            col_a.markdown("📷❌")
        col_b.markdown(f"**{row['Cliente']}** — {row['Frequência Média (dias)']} dias")

# === TOP 10 ATENDIMENTOS COM FOTO ===
st.divider()
st.subheader("💪 Top 10 Clientes por Quantidade de Atendimentos")
top_atendimentos = freq_df.sort_values("Qtd Atendimentos", ascending=False).head(10)
for _, row in top_atendimentos.iterrows():
    col1, col2 = st.columns([1, 6])
    imagem = carregar_imagem(row["Imagem"])
    if imagem:
        col1.image(imagem, width=60)
    else:
        col1.markdown("📷❌")
    col2.markdown(f"**{row['Cliente']}** — {row['Qtd Atendimentos']} atendimentos")

with st.expander("📊 Ver gráfico"):
    fig2 = px.bar(
        top_atendimentos,
        x="Cliente",
        y="Qtd Atendimentos",
        text="Qtd Atendimentos",
        color_discrete_sequence=["#36a2eb"]
    )
    fig2.update_traces(textposition="outside")
    fig2.update_layout(
        xaxis_tickangle=-45,
        height=500,
        yaxis_title="Atendimentos",
        xaxis_title="Cliente"
    )
    st.plotly_chart(fig2, use_container_width=True)

# === DIAGNÓSTICO DE IMAGENS ===
st.divider()
st.subheader("📷 Diagnóstico de Imagens dos Clientes")
diagnostico = freq_df[["Cliente", "Imagem"]].drop_duplicates().copy()
diagnostico["Status da Imagem"] = diagnostico["Imagem"].apply(verificar_status_imagem)
st.dataframe(diagnostico, use_container_width=True)

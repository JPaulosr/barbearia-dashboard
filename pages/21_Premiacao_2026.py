import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide")
st.title("\U0001F3C6 Top 3 Clientes por Categoria")

# === GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_STATUS = "clientes_status"

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
    df = get_as_dataframe(planilha.worksheet(ABA_BASE)).dropna(how="all")
    df.columns = [c.strip() for c in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df = df.dropna(subset=["Cliente", "Funcionário"])
    df = df[df["Cliente"].str.lower().str.contains("boliviano|brasileiro|menino|sem preferencia|funcionário") == False]
    df = df[df["Cliente"].str.strip() != ""]
    df = df.drop_duplicates(subset=["Cliente", "Data", "Funcionário"])
    return df

@st.cache_data
def carregar_fotos():
    planilha = conectar_sheets()
    df_status = get_as_dataframe(planilha.worksheet(ABA_STATUS)).dropna(how="all")
    df_status.columns = [c.strip() for c in df_status.columns]
    return df_status[["Cliente", "Foto", "Família"]].dropna(subset=["Cliente"])

df = carregar_dados()
df_fotos = carregar_fotos()

# === Função de ranking ===
def gerar_top3(df_base, titulo):
    col1, col2, col3 = st.columns([0.05, 0.15, 0.8])
    col1.markdown("### ")
    col2.markdown(f"#### {titulo}")

    total_por_cliente = df_base.groupby("Cliente")["Valor"].sum()
    top3 = total_por_cliente.sort_values(ascending=False).head(3).index.tolist()

    medalhas = ["🥇", "🥈", "🥉"]

    for i, cliente in enumerate(top3):
        qtd = df_base[df_base["Cliente"] == cliente]["Data"].nunique()
        linha = st.columns([0.05, 0.12, 0.83])
        linha[0].markdown(f"### {medalhas[i]}")

        link_foto = df_fotos[df_fotos["Cliente"] == cliente]["Foto"].dropna().values
        if len(link_foto):
            try:
                response = requests.get(link_foto[0])
                img = Image.open(BytesIO(response.content))
                linha[1].image(img, width=50)
            except:
                linha[1].text("[sem imagem]")
        else:
            linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)

        linha[2].markdown(f"**{cliente.lower()}** — {qtd} atendimentos")

# === Top 3 Geral ===
st.subheader("Top 3 Geral")
gerar_top3(df, "")

# === Top 3 JPaulo ===
st.subheader("Top 3 JPaulo")
gerar_top3(df[df["Funcionário"] == "JPaulo"], "")

# === Top 3 Vinicius ===
st.subheader("Top 3 Vinicius")
gerar_top3(df[df["Funcionário"] == "Vinicius"], "")

# === Cliente Família ===
st.subheader("\U0001F468‍\U0001F469‍\U0001F467 Cliente Família")
familia_df = df_fotos[df_fotos["Família"].notna() & (df_fotos["Família"] != "")]
familias = familia_df["Família"].unique()

for grupo in familias:
    membros = familia_df[familia_df["Família"] == grupo]
    for _, row in membros.iterrows():
        linha = st.columns([0.05, 0.12, 0.83])
        linha[0].text("")
        if pd.notna(row["Foto"]):
            try:
                response = requests.get(row["Foto"])
                img = Image.open(BytesIO(response.content))
                linha[1].image(img, width=50)
            except:
                linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)
        else:
            linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)

        linha[2].markdown(f"**{row['Cliente']}** — Membro da Família {grupo} 🍷")

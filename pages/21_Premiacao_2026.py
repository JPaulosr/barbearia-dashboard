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
st.title("🏆 Premiação Especial - Top 3 por Categoria")

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
    df = df.dropna(subset=["Data", "Cliente", "Funcionário"])
    df = df[~df["Cliente"].str.lower().str.contains("boliviano|brasileiro|menino|sem preferencia|funcionário")]
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
df = df.merge(df_fotos[["Cliente", "Família"]], on="Cliente", how="left")

def mostrar_cliente(cliente, pos):
    col1, col2, col3 = st.columns([0.06, 0.15, 0.79])
    medalhas = ["🥇", "🥈", "🥉"]
    col1.markdown(f"### {medalhas[pos]}")
    link_foto = df_fotos[df_fotos["Cliente"] == cliente]["Foto"].dropna().values
    if len(link_foto):
        try:
            response = requests.get(link_foto[0])
            img = Image.open(BytesIO(response.content))
            col2.image(img, width=60)
        except:
            col2.text("sem imagem")
    else:
        col2.image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=60)
    qtd = df[df["Cliente"] == cliente]["Data"].nunique()
    col3.markdown(f"**{cliente.lower()}** — {qtd} atendimentos")

def gerar_top3(df_filtrado, titulo):
    st.subheader(titulo)
    top = df_filtrado.groupby("Cliente")["Valor"].sum().sort_values(ascending=False).head(3).index.tolist()
    for i, cliente in enumerate(top):
        mostrar_cliente(cliente, i)

def gerar_top3_familia(df_completo):
    st.subheader("👨‍👩‍👧‍👦 Top 3 Famílias")
    df_validas = df_completo[df_completo["Família"].notna()]
    top_familias = df_validas.groupby("Família")["Valor"].sum().sort_values(ascending=False).head(3)
    for i, familia in enumerate(top_familias.index.tolist()):
        membros = df_validas[df_validas["Família"] == familia]["Cliente"].unique()
        col1, col2 = st.columns([0.1, 0.9])
        col1.markdown(f"### {'🥇🥈🥉'[i]}")
        col2.markdown(f"**Família {familia}** — membros: {', '.join(membros)}")

# === Exibir Rankings ===
gerar_top3(df, "⭐ Top 3 Geral")
gerar_top3(df[df["Funcionário"] == "JPaulo"], "✂️ Top 3 JPaulo")
gerar_top3(df[df["Funcionário"] == "Vinicius"], "🧔 Top 3 Vinicius")
gerar_top3_familia(df)


import streamlit as st
import pandas as pd
import requests
from PIL import Image
from io import BytesIO
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("\U0001F3C6 Premiação Especial - Top 3 por Categoria")

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
def carregar_fotos():
    planilha = conectar_sheets()
    df_status = get_as_dataframe(planilha.worksheet(ABA_STATUS)).dropna(how="all")
    df_status.columns = [c.strip() for c in df_status.columns]
    return df_status[["Cliente", "Foto"]].dropna(subset=["Cliente"])

df_fotos = carregar_fotos()

# Dados fixos do ranking baseado nas imagens
ranking_geral = ["gabriel lutador", "fábio jr", "josé severino"]
ranking_jpaulo = ["fábio jr", "ronald", "raphael"]
ranking_vinicius = ["gilmar", "jorge", "gabriel lutador"]

medalhas = ["🥇", "🥈", "🥉"]


def mostrar_ranking(titulo, lista_clientes, emoji):
    st.markdown(f"### {emoji} {titulo}")
    for i, cliente in enumerate(lista_clientes):
        linha = st.columns([0.05, 0.12, 0.83])
        linha[0].markdown(f"### {medalhas[i]}")

        link_foto = df_fotos[df_fotos["Cliente"] == cliente]["Foto"].dropna().values
        if len(link_foto):
            try:
                response = requests.get(link_foto[0])
                img = Image.open(BytesIO(response.content))
                linha[1].image(img, width=50)
            except:
                linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)
        else:
            linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)

        linha[2].markdown(f"**{cliente.lower()}** — atendimentos")

# Exibir rankings
mostrar_ranking("Top 3 Geral", ranking_geral, "⭐")
mostrar_ranking("Top 3 JPaulo", ranking_jpaulo, "✂️")
mostrar_ranking("Top 3 Vinicius", ranking_vinicius, "🤔")

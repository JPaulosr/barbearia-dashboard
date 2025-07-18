
import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide")
st.title("🎉 Premiação Anual - 2025")

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
    return df

@st.cache_data
def carregar_fotos_clientes():
    try:
        planilha = conectar_sheets()
        aba_status = planilha.worksheet("clientes_status")
        df_status = get_as_dataframe(aba_status).dropna(how="all")
        df_status.columns = [str(col).strip() for col in df_status.columns]
        return df_status.set_index("Cliente")["Foto"].to_dict()
    except:
        return {}

def gerar_top3(df):
    df = df.groupby(["Cliente", "Data"]).agg({"Valor": "sum"}).reset_index()
    soma_valores = df.groupby("Cliente")["Valor"].sum().reset_index(name="Total_Gasto")
    atendimentos_por_dia = df.groupby("Cliente")["Data"].nunique().reset_index(name="Qtd_Atendimentos")
    ranking = pd.merge(soma_valores, atendimentos_por_dia, on="Cliente")
    nomes_invalidos = ["boliviano", "brasileiro", "menino", "cliente", "moicano", "morador", "menina"]
    ranking = ranking[~ranking["Cliente"].str.lower().isin(nomes_invalidos)]
    ranking = ranking[~ranking["Cliente"].str.lower().str.contains("sem nome|desconhecido|teste")]
    ranking = ranking.sort_values("Total_Gasto", ascending=False).reset_index(drop=True)
    return ranking.head(3)

def exibir_top3(titulo, ranking, fotos_clientes):
    st.markdown(f"### {titulo}")
    for i, row in ranking.iterrows():
        cliente = row["Cliente"]
        qtd = row["Qtd_Atendimentos"]
        foto_url = fotos_clientes.get(cliente, "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png")
        col1, col2, col3 = st.columns([1, 2, 10])
        with col1:
            medalha = "🥇" if i == 0 else "🥈" if i == 1 else "🥉"
            st.markdown(medalha)
        with col2:
            try:
                response = requests.get(foto_url)
                img = Image.open(BytesIO(response.content))
                st.image(img, width=60)
            except:
                st.image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=60)
        with col3:
            st.markdown(f"**{cliente}** — {qtd} atendimentos")

# Dados e imagens
df = carregar_dados()
fotos = carregar_fotos_clientes()

# Título geral
st.markdown("## 🏆 Top 3 Clientes por Categoria")

# Três colunas
col1, col2, col3 = st.columns(3)

with col1:
    exibir_top3("Top 3 Geral", gerar_top3(df), fotos)

with col2:
    exibir_top3("Top 3 JPaulo", gerar_top3(df[df["Funcionário"] == "JPaulo"]), fotos)

with col3:
    exibir_top3("Top 3 Vinicius", gerar_top3(df[df["Funcionário"] == "Vinicius"]), fotos)

# Cliente Família
st.markdown("## 👨‍👩‍👧 Cliente Família")

clientes_familia = ["João Pantanal", "Pedro Pantanal", "Lucas Pantanal"]

for nome in clientes_familia:
    col1, col2 = st.columns([1, 9])
    with col1:
        try:
            foto = fotos.get(nome, "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png")
            response = requests.get(foto)
            img = Image.open(BytesIO(response.content))
            st.image(img, width=60)
        except:
            st.image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=60)
    with col2:
        st.markdown(f"**{nome}** — Membro da Família Pantanal 💈")

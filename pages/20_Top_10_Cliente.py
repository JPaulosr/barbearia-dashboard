
import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(layout="wide")
st.title("🏆 Top 10 Clientes - Geral, JPaulo e Vinicius")

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

def gerar_ranking(df, fotos_clientes):
    df = df.groupby(["Cliente", "Data"]).agg({"Valor": "sum"}).reset_index()
    soma_valores = df.groupby("Cliente")["Valor"].sum().reset_index(name="Total_Gasto")
    atendimentos_por_dia = df.groupby("Cliente")["Data"].nunique().reset_index(name="Qtd_Atendimentos")
    ranking = pd.merge(soma_valores, atendimentos_por_dia, on="Cliente")

    nomes_invalidos = ["boliviano", "brasileiro", "menino", "cliente", "moicano", "morador", "menina"]
    ranking = ranking[~ranking["Cliente"].str.lower().isin(nomes_invalidos)]
    ranking = ranking[~ranking["Cliente"].str.lower().str.contains("sem nome|desconhecido|teste")]
    ranking = ranking.sort_values("Total_Gasto", ascending=False).reset_index(drop=True)
    return ranking.head(10)

def exibir_ranking(nome_lista, ranking, fotos_clientes):
    st.subheader(f"👑 Top 10 - {nome_lista}")
    for i, row in ranking.iterrows():
        cliente = row["Cliente"]
        qtd = row["Qtd_Atendimentos"]
        foto_url = fotos_clientes.get(cliente, "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png")
        col1, col2, col3 = st.columns([1, 2, 10])
        with col1:
            medalha = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"#{i+1}"
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

# Execução
df = carregar_dados()
fotos_clientes = carregar_fotos_clientes()

# Lista Geral
st.markdown("## 🌟 Top 10 Geral")
exibir_ranking("Geral", gerar_ranking(df, fotos_clientes), fotos_clientes)

# Duas colunas para JPaulo e Vinicius
col1, col2 = st.columns(2)

with col1:
    df_jp = df[df["Funcionário"] == "JPaulo"]
    exibir_ranking("JPaulo", gerar_ranking(df_jp, fotos_clientes), fotos_clientes)

with col2:
    df_vinicius = df[df["Funcionário"] == "Vinicius"]
    exibir_ranking("Vinicius", gerar_ranking(df_vinicius, fotos_clientes), fotos_clientes)

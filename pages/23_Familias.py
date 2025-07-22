import streamlit as st
import pandas as pd
import requests
from PIL import Image
from io import BytesIO
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.subheader("👨‍👩‍👧‍👦 Cliente Família — Todas as Famílias")

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
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0)
    return df

@st.cache_data
def carregar_fotos():
    planilha = conectar_sheets()
    df_status = get_as_dataframe(planilha.worksheet(ABA_STATUS)).dropna(how="all")
    df_status.columns = [c.strip() for c in df_status.columns]
    return df_status[["Cliente", "Foto", "Família"]].dropna(subset=["Cliente"])

df = carregar_dados()
df_fotos = carregar_fotos()

# Junta dados com 'Família'
df_familia = df.merge(df_fotos[["Cliente", "Família"]], on="Cliente", how="left")
df_familia = df_familia[df_familia["Família"].notna() & (df_familia["Família"].str.strip() != "")]

# Agrupa por Família e soma valores
familia_valores = df_familia.groupby("Família")["Valor"].sum()
familia_valores = familia_valores[familia_valores > 0].sort_values(ascending=False)

# Conta atendimentos únicos por cliente + data
atendimentos_unicos = df_familia.drop_duplicates(subset=["Cliente", "Data"])
familia_atendimentos = atendimentos_unicos.groupby("Família").size()
dias_distintos = df_familia.drop_duplicates(subset=["Família", "Data"]).groupby("Família").size()

for idx, familia in enumerate(familia_valores.index):
    valor_total = familia_valores[familia]
    qtd_atendimentos = familia_atendimentos.get(familia, 0)
    qtd_dias = dias_distintos.get(familia, 0)

    membros = df_fotos[df_fotos["Família"] == familia]
    qtd_membros = len(membros)

    nome_pai = familia.replace("Família ", "").strip().lower()
    nome_pai_formatado = nome_pai.capitalize()
    membro_foto = None

    for i, row in membros.iterrows():
        cliente_nome = str(row["Cliente"]).strip().lower()
        foto = row["Foto"]
        if cliente_nome == nome_pai and pd.notna(foto):
            membro_foto = foto
            break

    if not membro_foto and membros["Foto"].notna().any():
        membro_foto = membros["Foto"].dropna().values[0]

    linha = st.columns([0.05, 0.12, 0.83])
    linha[0].markdown(f"### {idx + 1}")

    if membro_foto:
        try:
            response = requests.get(membro_foto)
            img = Image.open(BytesIO(response.content))
            linha[1].image(img, width=50)
        except:
            linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)
    else:
        linha[1].image("https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png", width=50)

    texto = f"""
    Família **{nome_pai_formatado}**  
    💰 Total gasto: R$ {valor_total:,.2f}  
    📆 Dias distintos: {qtd_dias}  
    🧼 Atendimentos: {qtd_atendimentos}  
    👥 Membros: {qtd_membros}
    """
    linha[2].markdown(texto)

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

    if "Duração (min)" not in df.columns or df["Duração (min)"].isna().all():
        if set(["Hora Chegada", "Hora Saída do Salão"]).issubset(df.columns):
            def calcular_duracao(row):
                try:
                    h1 = pd.to_datetime(row["Hora Chegada"], format="%H:%M:%S")
                    h2 = pd.to_datetime(row["Hora Saída do Salão"], format="%H:%M:%S")
                    return (h2 - h1).total_seconds() / 60 if h2 > h1 else None
                except:
                    return None
            df["Duração (min)"] = df.apply(calcular_duracao, axis=1)

    return df

df = carregar_dados()

# === 🔍 Filtro e Comparativo ===
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

# === Mostrar imagem do cliente ===
def buscar_link_foto(nome):
    try:
        planilha = conectar_sheets()
        aba_status = planilha.worksheet("clientes_status")
        df_status = get_as_dataframe(aba_status).dropna(how="all")
        df_status.columns = [str(col).strip() for col in df_status.columns]
        foto = df_status[df_status["Cliente"] == nome]["Foto"].dropna().values
        return foto[0] if len(foto) > 0 else None
    except:
        return None

link_foto = buscar_link_foto(cliente)
if link_foto:
    try:
        response = requests.get(link_foto)
        img = Image.open(BytesIO(response.content))
        st.image(img, caption=f"Foto de {cliente}", use_container_width=True)
    except:
        st.warning("Erro ao carregar imagem do cliente.")
else:
    st.info("Cliente sem imagem cadastrada.")

# === Comparativo entre Clientes ===
with st.expander("🧪 Comparativo entre Clientes", expanded=False):
    col_c1, col_c2 = st.columns(2)
    cliente_1 = col_c1.selectbox("Cliente 1", clientes_disponiveis, key="c1")
    cliente_2 = col_c2.selectbox("Cliente 2", clientes_disponiveis, index=1, key="c2")

    def indicadores(cliente_nome):
        dados = df[df["Cliente"] == cliente_nome].copy()
        meses = dados["Mês_Ano"].nunique()
        gasto_total = dados["Valor"].sum()
        ticket_medio = gasto_total / len(dados) if len(dados) > 0 else 0
        gasto_mensal = gasto_total / meses if meses > 0 else 0
        return {
            "Cliente": cliente_nome,
            "Atendimentos": len(dados),
            "Ticket Médio": round(ticket_medio, 2),
            "Gasto Total": round(gasto_total, 2),
            "Gasto Mensal Médio": round(gasto_mensal, 2),
        }

    df_comp = pd.DataFrame([indicadores(cliente_1), indicadores(cliente_2)])
    st.dataframe(df_comp, use_container_width=True)

# === 📊 Análises Detalhadas do Cliente Selecionado ===
# (continua o restante do código sem alterações...)

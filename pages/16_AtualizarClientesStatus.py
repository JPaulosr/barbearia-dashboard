import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

st.set_page_config(page_title="Atualizar Clientes Status", layout="wide")
st.title("🔄 Atualizar Lista de Clientes (clientes_status)")

# === CONFIGURAÇÃO ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_CLIENTES = "clientes_status"
CAMINHO_CREDENCIAL = "barbearia-dashboard-04c0ce9b53d4.json"

# === Conectar ao Google Sheets ===
@st.cache_resource
def conectar_planilha():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
        "https://spreadsheets.google.com/feeds"
    ]
    credenciais = Credentials.from_service_account_file(CAMINHO_CREDENCIAL, scopes=scopes)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

# === Carregar dados ===
def carregar_clientes_base():
    aba = planilha.worksheet(ABA_DADOS)
    df = get_as_dataframe(aba)
    df = df.dropna(subset=["Cliente"])
    clientes_base = sorted(df["Cliente"].astype(str).str.strip().unique().tolist())
    return clientes_base

def carregar_clientes_status():
    aba = planilha.worksheet(ABA_CLIENTES)
    df = get_as_dataframe(aba)
    df = df.dropna(subset=["Cliente"])
    clientes_status = df["Cliente"].astype(str).str.strip().tolist()
    return df, clientes_status

# === Execução ===
planilha = conectar_planilha()
clientes_base = carregar_clientes_base()
df_status, clientes_status = carregar_clientes_status()

faltando = sorted([c for c in clientes_base if c not in clientes_status])

st.subheader("📋 Clientes faltando em 'clientes_status'")
st.write(f"Total de clientes na base de dados: {len(clientes_base)}")
st.write(f"Total de clientes já na 'clientes_status': {len(clientes_status)}")
st.write(f"Total de novos clientes a adicionar: {len(faltando)}")

if faltando:
    st.dataframe(pd.DataFrame({"Cliente": faltando}), use_container_width=True)

    if st.button("✅ Adicionar clientes faltantes"):
        aba = planilha.worksheet(ABA_CLIENTES)
        df_atualizado = pd.concat([df_status, pd.DataFrame({"Cliente": faltando})], ignore_index=True)
        df_atualizado = df_atualizado.drop_duplicates(subset=["Cliente"])
        set_with_dataframe(aba, df_atualizado)
        st.success("Clientes adicionados com sucesso à aba 'clientes_status'!")
else:
    st.success("Todos os clientes já estão cadastrados na aba 'clientes_status'.")

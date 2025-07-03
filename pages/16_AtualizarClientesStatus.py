import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import json

st.set_page_config(page_title="Atualizar Clientes", page_icon="🔄", layout="wide")
st.title("🔄 Atualizar Lista de Clientes (clientes_status)")

# Função para autenticar com base nos secrets do Streamlit
@st.cache_data
def conectar_planilha():
    # Carrega o JSON das credenciais do secrets
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    
    # Cria credenciais a partir do dicionário
    credentials = Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/spreadsheets"])
    
    # Conecta com gspread
    gc = gspread.authorize(credentials)
    
    # Abre a planilha e retorna a aba clientes_status
    sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/edit")
    aba = sh.worksheet("clientes_status")
    return aba

# Função para carregar clientes únicos da base de dados
@st.cache_data
def carregar_clientes_base():
    url_base = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url_base)
    df["Cliente"] = df["Cliente"].fillna("").str.strip()
    clientes_unicos = sorted(df["Cliente"].unique())
    return clientes_unicos

# Botão para atualizar
if st.button("🔁 Atualizar clientes_status com nomes únicos da Base de Dados"):
    try:
        aba = conectar_planilha()
        clientes = carregar_clientes_base()
        
        # Atualiza os dados na planilha
        dados = [["Cliente", "Status"]] + [[nome, ""] for nome in clientes]
        aba.clear()
        aba.update(dados)
        st.success("✅ Lista de clientes atualizada com sucesso!")
    except Exception as e:
        st.error(f"Erro ao atualizar: {e}")

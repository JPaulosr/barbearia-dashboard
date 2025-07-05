import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Galeria de Clientes", layout="wide")
st.title("🖼️ Galeria de Clientes")

# Conexão segura com planilha
@st.cache_data(show_spinner=False)
def conectar_e_carregar():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"],
        scopes=escopos
    )
    cliente = gspread.authorize(credenciais)
    url = st.secrets["PLANILHA_URL"]["url"]
    planilha = cliente.open_by_url(url)
    aba = planilha.worksheet("clientes_status")
    dados = pd.DataFrame(aba.get_all_records())
    return dados

# Carrega e trata
df = conectar_e_carregar()
df["Cliente"] = df["Cliente"].astype(str).str.strip()
df["Foto_URL"] = df["Foto_URL"].fillna("")

# Filtro de nome
nome_filtrado = st.text_input("🔍 Buscar cliente pelo nome").strip().lower()
if nome_filtrado:
    df = df[df["Cliente"].str.lower().str.contains(nome_filtrado)]

# Layout da galeria
cols = st.columns(4)
for i, (idx, row) in enumerate(df.iterrows()):
    col = cols[i % 4]
    with col:
        st.markdown(f"**{row['Cliente']}**")
        if row["Foto_URL"]:
            st.image(row["Foto_URL"], use_column_width=True)
        else:
            st.info("Sem imagem")

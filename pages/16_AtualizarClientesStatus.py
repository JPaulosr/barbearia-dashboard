import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

st.set_page_config(page_title="Atualizar Clientes", layout="wide")
st.markdown("## 🔄 Atualizar Lista de Clientes (clientes_status)")

# ⬇️ Conectar com a planilha Google Sheets via SECRETS
@st.cache_data(show_spinner=False)
def conectar_planilha():
    escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"],
        scopes=escopos
    )
    cliente = gspread.authorize(credenciais)
    url = st.secrets["PLANILHA_URL"]
    planilha = cliente.open_by_url(url)
    return planilha

# ⬇️ Carregar abas da planilha
@st.cache_data(show_spinner=False)
def carregar_abas():
    planilha = conectar_planilha()
    base_dados = planilha.worksheet("Base de Dados")
    clientes_status = planilha.worksheet("clientes_status")
    return base_dados, clientes_status

# ⬇️ Atualizar lista de clientes
def atualizar_clientes():
    base_dados, clientes_status = carregar_abas()
    dados = base_dados.get_all_records()
    df = pd.DataFrame(dados)
    df["Cliente"] = df["Cliente"].str.strip()
    clientes_unicos = sorted(df["Cliente"].dropna().unique())

    # Limpar aba atual
    clientes_status.clear()

    # Atualizar com novos dados
    nova_lista = pd.DataFrame({"Cliente": clientes_unicos, "Status": ""})
    clientes_status.update([nova_lista.columns.values.tolist()] + nova_lista.values.tolist())

    return nova_lista

# ⬇️ Botão para atualizar
if st.button("🔁 Atualizar Lista de Clientes"):
    with st.spinner("Atualizando lista de clientes..."):
        resultado = atualizar_clientes()
        st.success("Lista de clientes atualizada com sucesso!")
        st.dataframe(resultado, use_container_width=True)

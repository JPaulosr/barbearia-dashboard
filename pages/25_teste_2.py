import streamlit as st
import gspread
import pandas as pd
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="🔄 Sincronizar Clientes", layout="wide")
st.title("🔄 Sincronizar Novos Clientes com a Tabela 'clientes_status'")

# === CONFIGURAÇÃO ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

# === CONECTA AO GOOGLE SHEETS ===
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

# === SINCRONIZA NOVOS CLIENTES ===
def sincronizar_clientes():
    planilha = conectar_sheets()

    # Carrega as duas abas
    base_df = get_as_dataframe(planilha.worksheet(BASE_ABA)).dropna(how="all")
    status_df = get_as_dataframe(planilha.worksheet(STATUS_ABA)).dropna(how="all")

    base_df.columns = base_df.columns.str.strip()
    status_df.columns = status_df.columns.str.strip()

    # Extrai lista única de clientes da base
    clientes_base = set(base_df["Cliente"].dropna().unique())
    clientes_status = set(status_df["Cliente"].dropna().unique())

    novos_clientes = sorted(list(clientes_base - clientes_status))

    if not novos_clientes:
        st.success("✅ Nenhum novo cliente para adicionar. Tudo atualizado!")
        return

    novos_df = pd.DataFrame(novos_clientes, columns=["Cliente"])
    novos_df["Status"] = "Ativo"
    novos_df["Foto"] = ""
    novos_df["Família"] = ""

    # Concatena com o DataFrame existente e reenvia
    status_final = pd.concat([status_df, novos_df], ignore_index=True)
    aba = planilha.worksheet(STATUS_ABA)
    aba.clear()
    set_with_dataframe(aba, status_final)

    st.success(f"✅ {len(novos_clientes)} cliente(s) novo(s) adicionados com sucesso à aba 'clientes_status'.")

# === BOTÃO DE AÇÃO ===
st.markdown("Clique abaixo para verificar e adicionar automaticamente novos clientes à aba `clientes_status`.")

if st.button("🔄 Sincronizar novos clientes"):
    sincronizar_clientes()

import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🔄 Atualizar Clientes no Status")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

# === CONEXÃO GOOGLE SHEETS ===
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def carregar_dados():
    planilha = conectar_sheets()
    aba_base = planilha.worksheet(BASE_ABA)
    aba_status = planilha.worksheet(STATUS_ABA)

    # Carrega base
    df_base = get_as_dataframe(aba_base).dropna(how="all")
    df_base.columns = [col.strip() for col in df_base.columns]

    # Carrega status
    df_status = get_as_dataframe(aba_status).dropna(how="all")
    df_status.columns = [col.strip() for col in df_status.columns]

    return df_base, df_status, aba_status

def atualizar_status():
    df_base, df_status, aba_status = carregar_dados()

    # Normaliza nomes
    base_clientes = df_base["Cliente"].dropna().str.strip().unique()
    status_clientes = df_status["Cliente"].dropna().str.strip().unique()

    # Identifica clientes novos
    novos_clientes = sorted(set(base_clientes) - set(status_clientes))

    if not novos_clientes:
        st.success("✅ Nenhum cliente novo para adicionar.")
        return

    # Cria DataFrame com novos clientes
    novos_df = pd.DataFrame({
        "Cliente": novos_clientes,
        "Status": "Ativo"
    })

    # Junta com existente
    df_atualizado = pd.concat([df_status, novos_df], ignore_index=True)

    # Atualiza no Google Sheets
    aba_status.clear()
    set_with_dataframe(aba_status, df_atualizado)

    st.success(f"🎉 {len(novos_clientes)} novo(s) cliente(s) adicionados com sucesso!")

# === Botão de ação ===
if st.button("🚀 Verificar e Atualizar Clientes"):
    atualizar_status()

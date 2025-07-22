import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="🔄 Sincronizar Clientes", layout="wide")
st.title("🔄 Sincronizar Clientes")

# === CONFIG GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

# === Carregar dados ===
def carregar_bases():
    planilha = conectar_sheets()
    base = get_as_dataframe(planilha.worksheet(BASE_ABA)).dropna(how="all")
    status = get_as_dataframe(planilha.worksheet(STATUS_ABA)).dropna(how="all")
    base.columns = [c.strip() for c in base.columns]
    status.columns = [c.strip() for c in status.columns]
    return base, status, planilha

base_df, status_df, planilha = carregar_bases()

# === Normalizar e comparar ===
clientes_base = set(base_df["Cliente"].dropna().unique())
clientes_status = set(status_df["Cliente"].dropna().unique())
novos_clientes = sorted(list(clientes_base - clientes_status))

st.markdown(f"### 👥 Clientes novos detectados: `{len(novos_clientes)}`")

if novos_clientes:
    novos_df = pd.DataFrame({
        "Cliente": novos_clientes,
        "Status": ["Ativo"] * len(novos_clientes),
        "Foto": [""] * len(novos_clientes),
        "Família": [""] * len(novos_clientes)
    })

    st.dataframe(novos_df, use_container_width=True)

    if st.button("✅ Adicionar ao clientes_status"):
        aba_status = planilha.worksheet(STATUS_ABA)
        status_atualizado = pd.concat([status_df, novos_df], ignore_index=True)
        set_with_dataframe(aba_status, status_atualizado)
        st.success(f"{len(novos_clientes)} novos clientes adicionados com sucesso!")
else:
    st.success("Nenhum cliente novo para adicionar. Tudo sincronizado! ✅")

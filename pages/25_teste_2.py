import time
import pandas as pd
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe

# === CONFIGURAÇÕES ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"

# Colunas oficiais e fiado
COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período"
]
COLS_FIADO = ["StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"]

# === CONEXÃO GOOGLE SHEETS ===
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

# === FUNÇÃO SEGURA DE CARREGAR BASE ===
@st.cache_data(ttl=300, show_spinner=False)
def carregar_base_seguro():
    t0 = time.perf_counter()
    try:
        sh = conectar_sheets()
        ws = sh.worksheet(ABA_DADOS)

        # Tenta caminho rápido
        records = ws.get_all_records(numericise_ignore=['all'])
        df = pd.DataFrame(records)

        # Se vier vazio, usa fallback
        if df.empty:
            df = get_as_dataframe(ws).dropna(how="all")

        df.columns = [str(col).strip() for col in df.columns]

        # Garante colunas
        for coluna in [*COLS_OFICIAIS, *COLS_FIADO]:
            if coluna not in df.columns:
                df[coluna] = ""

        # Normaliza Período
        norm = {"manha": "Manhã", "Manha": "Manhã", "manha ": "Manhã", "tarde": "Tarde", "noite": "Noite"}
        df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
        df.loc[~df["Período"].isin(["Manhã", "Tarde", "Noite"]), "Período"] = ""

        df["Combo"] = df["Combo"].fillna("")

        st.session_state["_LOAD_MS"] = int((time.perf_counter() - t0) * 1000)
        return df, ws

    except Exception as e:
        st.error(f"❌ Falha ao carregar a planilha: {e}")
        raise

def carregar_base():
    return carregar_base_seguro()

# === DRIVER DA PÁGINA (renderização) ===
st.set_page_config(page_title="Utils Notificação — Debug", layout="wide")
st.title("🛠️ Utils Notificação — Debug")

# Botão para rodar teste
if st.button("▶️ Testar carregar_base()"):
    with st.spinner("Carregando dados do Google Sheets..."):
        df, ws = carregar_base()
    st.success(
        f"✅ Carregado! Linhas: {len(df)} | Colunas: {len(df.columns)} "
        f"| Tempo: {st.session_state.get('_LOAD_MS','?')} ms"
    )
    st.dataframe(df.head(50))

# Carrega automaticamente ao abrir (lazy load)
if "df_demo" not in st.session_state:
    try:
        with st.spinner("Inicializando conteúdo..."):
            st.session_state.df_demo, _ = carregar_base()
    except Exception as e:
        st.stop()

st.subheader("Pré-visualização (20 primeiras linhas)")
st.dataframe(st.session_state.df_demo.head(20))

# Mostrar secrets presentes
with st.expander("🔐 Checagem de secrets"):
    def _has(k):
        try:
            _ = st.secrets[k]
            return True
        except Exception:
            return False
    st.write({
        "GCP_SERVICE_ACCOUNT": _has("GCP_SERVICE_ACCOUNT"),
        "TELEGRAM_TOKEN": _has("TELEGRAM_TOKEN"),
        "TELEGRAM_CHAT_ID": _has("TELEGRAM_CHAT_ID"),
    })

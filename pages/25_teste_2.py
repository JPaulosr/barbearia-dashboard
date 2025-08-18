import time
import pandas as pd
import streamlit as st

# ❗Não importe gspread/gspread_dataframe no topo. Vamos importar dentro da função e capturar erros.
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"

COLS_OFICIAIS = [
    "Data","Serviço","Valor","Conta","Cliente","Combo",
    "Funcionário","Fase","Tipo","Período"
]
COLS_FIADO = ["StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento"]

st.title("🛠️ Utils Notificação — Debug (sem cache/decorators)")

def conectar_sheets_sem_cache():
    try:
        import gspread
        from google.oauth2.service_account import Credentials

        info = st.secrets["GCP_SERVICE_ACCOUNT"]  # vai levantar KeyError se faltar
        scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(info, scopes=scopes)
        client = gspread.authorize(creds)
        return client.open_by_key(SHEET_ID)
    except Exception as e:
        st.error(f"❌ Erro em conectar_sheets: {e}")
        raise

def carregar_base_sem_cache():
    t0 = time.perf_counter()
    try:
        sh = conectar_sheets_sem_cache()
        ws = sh.worksheet(ABA_DADOS)

        # Tenta caminho 1: get_all_records (estável)
        records = ws.get_all_records(numericise_ignore=['all'])
        df = pd.DataFrame(records)

        # Fallback: gspread_dataframe
        if df.empty:
            from gspread_dataframe import get_as_dataframe
            df = get_as_dataframe(ws).dropna(how="all")

        df.columns = [str(c).strip() for c in df.columns]
        for col in [*COLS_OFICIAIS, *COLS_FIADO]:
            if col not in df.columns:
                df[col] = ""

        norm = {"manha":"Manhã","Manha":"Manhã","manha ":"Manhã","tarde":"Tarde","noite":"Noite"}
        df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
        df.loc[~df["Período"].isin(["Manhã","Tarde","Noite"]), "Período"] = ""
        df["Combo"] = df["Combo"].fillna("")

        st.caption(f"⏱️ Carregou em {int((time.perf_counter()-t0)*1000)} ms")
        return df, ws
    except Exception as e:
        st.error(f"❌ Falha em carregar_base: {e}")
        raise

# UI mínima para FORÇAR renderização primeiro
st.write("Clique no botão abaixo para carregar e ver um preview. Se der erro, ele aparece aqui na página.")

if st.button("▶️ Carregar planilha agora"):
    try:
        with st.spinner("Conectando e lendo Google Sheets..."):
            df, ws = carregar_base_sem_cache()
        st.success(f"✅ Linhas: {len(df)} | Colunas: {len(df.columns)}")
        st.dataframe(df.head(20))
    except Exception:
        st.stop()

with st.expander("🔐 Verificação de secrets (presença)"):
    def _has(k):
        try:
            _ = st.secrets[k]; return True
        except Exception:
            return False
    st.write({
        "GCP_SERVICE_ACCOUNT": _has("GCP_SERVICE_ACCOUNT"),
        "TELEGRAM_TOKEN": _has("TELEGRAM_TOKEN"),
        "TELEGRAM_CHAT_ID": _has("TELEGRAM_CHAT_ID"),
    })

st.info("Se esta página aparece mas o botão gera erro, abra os Logs (⋮ → Manage app → Logs) para detalhes (403/404/permissão, etc).")

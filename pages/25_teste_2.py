import os
import time
import json
import pandas as pd
import streamlit as st
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from contextlib import suppress

# ----------------------------
# CONFIG BÁSICA (ajuste se precisar)
# ----------------------------
TZ = "America/Sao_Paulo"
# Essas variáveis precisam existir no seu app:
#   ABA_DADOS: nome da aba, ex.: "Base de Dados"
#   COLS_OFICIAIS: lista de colunas esperadas
#   COLS_FIADO: lista extra usada no seu app
# Certifique-se de defini-las ANTES de chamar carregar_base().

# ----------------------------
# CONEXÃO CACHEADA
# ----------------------------
@st.cache_resource(show_spinner=False)
def conectar_sheets():
    """
    Usa o secret GCP_SERVICE_ACCOUNT (json) OU as variáveis padrão do
    ambiente do Streamlit (credenciais em secrets.toml).
    """
    # 1) Tenta pegar JSON bruto do secret GCP_SERVICE_ACCOUNT
    sa_raw = st.secrets.get("GCP_SERVICE_ACCOUNT", None)
    if isinstance(sa_raw, str):
        # pode chegar escapado; tenta desserializar
        with suppress(Exception):
            sa_raw = json.loads(sa_raw)

    if isinstance(sa_raw, dict):
        info = sa_raw
    else:
        # 2) Monta a partir de st.secrets["GCP_SERVICE_ACCOUNT"] em formato seccionado
        if "GCP_SERVICE_ACCOUNT" in st.secrets and isinstance(st.secrets["GCP_SERVICE_ACCOUNT"], dict):
            info = dict(st.secrets["GCP_SERVICE_ACCOUNT"])
        else:
            raise RuntimeError("Credencial não encontrada. Defina 'GCP_SERVICE_ACCOUNT' em st.secrets.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)

    # Permite usar SHEET_ID direto em env/secrets
    sheet_id = os.environ.get("SHEET_ID") or st.secrets.get("SHEET_ID")
    if not sheet_id:
        raise RuntimeError("SHEET_ID não definido nos secrets/variáveis.")
    sh = gc.open_by_key(sheet_id)
    return sh

# ----------------------------
# LEITURA COM TIMEOUT/RETRY
# ----------------------------
def _try_get_all_records(ws, timeout_s=12):
    """get_all_records com timeout simples."""
    t0 = time.time()
    while True:
        records = ws.get_all_records(numericise_ignore=['all'])
        if records is not None:
            return pd.DataFrame(records)
        if time.time() - t0 > timeout_s:
            raise TimeoutError("get_all_records demorou além do timeout.")
        time.sleep(0.2)

def _fallback_read(ws):
    """Fallback robusto: tenta get_all_values e, se falhar, gspread_dataframe."""
    try:
        values = ws.get_all_values()
        if values and len(values) > 0:
            header = [str(c).strip() for c in values[0]]
            rows = values[1:] if len(values) > 1 else []
            return pd.DataFrame(rows, columns=header)
    except Exception:
        pass
    # Último recurso
    df = get_as_dataframe(ws)
    # remove linhas completamente vazias
    return df.dropna(how="all")

# ----------------------------
# NORMALIZAÇÃO DE COLUNAS
# ----------------------------
def _assegurar_colunas(df: pd.DataFrame, cols_oficiais, cols_fiado):
    for coluna in [*(cols_oficiais or []), *(cols_fiado or [])]:
        if coluna not in df.columns:
            df[coluna] = ""
    return df

def _normalizar_periodo(df: pd.DataFrame):
    if "Período" not in df.columns:
        return df
    norm = {"manha": "Manhã", "Manha": "Manhã", "manha ": "Manhã",
            "tarde": "Tarde", "noite": "Noite"}
    df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
    df.loc[~df["Período"].isin(["Manhã", "Tarde", "Noite"]), "Período"] = ""
    return df

# ----------------------------
# LOADER PRINCIPAL (COM SPINNER)
# ----------------------------
@st.cache_data(ttl=300, show_spinner=False)
def carregar_base_seguro():
    """
    Retorna (df, ws) sem travar a UI.
    """
    t0 = time.perf_counter()

    # Checagem básica para evitar NameError invisível
    missing = []
    for varname in ("ABA_DADOS", "COLS_OFICIAIS", "COLS_FIADO"):
        if varname not in globals():
            missing.append(varname)
    if missing:
        raise RuntimeError(f"Variáveis não definidas: {', '.join(missing)}")

    sh = conectar_sheets()
    ws = sh.worksheet(ABA_DADOS)

    # Tentativa rápida + fallback
    try:
        df = _try_get_all_records(ws, timeout_s=12)
    except Exception:
        df = _fallback_read(ws)

    # Padroniza cabeçalhos
    df.columns = [str(col).strip() for col in df.columns]

    # Garante colunas essenciais
    df = _assegurar_colunas(df, COLS_OFICIAIS, COLS_FIADO)

    # Normalizações
    if "Combo" in df.columns:
        df["Combo"] = df["Combo"].fillna("")
    df = _normalizar_periodo(df)

    st.session_state["_LOAD_MS"] = int((time.perf_counter() - t0) * 1000)
    return df, ws

def carregar_base():
    # wrapper para manter assinatura original
    with st.spinner("Carregando dados da planilha..."):
        try:
            return carregar_base_seguro()
        except Exception as e:
            st.error(f"❌ Falha ao carregar a planilha: {e}")
            st.caption("Dica: verifique SHEET_ID, credenciais GCP_SERVICE_ACCOUNT e o nome da aba ABA_DADOS.")
            st.stop()

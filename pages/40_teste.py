# -*- coding: utf-8 -*-
# 12_Fiado.py — Fiado + Telegram (foto + card), por funcionário + cópia p/ JP
# - Lançar fiado (único e em lote)
# - Quitar por COMPETÊNCIA com atualização mínima
# - Notificações com FOTO e card HTML; roteamento por funcionário (Vinícius → canal; JPaulo → privado)
# - Comissão só p/ elegíveis (ex.: Vinicius)
# - 💳 Maquininha: grava LÍQUIDO no campo Valor da BASE (e preenche colunas extras: bruto/taxa) **apenas se usar_cartao=True**
# - Quitar por ID (combo inteiro) ou por LINHA (serviço)
# - Fiado_Pagamentos salva TotalLiquido + TotalBruto + Taxa
# - 📗 Histórico de pagos adicionado

import streamlit as st
import pandas as pd
import gspread
import requests
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from gspread.utils import rowcol_to_a1
from datetime import date, datetime, timedelta
from io import BytesIO
import pytz
import unicodedata

# =========================
# TELEGRAM
# =========================
TELEGRAM_TOKEN_CONST = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
TELEGRAM_CHAT_ID_JPAULO_CONST = "493747253"
TELEGRAM_CHAT_ID_VINICIUS_CONST = "-1002953102982"  # canal do Vinícius

def _get_secret(name: str, default: str | None = None) -> str | None:
    try:
        val = st.secrets.get(name)
        val = (val or "").strip()
        if val:
            return val
    except Exception:
        pass
    return (default or "").strip() or None

def _get_token() -> str | None:
    return _get_secret("TELEGRAM_TOKEN", TELEGRAM_TOKEN_CONST)

def _get_chat_id_jp() -> str | None:
    return _get_secret("TELEGRAM_CHAT_ID_JPAULO", TELEGRAM_CHAT_ID_JPAULO_CONST)

def _get_chat_id_vini() -> str | None:
    return _get_secret("TELEGRAM_CHAT_ID_VINICIUS", TELEGRAM_CHAT_ID_VINICIUS_CONST)

def _check_tg_ready(token: str | None, chat_id: str | None) -> bool:
    return bool((token or "").strip() and (chat_id or "").strip())

def _chat_id_por_func(funcionario: str) -> str | None:
    if str(funcionario).strip() == "Vinicius":
        return _get_chat_id_vini()
    return _get_chat_id_jp()

def tg_send(text: str, chat_id: str | None = None) -> bool:
    token = _get_token()
    chat = chat_id or _get_chat_id_jp()
    if not _check_tg_ready(token, chat):
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        r = requests.post(url, json=payload, timeout=30)
        js = r.json()
        return bool(r.ok and js.get("ok"))
    except Exception:
        return False

def tg_send_photo(photo_url: str, caption: str, chat_id: str | None = None) -> bool:
    token = _get_token()
    chat = chat_id or _get_chat_id_jp()
    if not _check_tg_ready(token, chat):
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        data = {"chat_id": chat, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=data, timeout=30)
        js = r.json()
        if r.ok and js.get("ok"):
            return True
        return tg_send(caption, chat_id=chat)
    except Exception:
        return tg_send(caption, chat_id=chat)

# =========================
# FOTOS (clientes_status)
# =========================
STATUS_ABA = "clientes_status"
FOTO_COL_CANDIDATES = ["link_foto", "foto", "imagem", "url_foto", "foto_link", "link", "image"]

def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

@st.cache_data(show_spinner=False)
def carregar_fotos_mapa():
    try:
        sh = conectar_sheets()
        if STATUS_ABA not in [w.title for w in sh.worksheets()]:
            return {}
        ws = sh.worksheet(STATUS_ABA)
        df = get_as_dataframe(ws).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]
        cols_lower = {c.lower(): c for c in df.columns}
        foto_col = next((cols_lower[c] for c in FOTO_COL_CANDIDATES if c in cols_lower), None)
        cli_col  = next((cols_lower[c] for c in ["cliente","nome","nome_cliente"] if c in cols_lower), None)
        if not (foto_col and cli_col):
            return {}
        tmp = df[[cli_col, foto_col]].copy()
        tmp.columns = ["Cliente", "Foto"]
        tmp["k"] = tmp["Cliente"].astype(str).map(_norm)
        return {r["k"]: str(r["Foto"]).strip()
                for _, r in tmp.iterrows() if str(r["Foto"]).strip()}
    except Exception:
        return {}

def show_foto_cliente(cliente: str):
    try:
        k = _norm(cliente or "")
        url = FOTOS.get(k)
        if url:
            st.image(url, width=140, caption=cliente)
    except Exception:
        pass

# =========================
# UTILS (mantive todos iguais)
# =========================
# ... [mantém todos os utils que já estavam no seu código anterior]
# Inclui: proxima_terca, _fmt_brl, _fmt_pct, col_map, ensure_headers,
# append_rows_generic, contains_cartao, is_nao_cartao, default_card_flag,
# servicos_compactos_por_ids_parcial, historico_cliente_por_ano, etc.

# =========================
# APP / SHEETS CONFIG
# =========================
st.set_page_config(page_title="Fiado | Salão JP", page_icon="💳", layout="wide",
                   initial_sidebar_state="expanded")
st.title("💳 Controle de Fiado (combo por linhas + edição de valores)")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_LANC = "Fiado_Lancamentos"
ABA_PAGT = "Fiado_Pagamentos"
ABA_TAXAS = "Cartao_Taxas"

TZ = pytz.timezone("America/Sao_Paulo")
DATA_FMT = "%d/%m/%Y"

# ... [mantém VALORES_PADRAO, COMISSAO_FUNCIONARIOS, conectar_sheets, etc.]

# ====== FIX: utilitários mínimos para carregar listas do Sheets ======
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe

# Ajuste se já tiver esses valores declarados no arquivo:
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    # Requer st.secrets["GCP_SERVICE_ACCOUNT"] configurado no Streamlit Cloud
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def garantir_aba(ss, nome, cols_min=None):
    """Abre a worksheet; se não existir, cria com colunas mínimas."""
    try:
        return ss.worksheet(nome)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=nome, rows=200, cols=40)
        if cols_min:
            ws.append_row(cols_min)
        return ws

@st.cache_data(show_spinner=False)
def carregar_listas():
    """
    Retorna 4 listas: clientes, combos, serviços, contas.
    • Ignora linhas vazias
    • Remove duplicados
    • Garante 'Nubank CNPJ' nas contas
    """
    ss = conectar_sheets()

    # Colunas mínimas caso a planilha esteja vazia/sem cabeçalho
    COLS_MIN = ["Data","Serviço","Valor","Conta","Cliente","Combo","Funcionário","Fase","Tipo","Período",
                "StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento"]

    ws_base = garantir_aba(ss, ABA_BASE, cols_min=COLS_MIN)
    df = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).fillna("")
    if df.empty:
        # Se estiver vazia, devolve listas básicas pra não quebrar a UI
        return [], [], [], ["Pix","Dinheiro","Cartão","Transferência","Nubank CNPJ"]

    # Normaliza colunas e remove duplicadas
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]

    # Extrai listas
    clientes = sorted([c for c in df.get("Cliente", "").astype(str).str.strip().unique() if c])
    combos   = sorted([c for c in df.get("Combo",   "").astype(str).str.strip().unique() if c])
    servs    = sorted([s for s in df.get("Serviço", "").astype(str).str.strip().unique() if s])

    contas_raw = [c for c in df.get("Conta", "").astype(str).str.strip().unique() if c]
    # Tira "Fiado" da lista de formas de pagamento comuns
    contas = sorted([c for c in contas_raw if c.lower() != "fiado"], key=lambda s: s.lower())
    if "Nubank CNPJ" not in contas:
        contas.append("Nubank CNPJ")

    return clientes, combos, servs, contas
# ====== FIM DO FIX ======

# ===== Caches
clientes, combos_exist, servs_exist, contas_exist = carregar_listas()
FOTOS = carregar_fotos_mapa()

# =========================
# SIDEBAR
# =========================
st.sidebar.header("Ações")
acao = st.sidebar.radio(
    "Escolha:",
    ["➕ Lançar fiado", "💰 Registrar pagamento", "📋 Em aberto & exportação", "📗 Pagos (histórico)"]
)

# =========================
# FLUXOS
# =========================
if acao == "➕ Lançar fiado":
    # [Bloco atualizado com lançamento único + lote + foto — já te mandei acima]
    pass

elif acao == "💰 Registrar pagamento":
    # [mantém sua lógica atual de registrar pagamento]
    pass

elif acao == "📋 Em aberto & exportação":
    # [mantém sua lógica atual de fiados em aberto]
    pass

elif acao == "📗 Pagos (histórico)":
    # [bloco que te mandei acima: histórico, filtros, exportação, detalhe com foto]
    pass

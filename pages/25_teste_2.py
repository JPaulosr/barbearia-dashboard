# -*- coding: utf-8 -*-
# 11_Adicionar_Atendimento.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from gspread.utils import rowcol_to_a1
from datetime import datetime
import pytz
import unicodedata
import requests
from collections import Counter

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
STATUS_ABA = "clientes_status"
FOTO_COL_CANDIDATES = ["link_foto", "foto", "imagem", "url_foto", "foto_link", "link", "image"]

TZ = "America/Sao_Paulo"
REL_MULT = 1.5
DATA_FMT = "%d/%m/%Y"

COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período"
]
COLS_FIADO = ["StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"]
COLS_PAG_EXTRAS = [
    "ValorBrutoRecebido", "ValorLiquidoRecebido",
    "TaxaCartaoValor", "TaxaCartaoPct",
    "FormaPagDetalhe", "PagamentoID"
]
COLS_CAIXINHAS = ["CaixinhaDia", "CaixinhaFundo"]

# =========================
# UTILS
# =========================
def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def _norm_key(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s).strip()).casefold()

def _cap_first(s: str) -> str:
    return (str(s).strip().lower().capitalize()) if s is not None else ""

def _fmt_brl(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def gerar_pag_id(prefixo="A"):
    return f"{prefixo}-{datetime.now(pytz.timezone(TZ)).strftime('%Y%m%d%H%M%S%f')[:-3]}"

# =========================
# SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    for c in [*COLS_OFICIAIS, *COLS_FIADO, *COLS_PAG_EXTRAS, *COLS_CAIXINHAS]:
        if c not in df.columns:
            df[c] = ""
    return df, aba

def salvar_base(df_final: pd.DataFrame):
    aba = conectar_sheets().worksheet(ABA_DADOS)
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)

# =========================
# FOTOS (status sheet)
# =========================
@st.cache_data(show_spinner=False)
def carregar_fotos_mapa():
    try:
        sh = conectar_sheets()
        if STATUS_ABA not in [w.title for w in sh.worksheets()]:
            return {}
        ws = sh.worksheet(STATUS_ABA)
        df = get_as_dataframe(ws).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        cols_lower = {c.lower(): c for c in df.columns}
        foto_col = next((cols_lower[c] for c in FOTO_COL_CANDIDATES if c in cols_lower), None)
        cli_col = next((cols_lower[c] for c in ["cliente", "nome", "nome_cliente"] if c in cols_lower), None)
        if not (foto_col and cli_col): return {}
        tmp = df[[cli_col, foto_col]].copy()
        tmp.columns = ["Cliente", "Foto"]
        tmp["k"] = tmp["Cliente"].astype(str).map(_norm)
        return {r["k"]: str(r["Foto"]).strip() for _, r in tmp.iterrows() if str(r["Foto"]).strip()}
    except Exception:
        return {}
FOTOS = carregar_fotos_mapa()

# =========================
# TELEGRAM
# =========================
TELEGRAM_TOKEN_CONST = "SEU_TOKEN"
TELEGRAM_CHAT_ID_JPAULO_CONST = "CHAT1"
TELEGRAM_CHAT_ID_VINICIUS_CONST = "CHAT2"

def _get_secret(name: str, default: str | None = None) -> str | None:
    try:
        val = st.secrets.get(name)
        val = (val or "").strip()
        if val:
            return val
    except Exception:
        pass
    return (default or "").strip() or None

def _get_token(): return _get_secret("TELEGRAM_TOKEN", TELEGRAM_TOKEN_CONST)
def _get_chat_id_jp(): return _get_secret("TELEGRAM_CHAT_ID_JPAULO", TELEGRAM_CHAT_ID_JPAULO_CONST)
def _get_chat_id_vini(): return _get_secret("TELEGRAM_CHAT_ID_VINICIUS", TELEGRAM_CHAT_ID_VINICIUS_CONST)

def tg_send(text: str, chat_id: str | None = None):
    token = _get_token()
    chat = chat_id or _get_chat_id_jp()
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat, "text": text, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=30)
    except Exception:
        pass

def tg_send_photo(photo_url: str, caption: str, chat_id: str | None = None):
    token = _get_token()
    chat = chat_id or _get_chat_id_jp()
    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = {"chat_id": chat, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        requests.post(url, data=payload, timeout=30)
    except Exception:
        tg_send(caption, chat_id=chat)

# =========================
# EXTRAS: Caixinha e Cartão
# =========================
def _secao_caixinha(df_all, cliente, data_str):
    df = df_all[
        (df_all["Cliente"].astype(str).str.strip() == cliente) &
        (df_all["Data"].astype(str).str.strip() == data_str)
    ].copy()
    total_dia = pd.to_numeric(df.get("CaixinhaDia", 0), errors="coerce").fillna(0).sum()
    total_fundo = pd.to_numeric(df.get("CaixinhaFundo", 0), errors="coerce").fillna(0).sum()
    if total_dia <= 0 and total_fundo <= 0:
        return ""
    linhas = ["------------------------------", "💝 <b>Caixinha</b>"]
    if total_dia > 0:
        linhas.append(f"Do dia: <b>{_fmt_brl(total_dia)}</b>")
    if total_fundo > 0:
        linhas.append(f"Fundo: <b>{_fmt_brl(total_fundo)}</b>")
    return "\n".join(linhas)

# =========================
# CARD – Mensagem Telegram
# =========================
def make_card_caption_v2(df_all, cliente, data_str, funcionario,
                         servico_label, valor_total, periodo_label,
                         append_sections=None, caixinha_total=0.0):

    valor_total += caixinha_total
    valor_str = _fmt_brl(valor_total)

    base = (
        "📌 <b>Atendimento registrado</b>\n"
        f"👤 Cliente: <b>{cliente}</b>\n"
        f"🗓️ Data: <b>{data_str}</b>\n"
        f"🕒 Período: <b>{periodo_label}</b>\n"
        f"✂️ Serviço: <b>{servico_label}</b>\n"
        f"💰 Valor (inclui caixinha): <b>{valor_str}</b>\n"
        f"👨‍🔧 Atendido por: <b>{funcionario}</b>"
    )

    if append_sections:
        base += "\n\n" + "\n\n".join([s for s in append_sections if s and s.strip()])
    return base

def enviar_card(df_all, cliente, funcionario, data_str, servico=None, valor=None, combo=None):
    if servico is None or valor is None:
        servico_label, valor_total, _, _, periodo_label = "-", 0.0, None, None, "-"
    else:
        is_combo = bool(combo and str(combo).strip())
        eh_combo = is_combo or ("+" in str(servico))
        servico_label = f"{servico} (Combo)" if eh_combo else f"{servico} (Simples)"
        valor_total = float(valor)
        periodo_label = "-"

    sec_caixa = _secao_caixinha(df_all, cliente, data_str)
    caixinha_total = 0.0
    if sec_caixa:
        df = df_all[
            (df_all["Cliente"].astype(str).str.strip() == cliente) &
            (df_all["Data"].astype(str).str.strip() == data_str)
        ]
        caixinha_total = df["CaixinhaDia"].astype(float).sum() + df["CaixinhaFundo"].astype(float).sum()

    extras = []
    if sec_caixa:
        extras.append(sec_caixa)

    caption = make_card_caption_v2(
        df_all, cliente, data_str, funcionario,
        servico_label, valor_total, periodo_label,
        append_sections=extras, caixinha_total=caixinha_total
    )

    foto = FOTOS.get(_norm(cliente))
    destino = _get_chat_id_jp() if funcionario == "JPaulo" else _get_chat_id_vini()
    if foto:
        tg_send_photo(foto, caption, chat_id=destino)
    else:
        tg_send(caption, chat_id=destino)

# =========================
# STREAMLIT UI (simplificado)
# =========================
st.set_page_config(layout="wide")
st.title("📅 Adicionar Atendimento")

st.info("Demo simplificada só com notificação + caixinha incluída.")

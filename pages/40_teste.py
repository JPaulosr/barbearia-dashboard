# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão por DIA + Caixinha (AGORA agrupada por competência)
# - Uma linha por competência (não por dia).
# - Regra: mesmo mês da terça → 1 linha única na terça; outro mês → 1 linha no último dia do mês da competência (ou terça, se usuário escolher).
# - Trava anti-duplicação oficial via coluna RefID.
# - Telegram: Vinícius + JPaulo.
# - Botão 📲 Reenviar resumo.

import streamlit as st
import pandas as pd
import gspread
import hashlib
import re
import requests
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
import sys, importlib, calendar

# --- DEV: limpador de caches e recarga de módulos auxiliares ---
def _dev_clear_everything(mod_prefixes=("utils", "commons", "shared")):
    try: st.cache_data.clear()
    except: pass
    try: st.cache_resource.clear()
    except: pass
    try:
        for name in list(sys.modules):
            if any(name.startswith(pfx) for pfx in mod_prefixes) and sys.modules.get(name):
                importlib.reload(sys.modules[name])
    except: pass

with st.expander("🛠️ Dev • Cache/Módulos (temporário)"):
    if st.button("♻️ Limpar cache + recarregar módulos"):
        _dev_clear_everything()
        st.success("Caches limpos. Clique em Rerun.")

# =============================
# CONFIG
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"
TZ = "America/Sao_Paulo"

# Telegram (fallbacks)
TELEGRAM_TOKEN_FALLBACK = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
TELEGRAM_CHAT_ID_JPAULO_FALLBACK = "493747253"
TELEGRAM_CHAT_ID_VINICIUS_FALLBACK = "-1002953102982"

COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período",
    "StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento",
    "ValorBrutoRecebido", "ValorLiquidoRecebido",
    "TaxaCartaoValor", "TaxaCartaoPct",
    "FormaPagDetalhe", "PagamentoID",
    "CaixinhaDia", "CaixinhaFundo",
]

COLS_DESPESAS_FIX = ["Data", "Prestador", "Descrição", "Valor", "Me Pag:", "RefID"]

PERCENTUAL_PADRAO = 50.0
VALOR_TABELA = {
    "Corte": 25.00, "Barba": 15.00, "Sobrancelha": 7.00,
    "Luzes": 45.00, "Tintura": 20.00, "Alisamento": 40.00,
    "Gel": 10.00, "Pomada": 15.00,
}

# =============================
# CONEXÃO SHEETS
# =============================
@st.cache_resource
def _conn():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    cred = Credentials.from_service_account_info(info, scopes=escopo)
    cli = gspread.authorize(cred)
    return cli.open_by_key(SHEET_ID)

def _ws(title: str):
    sh = _conn()
    try: return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=50)

def _read_df(title: str) -> pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").replace({pd.NA: ""})
    if title == ABA_DADOS:
        for c in COLS_OFICIAIS:
            if c not in df.columns: df[c] = ""
    return df

def _write_df(title: str, df: pd.DataFrame):
    ws = _ws(title)
    ws.clear()
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================
# HELPERS
# =============================
def br_now(): return datetime.now(pytz.timezone(TZ))
def parse_br_date(s: str):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try: return datetime.strptime(s, fmt)
        except: pass
    return None
def to_br_date(dt):
    if dt is None: return ""
    return pd.to_datetime(dt).strftime("%d/%m/%Y")
def competencia_from_data_str(data_servico_str: str) -> str:
    dt = parse_br_date(data_servico_str)
    return dt.strftime("%m/%Y") if dt else ""

def janela_terca_a_segunda(terca_pagto: datetime):
    inicio = terca_pagto - timedelta(days=7)
    fim = inicio + timedelta(days=6)
    return inicio, fim

def garantir_colunas(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df

def s_lower(s: pd.Series): return s.astype(str).str.strip().str.lower()
def _to_float_brl(v) -> float:
    s = str(v).strip()
    if not s: return 0.0
    s = s.replace("R$", "").replace(" ", "")
    s = re.sub(r"\.(?=\d{3}(\D|$))", "", s)
    s = s.replace(",", ".")
    try: return float(s)
    except: return 0.0

def snap_para_preco_cheio(servico: str, valor: float, tol: float, habilitado: bool) -> float:
    if not habilitado: return valor
    cheio = VALOR_TABELA.get((servico or "").strip())
    if isinstance(cheio, (int, float)) and abs(valor - float(cheio)) <= tol:
        return float(cheio)
    return valor

def format_brl(v: float) -> str:
    try: v = float(v)
    except: v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _refid_despesa(data_br: str, prestador: str, descricao: str, valor_float: float, mepag: str) -> str:
    base = f"{data_br.strip()}|{prestador.strip().lower()}|{descricao.strip().lower()}|{valor_float:.2f}|{str(mepag).strip().lower()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def make_refid_atendimento(row: pd.Series) -> str:
    key = "|".join([str(row.get(k, "")).strip() for k in ["Cliente","Data","Serviço","Valor","Funcionário","Combo"]])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

# =============================
# TELEGRAM
# =============================
def _get_token(): return (st.secrets.get("TELEGRAM_TOKEN","") or TELEGRAM_TOKEN_FALLBACK).strip()
def _get_chat_jp(): return (st.secrets.get("TELEGRAM_CHAT_ID_JPAULO","") or TELEGRAM_CHAT_ID_JPAULO_FALLBACK).strip()
def _get_chat_vini(): return (st.secrets.get("TELEGRAM_CHAT_ID_VINICIUS","") or TELEGRAM_CHAT_ID_VINICIUS_FALLBACK).strip()

def tg_send_html(text: str, chat_id: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{_get_token()}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
            timeout=30
        )
        return bool(r.ok and r.json().get("ok"))
    except: return False

# =============================
# RESUMO TELEGRAM
# =============================
def build_text_resumo(period_ini, period_fim,
                      valor_nao_fiado, valor_fiado_liberado, valor_caixinha,
                      total_futuros, df_semana, df_fiados, df_pend,
                      qtd_fiado_pago_hoje=0):
    total_geral = float(valor_nao_fiado) + float(valor_fiado_liberado) + float(valor_caixinha or 0.0)
    linhas = [
        f"💈 <b>Resumo — Vinícius</b>  ({to_br_date(period_ini)} → {to_br_date(period_fim)})",
        f"🧾 NÃO fiado: <b>{format_brl(valor_nao_fiado)}</b>",
        f"🧾 Fiados liberados: <b>{format_brl(valor_fiado_liberado)}</b>",
        f"🎁 Caixinha: <b>{format_brl(valor_caixinha)}</b>",
        f"💵 Total GERAL: <b>{format_brl(total_geral)}</b>",
        f"🕒 Futuro (pendentes): <b>{format_brl(total_futuros)}</b>"
    ]
    return "\n".join(linhas)

# =============================
# UI
# =============================
st.set_page_config(layout="wide")
st.title("💈 Pagamento de Comissão — Vinicius (1 linha por competência)")

# Carrega base
base = _read_df(ABA_DADOS).copy()

# Inputs
colA, colB, colC = st.columns([1,1,1])
with colA:
    hoje = br_now()
    if hoje.weekday() == 1:  # terça
        sugestao_terca = hoje
    else:
        delta = (1 - hoje.weekday()) % 7
        if delta == 0: delta = 7
        sugestao_terca = (hoje + timedelta(days=delta))
    terca_pagto = st.date_input("🗓️ Terça do pagamento", value=sugestao_terca.date())
    terca_pagto = datetime.combine(terca_pagto, datetime.min.time())
with colB:
    perc_padrao = st.number_input("Percentual padrão da comissão (%)", value=PERCENTUAL_PADRAO, step=1.0)
with colC:
    incluir_produtos = st.checkbox("Incluir PRODUTOS?", value=False)

estrategia_cross = st.selectbox(
    "Data p/ fiados quitados em competência anterior",
    ["Último dia da competência", "Data da terça de pagamento"],
    index=0
)

# ... [demais blocos de cálculo iguais ao seu código anterior] ...

# =============================
# 3) Constrói linhas de comissão AGRUPADAS
# =============================
def _last_day_of_comp(comp_str: str) -> str:
    if not comp_str or "/" not in comp_str: return ""
    mm, yyyy = comp_str.split("/")
    y, m = int(yyyy), int(mm)
    last = calendar.monthrange(y, m)[1]
    return f"{last:02d}/{int(mm):02d}/{y}"

# >>> aqui entra o bloco que te passei na mensagem anterior <<<

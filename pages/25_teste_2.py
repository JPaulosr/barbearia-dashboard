# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Pagamento de comissão (linhas por DIA do atendimento)

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
from typing import Optional, List

# =============================
# CONFIG BÁSICA
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"
TZ = "America/Sao_Paulo"

COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período",
    "StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"
]
COLS_DESPESAS_FIX = ["Data", "Prestador", "Descrição", "Valor", "Me Pag:"]
PERCENTUAL_PADRAO = 50.0

VALOR_TABELA = {
    "Corte": 25.00,
    "Barba": 15.00,
    "Sobrancelha": 7.00,
    "Luzes": 45.00,
    "Tintura": 20.00,
    "Alisamento": 40.00,
    "Gel": 10.00,
    "Pomada": 15.00,
}

# =============================
# TELEGRAM (usa secrets ou FALLBACKS)
# =============================
TELEGRAM_TOKEN_FALLBACK = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
CHAT_ID_JP_FALLBACK     = "493747253"
CHAT_ID_VINI_FALLBACK   = "-1002953102982"   # id real do canal Salão JP 🎖 Premiação 🎖

TELEGRAM_TOKEN            = st.secrets.get("TELEGRAM_TOKEN", TELEGRAM_TOKEN_FALLBACK)
TELEGRAM_CHAT_ID_VINICIUS = st.secrets.get("TELEGRAM_CHAT_ID_VINICIUS", CHAT_ID_VINI_FALLBACK)
TELEGRAM_CHAT_ID_JPAULO   = st.secrets.get("TELEGRAM_CHAT_ID_JPAULO", CHAT_ID_JP_FALLBACK)

def _tg_send_text(token: str, chat_id: str, text: str, parse_mode: str = "HTML"):
    if not token or not chat_id:
        return (False, None, "Missing token or chat_id")
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(url,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        ok = (resp.status_code == 200)
        return (ok, resp.status_code, resp.text)
    except Exception as e:
        return (False, None, str(e))

def tg_send_long(token: str, chat_id: str, text: str, parse_mode: str = "HTML", chunk: int = 3800):
    detalhes, ok_all = [], True
    for i in range(0, len(text), chunk):
        part = text[i:i+chunk]
        ok, status, body = _tg_send_text(token, chat_id, part, parse_mode=parse_mode)
        detalhes.append((ok, status, body))
        ok_all = ok_all and ok
    return ok_all, detalhes

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
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=50)

def _read_df(title: str) -> pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all").replace({pd.NA: ""})

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
def to_br_date(dt: datetime): return dt.strftime("%d/%m/%Y")
def competencia_from_data_str(data_servico_str: str) -> str:
    dt = parse_br_date(data_servico_str); return dt.strftime("%m/%Y") if dt else ""
def janela_terca_a_segunda(terca_pagto: datetime):
    inicio = terca_pagto - timedelta(days=7); fim = inicio + timedelta(days=6); return inicio, fim
def make_refid(row: pd.Series) -> str:
    key = "|".join([str(row.get(c, "")).strip() for c in ["Cliente","Data","Serviço","Valor","Funcionário","Combo"]])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
def garantir_colunas(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for c in cols: 
        if c not in df.columns: df[c] = ""
    return df
def s_lower(s): return s.astype(str).str.strip().str.lower()
def is_cartao(conta: str) -> bool:
    return bool(re.search(r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos)", (conta or "").strip().lower()))
def snap_para_preco_cheio(servico: str, valor: float, tol: float, habilitado: bool) -> float:
    if not habilitado: return valor
    cheio = VALOR_TABELA.get((servico or "").strip())
    return float(cheio) if isinstance(cheio,(int,float)) and abs(valor-float(cheio))<=tol else valor
def format_brl(v: float) -> str: return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# =============================
# UI
# =============================
st.set_page_config(layout="wide")
st.title("💈 Pagamento de Comissão — Vinicius (1 linha por DIA do atendimento)")

# ... [MESMO CÓDIGO de leitura de dados, cálculo de semana, fiados, grids etc — igual ao que você já tem] ...

# =============================
# RESUMOS TELEGRAM
# =============================
def _contagem_servicos(df: pd.DataFrame) -> str:
    if df is None or df.empty or "Serviço" not in df.columns: return "—"
    cont = df["Serviço"].astype(str).str.strip().value_counts()
    return ", ".join([f"{s}×{q}" for s,q in cont.items()]) if not cont.empty else "—"

def _somar_base_para_comissao(df: pd.DataFrame) -> float:
    if df is None or df.empty: return 0.0
    col = "Valor (para comissão)" if "Valor (para comissão)" in df.columns else "Valor_base_comissao"
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum()) if col in df.columns else 0.0

def _clientes_unicos(*dfs: pd.DataFrame) -> int:
    vals=[]; [vals.extend(d["Cliente"].astype(str).tolist()) for d in dfs if d is not None and not d.empty and "Cliente" in d.columns]
    return len(pd.Series(vals).dropna().unique())

def _build_resumo_msg_resumido(ini, fim, semana_edit, total_sem, fiados_edit, total_fia, pend_df, total_pend) -> str:
    a = semana_edit if semana_edit is not None else pd.DataFrame()
    b = fiados_edit if fiados_edit is not None else pd.DataFrame()
    juntos = pd.concat([a,b], ignore_index=True) if not a.empty or not b.empty else a
    clientes = _clientes_unicos(semana_edit, fiados_edit)
    servicos_txt = _contagem_servicos(juntos)
    base_total = _somar_base_para_comissao(semana_edit)+_somar_base_para_comissao(fiados_edit)
    com_total = float(total_sem+total_fia)
    linhas=[
        f"<b>💈 Resumo — Vinícius</b>  ({to_br_date(ini)} → {to_br_date(fim)})",
        f"👥 Clientes: <b>{clientes}</b>",
        f"✂️ Serviços: {servicos_txt}",
        f"💵 Base p/ comissão: <b>{format_brl(base_total)}</b>",
        f"🧾 Comissão de hoje: <b>{format_brl(com_total)}</b>",
    ]
    if total_pend>0: linhas.append(f"🕒 Comissão futura (fiados pendentes): <b>{format_brl(total_pend)}</b>")
    return "\n".join(linhas)

# =============================
# BOTÃO TELEGRAM
# =============================
st.divider()
formato_resumo = st.radio("Formato do resumo", ["Resumido","Detalhado"], index=0, horizontal=True)

col_tg1, col_tg2 = st.columns([1,1])
with col_tg1:
    if st.button("📢 Enviar resumo para o Telegram (Vinícius)"):
        pend_ok = fiados_pendentes if 'Valor_base_comissao' in fiados_pendentes.columns else montar_valor_base(fiados_pendentes)
        if formato_resumo=="Resumido":
            msg=_build_resumo_msg_resumido(ini,fim,semana_grid,total_semana,fiados_liberados_grid,total_fiados,pend_ok,total_fiados_pend)
        else:
            msg=_build_resumo_msg(ini,fim,semana_grid,total_semana,fiados_liberados_grid,total_fiados,pend_ok,total_fiados_pend)
        ok_v, det_v = tg_send_long(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID_VINICIUS, msg)
        if ok_v: st.success("Resumo enviado ✅")
        else: st.error(det_v)

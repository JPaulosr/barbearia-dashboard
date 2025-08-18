# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão consolidada (um bloco só, inclui fiados a receber)

import streamlit as st
import pandas as pd
import gspread, re, hashlib
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz

# =============================
# CONFIG
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"
TZ = "America/Sao_Paulo"

COLS_OFICIAIS = [
    "Data","Serviço","Valor","Conta","Cliente","Combo",
    "Funcionário","Fase","Tipo","Período",
    "StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento"
]
COLS_DESPESAS_FIX = ["Data","Prestador","Descrição","Valor","Me Pag:"]

PERCENTUAL_PADRAO = 50.0

VALOR_TABELA = {
    "Corte": 25.00,"Barba": 15.00,"Sobrancelha": 7.00,
    "Luzes": 45.00,"Tintura": 20.00,"Alisamento": 40.00,
    "Gel": 10.00,"Pomada": 15.00,
}

# =============================
# CONEXÃO SHEETS
# =============================
@st.cache_resource
def _conn():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    cred = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(cred).open_by_key(SHEET_ID)

def _ws(title:str):
    sh = _conn()
    try: return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=50)

def _read_df(title:str)->pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how="all").fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _write_df(title:str, df:pd.DataFrame):
    ws = _ws(title); ws.clear()
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================
# HELPERS
# =============================
def br_now(): return datetime.now(pytz.timezone(TZ))
def parse_br_date(s:str):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d"):
        try: return datetime.strptime(s, fmt)
        except: pass
    return None
def to_br_date(dt:datetime): return dt.strftime("%d/%m/%Y")
def competencia_from_data_str(s:str):
    dt = parse_br_date(s);  return dt.strftime("%m/%Y") if dt else ""
def janela_terca_a_segunda(terca:datetime):
    ini = terca - timedelta(days=7); fim = ini + timedelta(days=6); return ini, fim
def make_refid(row:pd.Series)->str:
    key = "|".join([str(row.get(k,"")).strip() for k in ["Cliente","Data","Serviço","Valor","Funcionário","Combo"]])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
def garantir_colunas(df:pd.DataFrame, cols:list[str])->pd.DataFrame:
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df
def is_cartao(conta:str)->bool:
    c = (conta or "").strip().lower()
    return bool(re.search(r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos)", c))

def _money_to_float_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.str.replace(r"[^\d,.\-+]", "", regex=True)
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

# =============================
# UI
# =============================
st.set_page_config(layout="wide")
st.title("💈 Comissão — Vinícius (inclui fiados pendentes)")

base = _read_df(ABA_DADOS)
base = garantir_colunas(base, COLS_OFICIAIS).copy()

# Inputs
colA, colB = st.columns([1,1])
with colA:
    hoje = br_now()
    sugestao_terca = hoje if hoje.weekday()==1 else hoje + timedelta(days=(1 - hoje.weekday()) % 7 or 7)
    terca_pagto = datetime.combine(st.date_input("🗓️ Terça do pagamento", value=sugestao_terca.date()), datetime.min.time())
with colB:
    perc_padrao = st.number_input("Percentual padrão da comissão (%)", value=PERCENTUAL_PADRAO, step=1.0)

descricao_padrao = st.text_input("Descrição (para DESPESAS)", value="Comissão Vinícius")
usar_tabela_cartao = st.checkbox("Usar TABELA quando cartão", value=True)
usar_tabela_quando_valor_zero = st.checkbox("Usar TABELA quando Valor 0/vazio", value=True)

# =============================
# FILTRAGEM
# =============================
dfv = base[base["Funcionário"].astype(str).str.strip()=="Vinicius"].copy()
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}** (terça→segunda)")

mask_semana = (dfv["_dt_serv"].notna()) & (dfv["_dt_serv"]>=ini) & (dfv["_dt_serv"]<=fim)
todos_df = dfv[mask_semana].copy()

# Coluna "Fiado?"
todos_df["Fiado?"] = todos_df["StatusFiado"].astype(str).str.strip().apply(lambda x: "Sim" if x.lower() not in ("","nao") else "Não")

# =============================
# CÁLCULO DE COMISSÃO
# =============================
col_val = "Valor"
todos_df["Valor_num"] = _money_to_float_series(todos_df[col_val])

def _base_valor(row):
    serv = str(row.get("Serviço", "")).strip()
    val  = float(row.get("Valor_num", 0.0))
    if val > 0: return val
    if usar_tabela_quando_valor_zero and serv in VALOR_TABELA:
        return float(VALOR_TABELA[serv])
    if usar_tabela_cartao and is_cartao(row.get("Conta", "")):
        return float(VALOR_TABELA.get(serv, val))
    return val

todos_df["Valor_base_comissao"] = todos_df.apply(_base_valor, axis=1)
todos_df["Competência"] = todos_df["Data"].apply(competencia_from_data_str)
todos_df["% Comissão"] = perc_padrao
todos_df["Comissão (R$)"] = (todos_df["Valor_base_comissao"] * todos_df["% Comissão"] / 100).round(2)

# =============================
# MOSTRAR GRID ÚNICO
# =============================
st.subheader("Comissão desta semana (inclui fiados)")
st.dataframe(
    todos_df[["Data","Cliente","Serviço","Fiado?","Valor_base_comissao","% Comissão","Comissão (R$)"]],
    use_container_width=True
)

total_geral = float(todos_df["Comissão (R$)"].sum())
total_fiados = float(todos_df.loc[todos_df["Fiado?"]=="Sim","Comissão (R$)"].sum())

st.success(f"💵 Total geral: R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
st.info(f"📌 Dentro desse total há R$ {total_fiados:,.2f} de fiados (a pagar quando receber)."
        .replace(",", "X").replace(".", ",").replace("X","."))

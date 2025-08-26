# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão por DIA + Caixinha
# - MESMO mês da terça → 1 linha única (data = terça)
# - OUTRO mês → 1 linha por DIA do atendimento
# - Descrição: "Comissão Vinícius" e "Caixinha Vinícius"
# - Exporta XLS p/ Mobills com valores NEGATIVOS

import streamlit as st
import pandas as pd
import gspread
import hashlib, re, requests
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
from io import BytesIO

# =============================
# CONFIG
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"
TZ = "America/Sao_Paulo"

COLS_DESPESAS_FIX = ["Data","Prestador","Descrição","Valor","Me Pag:","TerçaPagto","RefID"]

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
    escopo = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
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
    df = df.dropna(how="all").replace({pd.NA: ""})
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
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d"):
        try: return datetime.strptime(s, fmt)
        except: pass
    return None

def to_br_date(dt):
    if dt is None: return ""
    return pd.to_datetime(dt).strftime("%d/%m/%Y")

def competencia_from_dt(dt: datetime) -> str:
    return dt.strftime("%m/%Y") if isinstance(dt, datetime) else ""

def _to_float_brl(v) -> float:
    s = str(v).strip().replace("R$","").replace(" ","").replace(",",".")
    try: return float(s)
    except: return 0.0

def snap_para_preco_cheio(servico: str, valor: float, tol: float, habilitado: bool) -> float:
    if not habilitado: return valor
    cheio = VALOR_TABELA.get((servico or "").strip())
    if isinstance(cheio,(int,float)) and abs(valor - float(cheio)) <= tol:
        return float(cheio)
    return valor

def format_brl(v: float) -> str:
    return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

def _refid_despesa(data_br: str, prestador: str, descricao: str, valor_float: float, mepag: str) -> str:
    base = f"{data_br.strip()}|{prestador.strip().lower()}|{descricao.strip().lower()}|{valor_float:.2f}|{str(mepag).strip().lower()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

# =============================
# VALOR BASE P/ COMISSÃO
# =============================
def montar_valor_base(df: pd.DataFrame, tol_reais=2.0, arred_cheio=True) -> pd.DataFrame:
    if df.empty:
        return df.assign(Valor_num=[], Competência=[], Valor_base_comissao=[])
    df = df.copy()
    df["_dt"] = df["Data"].apply(parse_br_date)
    df["Valor_num"] = pd.to_numeric(df["Valor"].apply(_to_float_brl), errors="coerce").fillna(0.0)

    def _base_valor(row):
        return snap_para_preco_cheio(str(row.get("Serviço","")).strip(),
                                     float(row.get("Valor_num",0.0)),
                                     tol_reais, arred_cheio)
    df["Valor_base_comissao"] = df.apply(_base_valor, axis=1)
    df["Competência"] = df["_dt"].apply(competencia_from_dt)
    return df

# =============================
# EXEMPLO DE CONSOLIDAÇÃO
# =============================
def consolidar_pagamentos(pagos: pd.DataFrame, terca_pagto: datetime,
                          descricao_padrao: str, meio_pag: str):
    linhas = []
    pagos["_dt"] = pagos["Data"].apply(parse_br_date)

    comp_pagto_mes = terca_pagto.month
    comp_pagto_ano = terca_pagto.year

    mesmo_mes_mask = pagos["_dt"].apply(
        lambda d: isinstance(d, datetime) and d.month == comp_pagto_mes and d.year == comp_pagto_ano
    )
    mesmos_mes = pagos[mesmo_mes_mask].copy()
    outros_mes = pagos[~mesmo_mes_mask].copy()

    # OUTRO MÊS → por DIA
    if not outros_mes.empty:
        por_dia = outros_mes.groupby(["Data"], dropna=False)["ComissaoValor"].sum().reset_index()
        for _, row in por_dia.iterrows():
            data_serv = str(row["Data"]).strip()
            valf = float(row["ComissaoValor"])
            valor_txt = f'R$ {valf:.2f}'.replace(".",",")
            refid = _refid_despesa(data_serv, "Vinicius", descricao_padrao, valf, meio_pag)
            linhas.append({
                "Data": data_serv,
                "Prestador": "Vinicius",
                "Descrição": descricao_padrao,
                "Valor": valor_txt,
                "Me Pag:": meio_pag,
                "TerçaPagto": to_br_date(terca_pagto),
                "RefID": refid
            })

    # MESMO MÊS → 1 linha
    if not mesmos_mes.empty:
        total_mesmo_mes = float(pd.to_numeric(mesmos_mes["ComissaoValor"], errors="coerce").fillna(0.0).sum())
        if total_mesmo_mes > 0:
            valor_txt = f'R$ {total_mesmo_mes:.2f}'.replace(".",",")
            data_da_linha = to_br_date(terca_pagto)
            refid = _refid_despesa(data_da_linha, "Vinicius", descricao_padrao, total_mesmo_mes, meio_pag)
            linhas.append({
                "Data": data_da_linha,
                "Prestador": "Vinicius",
                "Descrição": descricao_padrao,
                "Valor": valor_txt,
                "Me Pag:": meio_pag,
                "TerçaPagto": to_br_date(terca_pagto),
                "RefID": refid
            })
    return linhas

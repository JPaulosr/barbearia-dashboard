# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão (agrupado por competência) + Caixinha + Export p/ Mobills

import io
import re
import sys
import pytz
import json
import hashlib
import importlib
import requests
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials

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
    "Data","Serviço","Valor","Conta","Cliente","Combo",
    "Funcionário","Fase","Tipo","Período",
    "StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento",
    "ValorBrutoRecebido","ValorLiquidoRecebido",
    "TaxaCartaoValor","TaxaCartaoPct",
    "FormaPagDetalhe","PagamentoID",
    "CaixinhaDia","CaixinhaFundo",
]
COLS_DESPESAS_FIX = ["Data","Prestador","Descrição","Valor","Me Pag:","RefID"]

PERCENTUAL_PADRAO = 50.0
VALOR_TABELA = {
    "Corte":25.00,"Barba":15.00,"Sobrancelha":7.00,
    "Luzes":45.00,"Tintura":20.00,"Alisamento":40.00,
    "Gel":10.00,"Pomada":15.00,
}

# =============================
# DEV – Cache/Módulos
# =============================
def _dev_clear_everything(mod_prefixes=("utils","commons","shared")):
    try: st.cache_data.clear()
    except: pass
    try: st.cache_resource.clear()
    except: pass
    try:
        for name in list(sys.modules):
            if any(name.startswith(pfx) for pfx in mod_prefixes) and sys.modules.get(name):
                importlib.reload(sys.modules[name])
    except: pass


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

def _ws(title:str):
    sh = _conn()
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=50)

def _read_df(title:str)->pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").replace({pd.NA:""})
    if title == ABA_DADOS:
        for c in COLS_OFICIAIS:
            if c not in df.columns: df[c] = ""
    return df

def _write_df(title:str, df:pd.DataFrame):
    ws = _ws(title)
    ws.clear()
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

def to_br_date(dt):
    if dt is None or (hasattr(dt,"tz_localize") and pd.isna(dt)): return ""
    return pd.to_datetime(dt).strftime("%d/%m/%Y")

def competencia_from_data_str(s:str)->str:
    dt = parse_br_date(s)
    return dt.strftime("%m/%Y") if dt else ""

def janela_terca_a_segunda(terca_pagto:datetime):
    inicio = terca_pagto - timedelta(days=7)
    fim = inicio + timedelta(days=6)
    return inicio, fim

def garantir_colunas(df:pd.DataFrame, cols:list[str])->pd.DataFrame:
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df

def s_lower(s:pd.Series): return s.astype(str).str.strip().str.lower()

def _to_float_brl(v)->float:
    s = str(v).strip()
    if not s: return 0.0
    s = s.replace("R$","").replace(" ","")
    s = re.sub(r"\.(?=\d{3}(\D|$))","",s)
    s = s.replace(",",".")
    try: return float(s)
    except: return 0.0

def snap_para_preco_cheio(servico:str, valor:float, tol:float, habilitado:bool)->float:
    if not habilitado: return valor
    cheio = VALOR_TABELA.get((servico or "").strip())
    if isinstance(cheio,(int,float)) and abs(valor - float(cheio)) <= tol:
        return float(cheio)
    return valor

def format_brl(v:float)->str:
    try: v = float(v)
    except: v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

def _refid_despesa(data_br:str, prestador:str, descricao:str, valor_float:float, mepag:str)->str:
    base = f"{data_br.strip()}|{prestador.strip().lower()}|{descricao.strip().lower()}|{valor_float:.2f}|{str(mepag).strip().lower()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def make_refid_atendimento(row:pd.Series)->str:
    key = "|".join([str(row.get(k,"")).strip() for k in ["Cliente","Data","Serviço","Valor","Funcionário","Combo"]])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

# --- Normalização de nomes de serviço para evitar duplicidades ---
def normalizar_servico(s: str) -> str:
    s0 = (s or "").strip().lower()
    mapa = {
        "sobrancelhas": "Sobrancelha",
        "sobrancelha": "Sobrancelha",
        "luz": "Luzes",
        "luzes": "Luzes",
        "pezinho": "Pezinho",
        "barba": "Barba",
        "corte": "Corte",
        "alisamento": "Alisamento",
        "tintura": "Tintura",
        "gel": "Gel",
        "pomada": "Pomada",
        "caixinha": "Caixinha",
    }
    return mapa.get(s0, s.strip() if s else "")

# =============================
# TELEGRAM
# =============================
def _get_token(): return (st.secrets.get("TELEGRAM_TOKEN","") or TELEGRAM_TOKEN_FALLBACK).strip()
def _get_chat_jp(): return (st.secrets.get("TELEGRAM_CHAT_ID_JPAULO","") or TELEGRAM_CHAT_ID_JPAULO_FALLBACK).strip()
def _get_chat_vini(): return (st.secrets.get("TELEGRAM_CHAT_ID_VINICIUS","") or TELEGRAM_CHAT_ID_VINICIUS_FALLBACK).strip()

def tg_send_html(text:str, chat_id:str)->bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{_get_token()}/sendMessage",
            json={"chat_id":chat_id,"text":text,"parse_mode":"HTML","disable_web_page_preview":True},
            timeout=30
        )
        return bool(r.ok and r.json().get("ok"))
    except: return False

# =============================
# RESUMO (Telegram) — usando GRIDS
# =============================
def build_text_resumo(period_ini, period_fim,
                      valor_nao_fiado, valor_fiado_liberado, valor_caixinha,
                      total_futuros,
                      df_semana=None, df_fiados=None, df_pend=None,
                      qtd_fiado_pago_hoje=0,
                      df_semana_grid=None, df_fiados_grid=None):
    """
    Se df_semana_grid / df_fiados_grid forem passados, o resumo usa esses
    (já filtrados por 'ja_pagos') para contar Clientes e Serviços.
    """
    # 1) Fonte de dados para o que será pago hoje
    fontes_pagaveis = []
    if df_semana_grid is not None and not df_semana_grid.empty:
        fontes_pagaveis.append(df_semana_grid)
    if df_fiados_grid is not None and not df_fiados_grid.empty:
        fontes_pagaveis.append(df_fiados_grid)

    if fontes_pagaveis:
        df_all = pd.concat(fontes_pagaveis, ignore_index=True)
    else:
        # fallback – NÃO recomendado, mas mantém compatibilidade
        cand = [d for d in [df_semana, df_fiados] if d is not None and not getattr(d, "empty", True)]
        df_all = pd.concat(cand, ignore_index=True) if cand else pd.DataFrame()

    # 2) Contagens
    clientes = 0
    servs = {}
    if not df_all.empty:
        col_cli = "Cliente" if "Cliente" in df_all.columns else df_all.columns[df_all.columns.str.lower().str.contains("cliente")][0]
        col_srv = "Serviço" if "Serviço" in df_all.columns else df_all.columns[df_all.columns.str.lower().str.contains("serv")][0]

        # normaliza clientes e serviços
        clientes = df_all[col_cli].astype(str).str.strip().str.lower().nunique()
        srv_norm = df_all[col_srv].astype(str).map(normalizar_servico)
        servs = srv_norm.replace("", pd.NA).dropna().value_counts().to_dict()

    serv_lin = ", ".join([f"{k}×{v}" for k, v in servs.items()]) if servs else "—"

    # 3) Pendências
    qtd_pend = int(len(df_pend)) if df_pend is not None else 0
    clientes_pend = (df_pend["Cliente"].astype(str).str.strip().str.lower().nunique()
                     if df_pend is not None and not df_pend.empty else 0)
    dt_min = to_br_date(pd.to_datetime(df_pend["_dt_serv"], errors="coerce").min()) \
        if df_pend is not None and "_dt_serv" in df_pend.columns and not df_pend.empty else "—"

    total_geral = float(valor_nao_fiado) + float(valor_fiado_liberado) + float(valor_caixinha or 0.0)

    linhas = [
        f"💈 <b>Resumo — Vinícius</b>  ({to_br_date(period_ini)} → {to_br_date(period_fim)})",
        f"👥 Clientes: <b>{clientes}</b>",
        f"✂️ Serviços: <b>{serv_lin}</b>",
        f"🧾 Nesta terça — <b>NÃO fiado</b>: <b>{format_brl(valor_nao_fiado)}</b>",
        f"🧾 Nesta terça — <b>fiados liberados</b>: <b>{format_brl(valor_fiado_liberado)}</b>",
    ]
    if valor_caixinha and float(valor_caixinha) > 0:
        linhas.append(f"🎁 Caixinha de hoje: <b>{format_brl(valor_caixinha)}</b>")
    if qtd_fiado_pago_hoje > 0:
        linhas.append(f"🏦 Fiado pago hoje: <i>{qtd_fiado_pago_hoje} item(ns)</i>")
    linhas.append(f"💵 <b>Total GERAL pago hoje</b>: <b>{format_brl(total_geral)}</b>")
    linhas.append(f"🕒 Comissão futura (fiados pendentes): <b>{format_brl(total_futuros)}</b>")
    if qtd_pend > 0:
        linhas.append(f"   • {qtd_pend} itens • {clientes_pend} clientes • mais antigo: {dt_min}")
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

col_r1, col_r2 = st.columns([2,1])
with col_r1:
    arred_cheio = st.checkbox(
        "Arredondar para preço cheio de TABELA (tolerância abaixo)",
        value=True,
        help="Ex.: 23,00 / 24,75 / 25,10 → 25,00 (se dentro da tolerância)."
    )
with col_r2:
    tol_reais = st.number_input("Tolerância (R$)", value=1.70, step=0.50, min_value=0.0)

# ⚙️ Caixinha & Telegram
st.markdown("### 🎁 Caixinha & 📲 Telegram")
pagar_caixinha = st.checkbox("Pagar caixinha nesta terça (não lança em Despesas)", value=True)
meio_pag = st.selectbox("Meio de pagamento (para DESPESAS — comissão)", ["Dinheiro","Pix","Cartão","Transferência"], index=0)
descricao_padrao = st.text_input("Descrição (para DESPESAS — comissão)", value="Comissão Vinícius")
enviar_tg = st.checkbox("Enviar resumo no Telegram ao registrar", value=True)
dest_vini = st.checkbox("Enviar para canal do Vinícius", value=True)
dest_jp = st.checkbox("Enviar cópia para JPaulo (privado)", value=True)

# ✅ Reprocessar cache (não interfere na trava de Despesas)
reprocessar_terca = st.checkbox("Reprocessar esta terça (regravar cache de comissão)", value=False)

# ============ Pré-filtros da comissão ============
dfv = base[s_lower(base["Funcionário"]) == "vinicius"].copy()
if not incluir_produtos:
    dfv = dfv[s_lower(dfv["Tipo"]) == "serviço"]

# Remover 'caixinha' da comissão
mask_caixinha_lanc = (
    (s_lower(dfv["Conta"]) == "caixinha") |
    (s_lower(dfv["Tipo"]) == "caixinha") |
    (s_lower(dfv["Serviço"]) == "caixinha")
)
dfv = dfv[~mask_caixinha_lanc].copy()

# Datas auxiliares
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)
dfv["_dt_pagto"] = dfv["DataPagamento"].apply(parse_br_date)

# Janela terça→segunda anterior
ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}** (terça→segunda)")

# -------- Caixinha (somatório por janela, apenas para mostrar) --------
base["_dt_serv"] = base["Data"].apply(parse_br_date)
mask_vini = s_lower(base["Funcionário"]) == "vinicius"
mask_janela = base["_dt_serv"].notna() & (base["_dt_serv"] >= ini) & (base["_dt_serv"] <= fim)
base_jan_vini = base[mask_vini & mask_janela].copy()

def _num(v): return _to_float_brl(v)

base_jan_vini["CaixinhaDia_num"] = base_jan_vini["CaixinhaDia"].apply(_num)
base_jan_vini["CaixinhaFundo_num"] = base_jan_vini["CaixinhaFundo"].apply(_num)
mask_caixinha_rows_all = (
    (s_lower(base_jan_vini["Conta"]) == "caixinha") |
    (s_lower(base_jan_vini["Tipo"]) == "caixinha") |
    (s_lower(base_jan_vini["Serviço"]) == "caixinha")
)
base_jan_vini["CaixinhaRow_num"] = 0.0
if mask_caixinha_rows_all.any():
    base_jan_vini.loc[mask_caixinha_rows_all, "CaixinhaRow_num"] = base_jan_vini.loc[mask_caixinha_rows_all, "Valor"].apply(_num)

total_cx_dia_cols = float(base_jan_vini["CaixinhaDia_num"].sum())
total_cx_fundo_cols = float(base_jan_vini["CaixinhaFundo_num"].sum())
total_cx_rows = float(base_jan_vini["CaixinhaRow_num"].sum())
total_caixinha = total_cx_dia_cols + total_cx_fundo_cols + total_cx_rows

cxa, cxb, cxc = st.columns(3)
cxa.metric("🎁 Caixinha do Dia (janela)", format_brl(total_cx_dia_cols))
cxb.metric("🎁 Caixinha do Fundo (janela)", format_brl(total_cx_fundo_cols))
cxc.metric("🎁 Caixinha total (janela)", format_brl(total_caixinha))

# -------- Contadores/debug --------
total_linhas_vini = len(dfv)
na_janela = dfv[(dfv["_dt_serv"].notna()) & (dfv["_dt_serv"] >= ini) & (dfv["_dt_serv"] <= fim)]
nao_fiado = na_janela[(s_lower(na_janela["StatusFiado"]) == "") | (s_lower(na_janela["StatusFiado"]) == "nao")]
fiado_all = dfv[(s_lower(dfv["StatusFiado"]) != "") | (s_lower(dfv["IDLancFiado"]) != "")]
fiados_ok = fiado_all[(fiado_all["_dt_pagto"].notna()) & (fiado_all["_dt_pagto"] <= terca_pagto)]
fiados_pend_all = fiado_all[(fiado_all["_dt_pagto"].isna()) | (fiado_all["_dt_pagto"] > terca_pagto)]

st.caption(
    f"Linhas do Vinicius (sem 'caixinha' p/ comissão): {total_linhas_vini} | "
    f"Na janela (não fiado): {len(nao_fiado)} | "
    f"Fiados liberados: {len(fiados_ok)} | "
    f"Fiados pendentes: {len(fiados_pend_all)}"
)

# 1) Semana não fiado
mask_semana = (
    (dfv["_dt_serv"].notna()) &
    (dfv["_dt_serv"] >= ini) &
    (dfv["_dt_serv"] <= fim) &
    ((s_lower(dfv["StatusFiado"]) == "") | (s_lower(dfv["StatusFiado"]) == "nao"))
)
semana_df = dfv[mask_semana].copy()

# 2) Fiados liberados (pago até a terça)
fiados_liberados = fiado_all[(fiado_all["_dt_pagto"].notna()) & (fiado_all["_dt_pagto"] <= terca_pagto)].copy()

# 3) Fiados pendentes (ainda não pagos)
fiados_pendentes = fiado_all[(fiado_all["_dt_pagto"].isna()) | (fiado_all["_dt_pagto"] > terca_pagto)].copy()
if fiados_pendentes.empty:
    fiados_pendentes = pd.DataFrame(columns=["Data","Cliente","Serviço","_dt_serv"])
else:
    if "_dt_serv" not in fiados_pendentes.columns:
        fiados_pendentes["_dt_serv"] = fiados_pendentes["Data"].apply(parse_br_date)

# ---- valor base p/ comissão (apenas arredondamento por tolerância)
def montar_valor_base(df:pd.DataFrame)->pd.DataFrame:
    if df.empty:
        return df.assign(Valor_num=[], Competência=[], Valor_base_comissao=[])
    df = df.copy()
    df["Valor_num"] = pd.to_numeric(df["Valor"].apply(_to_float_brl), errors="coerce").fillna(0.0)
    df["Competência"] = df["Data"].apply(competencia_from_data_str)
    def _base_valor(row):
        serv = str(row.get("Serviço","")).strip()
        bruto = float(row.get("Valor_num",0.0))
        return snap_para_preco_cheio(serv, bruto, tol_reais, arred_cheio)
    df["Valor_base_comissao"] = df.apply(_base_valor, axis=1)
    return df

# Totais de fiados pendentes (preview)
_futuros_mb = montar_valor_base(fiados_pendentes).copy()
_futuros_mb["% Comissão"] = float(perc_padrao)
_futuros_mb["Comissão (R$)"] = (
    pd.to_numeric(_futuros_mb["Valor_base_comissao"], errors="coerce").fillna(0.0) * float(perc_padrao) / 100.0
).round(2)
total_fiados_pend = float(_futuros_mb["Comissão (R$)"].sum())
qtd_fiados_pend = int(len(fiados_pendentes))
clientes_fiados_pend = (
    fiados_pendentes["Cliente"].astype(str).str.strip().str.lower().nunique()
    if not fiados_pendentes.empty else 0
)
_dt_min_pend = pd.to_datetime(fiados_pendentes["_dt_serv"], errors="coerce").min() if not fiados_pendentes.empty else None
_dt_max_pend = pd.to_datetime(fiados_pendentes["_dt_serv"], errors="coerce").max() if not fiados_pendentes.empty else None
min_str = to_br_date(_dt_min_pend) if pd.notna(_dt_min_pend) else "—"
max_str = to_br_date(_dt_max_pend) if pd.notna(_dt_max_pend) else "—"

# ------- Cache histórico -------
cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID","PagoEm","TerçaPagamento","ValorComissao","Competencia","Observacao"]
cache = garantir_colunas(cache, cache_cols)
terca_str = to_br_date(terca_pagto)
ja_pagos = set(cache["RefID"].astype(str).tolist()) if not reprocessar_terca else set(cache[cache["TerçaPagamento"] != terca_str]["RefID"].astype(str).tolist())

# ------- GRADES EDITÁVEIS -------
def preparar_grid(df:pd.DataFrame, titulo:str, key_prefix:str):
    if df.empty:
        st.warning(f"Sem itens em **{titulo}**.")
        return pd.DataFrame(), 0.0
    df = df.copy()
    df["RefID"] = df.apply(make_refid_atendimento, axis=1)
    df = df[~df["RefID"].isin(ja_pagos)]
    if df.empty:
        st.info(f"Todos os itens de **{titulo}** já foram pagos.")
        return pd.DataFrame(), 0.0

    df = montar_valor_base(df)

    st.subheader(titulo)
    st.caption("Edite a % de comissão por linha, se precisar.")

    ed_cols = ["Data","Cliente","Serviço","Valor_base_comissao","Competência","RefID"]
    ed = df[ed_cols].rename(columns={"Valor_base_comissao":"Valor (para comissão)"})
    ed["% Comissão"] = float(perc_padrao)
    ed["Comissão (R$)"] = (
        pd.to_numeric(ed["Valor (para comissão)"], errors="coerce").fillna(0.0) *
        pd.to_numeric(ed["% Comissão"], errors="coerce").fillna(0.0) / 100.0
    ).round(2)
    ed = ed.reset_index(drop=True)

    edited = st.data_editor(
        ed, key=f"editor_{key_prefix}", num_rows="fixed",
        column_config={
            "Valor (para comissão)": st.column_config.NumberColumn(format="R$ %.2f"),
            "% Comissão": st.column_config.NumberColumn(format="%.1f %%", min_value=0.0, max_value=100.0, step=0.5),
            "Comissão (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        }
    )

    total = float(pd.to_numeric(edited["Comissão (R$)"], errors="coerce").fillna(0.0).sum())
    merged = df.merge(edited[["RefID","% Comissão","Comissão (R$)"]], on="RefID", how="left")
    merged["ComissaoValor"] = pd.to_numeric(merged["Comissão (R$)"], errors="coerce").fillna(0.0)

    st.success(f"Total de comissão em **{titulo}**: {format_brl(total)}")
    return merged, total

semana_grid, total_semana = preparar_grid(semana_df, "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_liberados_grid, total_fiados = preparar_grid(fiados_liberados, "Fiados liberados (pagos até a terça)", "fiados_liberados")

# NOVO: quantidade de itens de fiado pagos hoje (apenas informativo)
qtd_fiados_hoje = 0
if fiados_liberados_grid is not None and not fiados_liberados_grid.empty:
    qtd_fiados_hoje = int(len(fiados_liberados_grid))

# ------- TABELA — FIADOS A RECEBER -------
st.subheader("📌 Fiados a receber (histórico — ainda NÃO pagos)")
if _futuros_mb.empty:
    st.info("Nenhum fiado pendente no momento.")
else:
    vis = _futuros_mb[["Data","Cliente","Serviço","Valor_num","Valor_base_comissao","% Comissão","Comissão (R$)"]].rename(
        columns={"Valor_num":"Valor original","Valor_base_comissao":"Valor (para comissão)"}
    )
    st.dataframe(vis.sort_values(by=["Data","Cliente"]).reset_index(drop=True), use_container_width=True)
    st.warning(f"Comissão futura (quando pagarem): **{format_brl(total_fiados_pend)}**")

# ------- RESUMO DE MÉTRICAS -------
total_comissao_hoje = float(total_semana + total_fiados)
total_geral_hoje = float(total_comissao_hoje + (total_caixinha if pagar_caixinha else 0.0))

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1: st.metric("Nesta terça — NÃO fiado", format_brl(total_semana))
with col_m2: st.metric("Nesta terça — fiados liberados (a pagar)", format_brl(total_fiados))
with col_m3: st.metric("Total desta terça", format_brl(total_comissao_hoje))
with col_m4: st.metric("Fiados pendentes (futuro)", format_brl(total_fiados_pend), delta=f"{qtd_fiados_pend} itens / {clientes_fiados_pend} clientes")

st.caption(f"📌 Fiados pendentes: {qtd_fiados_pend} itens, {clientes_fiados_pend} clientes; mais antigo: {min_str}; mais recente: {max_str}.")
st.subheader("💵 Total GERAL a pagar nesta terça")
st.success(f"**{format_brl(total_geral_hoje)}**  "
           f"{'(inclui caixinha)' if pagar_caixinha and total_caixinha>0 else '(sem caixinha)'}")

# =============================
# Funções de agrupamento por competência
# =============================
def _last_day_of_competencia(comp_str:str)->datetime:
    try:
        mes, ano = comp_str.split("/")
        mes = int(mes); ano = int(ano)
        if mes == 12:
            prox = datetime(ano + 1, 1, 1)
        else:
            prox = datetime(ano, mes + 1, 1)
        return prox - timedelta(days=1)
    except Exception:
        return terca_pagto

def _linhas_comissao_agrupadas(semana_grid, fiados_liberados_grid, meio_pag, descricao_padrao, terca_pagto):
    """Retorna lista de dicionários (linhas de Despesas) e também dataframe p/ export."""
    pagaveis = []
    for df_part in [semana_grid, fiados_liberados_grid]:
        if df_part is None or df_part.empty: continue
        pagaveis.append(df_part[["Data","Competência","ComissaoValor"]].copy())

    linhas = []
    export_rows = []
    if pagaveis:
        pagos = pd.concat(pagaveis, ignore_index=True)
        pagos["ComissaoValor"] = pd.to_numeric(pagos["ComissaoValor"], errors="coerce").fillna(0.0)

        comp_terca = terca_pagto.strftime("%m/%Y")

        # Competências anteriores → último dia do mês da competência
        outros = pagos[pagos["Competência"] != comp_terca]
        if not outros.empty:
            por_comp_anteriores = outros.groupby("Competência", dropna=False)["ComissaoValor"].sum().reset_index()
            for _, row in por_comp_anteriores.iterrows():
                comp = str(row["Competência"]).strip()
                valf = float(row["ComissaoValor"])
                if valf <= 0: continue
                dt_reg = _last_day_of_competencia(comp)
                data_br = to_br_date(dt_reg)
                valor_txt = f'R$ {valf:.2f}'.replace(".", ",")
                desc_txt  = f"{descricao_padrao} — Comp {comp} — Pago em {to_br_date(terca_pagto)}"
                refid     = _refid_despesa(data_br, "Vinicius", desc_txt, valf, meio_pag)
                linhas.append({
                    "Data": data_br, "Prestador":"Vinicius", "Descrição":desc_txt,
                    "Valor": valor_txt, "Me Pag:": meio_pag, "RefID": refid
                })
                export_rows.append({
                    "Data": data_br, "Descrição": desc_txt, "Valor": -round(valf,2),
                    "Categoria":"Comissão", "Conta": meio_pag, "Observação": desc_txt
                })

        # Competência da terça → data = própria terça
        atuais = pagos[pagos["Competência"] == comp_terca]
        total_atuais = float(atuais["ComissaoValor"].sum()) if not atuais.empty else 0.0
        if total_atuais > 0:
            data_br = to_br_date(terca_pagto)
            valor_txt = f'R$ {total_atuais:.2f}'.replace(".", ",")
            desc_txt  = f"{descricao_padrao} — Comp {comp_terca} — Pago em {to_br_date(terca_pagto)}"
            refid     = _refid_despesa(data_br, "Vinicius", desc_txt, total_atuais, meio_pag)
            linhas.append({
                "Data": data_br, "Prestador":"Vinicius", "Descrição":desc_txt,
                "Valor": valor_txt, "Me Pag:": meio_pag, "RefID": refid
            })
            export_rows.append({
                "Data": data_br, "Descrição": desc_txt, "Valor": -round(total_atuais,2),
                "Categoria":"Comissão", "Conta": meio_pag, "Observação": desc_txt
            })

    export_df = pd.DataFrame(export_rows, columns=["Data","Descrição","Valor","Categoria","Conta","Observação"])
    return linhas, export_df

# =============================
# 📲 Botão REENVIAR RESUMO (sem gravar)
# =============================
if st.button("📲 Reenviar resumo (sem gravar)"):
    texto = build_text_resumo(
        period_ini=ini, period_fim=fim,
        valor_nao_fiado=float(total_semana),
        valor_fiado_liberado=float(total_fiados),
        valor_caixinha=float(total_caixinha if pagar_caixinha else 0.0),
        total_futuros=float(total_fiados_pend),
        df_semana=semana_df, df_fiados=fiados_liberados, df_pend=fiados_pendentes,
        qtd_fiado_pago_hoje=int(qtd_fiados_hoje),
        df_semana_grid=semana_grid,                 # << usa GRID
        df_fiados_grid=fiados_liberados_grid        # << usa GRID
    )
    enviados = []
    if dest_vini: enviados.append(("Vinícius", tg_send_html(texto, _get_chat_vini())))
    if dest_jp:   enviados.append(("JPaulo",   tg_send_html(texto, _get_chat_jp())))
    if not enviados:
        st.info("Marque ao menos um destino (Vinícius/JPaulo) para reenviar.")
    else:
        ok_total = all(ok for _, ok in enviados)
        st.success("Resumo reenviado com sucesso ✅" if ok_total else
                   f"Resumo reenviado, mas houve falha em: {', '.join([n for n, ok in enviados if not ok])}")

# =============================
# ✅ CONFIRMAR E GRAVAR
# =============================
if st.button("✅ Registrar comissão (1 linha por competência) e marcar itens como pagos"):
    if (semana_grid is None or semana_grid.empty) and (fiados_liberados_grid is None or fiados_liberados_grid.empty):
        st.warning("Não há itens para pagar.")
    else:
        # 1) Atualiza cache histórico
        novos_cache = []
        for df_part in [semana_grid, fiados_liberados_grid]:
            if df_part is None or df_part.empty: continue
            for _, r in df_part.iterrows():
                novos_cache.append({
                    "RefID": r["RefID"],
                    "PagoEm": to_br_date(br_now()),
                    "TerçaPagamento": to_br_date(terca_pagto),
                    "ValorComissao": f'{float(r["ComissaoValor"]):.2f}'.replace(".", ","),
                    "Competencia": r.get("Competência",""),
                    "Observacao": f'{r.get("Cliente","")} | {r.get("Serviço","")} | {r.get("Data","")}',
                })

        cache_df = _read_df(ABA_COMISSOES_CACHE)
        cache_cols = ["RefID","PagoEm","TerçaPagamento","ValorComissao","Competencia","Observacao"]
        cache_df = garantir_colunas(cache_df, cache_cols)
        if reprocessar_terca:
            cache_df = cache_df[cache_df["TerçaPagamento"] != to_br_date(terca_pagto)].copy()
        cache_upd = pd.concat([cache_df[cache_cols], pd.DataFrame(novos_cache)], ignore_index=True)
        _write_df(ABA_COMISSOES_CACHE, cache_upd)

        # 2) Lê Despesas e garante RefID
        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)

        # 3) Linhas agrupadas por competência
        linhas, export_df_preview = _linhas_comissao_agrupadas(
            semana_grid, fiados_liberados_grid, meio_pag, descricao_padrao, terca_pagto
        )

        # 4) (Caixinha não grava em Despesas)

        # 5) Dedup por RefID e grava em Despesas
        if linhas:
            novos = pd.DataFrame(linhas, columns=COLS_DESPESAS_FIX)
            ref_exist = set(despesas_df["RefID"].astype(str).tolist())
            novos = novos[~novos["RefID"].isin(ref_exist)].copy()
            if not novos.empty:
                despesas_upd = pd.concat([despesas_df[COLS_DESPESAS_FIX], novos], ignore_index=True)
                _write_df(ABA_DESPESAS, despesas_upd)
            st.success(f"Gravado em Despesas: {len(novos)} novas linha(s).")
        else:
            st.info("Nada novo para gravar em Despesas (tudo já lançado).")

        # 6) Telegram
        if enviar_tg:
            texto = build_text_resumo(
                period_ini=ini, period_fim=fim,
                valor_nao_fiado=float(total_semana),
                valor_fiado_liberado=float(total_fiados),
                valor_caixinha=float(total_caixinha if pagar_caixinha else 0.0),
                total_futuros=float(total_fiados_pend),
                df_semana=semana_df, df_fiados=fiados_liberados, df_pend=fiados_pendentes,
                qtd_fiado_pago_hoje=int(qtd_fiados_hoje),
                df_semana_grid=semana_grid,            # << usa GRID
                df_fiados_grid=fiados_liberados_grid   # << usa GRID
            )
            if dest_vini: tg_send_html(texto, _get_chat_vini())
            if dest_jp:   tg_send_html(texto, _get_chat_jp())
        st.success("Processo concluído ✅")

# ============================================
# 🔎 CONFERÊNCIA RÁPIDA (só sistema, sem digitar nada)
# ============================================
st.markdown("## 🔎 Conferência rápida (serviços pagáveis hoje)")

# 1) Junta os itens que serão pagos HOJE (usa os GRIDS já filtrados)
def _df_pagaveis(sem_grid, fiad_grid):
    partes = []
    for d in [sem_grid, fiad_grid]:
        if d is not None and not d.empty:
            partes.append(d.copy())
    if not partes:
        return pd.DataFrame(columns=["Data","Cliente","Serviço","Valor_base_comissao","Competência","RefID"])
    df = pd.concat(partes, ignore_index=True)
    # normaliza nomes de serviço para evitar duplicidades
    if "Serviço" in df.columns:
        df["Serviço"] = df["Serviço"].astype(str).map(normalizar_servico)
    return df

df_pagaveis = _df_pagaveis(semana_grid, fiados_liberados_grid)

# 2) Agrega por serviço (Qtde e Valor do sistema)
def _agg_por_servico(df):
    if df.empty:
        return pd.DataFrame(columns=["Serviço","Qtde","Valor (para comissão)"])
    tmp = df.copy()
    base_col = "Valor (para comissão)" if "Valor (para comissão)" in tmp.columns else "Valor_base_comissao"
    tmp["__valor"] = pd.to_numeric(tmp[base_col], errors="coerce").fillna(0.0)
    out = (tmp.groupby("Serviço", dropna=False)["__valor"]
           .agg(Qtde="count", Valor="sum")
           .reset_index()
           .rename(columns={"Valor":"Valor (para comissão)"}))
    return out.sort_values("Valor (para comissão)", ascending=False)

agg_sis = _agg_por_servico(df_pagaveis)

# 3) Mostra a grade resumida
if agg_sis.empty:
    st.info("Nenhum item pagável hoje.")
else:
    col_tot1, col_tot2 = st.columns(2)
    with col_tot1:
        st.metric("Total por serviços (sem caixinha)", format_brl(float(agg_sis["Valor (para comissão)"].sum())))
    with col_tot2:
        st.metric("Qtde total de serviços", int(agg_sis["Qtde"].sum()))
    st.dataframe(agg_sis.reset_index(drop=True), use_container_width=True)

# 4) Ver as linhas que compõem um serviço
st.markdown("### 🔍 Ver linhas por serviço")
serv_list = sorted(agg_sis["Serviço"].astype(str).unique()) if not agg_sis.empty else []
serv_sel = st.selectbox("Escolha um serviço para listar as linhas:", serv_list or ["—"])
if serv_sel and serv_sel != "—":
    mask = df_pagaveis["Serviço"].astype(str) == serv_sel
    cols_show = ["Data","Cliente","Serviço"]
    for extra in ["Valor (para comissão)","Valor_base_comissao","Competência","RefID"]:
        if extra in df_pagaveis.columns: cols_show.append(extra)
    st.dataframe(df_pagaveis.loc[mask, cols_show].reset_index(drop=True), use_container_width=True)
    st.caption("Essas são as linhas consideradas pelo sistema para este serviço.")

# =============================
# 📤 Exportar para Mobills (SEM gravar) — atual ou histórico
# =============================
st.markdown("## 📤 Exportar para Mobills")

modo_export = st.selectbox(
    "O que você quer exportar?",
    ["Gerar desta terça (sem gravar)","Histórico (carrega do 'Despesas')"],
    index=0
)

if modo_export == "Gerar desta terça (sem gravar)":
    export_lines, export_df = _linhas_comissao_agrupadas(
        semana_grid, fiados_liberados_grid, meio_pag, descricao_padrao, terca_pagto
    )
else:
    # Lê histórico direto de "Despesas"
    ddf = _read_df(ABA_DESPESAS)
    ddf = garantir_colunas(ddf, COLS_DESPESAS_FIX)
    mask = (s_lower(ddf["Prestador"]) == "vinicius") & (ddf["Descrição"].astype(str).str.contains(r"^Comiss[aã]o Vin[ií]cius — Comp", regex=True))
    ddf = ddf[mask].copy()
    ddf["Valor_float"] = ddf["Valor"].apply(_to_float_brl)
    export_df = pd.DataFrame({
        "Data": ddf["Data"].astype(str),
        "Descrição": ddf["Descrição"].astype(str),
        "Valor": -ddf["Valor_float"].round(2),        # negativo p/ Mobills
        "Categoria": "Comissão",
        "Conta": ddf["Me Pag:"].replace("", "Dinheiro"),
        "Observação": ddf["Descrição"].astype(str),
    })[["Data","Descrição","Valor","Conta","Categoria","Observação"]]

st.dataframe(export_df.reset_index(drop=True), use_container_width=True)

col_bcsv, col_bxls = st.columns([1,1])
with col_bcsv:
    csv_bytes = export_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Baixar CSV para Mobills",
        data=csv_bytes,
        file_name="comissoes_vinicius_mobills.csv",
        mime="text/csv",
        use_container_width=True
    )

with col_bxls:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Comissoes")
    st.download_button(
        "⬇️ Baixar XLSX para Mobills",
        data=buf.getvalue(),
        file_name="comissoes_vinicius_mobills.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )

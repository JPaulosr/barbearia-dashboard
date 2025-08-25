# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão por DIA + Caixinha
# - Regra: MESMO mês da terça → 1 linha única (data = terça) | OUTRO mês → 1 linha por DIA (data do atendimento)
# - Descrição: "Comissão Vinícius" e "Caixinha Vinícius" (sem "Comp", sem "Pago em")
# - Trava anti-duplicação via RefID em Despesas
# - Coluna técnica "TerçaPagto" em Despesas para exportação/retroativos
# - Exporta XLS p/ Mobills com valores NEGATIVOS

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
from io import BytesIO

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
TELEGRAM_CHAT_ID_VINICIUS_FALLBACK = "-1001234567890"

COLS_OFICIAIS = [
    "Data","Serviço","Valor","Conta","Cliente","Combo",
    "Funcionário","Fase","Tipo","Período",
    "StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento",
    "ValorBrutoRecebido","ValorLiquidoRecebido",
    "TaxaCartaoValor","TaxaCartaoPct",
    "FormaPagDetalhe","PagamentoID",
    "CaixinhaDia","CaixinhaFundo",
]

# >>> inclui coluna técnica "TerçaPagto"
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
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d"):
        try: return datetime.strptime(s, fmt)
        except: pass
    return None

def to_br_date(dt):
    if dt is None or (hasattr(dt,"tz_localize") and pd.isna(dt)): return ""
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
    s = s.replace("R$","").replace(" ","")
    s = re.sub(r"\.(?=\d{3}(\D|$))","",s)
    s = s.replace(",",".")
    try: return float(s)
    except: return 0.0

def snap_para_preco_cheio(servico: str, valor: float, tol: float, habilitado: bool) -> float:
    if not habilitado: return valor
    cheio = VALOR_TABELA.get((servico or "").strip())
    if isinstance(cheio,(int,float)) and abs(valor - float(cheio)) <= tol:
        return float(cheio)
    return valor

def format_brl(v: float) -> str:
    try: v = float(v)
    except: v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

def _refid_despesa(data_br: str, prestador: str, descricao: str, valor_float: float, mepag: str) -> str:
    base = f"{data_br.strip()}|{prestador.strip().lower()}|{descricao.strip().lower()}|{valor_float:.2f}|{str(mepag).strip().lower()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def make_refid_atendimento(row: pd.Series) -> str:
    key = "|".join([str(row.get(k,"")).strip() for k in ["Cliente","Data","Serviço","Valor","Funcionário","Combo"]])
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
# RESUMO (HTML Telegram)
# =============================
def build_text_resumo(period_ini, period_fim,
                      valor_nao_fiado, valor_fiado_liberado, valor_caixinha,
                      total_futuros, df_semana, df_fiados, df_pend,
                      qtd_fiado_pago_hoje=0):
    clientes, servs = 0, {}
    if any(d is not None and not d.empty for d in [df_semana, df_fiados]):
        df_all = pd.concat([d for d in [df_semana, df_fiados] if d is not None and not d.empty], ignore_index=True)
        clientes = df_all["Cliente"].astype(str).str.strip().str.lower().nunique() if "Cliente" in df_all.columns else 0
        servs = df_all["Serviço"].astype(str).str.strip().value_counts().to_dict() if "Serviço" in df_all.columns else {}
    serv_lin = ", ".join([f"{k}×{v}" for k,v in servs.items()]) if servs else "—"

    qtd_pend = int(len(df_pend)) if df_pend is not None else 0
    clientes_pend = df_pend["Cliente"].astype(str).str.strip().str.lower().nunique() if df_pend is not None and not df_pend.empty else 0
    dt_min = to_br_date(pd.to_datetime(df_pend["_dt_serv"], errors="coerce").min()) if df_pend is not None and "_dt_serv" in df_pend.columns and not df_pend.empty else "—"

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
st.title("💈 Pagamento de Comissão — Vinicius (1 linha por DIA do atendimento)")

# Carrega base
base = _read_df(ABA_DADOS).copy()

# Inputs (linha 1)
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

# Inputs (linha 3)
col_r1, col_r2 = st.columns([2,1])
with col_r1:
    arred_cheio = st.checkbox(
        "Arredondar para preço cheio de TABELA (tolerância abaixo)",
        value=True,
        help="Ex.: 23,00 / 24,75 / 25,10 → 25,00 (se dentro da tolerância)."
    )
with col_r2:
    tol_reais = st.number_input("Tolerância (R$)", value=2.00, step=0.50, min_value=0.0)

# ⚙️ Caixinha & Telegram
st.markdown("### 🎁 Caixinha & 📲 Telegram")
pagar_caixinha = st.checkbox("Pagar caixinha nesta terça (lançar em Despesas por DIA)", value=True)
meio_pag = st.selectbox("Meio de pagamento (para DESPESAS — comissão)", ["Dinheiro","Pix","Cartão","Transferência"], index=0)
meio_pag_cx = st.selectbox("Meio de pagamento (para DESPESAS — caixinha)", ["Dinheiro","Pix","Cartão","Transferência"],
                           index=["Dinheiro","Pix","Cartão","Transferência"].index(meio_pag))
descricao_padrao = "Comissão Vinícius"
descricao_cx     = "Caixinha Vinícius"
enviar_tg = st.checkbox("Enviar resumo no Telegram ao registrar", value=True)
dest_vini = st.checkbox("Enviar para canal do Vinícius", value=True)
dest_jp = st.checkbox("Enviar cópia para JPaulo (privado)", value=True)

# ✅ Reprocessar esta terça (apenas cache histórico; Despesas tem trava própria)
reprocessar_terca = st.checkbox("Reprocessar esta terça (regravar cache de comissão)", value=False)

# ============ Pré-filtros ============
dfv = base[s_lower(base["Funcionário"]) == "vinicius"].copy()
if not incluir_produtos:
    dfv = dfv[s_lower(dfv["Tipo"]) == "serviço"]

mask_caixinha_lanc = (
    (s_lower(dfv["Conta"]) == "caixinha") |
    (s_lower(dfv["Tipo"]) == "caixinha") |
    (s_lower(dfv["Serviço"]) == "caixinha")
)
dfv = dfv[~mask_caixinha_lanc].copy()

dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)
dfv["_dt_pagto"] = dfv["DataPagamento"].apply(parse_br_date)

ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}** (terça→segunda)")

# -------- CAIXINHA (somatório por janela) --------
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
na_janela = dfv[(dfv["_dt_serv"].notna()) & (dfv["_dt_serv"] >= ini) & (dfv["_dt_serv"] <= fim)]
nao_fiado = na_janela[(s_lower(na_janela["StatusFiado"]) == "") | (s_lower(na_janela["StatusFiado"]) == "nao")]
fiado_all = dfv[(s_lower(dfv["StatusFiado"]) != "") | (s_lower(dfv["IDLancFiado"]) != "")]
fiados_ok = fiado_all[(fiado_all["_dt_pagto"].notna()) & (fiado_all["_dt_pagto"] <= terca_pagto)]
fiados_pend_all = fiado_all[(fiado_all["_dt_pagto"].isna()) | (fiado_all["_dt_pagto"] > terca_pagto)]

# 1) Semana não fiado
mask_semana = (
    (dfv["_dt_serv"].notna()) &
    (dfv["_dt_serv"] >= ini) &
    (dfv["_dt_serv"] <= fim) &
    ((s_lower(dfv["StatusFiado"]) == "") | (s_lower(dfv["StatusFiado"]) == "nao"))
)
semana_df = dfv[mask_semana].copy()

# 2) Fiados liberados
fiados_liberados = fiado_all[(fiado_all["_dt_pagto"].notna()) & (fiado_all["_dt_pagto"] <= terca_pagto)].copy()

# 3) Fiados pendentes
fiados_pendentes = fiado_all[(fiado_all["_dt_pagto"].isna()) | (fiado_all["_dt_pagto"] > terca_pagto)].copy()
if fiados_pendentes.empty:
    fiados_pendentes = pd.DataFrame(columns=["Data","Cliente","Serviço","_dt_serv"])
else:
    if "_dt_serv" not in fiados_pendentes.columns:
        fiados_pendentes["_dt_serv"] = fiados_pendentes["Data"].apply(parse_br_date)

# ---- valor base p/ comissão
def montar_valor_base(df: pd.DataFrame) -> pd.DataFrame:
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

_futuros_mb = montar_valor_base(fiados_pendentes).copy()
_futuros_mb["% Comissão"] = float(perc_padrao)
_futuros_mb["Comissão (R$)"] = (
    pd.to_numeric(_futuros_mb["Valor_base_comissao"], errors="coerce").fillna(0.0) * float(perc_padrao) / 100.0
).round(2)
total_fiados_pend = float(_futuros_mb["Comissão (R$)"].sum())

st.caption(
    f"Na janela (não fiado): {len(nao_fiado)} | "
    f"Fiados liberados: {len(fiados_ok)} | "
    f"Fiados pendentes: {len(fiados_pend_all)}"
)

# ------- GRADES EDITÁVEIS -------
def preparar_grid(df: pd.DataFrame, titulo: str, key_prefix: str):
    if df.empty:
        st.warning(f"Sem itens em **{titulo}**.")
        return pd.DataFrame(), 0.0
    df = df.copy()
    df["RefID"] = df.apply(make_refid_atendimento, axis=1)
    df = df[~df["RefID"].isin(set(_read_df(ABA_COMISSOES_CACHE)["RefID"].astype(str).tolist()))]
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

qtd_fiados_hoje = int(len(fiados_liberados_grid)) if (fiados_liberados_grid is not None and not fiados_liberados_grid.empty) else 0

# ------- RESUMO -------
total_comissao_hoje = float(total_semana + total_fiados)
total_geral_hoje = float(total_comissao_hoje + (total_caixinha if pagar_caixinha else 0.0))

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1: st.metric("Nesta terça — NÃO fiado", format_brl(total_semana))
with col_m2: st.metric("Nesta terça — fiados liberados (a pagar)", format_brl(total_fiados))
with col_m3: st.metric("Total desta terça", format_brl(total_comissao_hoje))
with col_m4: st.metric("Fiados pendentes (futuro)", format_brl(total_fiados_pend))

# =============================
# BACKFILL RefID + TerçaPagto
# =============================
def _backfill_refid_em_despesas(despesas_df: pd.DataFrame) -> pd.DataFrame:
    despesas_df = garantir_colunas(despesas_df.copy(), COLS_DESPESAS_FIX)
    # RefID
    faltando = despesas_df["RefID"].astype(str).str.strip() == ""
    if faltando.any():
        for idx, r in despesas_df[faltando].iterrows():
            data_br = str(r.get("Data","")).strip()
            prest   = str(r.get("Prestador","")).strip()
            desc    = str(r.get("Descrição","")).strip()
            valtxt  = str(r.get("Valor","")).strip()
            mepag   = str(r.get("Me Pag:","")).strip()
            if not data_br or not prest or not desc or not valtxt:
                continue
            valf = _to_float_brl(valtxt)
            despesas_df.at[idx, "RefID"] = _refid_despesa(data_br, prest, desc, valf, mepag)
    # Garante coluna técnica
    if "TerçaPagto" not in despesas_df.columns:
        despesas_df["TerçaPagto"] = ""
    return despesas_df

# ====== Mapeamento p/ "Conta" no Mobills ======
def _map_conta_mobills(meio_pag: str) -> str:
    m = {"dinheiro":"Carteira","pix":"Carteira","transferência":"Carteira","cartão":"Cartão"}
    return m.get((meio_pag or "").strip().lower(), "Carteira")

# ====== Gerar arquivo Mobills ======
def _gerar_arquivo_mobills(df_export: pd.DataFrame, nome_base: str) -> tuple[BytesIO, str, str]:
    buf = BytesIO()
    filename = f"{nome_base}.xls"
    mime = "application/vnd.ms-excel"
    try:
        with pd.ExcelWriter(buf, engine="xlwt") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Mobills")
    except Exception:
        buf = BytesIO()
        filename = f"{nome_base}.xlsx"
        mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df_export.to_excel(writer, index=False, sheet_name="Mobills")
    buf.seek(0)
    return buf, filename, mime

# =============================
# ⬇️ EXPORTAÇÃO RETROATIVA
# =============================
st.markdown("### ⬇️ Exportação retroativa para Mobills")
if st.button("⬇️ Exportar para Mobills (pela terça escolhida)"):
    despesas = _read_df(ABA_DESPESAS)
    despesas = garantir_colunas(despesas, COLS_DESPESAS_FIX)

    data_terca = to_br_date(terca_pagto)
    mask_terca = despesas["TerçaPagto"].astype(str).str.strip() == data_terca

    mask_comissao = (s_lower(despesas["Prestador"]) == "vinicius") & mask_terca
    mask_caixinha = (s_lower(despesas["Prestador"]) == "vinicius (caixinha)") & mask_terca
    exp_base = despesas[mask_comissao | mask_caixinha].copy()

    # Fallback p/ linhas antigas sem TerçaPagto
    if exp_base.empty:
        janela_ini, janela_fim = janela_terca_a_segunda(terca_pagto)
        in_janela = despesas["Data"].apply(parse_br_date).between(janela_ini, janela_fim, inclusive="both")
        mask_fallback_terca = (s_lower(despesas["Prestador"]) == "vinicius") & (despesas["Data"].astype(str).str.strip() == data_terca)
        mask_fallback_outro = (s_lower(despesas["Prestador"]) == "vinicius") & in_janela
        mask_fallback_cx    = (s_lower(despesas["Prestador"]) == "vinicius (caixinha)") & in_janela
        exp_base = despesas[mask_fallback_terca | mask_fallback_outro | mask_fallback_cx].copy()

    if exp_base.empty:
        st.warning("Não encontrei linhas em Despesas para exportar nessa terça.")
    else:
        def _row_to_mobills(r):
            data = str(r["Data"]).strip()
            desc = str(r["Descrição"]).strip()
            val  = -abs(_to_float_brl(str(r["Valor"])))  # NEGATIVO
            conta = _map_conta_mobills(str(r.get("Me Pag:","")))
            cat = "Caixinha Vinícius" if "Caixinha" in str(r["Prestador"]) else "Comissão Vinícius"
            return {"Data": data, "Descrição": desc, "Valor": val, "Conta": conta, "Categoria": cat}

        df_export = pd.DataFrame([_row_to_mobills(r) for _, r in exp_base.iterrows()],
                                 columns=["Data","Descrição","Valor","Conta","Categoria"])
        nome_base = f"mobills_comissao_vinicius_{data_terca.replace('/','-')}"
        buf, fname, mime = _gerar_arquivo_mobills(df_export, nome_base)

        st.download_button("⬇️ Baixar arquivo para Mobills (retroativo)",
                           data=buf, file_name=fname, mime=mime, use_container_width=True)
        st.info("Mobills → Transações → Importar planilha → selecione o arquivo baixado.")

# =============================
# 📲 Reenviar resumo (sem gravar)
# =============================
if st.button("📲 Reenviar resumo (sem gravar)"):
    texto = build_text_resumo(
        period_ini=ini, period_fim=fim,
        valor_nao_fiado=float(total_semana),
        valor_fiado_liberado=float(total_fiados),
        valor_caixinha=float(total_caixinha if pagar_caixinha else 0.0),
        total_futuros=float(total_fiados_pend),
        df_semana=semana_df, df_fiados=fiados_liberados, df_pend=fiados_pendentes,
        qtd_fiado_pago_hoje=int(qtd_fiados_hoje)
    )
    if dest_vini: tg_send_html(texto, _get_chat_vini())
    if dest_jp:   tg_send_html(texto, _get_chat_jp())
    st.success("Resumo reenviado ✅")

# =============================
# ✅ REGISTRAR + CONSOLIDAR + EXPORT
# =============================
if st.button("✅ Registrar comissão (por DIA do atendimento) e marcar itens como pagos"):
    if (semana_grid is None or semana_grid.empty) and (fiados_liberados_grid is None or fiados_liberados_grid.empty) and not (pagar_caixinha and total_caixinha > 0):
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
                    "ValorComissao": f'{float(r["ComissaoValor"]):.2f}'.replace(".",","),
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

        # 2) Lê Despesas (e garante colunas)
        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = _backfill_refid_em_despesas(despesas_df)

        # 3) Constrói linhas (MESMO mês = 1 linha | OUTRO mês = por DIA)
        pagaveis = []
        for df_part in [semana_grid, fiados_liberados_grid]:
            if df_part is None or df_part.empty: continue
            pagaveis.append(df_part[["Data","Competência","ComissaoValor"]].copy())

        linhas = []
        linhas_comissao = 0
        if pagaveis:
            pagos = pd.concat(pagaveis, ignore_index=True)

            def _norm_dt(s):
                s = (s or "").strip()
                for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d"):
                    try: return datetime.strptime(s, fmt)
                    except: pass
                return None
            pagos["_dt"] = pagos["Data"].apply(_norm_dt)
            pagos = pagos[pagos["_dt"].notna()].copy()

            competencia_pagto = datetime.strftime(terca_pagto, "%m/%Y")

            mesmos_mes = pagos[pagos["Competência"].astype(str).str.strip() == competencia_pagto].copy()
            outros_mes = pagos[pagos["Competência"].astype(str).str.strip() != competencia_pagto].copy()

            # OUTRO MÊS → por DIA (data do atendimento)
            if not outros_mes.empty:
                por_dia = outros_mes.groupby(["Data","Competência"], dropna=False)["ComissaoValor"].sum().reset_index()
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

            # MESMO MÊS → 1 linha (data = terça)
            if not mesmos_mes.empty:
                total_mesmo_mes = float(mesmos_mes["ComissaoValor"].sum())
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
            linhas_comissao = len(linhas)

        # 4) Caixinha por dia (sempre por DIA na janela)
        linhas_caixinha = 0
        if pagar_caixinha and total_caixinha > 0:
            cx_df = base_jan_vini.copy()
            cx_df["TotalCxDia"] = cx_df["CaixinhaDia_num"] + cx_df["CaixinhaFundo_num"] + cx_df["CaixinhaRow_num"]
            cx_df = cx_df.groupby("Data", dropna=False)["TotalCxDia"].sum().reset_index()
            cx_df["TotalCxDia"] = pd.to_numeric(cx_df["TotalCxDia"], errors="coerce").fillna(0.0)
            cx_df = cx_df[cx_df["TotalCxDia"] > 0]

            for _, r in cx_df.iterrows():
                data_br = str(r["Data"]).strip()
                valf = float(r["TotalCxDia"])
                valor_txt = f'R$ {valf:.2f}'.replace(".",",")
                refid = _refid_despesa(data_br, "Vinicius (Caixinha)", descricao_cx, valf, meio_pag_cx)
                linhas.append({
                    "Data": data_br,
                    "Prestador": "Vinicius (Caixinha)",
                    "Descrição": descricao_cx,
                    "Valor": valor_txt,
                    "Me Pag:": meio_pag_cx,
                    "TerçaPagto": to_br_date(terca_pagto),
                    "RefID": refid
                })
            linhas_caixinha = len(cx_df)

        # 5) CONSOLIDAR + gravar + export desta execução
        novos = pd.DataFrame(columns=COLS_DESPESAS_FIX)
        refids_gerados = []

        # --- Base atual de Despesas ---
        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = _backfill_refid_em_despesas(despesas_df)

        # Remover "por dia" do MESMO MÊS desta terça (Prestador=Vinicius; TerçaPagto = data_terca; Data != terça)
        data_terca_br = to_br_date(terca_pagto)
        mes_terca = terca_pagto.month
        ano_terca = terca_pagto.year

        def _dt_or_none(s):
            try: return parse_br_date(str(s))
            except: return None

        mask_vini   = s_lower(despesas_df["Prestador"]) == "vinicius"
        mask_terca  = despesas_df["TerçaPagto"].astype(str).str.strip() == data_terca_br
        datas_real = despesas_df["Data"].apply(_dt_or_none)
        same_month = datas_real.apply(lambda d: (d is not None) and (d.month == mes_terca) and (d.year == ano_terca))
        mask_por_dia_mesmo_mes = mask_vini & mask_terca & same_month & (despesas_df["Data"].astype(str).str.strip() != data_terca_br)

        if mask_por_dia_mesmo_mes.any():
            despesas_df = despesas_df[~mask_por_dia_mesmo_mes].copy()

        # Preparar novos lançamentos desta execução
        if linhas:
            novos = pd.DataFrame(linhas, columns=COLS_DESPESAS_FIX)
            ref_exist = set(despesas_df["RefID"].astype(str).tolist())
            refids_gerados = novos["RefID"].astype(str).tolist()
            a_gravar = novos[~novos["RefID"].isin(ref_exist)].copy()

            if not a_gravar.empty:
                despesas_upd = pd.concat([despesas_df[COLS_DESPESAS_FIX], a_gravar], ignore_index=True)
                _write_df(ABA_DESPESAS, despesas_upd)
                st.success(
                    f"Gravado em Despesas: {len(a_gravar)} novas linha(s).  "
                    f"(Comissão: {linhas_comissao}; Caixinha: {linhas_caixinha}). "
                    f"Linhas por dia do mesmo mês foram consolidadas em 1 linha."
                )
            else:
                _write_df(ABA_DESPESAS, despesas_df)
                st.info("Nada novo para gravar, mas consolidei as linhas por dia do mesmo mês em uma linha única.")
        else:
            _write_df(ABA_DESPESAS, despesas_df)
            st.info("Nada a lançar nesta execução. (Se existiam linhas por dia do mesmo mês, foram consolidadas.)")

        # ===== Export desta execução (ou fallback) =====
        despesas_atual = _read_df(ABA_DESPESAS)
        despesas_atual = garantir_colunas(despesas_atual, COLS_DESPESAS_FIX)

        if refids_gerados:
            exp_base = despesas_atual[despesas_atual["RefID"].astype(str).isin(refids_gerados)].copy()
        else:
            data_terca2 = to_br_date(terca_pagto)
            mask_terca2 = despesas_atual["TerçaPagto"].astype(str).str.strip() == data_terca2
            mask_comissao2 = (s_lower(despesas_atual["Prestador"]) == "vinicius") & mask_terca2
            mask_caixinha2 = (s_lower(despesas_atual["Prestador"]) == "vinicius (caixinha)") & mask_terca2
            exp_base = despesas_atual[mask_comissao2 | mask_caixinha2].copy()

            if exp_base.empty:
                janela_ini2, janela_fim2 = janela_terca_a_segunda(terca_pagto)
                in_janela2 = despesas_atual["Data"].apply(parse_br_date).between(janela_ini2, janela_fim2, inclusive="both")
                mask_fallback_terca2 = (s_lower(despesas_atual["Prestador"]) == "vinicius") & (despesas_atual["Data"].astype(str).str.strip() == data_terca2)
                mask_fallback_outro2 = (s_lower(despesas_atual["Prestador"]) == "vinicius") & in_janela2
                mask_fallback_cx2    = (s_lower(despesas_atual["Prestador"]) == "vinicius (caixinha)") & in_janela2
                exp_base = despesas_atual[mask_fallback_terca2 | mask_fallback_outro2 | mask_fallback_cx2].copy()

        if exp_base.empty:
            st.warning("Não encontrei linhas em Despesas para exportar nessa terça.")
        else:
            def _row_to_mobills(r):
                data = str(r["Data"]).strip()
                desc = str(r["Descrição"]).strip()
                val  = -abs(_to_float_brl(str(r["Valor"])))  # NEGATIVO
                conta = _map_conta_mobills(str(r.get("Me Pag:","")))
                cat = "Caixinha Vinícius" if "Caixinha" in str(r["Prestador"]) else "Comissão Vinícius"
                return {"Data": data, "Descrição": desc, "Valor": val, "Conta": conta, "Categoria": cat}

            df_export = pd.DataFrame([_row_to_mobills(r) for _, r in exp_base.iterrows()],
                                     columns=["Data","Descrição","Valor","Conta","Categoria"])
            nome_base = f"mobills_comissao_vinicius_{to_br_date(terca_pagto).replace('/','-')}"
            buf, fname, mime = _gerar_arquivo_mobills(df_export, nome_base)

            st.download_button("⬇️ Baixar arquivo para Mobills",
                               data=buf, file_name=fname, mime=mime, use_container_width=True)
            st.info("Mobills → Transações → Importar planilha → selecione o arquivo baixado.")

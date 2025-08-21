# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Pagamento de comissão (linhas por DIA do atendimento)
# - Paga toda terça o período de terça→segunda anterior.
# - Fiado só entra quando DataPagamento <= terça do pagamento.
# - Em Despesas grava UMA LINHA POR DIA DO ATENDIMENTO (Data = data do serviço).
# - Evita duplicidades via sheet "comissoes_cache" com RefID por atendimento.
# - Preço de TABELA para cartão (opcional) e arredondamento com tolerância.
# - Caixinha NÃO entra na comissão; pode ser paga junto (opção).
# - Envia resumo no Telegram (comissão, caixinha, fiados futuros detalhados).

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

# =============================
# CONFIG BÁSICA
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"

TZ = "America/Sao_Paulo"

# Telegram fallbacks
TG_TOKEN_FALLBACK = "SEU_TOKEN_AQUI"
TG_CHAT_JPAULO_FALLBACK = "SEU_CHATID_PESSOAL"
TG_CHAT_VINICIUS_FALLBACK = "SEU_CHATID_VINICIUS"

# Colunas da planilha
COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período",
    "StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento",
    "ValorBrutoRecebido", "ValorLiquidoRecebido",
    "TaxaCartaoValor", "TaxaCartaoPct",
    "FormaPagDetalhe", "PagamentoID",
    "CaixinhaDia", "CaixinhaFundo",
]
COLS_DESPESAS_FIX = ["Data", "Prestador", "Descrição", "Valor", "Me Pag:"]
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
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=50)

def _read_df(title: str) -> pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").replace({pd.NA: ""})
    for c in COLS_OFICIAIS:
        if c not in df.columns:
            df[c] = ""
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
def to_br_date(dt: datetime): return dt.strftime("%d/%m/%Y")
def competencia_from_data_str(data): 
    dt = parse_br_date(data)
    return dt.strftime("%m/%Y") if dt else ""
def janela_terca_a_segunda(terca):
    ini = terca - timedelta(days=7); fim = ini + timedelta(days=6); return ini, fim
def make_refid(row: pd.Series) -> str:
    key = "|".join([str(row.get(k, "")).strip() for k in ["Cliente","Data","Serviço","Valor","Funcionário","Combo"]])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
def garantir_colunas(df, cols): 
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df
def s_lower(s): return s.astype(str).str.strip().str.lower()
def is_cartao(conta): return bool(re.search(r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pagseguro|sumup|cielo|stone|getnet|nubank)", (conta or "").lower()))
def _to_float_brl(v):
    s=str(v).strip().replace("R$","").replace(" ","").replace(".","",1).replace(",",".")
    try: return float(s)
    except: return 0.0
def snap_para_preco_cheio(serv, valor, tol, habil): 
    cheio = VALOR_TABELA.get(serv.strip()) if habil else None
    return cheio if cheio and abs(valor-cheio)<=tol else valor
def format_brl(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# Telegram
def _get_telegram_creds():
    token, chat_jp, chat_vn = TG_TOKEN_FALLBACK, TG_CHAT_JPAULO_FALLBACK, TG_CHAT_VINICIUS_FALLBACK
    try:
        tg = st.secrets.get("TELEGRAM",{})
        token = tg.get("TOKEN",token); chat_jp=tg.get("CHAT_ID_JPAULO",chat_jp); chat_vn=tg.get("CHAT_ID_VINICIUS",chat_vn)
    except: pass
    return token, chat_jp, chat_vn
def tg_send_text(token, chat, text):
    try: requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat,"text":text},timeout=15)
    except: pass

def contar_clientes_e_servicos(df_list):
    if not any(d is not None and not d.empty for d in df_list): return 0, {}
    df_all = pd.concat([d for d in df_list if d is not None and not d.empty])
    return df_all["Cliente"].nunique(), df_all["Serviço"].value_counts().to_dict()

def build_text_resumo(ini,fim,total_comissao_hoje,total_futuros,pagar_cx,total_cx,df_semana,df_fiados,df_pend):
    clientes, servs = contar_clientes_e_servicos([df_semana,df_fiados])
    serv_lin = ", ".join([f"{k}×{v}" for k,v in servs.items()]) if servs else "—"
    qtd_pend = len(df_pend); cli_pend=df_pend["Cliente"].nunique() if not df_pend.empty else 0
    dt_min = to_br_date(df_pend["_dt_serv"].min()) if "_dt_serv" in df_pend.columns and not df_pend.empty else "—"
    linhas=[
        f"💈 Resumo — Vinícius  ({to_br_date(ini)} → {to_br_date(fim)})",
        f"👥 Clientes: {clientes}",
        f"✂️ Serviços: {serv_lin}",
        f"🧾 Comissão de hoje: {format_brl(total_comissao_hoje)}"
    ]
    if pagar_cx and total_cx>0: 
        linhas.append(f"🎁 Caixinha de hoje: {format_brl(total_cx)}")
        linhas.append(f"💵 Total GERAL pago hoje: {format_brl(total_comissao_hoje+total_cx)}")
    linhas.append(f"🕒 Comissão futura (fiados pendentes): {format_brl(total_futuros)}")
    if qtd_pend>0: linhas.append(f"   • {qtd_pend} itens • {cli_pend} clientes • mais antigo: {dt_min}")
    return "\n".join(linhas)

# =============================
# UI
# =============================
st.set_page_config(layout="wide")
st.title("💈 Pagamento de Comissão — Vinicius (1 linha por DIA do atendimento)")

# ... (código de carregamento da base, filtros, grids, fiados liberados, caixinha é igual ao que já enviei antes) ...

# ------- FIADOS PENDENTES -------
# depois de calcular total_fiados_pend:
qtd_fiados_pend = len(fiados_pendentes)
clientes_fiados_pend = fiados_pendentes["Cliente"].nunique() if not fiados_pendentes.empty else 0
_dt_min_pend = fiados_pendentes["_dt_serv"].min() if "_dt_serv" in fiados_pendentes.columns and not fiados_pendentes.empty else None
_dt_max_pend = fiados_pendentes["_dt_serv"].max() if "_dt_serv" in fiados_pendentes.columns and not fiados_pendentes.empty else None
min_str = to_br_date(_dt_min_pend) if _dt_min_pend else "—"
max_str = to_br_date(_dt_max_pend) if _dt_max_pend else "—"

# ------- MÉTRICAS -------
total_comissao_hoje = total_semana+total_fiados
total_geral_hoje = total_comissao_hoje+(total_caixinha if pagar_caixinha else 0)
c1,c2,c3,c4=st.columns(4)
c1.metric("Nesta terça — NÃO fiado", format_brl(total_semana))
c2.metric("Nesta terça — fiados liberados", format_brl(total_fiados))
c3.metric("Total desta terça", format_brl(total_comissao_hoje))
c4.metric("Fiados pendentes (futuro)", format_brl(total_fiados_pend), delta=f"{qtd_fiados_pend} itens / {clientes_fiados_pend} clientes")
st.caption(f"📌 Fiados pendentes: {qtd_fiados_pend} itens, {clientes_fiados_pend} clientes; mais antigo: {min_str}; mais recente: {max_str}.")
st.success(f"Total GERAL hoje: {format_brl(total_geral_hoje)}")

# ... (resto: gravação em Despesas, cache, envio Telegram com build_text_resumo, igual antes)

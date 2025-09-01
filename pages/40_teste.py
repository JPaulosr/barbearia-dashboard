# -*- coding: utf-8 -*-
# 12_Fiado.py — App Feminino (Base & Fotos exclusivas + Telegram Feminino)
# - Usa "Base de Dados Feminino" e "clientes_status_feminino"
# - Lançar fiado, quitar por competência, cartões gravam LÍQUIDO em Valor
# - Inclui campo de Caixinha em Registrar Pagamento e envia no Telegram

import streamlit as st
import pandas as pd
import gspread
import requests
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from gspread.utils import rowcol_to_a1
from datetime import date, datetime, timedelta
import pytz, unicodedata

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE   = "Base de Dados Feminino"
ABA_LANC   = "Fiado_Lancamentos"
ABA_PAGT   = "Fiado_Pagamentos"
STATUS_ABA = "clientes_status_feminino"

TZ = "America/Sao_Paulo"
DATA_FMT = "%d/%m/%Y"

BASE_COLS_MIN = ["Data","Serviço","Valor","Conta","Cliente","Combo","Funcionário","Fase","Tipo","Período"]
EXTRA_COLS    = ["StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento"]
BASE_PAG_EXTRAS = ["ValorBrutoRecebido","ValorLiquidoRecebido","TaxaCartaoValor","TaxaCartaoPct","FormaPagDetalhe","PagamentoID"]
CAIXINHA_COLS = ["CaixinhaDia"]
BASE_COLS_ALL = BASE_COLS_MIN + EXTRA_COLS + BASE_PAG_EXTRAS + CAIXINHA_COLS

# =========================
# CONEXÃO
# =========================
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds).open_by_key(SHEET_ID)

# =========================
# TELEGRAM
# =========================
TELEGRAM_TOKEN_CONST = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
TELEGRAM_CHAT_ID_JPAULO_CONST = "493747253"
TELEGRAM_CHAT_ID_FEMININO_CONST = "-1002965378062"

def tg_send(text: str, chat_id: str = TELEGRAM_CHAT_ID_JPAULO_CONST):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN_CONST}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        r = requests.post(url, json=payload, timeout=30)
        return r.ok
    except Exception:
        return False

# =========================
# FUNÇÕES BASE
# =========================
def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def _fmt_brl(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# =========================
# CARREGAR BASE
# =========================
@st.cache_data(show_spinner=False)
def carregar_base():
    ws = conectar_sheets().worksheet(ABA_BASE)
    df = get_as_dataframe(ws).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    for c in BASE_COLS_ALL:
        if c not in df.columns:
            df[c] = ""
    return df, ws

# =========================
# UI
# =========================
st.title("💳 Fiado Feminino + Pagamentos")
acao = st.radio("Selecione a ação", ["📌 Lançar fiado","💰 Registrar pagamento"], horizontal=True)

df_base, ws_base = carregar_base()

if acao == "💰 Registrar pagamento":
    st.subheader("💰 Registrar Pagamento de Fiado")
    clientes = sorted(df_base["Cliente"].dropna().unique())
    cliente_sel = st.selectbox("Cliente", clientes)
    subset = df_base[df_base["Cliente"] == cliente_sel]
    linhas = st.multiselect("Selecione as linhas a quitar", subset.index.tolist())

    conta = st.text_input("Forma de Pagamento", "Carteira")
    total_bruto = float(subset.loc[linhas,"Valor"].sum()) if linhas else 0.0
    total_liquido = st.number_input("Valor líquido recebido", value=total_bruto, step=1.0, format="%.2f")
    obs = st.text_input("Observação (opcional)", "")

    with st.expander("💝 Caixinha (opcional)", expanded=False):
        caixinha_valor = st.number_input("Caixinha do dia", value=0.0, step=1.0, format="%.2f")

    if st.button("Registrar pagamento") and linhas:
        updates = []
        for idx in linhas:
            row_no = idx + 2
            col_valor = list(df_base.columns).index("DataPagamento") + 1
            updates.append({"range": rowcol_to_a1(row_no, col_valor), "values": [[date.today().strftime(DATA_FMT)]]})
        
        # grava caixinha em UMA linha
        cx_val = float(caixinha_valor or 0.0)
        if cx_val > 0:
            idx_target = min(linhas)
            row_no_cx = idx_target + 2
            col_cx = list(df_base.columns).index("CaixinhaDia") + 1
            updates.append({"range": rowcol_to_a1(row_no_cx, col_cx), "values": [[cx_val]]})

        if updates:
            ws_base.batch_update(updates, value_input_option="USER_ENTERED")
            st.success("Pagamento registrado!")

            msg = (
                f"✅ <b>Fiado quitado</b>\n"
                f"👤 Cliente: <b>{cliente_sel}</b>\n"
                f"💵 Líquido: <b>{_fmt_brl(total_liquido)}</b>"
                + (f"\n💝 Caixinha: <b>{_fmt_brl(cx_val)}</b>" if cx_val>0 else "")
                + (f"\n📝 Obs.: {obs}" if obs else "")
            )
            tg_send(msg, TELEGRAM_CHAT_ID_JPAULO_CONST)

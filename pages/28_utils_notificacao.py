# -*- coding: utf-8 -*-
# 13_Comissoes.py — Fila de Comissões (pagar na terça), integração com Despesas + Telegram

import streamlit as st
import pandas as pd
import gspread, requests
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date, datetime, timedelta
import pytz

# ====== Telegram (mesmo util do Fiado) ======
def _get_tg_creds():
    tg = st.secrets.get("TELEGRAM", {}) or {}
    token = (tg.get("bot_token") or "").strip()
    chat  = (tg.get("chat_id")  or "").strip()
    if not token: token = (st.secrets.get("TELEGRAM_TOKEN") or "").strip()
    if not chat:
        chat = (st.secrets.get("TELEGRAM_CHAT_ID") or "").strip() \
            or (st.secrets.get("TELEGRAM_CHAT_ID_VINICIUS") or "").strip() \
            or (st.secrets.get("TELEGRAM_CHAT_ID_JPAULO") or "").strip()
    if not token: token = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
    if not chat:  chat  = "-1002953102982"
    return token, chat

def _tg(md_text: str):
    token, chat = _get_tg_creds()
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          json={"chat_id": chat, "text": md_text, "parse_mode": "Markdown"}, timeout=15)
        return r.ok and r.json().get("ok")
    except Exception:
        return False

# ====== Config / Sheets ======
SHEET_ID  = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_COMIS = "Comissoes_A_Pagar"
ABA_DESP  = "Despesas"
DATA_FMT  = "%d/%m/%Y"
TZ = pytz.timezone("America/Sao_Paulo")

st.set_page_config(page_title="Comissões | Salão JP", page_icon="💼", layout="wide")
st.title("💼 Pagamento de Comissões (fila)")

@st.cache_resource
def _open():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    creds = Credentials.from_service_account_info(info, scopes=[
        "https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"
    ])
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def _load():
    ss = _open()
    wsC = ss.worksheet(ABA_COMIS)
    wsD = ss.worksheet(ABA_DESP)
    dfC = get_as_dataframe(wsC, evaluate_formulas=True, header=0).dropna(how="all")
    dfD = get_as_dataframe(wsD, evaluate_formulas=True, header=0).dropna(how="all")
    return ss, wsC, wsD, dfC, dfD

def _proxima_terca(ref: date) -> date:
    w = ref.weekday()
    delta = (1 - w) % 7
    delta = 7 if delta == 0 else delta
    return ref + timedelta(days=delta)

ss, wsC, wsD, dfC, dfD = _load()

if dfC.empty:
    st.info("Nenhuma comissão cadastrada na fila.")
    st.stop()

# filtros
df = dfC.copy()
df["Vencimento"] = pd.to_datetime(df["Vencimento"], format=DATA_FMT, errors="coerce").dt.date
df["DataClientePagou"] = pd.to_datetime(df["DataClientePagou"], format=DATA_FMT, errors="coerce").dt.date
df["ValorComissao"] = pd.to_numeric(df["ValorComissao"], errors="coerce").fillna(0.0)
df["Status"] = df["Status"].fillna("Pendente")

colf1, colf2, colf3 = st.columns([1,1,1])
with colf1:
    default_venc = _proxima_terca(date.today())
    dia = st.date_input("Vencimento (mostrar até)", value=default_venc)
with colf2:
    funcs = [""] + sorted(df["Funcionario"].dropna().astype(str).unique().tolist())
    filtro_func = st.selectbox("Funcionário", funcs)
with colf3:
    apenas_pend = st.checkbox("Mostrar apenas Pendentes", value=True)

if apenas_pend:
    df = df[df["Status"].astype(str).str.lower() == "pendente"]
if filtro_func:
    df = df[df["Funcionario"] == filtro_func]
df = df[df["Vencimento"].isna() | (df["Vencimento"] <= dia)]

df_view = df[[
    "IDCom","Funcionario","Cliente","IDsFiado","ValorBase","Percentual","ValorComissao",
    "DataAtendimentoMin","DataClientePagou","FormaClientePagamento",
    "Vencimento","Status","Observacao"
]].copy()

st.dataframe(df_view.sort_values(["Vencimento","Funcionario"]), use_container_width=True, hide_index=True)

ids = st.multiselect("Selecione comissões para pagar", options=df["IDCom"].tolist())
colp1, colp2, colp3 = st.columns([1,1,1])
with colp1:
    data_pag = st.date_input("Data do pagamento da comissão", value=date.today())
with colp2:
    forma_pag = st.selectbox("Forma de pagamento", ["Dinheiro","Pix","Cartão","Transferência","Outro"])
with colp3:
    enviar_cards = st.checkbox("Enviar cards no Telegram", value=True)

btn = st.button("Pagar comissões selecionadas", use_container_width=True, disabled=not ids)
if btn:
    # prepara linhas p/ Despesas e marca como Pago
    headersD = wsD.row_values(1) or ["Data","Prestador","Descrição","Valor","Forma de Pagamento"]
    colmap = {h.lower(): h for h in headersD}
    H = lambda x: colmap.get(x.lower(), x)

    total = 0.0
    for _, r in dfC[dfC["IDCom"].isin(ids)].iterrows():
        valor = float(pd.to_numeric(r.get("ValorComissao", 0), errors="coerce"))
        if valor <= 0: continue
        total += valor
        linha = {
            H("Data"): data_pag.strftime(DATA_FMT),
            H("Prestador"): r.get("Funcionario",""),
            H("Descrição"): f"Comissão {r.get('Funcionario','')} — {r.get('Cliente','')} — IDs {r.get('IDsFiado','')}",
            H("Valor"): valor,
            H("Forma de Pagamento"): forma_pag,
        }
        wsD.append_row([linha.get(h,"") for h in headersD], value_input_option="USER_ENTERED")
        # marca como pago na fila
        idx = dfC.index[dfC["IDCom"] == r["IDCom"]][0] + 2  # +2 por header e 1-indexed
        wsC.update_cell(idx, dfC.columns.get_loc("Status")+1, "Pago")
        wsC.update_cell(idx, dfC.columns.get_loc("PagoEm")+1, data_pag.strftime(DATA_FMT))
        wsC.update_cell(idx, dfC.columns.get_loc("FormaPagamentoComissao")+1, forma_pag)

        if enviar_cards:
            ids_txt = str(r.get("IDsFiado",""))
            md = (
                "💼 *Comissão paga*\n"
                f"👨‍🔧 Funcionário: *{r.get('Funcionario','')}*\n"
                f"💵 Valor: *R$ {valor:.2f}*\n"
                f"📅 Data: *{data_pag.strftime(DATA_FMT)}*\n"
                f"🆔 IDs: `{ids_txt}`"
            )
            _tg(md)

    st.success(f"Comissões pagas! Total: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

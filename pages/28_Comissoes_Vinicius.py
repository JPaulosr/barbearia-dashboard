# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Trava anti-duplicação + Telegram idempotente

import streamlit as st
import pandas as pd
import gspread, hashlib, requests, pytz
from datetime import datetime
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# ==============================
# CONFIG
# ==============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DESPESAS = "Despesas"               # ajuste se usar outro nome
ABA_CACHE = "comissoes_cache"           # RefID, Data, Func, Descricao, Valor, Conta, MessageID, Timestamp
TZ = "America/Sao_Paulo"

# Colunas esperadas em Despesas (ajuste se necessário)
COLS_DESPESAS = ["Data", "Funcionário", "Descrição", "Valor", "Conta", "Tipo"]  # "Tipo" é opcional

# Telegram (em st.secrets)
TELEGRAM_TOKEN = st.secrets.get("TELEGRAM_TOKEN", "")
CHAT_JPAULO = st.secrets.get("TELEGRAM_CHAT_ID_JPAULO", "")
CHAT_VINICIUS = st.secrets.get("TELEGRAM_CHAT_ID_VINICIUS", "")

# ==============================
# CONEXÃO GOOGLE SHEETS
# ==============================
@st.cache_resource
def conectar():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def garantir_ws(ss, nome, header_cols=None):
    try:
        return ss.worksheet(nome)
    except gspread.exceptions.WorksheetNotFound:
        rows, cols = (100, 20)
        ws = ss.add_worksheet(title=nome, rows=str(rows), cols=str(cols))
        if header_cols:
            ws.update("A1", [header_cols])
        return ws

def ler_df(ws_name):
    ss = conectar()
    ws = garantir_ws(ss, ws_name)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df = df.dropna(how="all")
    if df.empty and ws_name == ABA_CACHE:
        df = pd.DataFrame(columns=["RefID","Data","Func","Descricao","Valor","Conta","MessageID","Timestamp"])
    df.columns = [str(c).strip() for c in df.columns]
    return df

def salvar_df(ws_name, df):
    ss = conectar()
    # cria a planilha se faltar (com cabeçalho quando aplicável)
    header = None
    if ws_name == ABA_CACHE:
        header = ["RefID","Data","Func","Descricao","Valor","Conta","MessageID","Timestamp"]
    ws = garantir_ws(ss, ws_name, header_cols=header)
    df = df.copy().fillna("")
    set_with_dataframe(ws, df, include_index=False, include_column_header=True, resize=True)

# ==============================
# UTILS
# ==============================
def parse_valor(v):
    """Aceita 'R$  16,00' ou 16/16.0 e devolve float."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("R$", "").replace(".", "").replace("\u00A0"," ").strip()
    s = s.replace(",", ".")
    try:
        return float(s)
    except:
        return 0.0

def str_data_br(dt_str):
    """Normaliza datas (dd/mm/yyyy)."""
    s = str(dt_str).strip()
    try:
        d = datetime.strptime(s, "%d/%m/%Y").date()
        return d.strftime("%d/%m/%Y")
    except:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                d = datetime.strptime(s, fmt).date()
                return d.strftime("%d/%m/%Y")
            except:
                pass
    return s

def build_refid(data_br, funcionario, descricao, valor, conta):
    base = f"{data_br}|{funcionario.strip().lower()}|{descricao.strip().lower()}|{round(valor,2):.2f}|{str(conta).strip().lower()}"
    return hashlib.md5(base.encode("utf-8")).hexdigest()

# ==============================
# TELEGRAM
# ==============================
def telegram_send_html(chat_id, html, disable_web_page_preview=True):
    if not TELEGRAM_TOKEN or not chat_id:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": html,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_web_page_preview
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("result", {}).get("message_id")
    except Exception as e:
        st.warning(f"Falha ao enviar Telegram: {e}")
        return None

def montar_card_html(data_br, funcionario, descricao, valor, conta):
    vtxt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    linhas = [
        "<b>Pagamento registrado</b> ✅",
        f"<b>Data:</b> {data_br}",
        f"<b>Funcionário:</b> {funcionario}",
        f"<b>Descrição:</b> {descricao}",
        f"<b>Valor:</b> <b>{vtxt}</b>",
        f"<b>Conta:</b> {conta}",
    ]
    return "\n".join(linhas)

# ==============================
# CACHE / IDEMPOTÊNCIA
# ==============================
def garantir_cache():
    try:
        dfc = ler_df(ABA_CACHE)
    except gspread.exceptions.WorksheetNotFound:
        dfc = pd.DataFrame(columns=["RefID","Data","Func","Descricao","Valor","Conta","MessageID","Timestamp"])
        salvar_df(ABA_CACHE, dfc)
    return dfc

def ja_registrado(refid, df_cache):
    if not df_cache.empty and "RefID" in df_cache.columns:
        return refid in set(df_cache["RefID"].astype(str))
    return False

def registrar_no_cache(refid, data_br, func, desc, valor, conta, message_id=None):
    dfc = garantir_cache()
    now = datetime.now(pytz.timezone(TZ)).strftime("%Y-%m-%d %H:%M:%S")
    nova = {
        "RefID": refid,
        "Data": data_br,
        "Func": func,
        "Descricao": desc,
        "Valor": valor,
        "Conta": conta,
        "MessageID": message_id or "",
        "Timestamp": now
    }
    dfc = pd.concat([dfc, pd.DataFrame([nova])], ignore_index=True)
    salvar_df(ABA_CACHE, dfc)

# ==============================
# REGISTRO DE PAGAMENTO (com trava)
# ==============================
def registrar_pagamento_unico(data_br, funcionario, descricao, valor_raw, conta, enviar_telegram=True, forcar=False):
    """
    Registra 1 linha em Despesas + envia Telegram de forma idempotente.
    - data_br: 'dd/mm/yyyy'
    - funcionario: 'Vinicius'
    - descricao: ex. 'Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025'
                  ou 'Caixinha Vinícius — Pago em 26/08/2025'
    - valor_raw: ex. 'R$  16,00' / 16 / 16.0
    - conta: 'Dinheiro', 'PIX', etc.
    """
    data_br = str_data_br(data_br)
    valor = parse_valor(valor_raw)
    func = str(funcionario).strip()
    desc = str(descricao).strip()
    conta = str(conta).strip()

    refid = build_refid(data_br, func, desc, valor, conta)

    # Despesas: garantir colunas
    df_desp = ler_df(ABA_DESPESAS)
    for c in COLS_DESPESAS:
        if c not in df_desp.columns:
            df_desp[c] = ""

    df_cache = garantir_cache()

    if not forcar and ja_registrado(refid, df_cache):
        st.info(f"🔒 Já existe registro com RefID {refid}. Nada gravado nem reenviado.")
        return {"refid": refid, "gravado": False, "reenviado": False}

    # Append em Despesas
    nova = {
        "Data": data_br,
        "Funcionário": func,
        "Descrição": desc,
        "Valor": valor,
        "Conta": conta
    }
    tipo = "Comissão" if "comiss" in desc.lower() else ("Caixinha" if "caixinha" in desc.lower() else "")
    if "Tipo" in df_desp.columns:
        nova["Tipo"] = tipo

    df_desp = pd.concat([df_desp, pd.DataFrame([nova])], ignore_index=True)
    salvar_df(ABA_DESPESAS, df_desp)

    # Telegram (idempotente por cache de RefID)
    message_id = None
    if enviar_telegram:
        html = montar_card_html(data_br, func, desc, valor, conta)
        if func.lower().startswith("vinici"):
            if CHAT_VINICIUS:
                mid = telegram_send_html(CHAT_VINICIUS, html)
                if mid: message_id = f"vinicius:{mid}"
            if CHAT_JPAULO:
                telegram_send_html(CHAT_JPAULO, "📣 <b>Pagamento registrado (Vinícius)</b>\n" + html)
        else:
            if CHAT_JPAULO:
                mid = telegram_send_html(CHAT_JPAULO, html)
                if mid: message_id = f"jpaulo:{mid}"

    registrar_no_cache(refid, data_br, func, desc, valor, conta, message_id=message_id)
    st.success(f"✅ Registro salvo em Despesas. RefID: {refid}")
    return {"refid": refid, "gravado": True, "reenviado": False}

# ==============================
# LOTE DE EXEMPLO (usa as linhas que você mandou)
# ==============================
def processar_lote_exemplo():
    linhas = [
        ("02/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 19/08/2025","R$  16,00","Dinheiro"),
        ("12/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 19/08/2025","R$  20,00","Dinheiro"),
        ("13/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 19/08/2025","R$  16,00","Dinheiro"),
        ("14/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 19/08/2025","R$  35,00","Dinheiro"),
        ("15/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 19/08/2025","R$  12,50","Dinheiro"),
        ("16/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 19/08/2025","R$  75,00","Dinheiro"),
        ("17/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 19/08/2025","R$  81,00","Dinheiro"),
        ("29/07/2025","Vinicius","Comissão Vinícius — Comp 07/2025 — Pago em 19/08/2025","R$  12,50","Dinheiro"),
        ("08/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025","R$  38,50","Dinheiro"),
        ("16/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025","R$  12,50","Dinheiro"),
        ("19/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025","R$  19,50","Dinheiro"),
        ("20/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025","R$  41,00","Dinheiro"),
        ("20/08/2025","Vinicius","Caixinha Vinícius — Pago em 26/08/2025","R$  5,00","Dinheiro"),
        ("08/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025","R$  43,50","Dinheiro"),
        ("16/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025","R$  12,50","Dinheiro"),
        ("19/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025","R$  19,50","Dinheiro"),
        ("20/08/2025","Vinicius","Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025","R$  41,00","Dinheiro"),
        ("20/08/2025","Vinicius","Caixinha Vinícius — Pago em 26/08/2025","R$  5,00","Dinheiro"),
    ]
    st.write("Processando lote com trava anti-duplicação…")
    for (d,f,desc,v,conta) in linhas:
        registrar_pagamento_unico(d, f, desc, v, conta, enviar_telegram=True, forcar=False)

# ==============================
# UI (opcional)
# ==============================
def ui():
    st.title("Pagamento de Comissão / Caixinha — Trava + Telegram")
    col1, col2 = st.columns(2)
    with col1:
        data_br = st.text_input("Data (dd/mm/aaaa)", "20/08/2025")
        funcionario = st.text_input("Funcionário", "Vinicius")
        descricao = st.text_input("Descrição", "Comissão Vinícius — Comp 08/2025 — Pago em 26/08/2025")
    with col2:
        valor = st.text_input("Valor", "R$  41,00")
        conta = st.text_input("Conta", "Dinheiro")
        enviar_tg = st.checkbox("Enviar Telegram", value=True)
        forcar = st.checkbox("Forçar (ignorar trava)", value=False)

    if st.button("Registrar pagamento"):
        out = registrar_pagamento_unico(data_br, funcionario, descricao, valor, conta, enviar_telegram=enviar_tg, forcar=forcar)
        st.write(out)

    st.divider()
    if st.button("Processar lote (exemplo com as linhas que você enviou)"):
        processar_lote_exemplo()

# Para usar como página do Streamlit, deixe assim:
if __name__ == "__main__":
    ui()

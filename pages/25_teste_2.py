import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
import requests

st.set_page_config(page_title="🔔 Teste de Notificação Telegram", layout="wide")
st.title("🔔 Teste de Notificação Telegram")

# ======================
# CONFIG PLANILHA
# ======================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_STATUS_ALVOS = [
    "clientes_status", "Clientes_status", "clientes status",
    "clientes_status_feminino", "status_feminino"
]

# ======================
# TELEGRAM (lê dos secrets, com fallback na UI)
# ======================
TOKEN_DEFAULT = st.secrets.get("TELEGRAM_BOT_TOKEN", "")
CHAT_DEFAULT  = st.secrets.get("TELEGRAM_CHAT_ID", "")

with st.sidebar:
    st.subheader("⚙️ Configuração do Telegram")
    TELEGRAM_BOT_TOKEN = st.text_input("BOT TOKEN", value=TOKEN_DEFAULT, type="password")
    TELEGRAM_CHAT_ID   = st.text_input("CHAT ID", value=str(CHAT_DEFAULT))
    st.caption("Se preferir, salve em *Secrets* como TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID.")

# ======================
# Conexão com Google Sheets (com tratamento de ausência de secret)
# ======================
def conectar_sheets():
    info = st.secrets.get("gcp_service_account")
    if not info:
        st.warning("⚠️ Secret `gcp_service_account` não encontrado. "
                   "Sem ele não dá para ler a planilha. Configure nos Secrets.")
        return None
    creds = Credentials.from_service_account_info(
        info,
        scopes=["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def abrir_primeira_aba_existente(sh, nomes):
    existentes = {ws.title.strip().lower(): ws for ws in sh.worksheets()}
    for nome in nomes:
        key = nome.strip().lower()
        if key in existentes:
            return existentes[key]
    return None

def send_telegram(token: str, chat_id: str, text: str):
    if not token or not chat_id:
        return False, "Token/ChatID ausentes"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": int(chat_id), "text": text}, timeout=15)
        if r.ok:
            return True, "ok"
        else:
            return False, f"{r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)

# ======================
# UI / Execução
# ======================
gc = conectar_sheets()
if gc:
    sh = gc.open_by_key(SHEET_ID)
    ws = abrir_primeira_aba_existente(sh, ABA_STATUS_ALVOS)
    if not ws:
        st.error(f"Não encontrei nenhuma aba entre: {ABA_STATUS_ALVOS}.")
        st.stop()

    df_status = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")
    if df_status.empty:
        st.info("Aba de status vazia.")
    else:
        # Normaliza
        df_status.columns = [str(c).strip() for c in df_status.columns]
        if not {"Cliente","Status"}.issubset(df_status.columns):
            st.error("A aba precisa ter as colunas 'Cliente' e 'Status'.")
            st.stop()

        df_status["Cliente"] = df_status["Cliente"].astype(str).str.strip()
        df_status["Status"]  = df_status["Status"].astype(str).str.strip()

        st.subheader("📋 Status atual (amostra)")
        st.dataframe(df_status.head(50), use_container_width=True)

        df_alerta = df_status[df_status["Status"].isin(["Pouco atrasado", "Muito atrasado"])].copy()
        st.write(f"Clientes em alerta: **{len(df_alerta)}**")

        colA, colB = st.columns(2)
        with colA:
            if st.button("🚨 Enviar notificações agora"):
                if df_alerta.empty:
                    st.info("Nenhum cliente com atraso no momento.")
                else:
                    resultados = []
                    for _, row in df_alerta.iterrows():
                        cliente = row["Cliente"]
                        status  = row["Status"]
                        msg = f"⏰ Alerta: {cliente} está {status}."
                        ok, resp = send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
                        resultados.append({"Cliente": cliente, "Status": status, "Resultado": "Enviado" if ok else f"Erro: {resp}"})
                    st.success("Processo concluído.")
                    st.dataframe(pd.DataFrame(resultados))
        with colB:
            st.info("Dica: depois de testar, gere um **novo token** no @BotFather (/token) por segurança.")
else:
    st.stop()

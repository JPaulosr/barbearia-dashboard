import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
import requests
from datetime import datetime

st.set_page_config(page_title="🔔 Notificação Telegram", layout="wide")
st.title("🔔 Teste de Notificação Telegram")

# ======================
# CONFIGURAÇÕES
# ======================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_STATUS = "clientes_status"

TELEGRAM_BOT_TOKEN = st.secrets["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = int(st.secrets["TELEGRAM_CHAT_ID"])

def conectar_sheets():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
    return r.ok, r.text

# ======================
# LER STATUS DOS CLIENTES
# ======================
gc = conectar_sheets()
ws = gc.open_by_key(SHEET_ID).worksheet(ABA_STATUS)
df_status = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")

if not df_status.empty:
    df_status = df_status[["Cliente","Status"]].copy()
    df_status["Cliente"] = df_status["Cliente"].astype(str).str.strip()
    df_status["Status"] = df_status["Status"].astype(str).str.strip()

    st.subheader("📋 Status atual dos clientes")
    st.dataframe(df_status)

    # Filtra atrasados
    df_alerta = df_status[df_status["Status"].isin(["Pouco atrasado", "Muito atrasado"])]

    if st.button("🚨 Enviar notificações agora"):
        if df_alerta.empty:
            st.info("Nenhum cliente atrasado no momento ✅")
        else:
            enviados = []
            for _, row in df_alerta.iterrows():
                cliente = row["Cliente"]
                status = row["Status"]
                msg = f"⏰ Alerta: Cliente {cliente} está {status}!"
                ok, resp = send_telegram(msg)
                if ok:
                    enviados.append((cliente, status, "Enviado"))
                else:
                    enviados.append((cliente, status, f"Erro: {resp}"))
            st.success("Notificações processadas!")
            st.dataframe(pd.DataFrame(enviados, columns=["Cliente","Status","Resultado"]))
else:
    st.warning("⚠️ Nenhum dado encontrado na aba de status.")

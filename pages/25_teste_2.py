# 25_Teste_Telegram.py
import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="🔔 Teste de Notificação Telegram", layout="wide")
st.title("🔔 Teste de Notificação Telegram")

# ======================
# Lê TELEGRAM dos Secrets (aceita 2 formatos)
# ======================
tg_block = st.secrets.get("TELEGRAM", {})
TOKEN_DEFAULT = tg_block.get("bot_token") or st.secrets.get("TELEGRAM_BOT_TOKEN", "")
CHAT_DEFAULT  = tg_block.get("chat_id")   or st.secrets.get("TELEGRAM_CHAT_ID", "")

with st.sidebar:
    st.subheader("⚙️ Configuração do Telegram")
    TELEGRAM_BOT_TOKEN = st.text_input("BOT TOKEN", value=TOKEN_DEFAULT, type="password")
    TELEGRAM_CHAT_ID   = st.text_input("CHAT ID", value=str(CHAT_DEFAULT))
    st.caption("Você pode salvar no Secrets como [TELEGRAM] bot_token/chat_id ou TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID.")

def send_telegram(token: str, chat_id: str, text: str):
    if not token or not chat_id:
        return False, "Token/ChatID ausentes"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        # aceita chat_id numérico ou string (grupo começa com -100...)
        payload = {"chat_id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id,
                   "text": text}
        r = requests.post(url, json=payload, timeout=15)
        if r.ok:
            return True, "ok"
        else:
            return False, f"{r.status_code}: {r.text[:300]}"
    except Exception as e:
        return False, str(e)

# ======================
# Teste rápido (SEM Sheets)
# ======================
st.subheader("✅ Envio rápido (sem planilha)")
col1, col2 = st.columns([3,1])
with col1:
    msg = st.text_input("Mensagem", "🚀 Teste do Dashboard JP!")
with col2:
    if st.button("Enviar agora"):
        ok, resp = send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, msg)
        st.success("Mensagem enviada!") if ok else st.error(f"Falhou: {resp}")

st.divider()

# ======================
# (Opcional) Ler planilha e enviar alertas
# Só tenta se a credencial MAIÚSCULA existir
# ======================
if "GCP_SERVICE_ACCOUNT" in st.secrets:
    import gspread
    from gspread_dataframe import get_as_dataframe
    from google.oauth2.service_account import Credentials

    SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
    ABA_STATUS_ALVOS = [
        "clientes_status", "Clientes_status", "clientes status",
        "clientes_status_feminino", "status_feminino"
    ]

    st.subheader("📒 Enviar alertas a partir da planilha (opcional)")
    try:
        creds = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SHEET_ID)
        existentes = {ws.title.strip().lower(): ws for ws in sh.worksheets()}
        ws = None
        for nome in ABA_STATUS_ALVOS:
            if nome.strip().lower() in existentes:
                ws = existentes[nome.strip().lower()]
                break

        if ws is None:
            st.info(f"Não encontrei nenhuma aba entre: {ABA_STATUS_ALVOS}.")
        else:
            df = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")
            if df.empty:
                st.info("Aba vazia.")
            else:
                df.columns = [str(c).strip() for c in df.columns]
                if not {"Cliente", "Status"}.issubset(df.columns):
                    st.error("A aba precisa ter as colunas 'Cliente' e 'Status'.")
                else:
                    df["Cliente"] = df["Cliente"].astype(str).str.strip()
                    df["Status"]  = df["Status"].astype(str).str.strip()
                    df_alerta = df[df["Status"].isin(["Pouco atrasado", "Muito atrasado"])].copy()

                    st.write(f"Clientes em alerta: **{len(df_alerta)}**")
                    st.dataframe(df_alerta.head(50), use_container_width=True)

                    if st.button("🚨 Enviar notificações da planilha"):
                        if df_alerta.empty:
                            st.info("Nenhum cliente com atraso no momento.")
                        else:
                            resultados = []
                            for _, row in df_alerta.iterrows():
                                cliente = row["Cliente"]
                                status = row["Status"]
                                text = f"⏰ Alerta: {cliente} está {status}."
                                ok, resp = send_telegram(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, text)
                                resultados.append({"Cliente": cliente, "Status": status,
                                                   "Resultado": "Enviado" if ok else f"Erro: {resp}"})
                            st.success("Concluído.")
                            st.dataframe(pd.DataFrame(resultados), use_container_width=True)
    except Exception as e:
        st.error(f"Erro ao acessar planilha: {e}")
else:
    st.info("Para usar a leitura da planilha, adicione [GCP_SERVICE_ACCOUNT] nos Secrets. "
            "O teste rápido acima funciona mesmo sem isso. 😉")

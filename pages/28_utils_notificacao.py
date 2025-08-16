# utils_notificacao.py
import requests, streamlit as st

def notificar(mensagem: str) -> bool:
    """Envia notificação Telegram usando dados do secrets.toml"""
    tg = st.secrets.get("TELEGRAM", {})
    token = tg.get("bot_token")
    chat_id = tg.get("chat_id")

    if not token or not chat_id:
        st.error("⚠️ Configuração de Telegram ausente em [TELEGRAM].")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": int(chat_id), "text": mensagem}

    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.ok:
            return True
        st.error(f"Falhou: {r.status_code} - {r.text}")
        return False
    except Exception as e:
        st.error(f"Erro: {e}")
        return False

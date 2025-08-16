# 25_Teste_Telegram.py
import streamlit as st
import requests

st.set_page_config(page_title="🔔 Teste de Notificação Telegram", layout="wide")
st.title("🔔 Teste de Notificação Telegram")

tg = st.secrets.get("TELEGRAM", {})
TOKEN_DEFAULT = tg.get("bot_token", "")
CHAT_DEFAULT  = tg.get("chat_id", "")

with st.sidebar:
    st.subheader("⚙️ Configuração do Telegram")
    token = st.text_input("BOT TOKEN", value=TOKEN_DEFAULT, type="password")
    chat_id = st.text_input("CHAT ID (numérico ou -100... p/ grupo)", value=str(CHAT_DEFAULT))

def send_telegram(token: str, chat_id: str, text: str):
    if not token or not chat_id:
        return False, "Token/ChatID ausentes"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # aceita numérico ou string (ex.: -100123..., ou @canal não recomendado)
    payload = {"chat_id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id,
               "text": text}
    try:
        r = requests.post(url, json=payload, timeout=15)
        if r.ok:
            return True, "ok"
        return False, f"{r.status_code}: {r.text}"
    except Exception as e:
        return False, str(e)

def get_updates(token: str):
    if not token:
        return False, "Informe o token."
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        r = requests.get(url, timeout=15)
        if not r.ok:
            return False, f"{r.status_code}: {r.text}"
        data = r.json()
        if not data.get("ok"):
            return False, data
        # Extrai chats únicos
        chats = []
        seen = set()
        for upd in data.get("result", []):
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id")
            title = chat.get("title") or chat.get("username") or chat.get("first_name")
            ctype = chat.get("type")
            if cid and cid not in seen:
                seen.add(cid)
                chats.append({"chat_id": str(cid), "tipo": ctype, "titulo/usuario": title})
        if not chats:
            return False, "Sem updates. Envie /start para o bot (ou uma msg no grupo) e clique de novo."
        return True, chats
    except Exception as e:
        return False, str(e)

st.subheader("✅ Envio rápido (sem planilha)")
msg = st.text_input("Mensagem", "🚀 Teste do Dashboard JP!")
col1, col2 = st.columns([1,1])
with col1:
    if st.button("Enviar agora"):
        ok, resp = send_telegram(token, chat_id, msg)
        st.success("Mensagem enviada!") if ok else st.error(f"Falhou: {resp}")
with col2:
    if st.button("🔎 Descobrir chat_id"):
        ok, resp = get_updates(token)
        if ok:
            st.success("Chats encontrados pela API:")
            st.table(resp)  # mostra os chat_id válidos
            st.info("Copie o chat_id correto da tabela e cole no campo ao lado.")
        else:
            st.error(f"Não foi possível obter updates: {resp}")

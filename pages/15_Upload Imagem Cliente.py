import streamlit as st
import requests
import io
from PIL import Image
from urllib.parse import urlencode

# ========= CONFIGURAR SEUS DADOS =========
CLIENT_ID = st.secrets["OAUTH_CLIENT_ID"]
CLIENT_SECRET = st.secrets["OAUTH_CLIENT_SECRET"]
REDIRECT_URI = st.secrets["OAUTH_REDIRECT_URI"]
FOLDER_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

SCOPE = "https://www.googleapis.com/auth/drive.file"

# ========= FUNÇÕES =========

def gerar_link_autenticacao():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent"
    }
    return f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"

def trocar_codigo_por_token(auth_code):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    response = requests.post(token_url, data=data)
    return response.json()

def upload_para_drive(access_token, file_bytes, nome_arquivo, mimetype):
    headers = {"Authorization": f"Bearer {access_token}"}
    metadata = {
        "name": nome_arquivo,
        "parents": [FOLDER_ID]
    }

    files = {
        "data": ("metadata", io.BytesIO(str(metadata).encode()), "application/json"),
        "file": (nome_arquivo, file_bytes, mimetype)
    }

    upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
    response = requests.post(upload_url, headers=headers, files=files)
    return response.json()

# ========= INTERFACE =========

st.set_page_config("Upload de Imagem", layout="wide")
st.title("📸 Upload com Google OAuth (pessoal)")

st.markdown("1️⃣ Clique abaixo para autenticar com sua conta Google:")
st.markdown(f"[👉 Autenticar com Google]({gerar_link_autenticacao()})")

auth_code = st.text_input("2️⃣ Cole aqui o código de autorização que o Google te deu:", type="default")

if auth_code:
    token_info = trocar_codigo_por_token(auth_code)

    if "access_token" in token_info:
        st.success("✅ Autenticação concluída!")
        access_token = token_info["access_token"]

        cliente_nome = st.text_input("Nome do cliente:")
        imagem = st.file_uploader("Selecione a imagem", type=["jpg", "jpeg", "png"])

        if cliente_nome and imagem:
            extensao = imagem.name.split(".")[-1].lower()
            mimetype = imagem.type
            nome_arquivo = f"{cliente_nome.strip().lower()}.{extensao}"
            file_bytes = imagem.read()

            resultado = upload_para_drive(access_token, file_bytes, nome_arquivo, mimetype)

            if "id" in resultado:
                link_final = f"https://drive.google.com/uc?export=view&id={resultado['id']}"
                st.image(Image.open(io.BytesIO(file_bytes)), width=300)
                st.success(f"Imagem enviada com sucesso!\n[🔗 Ver imagem]({link_final})")
            else:
                st.error("❌ Falha no upload. Detalhes:")
                st.json(resultado)
    else:
        st.error("❌ Código inválido ou expirado.")
        st.json(token_info)

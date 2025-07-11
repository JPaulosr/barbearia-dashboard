import streamlit as st
from google_auth_oauthlib.flow import Flow
import google.auth.transport.requests
import requests
import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import tempfile

st.set_page_config(layout="wide")
st.title("📸 Upload de Imagem para o Google Drive")

st.info("🔹 Autentique sua conta Google para salvar no seu próprio Drive")

# === CARREGA SEGREDOS DO OAUTH ===
client_id = st.secrets["GOOGLE_OAUTH"]["client_id"]
client_secret = st.secrets["GOOGLE_OAUTH"]["client_secret"]
redirect_uri = st.secrets["GOOGLE_OAUTH"]["redirect_uris"][0]

# === CONFIGURA O FLOW DO OAUTH ===
flow = Flow.from_client_config(
    {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    },
    scopes=["https://www.googleapis.com/auth/drive.file"]
)
flow.redirect_uri = redirect_uri

# === ETAPA 1: MOSTRA LINK DE AUTORIZAÇÃO ===
auth_url, _ = flow.authorization_url(prompt='consent', include_granted_scopes='true')
st.markdown(f"[Clique aqui para autorizar o app com sua conta Google]({auth_url})")

# === ETAPA 2: INSERE CÓDIGO DE AUTORIZAÇÃO ===
codigo = st.text_input("Cole o código que você recebeu aqui:")

# === ETAPA 3: UPLOAD DA IMAGEM ===
nome_cliente = st.text_input("🧍 Nome do cliente")
imagem = st.file_uploader("📷 Escolha uma imagem do cliente", type=["jpg", "jpeg", "png"])

if st.button("🚀 Fazer upload"):
    if not codigo or not imagem or not nome_cliente:
        st.error("Preencha todos os campos antes de prosseguir.")
    else:
        try:
            # Troca o código de autorização por tokens
            flow.fetch_token(code=codigo)
            credenciais = flow.credentials

            # Inicializa o serviço do Drive
            drive_service = build("drive", "v3", credentials=credenciais)

            # Salva o arquivo temporariamente
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
                tmp.write(imagem.read())
                tmp_path = tmp.name

            # Define metadados
            metadata = {
                "name": f"{nome_cliente.lower().strip().replace(' ', '_')}.jpg",
                "mimeType": "image/jpeg"
            }

            media = MediaFileUpload(tmp_path, mimetype="image/jpeg")

            # Faz upload no Drive do usuário autenticado
            uploaded = drive_service.files().create(
                body=metadata,
                media_body=media,
                fields="id"
            ).execute()

            # Gera link compartilhável
            file_id = uploaded.get("id")
            shareable_url = f"https://drive.google.com/uc?export=download&id={file_id}"

            st.success("✅ Imagem enviada com sucesso!")
            st.code(shareable_url)

            # Limpa o arquivo temporário
            os.remove(tmp_path)

        except Exception as e:
            st.error(f"Erro ao autenticar ou fazer upload: {e}")

import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import requests
import io

st.set_page_config(page_title="Upload Imagem Cliente", layout="centered")

st.title("📸 Upload de Imagem para o Google Drive")

# ======= DADOS DE AUTENTICAÇÃO ========
client_id = st.secrets["GOOGLE_OAUTH"]["client_id"]
client_secret = st.secrets["GOOGLE_OAUTH"]["client_secret"]
redirect_uri = st.secrets["GOOGLE_OAUTH"]["redirect_uris"][0]

# ======= ETAPA 1: GERA LINK DE AUTORIZAÇÃO ========
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

auth_url, _ = flow.authorization_url(
    prompt='consent',
    include_granted_scopes='true',
    redirect_uri=redirect_uri
)

st.markdown(f"[🔐 Clique aqui para autorizar com Google]({auth_url})")

# ======= ETAPA 2: COLAR O CÓDIGO DE AUTORIZAÇÃO ========
code = st.text_input("Cole o código de autorização aqui")

if code:
    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials

        # Inicializa o serviço do Google Drive
        service = build("drive", "v3", credentials=credentials)

        # ======= UPLOAD DA IMAGEM ========
        uploaded_file = st.file_uploader("Selecione a imagem do cliente", type=["jpg", "jpeg", "png"])
        nome_cliente = st.text_input("Nome do cliente (para nomear o arquivo)")

        if uploaded_file and nome_cliente:
            file_metadata = {"name": f"{nome_cliente}.png", "parents": ["1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"]}  # ID da pasta no Drive
            media = MediaIoBaseUpload(uploaded_file, mimetype=uploaded_file.type)

            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink"
            ).execute()

            st.success("✅ Imagem enviada com sucesso!")
            st.markdown(f"[🔗 Ver imagem no Drive]({file['webViewLink']})")
    except Exception as e:
        st.error(f"Erro na autenticação ou envio: {e}")

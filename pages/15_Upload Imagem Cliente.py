import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials
import io
import base64

st.set_page_config(page_title="📸 Upload de Imagem", layout="centered")
st.title("📸 Upload de Imagem para o Google Drive")

st.info("🔹 Autentique sua conta Google para salvar no seu próprio Drive")

# ==== OAuth: fluxo para autenticação ====
client_id = st.secrets["GOOGLE_OAUTH"]["client_id"]
client_secret = st.secrets["GOOGLE_OAUTH"]["client_secret"]
redirect_uri = st.secrets["GOOGLE_OAUTH"]["redirect_uris"][0]

flow = Flow.from_client_config(
    {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    },
    scopes=["https://www.googleapis.com/auth/drive.file"],
)
flow.redirect_uri = redirect_uri

auth_url, _ = flow.authorization_url(prompt="consent", include_granted_scopes="true")

st.markdown(f"[Clique aqui para autorizar o app com sua conta Google]({auth_url})")

# ==== Entrada do código de autorização ====
auth_code = st.text_input("Cole o código que você recebeu aqui:")

uploaded_file = st.file_uploader("Selecione a imagem do cliente")
nome_cliente = st.text_input("Nome do cliente (será o nome da imagem)")

if st.button("Fazer Upload"):
    if not auth_code:
        st.error("⚠️ Você precisa colar o código de autenticação.")
    elif not uploaded_file or not nome_cliente:
        st.error("⚠️ Selecione uma imagem e informe o nome do cliente.")
    else:
        try:
            # Troca o código por token
            flow.fetch_token(code=auth_code)
            creds = flow.credentials

            # Cria o serviço do Drive com o token
            drive_service = build("drive", "v3", credentials=creds)

            # Prepara o arquivo para upload
            file_metadata = {
                "name": f"{nome_cliente}.jpg",
                "parents": ["PASTE_AQUI_ID_DA_PASTA"]
            }
            media = MediaIoBaseUpload(uploaded_file, mimetype=uploaded_file.type)

            uploaded = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id"
            ).execute()

            link = f"https://drive.google.com/uc?export=download&id={uploaded['id']}"
            st.success("✅ Imagem enviada com sucesso!")
            st.markdown(f"[🔗 Acessar imagem]({link})")
        except Exception as e:
            st.error(f"Erro ao autenticar ou fazer upload: {e}")

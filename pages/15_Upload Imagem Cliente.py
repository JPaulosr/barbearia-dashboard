import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

st.set_page_config(page_title="📸 Upload de Imagem para o Google Drive")
st.title("📸 Upload de Imagem para o Google Drive")

# =====================
# Corrigir chave do secrets
# =====================
secrets_raw = st.secrets["GCP_UPLOAD"]

# Monta dicionário com private_key corrigida
upload_info = {
    "type": secrets_raw["type"],
    "project_id": secrets_raw["project_id"],
    "private_key_id": secrets_raw["private_key_id"],
    "private_key": secrets_raw["private_key"].replace("\\n", "\n"),  # <-- ESSA LINHA É FUNDAMENTAL
    "client_email": secrets_raw["client_email"],
    "client_id": secrets_raw["client_id"],
    "auth_uri": secrets_raw["auth_uri"],
    "token_uri": secrets_raw["token_uri"],
    "auth_provider_x509_cert_url": secrets_raw["auth_provider_x509_cert_url"],
    "client_x509_cert_url": secrets_raw["client_x509_cert_url"]
}

# =====================
# Autenticação com Google
# =====================
scopes = ["https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(upload_info, scopes=scopes)
service = build("drive", "v3", credentials=credentials)

# =====================
# Configuração da pasta
# =====================
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

# =====================
# Upload da Imagem
# =====================
st.subheader("1️⃣ Escolha o cliente e envie a imagem")

cliente_nome = st.text_input("Nome do Cliente")
arquivo = st.file_uploader("Escolha a imagem do cliente", type=["jpg", "jpeg", "png"])

if st.button("📤 Enviar imagem para o Drive"):
    if not cliente_nome:
        st.warning("⚠️ Por favor, digite o nome do cliente.")
    elif not arquivo:
        st.warning("⚠️ Por favor, selecione uma imagem.")
    else:
        try:
            nome_arquivo = f"{cliente_nome.strip().lower()}.jpg"
            file_stream = io.BytesIO(arquivo.read())
            media = MediaIoBaseUpload(file_stream, mimetype="image/jpeg")

            file_metadata = {
                "name": nome_arquivo,
                "parents": [PASTA_ID]
            }

            uploaded = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id"
            ).execute()

            st.success(f"✅ Imagem enviada com sucesso para o Google Drive! ID: {uploaded['id']}")

        except Exception as e:
            st.error(f"❌ Erro no upload: {e}")

import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

st.set_page_config(page_title="📸 Upload de Imagem para o Google Drive")
st.title("📸 Upload de Imagem para o Google Drive")

# =====================
# Autenticação (conta de serviço para UPLOAD)
# =====================
upload_info_secret = st.secrets["GCP_UPLOAD"]

# ⚠️ Reconstrói manualmente o dicionário (sem deepcopy)
upload_info = {
    "type": upload_info_secret["type"],
    "project_id": upload_info_secret["project_id"],
    "private_key_id": upload_info_secret["private_key_id"],
    "private_key": upload_info_secret["private_key"].replace("\\n", "\n"),
    "client_email": upload_info_secret["client_email"],
    "client_id": upload_info_secret["client_id"],
    "auth_uri": upload_info_secret["auth_uri"],
    "token_uri": upload_info_secret["token_uri"],
    "auth_provider_x509_cert_url": upload_info_secret["auth_provider_x509_cert_url"],
    "client_x509_cert_url": upload_info_secret["client_x509_cert_url"]
}

scopes = ["https://www.googleapis.com/auth/drive"]
credentials = Credentials.from_service_account_info(upload_info, scopes=scopes)
service = build("drive", "v3", credentials=credentials)

# =====================
# ID da pasta no Drive onde salvar as imagens
# =====================
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

# =====================
# Interface do usuário
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
            # Prepara o arquivo para upload
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

            st.success(f"✅ Imagem enviada com sucesso para o Google Drive (ID: {uploaded['id']})")

        except Exception as e:
            st.error(f"❌ Erro ao fazer upload: {e}")

import streamlit as st
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

st.set_page_config(page_title="Upload de Imagem", layout="wide")

st.markdown("## 📸 Upload de Imagem para o Google Drive")
st.markdown("🔒 Envie o arquivo `.json` da conta de serviço")

# ========= AUTENTICAÇÃO GOOGLE DRIVE ========= #
try:
    upload_info = dict(st.secrets["GCP_UPLOAD"])
    upload_info["private_key"] = upload_info["private_key"].replace("\\n", "\n")

    scopes = ["https://www.googleapis.com/auth/drive"]
    credentials = Credentials.from_service_account_info(upload_info, scopes=scopes)
    service = build("drive", "v3", credentials=credentials)

except Exception as e:
    st.error("Erro ao autenticar com o Google Drive")
    st.exception(e)
    st.stop()

# ========= CONFIGURAÇÕES ========= #
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"  # ID da sua pasta no Drive
TIPOS_PERMITIDOS = ["image/jpeg", "image/png"]
MAX_MB = 10

# ========= UPLOAD ========= #
arquivo = st.file_uploader("📁 Enviar imagem do cliente", type=["jpg", "jpeg", "png"])

if arquivo:
    if arquivo.type not in TIPOS_PERMITIDOS:
        st.warning("Tipo de arquivo não suportado. Envie JPEG ou PNG.")
        st.stop()

    if arquivo.size > MAX_MB * 1024 * 1024:
        st.warning("Arquivo muito grande. Máximo permitido: 10MB.")
        st.stop()

    nome_cliente = st.text_input("Nome do cliente (sem espaços, sem acento):")
    if nome_cliente:
        nome_final = f"{nome_cliente}.png"

        # Monta mídia e metadados
        media = MediaIoBaseUpload(arquivo, mimetype=arquivo.type)
        file_metadata = {
            "name": nome_final,
            "parents": [PASTA_ID]
        }

        try:
            arquivo_drive = service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink"
            ).execute()

            st.success("✅ Imagem enviada com sucesso!")
            st.markdown(f"[🔗 Ver imagem no Google Drive]({arquivo_drive['webViewLink']})")

        except Exception as e:
            st.error("Erro ao enviar imagem para o Google Drive")
            st.exception(e)

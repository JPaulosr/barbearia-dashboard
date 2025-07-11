import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

st.set_page_config(page_title="Upload de Imagem", layout="wide")
st.title("📸 Upload de Imagem para o Google Drive")

# ===== CONFIGURAÇÕES ===== #
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"  # ID da pasta no Drive
TIPOS_PERMITIDOS = ["image/jpeg", "image/png"]
MAX_MB = 10

# ===== AUTENTICAÇÃO DIRETA COM SEGREDO FUNCIONAL ===== #
try:
    credentials = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"],
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
except Exception as e:
    st.error("❌ Falha na autenticação com o Google")
    st.exception(e)
    st.stop()

# ===== FORMULÁRIO DE ENVIO ===== #
arquivo = st.file_uploader("Selecione a imagem do cliente", type=["jpg", "jpeg", "png"])
nome_cliente = st.text_input("Nome do cliente (sem espaços):")

if arquivo and nome_cliente:
    if arquivo.type not in TIPOS_PERMITIDOS:
        st.warning("Tipo de arquivo não suportado. Use JPG ou PNG.")
        st.stop()

    if arquivo.size > MAX_MB * 1024 * 1024:
        st.warning("Arquivo maior que o limite de 10MB.")
        st.stop()

    # Nome do arquivo no Drive
    nome_final = f"{nome_cliente}.png"

    # Prepara mídia e metadados
    media = MediaIoBaseUpload(arquivo, mimetype=arquivo.type)
    metadata = {
        "name": nome_final,
        "parents": [PASTA_ID]
    }

    try:
        file = service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink"
        ).execute()

        st.success("✅ Imagem enviada com sucesso!")
        st.markdown(f"[🔗 Ver imagem no Google Drive]({file['webViewLink']})")

    except Exception as e:
        st.error("Erro ao enviar a imagem para o Google Drive")
        st.exception(e)

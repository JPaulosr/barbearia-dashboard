import streamlit as st
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

st.set_page_config(page_title="📸 Upload de Imagem para o Google Drive", layout="wide")
st.title("📸 Upload de Imagem para o Google Drive")

# ======= CONFIGURAÇÕES ======= #
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"  # ID da pasta 'Fotos clientes'
TIPOS_PERMITIDOS = ["image/jpeg", "image/png"]
MAX_MB = 10

# ======= AUTENTICAÇÃO COM SECRETS ======= #
try:
    credentials = Credentials.from_service_account_info(
        st.secrets["GCP_UPLOAD"],
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=credentials)
except Exception as e:
    st.error("❌ Erro na autenticação com o Google Drive")
    st.exception(e)
    st.stop()

# ======= FORMULÁRIO DE UPLOAD ======= #
arquivo = st.file_uploader("📂 Selecione a imagem do cliente", type=["jpg", "jpeg", "png"])
nome_cliente = st.text_input("Nome do cliente (sem espaços):")

if arquivo and nome_cliente:
    if arquivo.type not in TIPOS_PERMITIDOS:
        st.warning("Tipo de imagem inválido. Use JPG ou PNG.")
        st.stop()

    if arquivo.size > MAX_MB * 1024 * 1024:
        st.warning("Arquivo maior que o limite de 10MB.")
        st.stop()

    nome_final = f"{nome_cliente.lower().strip()}.jpg"

    media = MediaIoBaseUpload(arquivo, mimetype=arquivo.type)
    metadata = {
        "name": nome_final,
        "parents": [PASTA_ID]
    }

    try:
        uploaded = service.files().create(
            body=metadata,
            media_body=media,
            fields="id, webViewLink"
        ).execute()

        st.success("✅ Imagem enviada com sucesso!")
        st.markdown(f"[🔗 Ver imagem no Google Drive]({uploaded['webViewLink']})")

    except Exception as e:
        st.error("❌ Erro ao enviar a imagem para o Google Drive")
        st.exception(e)

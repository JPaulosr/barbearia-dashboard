import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io

st.set_page_config(page_title="📸 Upload de Imagem para o Google Drive")
st.title("📸 Upload de Imagem para o Google Drive")

# =====================
# Carregar arquivo JSON de autenticação
# =====================
arquivo_credencial = st.file_uploader("🔐 Envie o arquivo .json da conta de serviço", type="json")

if arquivo_credencial:
    try:
        scopes = ["https://www.googleapis.com/auth/drive"]
        credentials = Credentials.from_service_account_file(arquivo_credencial, scopes=scopes)
        service = build("drive", "v3", credentials=credentials)

        # =====================
        # ID da pasta no Drive
        # =====================
        PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

        # =====================
        # Upload da imagem
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

                    st.success(f"✅ Imagem enviada com sucesso! ID: {uploaded['id']}")
                except Exception as e:
                    st.error(f"Erro no upload: {e}")

    except Exception as e:
        st.error(f"Erro ao autenticar com Google Drive: {e}")

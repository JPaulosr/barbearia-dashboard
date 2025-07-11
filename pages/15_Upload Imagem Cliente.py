import streamlit as st
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import requests
import os

# Título da página
st.title("📸 Upload de Imagem para o Google Drive")

# Pega as credenciais do secrets.toml
client_id = st.secrets["GOOGLE_OAUTH"]["client_id"]
client_secret = st.secrets["GOOGLE_OAUTH"]["client_secret"]
redirect_uri = st.secrets["GOOGLE_OAUTH"]["redirect_uris"][0]

# Inicializa o fluxo OAuth 2.0
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
    redirect_uri=redirect_uri
)

# Exibe link de autorização para o usuário
auth_url, state = flow.authorization_url(prompt='consent', include_granted_scopes='true')

st.markdown("### 1️⃣ Autentique sua conta Google")
st.markdown(f"[Clique aqui para autorizar o app com sua conta Google]({auth_url})")

# Campo para colar o código gerado na etapa de autenticação
auth_code = st.text_input("Cole o código que você recebeu aqui:")

# Após colar o código, troca pelo token de acesso
if auth_code:
    try:
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials

        st.success("✅ Autenticação concluída com sucesso!")

        # Agora você pode continuar com o upload, por exemplo:
        uploaded_file = st.file_uploader("📤 Selecione a imagem do cliente para subir", type=["jpg", "jpeg", "png"])
        nome_cliente = st.text_input("Digite o nome do cliente:")

        if uploaded_file and nome_cliente:
            # Salva temporariamente
            file_path = f"/tmp/{uploaded_file.name}"
            with open(file_path, "wb") as f:
                f.write(uploaded_file.read())

            # Faz upload para o Google Drive
            headers = {
                "Authorization": f"Bearer {credentials.token}"
            }
            metadata = {
                "name": f"{nome_cliente}.jpg",
                "parents": ["PASTA_ID_AQUI"],  # Substitua pelo ID da pasta correta
            }
            files = {
                "data": ("metadata", str(metadata), "application/json"),
                "file": open(file_path, "rb")
            }

            response = requests.post(
                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                headers=headers,
                files=files
            )

            if response.status_code == 200:
                file_id = response.json()["id"]
                public_url = f"https://drive.google.com/uc?export=download&id={file_id}"
                st.success("📸 Imagem enviada com sucesso!")
                st.markdown(f"🔗 Link direto: [Abrir imagem]({public_url})")

                # Aqui você pode atualizar o Google Sheets com o link da imagem
                # (vamos fazer isso na próxima etapa se quiser)

            else:
                st.error("❌ Falha ao fazer upload no Google Drive.")

    except Exception as e:
        st.error(f"Erro ao autenticar ou fazer upload: {e}")

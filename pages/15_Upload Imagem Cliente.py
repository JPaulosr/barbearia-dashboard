import streamlit as st
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import os

# 1. Dados do secrets
client_id = st.secrets["GOOGLE_OAUTH"]["client_id"]
client_secret = st.secrets["GOOGLE_OAUTH"]["client_secret"]
redirect_uri = st.secrets["GOOGLE_OAUTH"]["redirect_uris"][0]

# 2. Inicia o fluxo de autenticação OAuth
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

# 3. Gera o link para o usuário autorizar
auth_url, _ = flow.authorization_url(prompt='consent')

st.markdown(f"[Clique aqui para autorizar com Google]({auth_url})")

# 4. Campo para colar o código de autenticação
auth_code = st.text_input("Cole aqui o código de autorização:")

if auth_code:
    try:
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials
        st.success("Autenticação concluída com sucesso!")

        # Aqui você pode usar `credentials.token` e `credentials.refresh_token` para subir a imagem para o Drive
        # Com esses dados, você pode usar o Google Drive API como autenticado

    except Exception as e:
        st.error(f"Erro ao autenticar: {e}")

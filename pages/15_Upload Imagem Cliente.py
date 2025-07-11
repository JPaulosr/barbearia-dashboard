import streamlit as st
import os
import pickle
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_PATH = "token_drive.pkl"

def autenticar_google_drive():
    creds = None

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config({
                "installed": {
                    "client_id": st.secrets["GOOGLE_OAUTH"]["client_id"],
                    "client_secret": st.secrets["GOOGLE_OAUTH"]["client_secret"],
                    "redirect_uris": st.secrets["GOOGLE_OAUTH"]["redirect_uris"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }, SCOPES)

            # Mostra o link e pede o código
            auth_url, _ = flow.authorization_url(prompt='consent')
            st.info("👉 Clique no link abaixo para fazer login com sua conta Google:")
            st.markdown(f"[Fazer login com o Google]({auth_url})")

            auth_code = st.text_input("Cole aqui o código que você recebeu após o login:")

            if auth_code:
                flow.fetch_token(code=auth_code)
                creds = flow.credentials

                with open(TOKEN_PATH, 'wb') as token:
                    pickle.dump(creds, token)
                st.success("✅ Login realizado com sucesso!")

    return creds

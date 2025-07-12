import streamlit as st
import os
import pickle
import requests
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------- CONFIG ---------- #
CLIENT_ID = st.secrets["OAUTH_CLIENT_ID"]
CLIENT_SECRET = st.secrets["OAUTH_CLIENT_SECRET"]
REDIRECT_URI = st.secrets["OAUTH_REDIRECT_URI"]

SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'client_oauth.json'
TOKEN_FILE = 'token_drive.pkl'

DRIVE_FOLDER_ID = '1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS'  # Pasta no seu Drive

# ---------- FUNÇÕES ---------- #

def salvar_client_oauth_json():
    data = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [REDIRECT_URI]
        }
    }
    with open(CREDENTIALS_FILE, "w") as f:
        import json
        json.dump(data, f)


def criar_flow():
    salvar_client_oauth_json()
    return Flow.from_client_secrets_file(
        CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )


def get_credentials_from_code(code):
    flow = criar_flow()
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_FILE, "wb") as token:
        pickle.dump(creds, token)
    return creds


def carregar_credenciais():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            return pickle.load(token)
    return None


def fazer_upload_arquivo(nome_arquivo, caminho_local, mime_type="image/jpeg"):
    creds = carregar_credenciais()
    if not creds:
        st.warning("Credenciais não encontradas. Autentique primeiro.")
        return None

    service = build('drive', 'v3', credentials=creds)
    media = MediaFileUpload(caminho_local, mimetype=mime_type)
    file_metadata = {
        'name': nome_arquivo,
        'parents': [DRIVE_FOLDER_ID]
    }

    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and name='{nome_arquivo}' and trashed=false",
        spaces='drive',
        fields='files(id, name)'
    ).execute()

    # Se já existe, substitui
    if results.get('files'):
        file_id = results['files'][0]['id']
        service.files().update(fileId=file_id, media_body=media).execute()
        return file_id
    else:
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get("id")


# ---------- INTERFACE ---------- #

st.title("📸 Upload de Imagem do Cliente")

code_param = st.experimental_get_query_params().get("code", [None])[0]

if code_param:
    try:
        get_credentials_from_code(code_param)
        st.success("✅ Autenticação concluída com sucesso!")
        st.experimental_set_query_params()  # Remove ?code=... da URL
    except Exception as e:
        st.error(f"Erro na autenticação: {e}")
        st.stop()

creds = carregar_credenciais()

if not creds:
    flow = criar_flow()
    auth_url, _ = flow.authorization_url(prompt='consent')
    st.info("🔐 Você precisa se autenticar com sua conta Google para subir imagens.")
    st.markdown(f"[Clique aqui para autenticar]({auth_url})")
    st.stop()

nome_cliente = st.text_input("Digite o nome do cliente (sem espaços):")

arquivo = st.file_uploader("📤 Envie uma imagem (.jpg ou .png)", type=["jpg", "jpeg", "png"])

if arquivo and nome_cliente:
    with open("temp_img.jpg", "wb") as f:
        f.write(arquivo.read())

    id_img = fazer_upload_arquivo(f"{nome_cliente}.jpg", "temp_img.jpg")

    if id_img:
        link = f"https://drive.google.com/uc?id={id_img}"
        st.success("✅ Imagem enviada com sucesso!")
        st.image(link, caption="Prévia da Imagem", width=300)
        st.markdown(f"[🔗 Link da Imagem]({link})")
    else:
        st.error("❌ Falha ao enviar imagem.")


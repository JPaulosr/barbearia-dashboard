import streamlit as st
import pandas as pd
import os
import requests
from PIL import Image
from io import BytesIO
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import gspread
from google.auth.transport.requests import Request

st.set_page_config(page_title="Upload de Imagem do Cliente", layout="wide")
st.title("📸 Upload de Imagem do Cliente")

# ======== CONFIGURAÇÕES ========
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

# ======== AUTENTICAÇÃO COM OAUTH ========
@st.cache_resource
def autenticar_drive():
    flow = Flow.from_client_secrets_file(
        "client_secret_999164949232-l5ml7hk7rsunto9rp9km94vvqfcmg8ss.apps.googleusercontent.com.json",
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ],
        redirect_uri="https://barbearia-dashboard.streamlit.app"
    )

    if "credentials" not in st.session_state:
        auth_url, _ = flow.authorization_url(prompt='consent')
        st.markdown(f"[🔐 Clique aqui para autorizar o acesso]({auth_url})")
        st.stop()
    else:
        creds = Credentials.from_authorized_user_info(st.session_state["credentials"])
        return creds

# ======== FUNÇÕES AUXILIARES ========
def carregar_lista_clientes():
    creds = autenticar_drive()
    gc = gspread.authorize(creds)
    planilha = gc.open_by_url(PLANILHA_URL)
    aba = planilha.worksheet("clientes_status")
    dados = aba.get_all_records()
    return sorted(pd.DataFrame(dados)["Cliente"].dropna().unique())

def upload_imagem(nome_arquivo, nome_cliente):
    creds = autenticar_drive()
    drive_service = build("drive", "v3", credentials=creds)

    metadata = {"name": f"{nome_cliente}.jpg", "parents": [PASTA_ID]}
    media = MediaFileUpload(nome_arquivo, resumable=True)
    arquivo = drive_service.files().create(body=metadata, media_body=media, fields="id").execute()

    # Torna o arquivo público
    drive_service.permissions().create(fileId=arquivo["id"], body={"type": "anyone", "role": "reader"}).execute()

    return f"https://drive.google.com/uc?export=download&id={arquivo['id']}"

# ======== INTERFACE ========
clientes = carregar_lista_clientes()
cliente = st.selectbox("Selecione o cliente:", clientes)

arquivo = st.file_uploader("Escolha a imagem do cliente:", type=["jpg", "jpeg", "png"])

if st.button("📤 Enviar imagem"):
    if cliente and arquivo:
        nome_temp = f"temp_{cliente}.jpg"
        with open(nome_temp, "wb") as f:
            f.write(arquivo.read())

        try:
            link = upload_imagem(nome_temp, cliente)
            creds = autenticar_drive()
            gc = gspread.authorize(creds)
            planilha = gc.open_by_url(PLANILHA_URL)
            aba = planilha.worksheet("clientes_status")
            dados = aba.get_all_records()

            for i, linha in enumerate(dados):
                if linha.get("Cliente") == cliente:
                    aba.update_cell(i + 2, 3, link)  # Coluna C (Foto)
                    break
            st.success("Imagem enviada e planilha atualizada com sucesso!")
        except Exception as e:
            st.error(f"Erro no upload: {e}")
        finally:
            os.remove(nome_temp)
    else:
        st.warning("Selecione um cliente e uma imagem.")

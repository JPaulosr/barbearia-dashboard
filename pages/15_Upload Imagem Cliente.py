import streamlit as st
import pandas as pd
import io
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from googleapiclient.errors import HttpError

# ========== CONFIG ==========
PLANILHA_URL = st.secrets["PLANILHA_URL"]
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

# ========== AUTENTICAÇÃO GOOGLE ==========
cred_upload = Credentials.from_service_account_info(
    st.secrets["GCP_UPLOAD"],
    scopes=["https://www.googleapis.com/auth/drive"]
)
drive_service = build("drive", "v3", credentials=cred_upload)

cred_sheets = Credentials.from_service_account_info(
    st.secrets["GCP_SERVICE_ACCOUNT"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
sheets_service = build("sheets", "v4", credentials=cred_sheets)

# ========== FUNÇÕES ==========
@st.cache_data(ttl=300)
def carregar_nomes_clientes():
    sheet = sheets_service.spreadsheets().values().get(
        spreadsheetId=PLANILHA_URL.split("/")[5],
        range="clientes_status!A2:A"
    ).execute()
    valores = sheet.get("values", [])
    return sorted([linha[0] for linha in valores if linha])

def buscar_arquivo_drive(nome_arquivo):
    query = f"name='{nome_arquivo}' and '{PASTA_ID}' in parents and trashed = false"
    response = drive_service.files().list(q=query, fields="files(id, webContentLink)").execute()
    files = response.get("files", [])
    return files[0] if files else None

def deletar_arquivo_drive(file_id):
    drive_service.files().delete(fileId=file_id).execute()

def atualizar_link_planilha(nome_cliente, link):
    valores = sheets_service.spreadsheets().values().get(
        spreadsheetId=PLANILHA_URL.split("/")[5],
        range="clientes_status!A2:C"
    ).execute().get("values", [])

    for idx, linha in enumerate(valores):
        if linha[0].strip().lower() == nome_cliente.strip().lower():
            sheets_service.spreadsheets().values().update(
                spreadsheetId=PLANILHA_URL.split("/")[5],
                range=f"clientes_status!C{idx + 2}",
                valueInputOption="RAW",
                body={"values": [[link]]}
            ).execute()
            break

# ========== INTERFACE ==========
st.set_page_config(page_title="Upload de Imagem para o Google Drive", layout="centered")
st.title("📸 Upload de Imagem para o Google Drive")
st.markdown("Selecione o cliente abaixo para visualizar, substituir ou excluir a imagem:")

nomes_clientes = carregar_nomes_clientes()
cliente_nome = st.selectbox("🔍 Nome do cliente", nomes_clientes)

nome_arquivo = f"{cliente_nome.strip().lower()}.jpg"
arquivo_drive = buscar_arquivo_drive(nome_arquivo)

if arquivo_drive:
    st.image(arquivo_drive["webContentLink"], width=300, caption="📸 Imagem atual")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Excluir imagem"):
            deletar_arquivo_drive(arquivo_drive["id"])
            st.success("Imagem excluída com sucesso!")
    with col2:
        substituir = st.file_uploader("📤 Substituir imagem", type=["jpg", "jpeg", "png"])
        if substituir:
            deletar_arquivo_drive(arquivo_drive["id"])
            file_stream = io.BytesIO(substituir.read())
            media = MediaIoBaseUpload(file_stream, mimetype="image/jpeg")
            file_metadata = {"name": nome_arquivo, "parents": [PASTA_ID]}
            novo_arquivo = drive_service.files().create(
                body=file_metadata, media_body=media, fields="id, webContentLink"
            ).execute()
            atualizar_link_planilha(cliente_nome, novo_arquivo["webContentLink"])
            st.success("Imagem substituída e link atualizado!")
else:
    novo = st.file_uploader("📤 Enviar nova imagem", type=["jpg", "jpeg", "png"])
    if novo:
        file_stream = io.BytesIO(novo.read())
        media = MediaIoBaseUpload(file_stream, mimetype="image/jpeg")
        file_metadata = {"name": nome_arquivo, "parents": [PASTA_ID]}
        novo_arquivo = drive_service.files().create(
            body=file_metadata, media_body=media, fields="id, webContentLink"
        ).execute()
        atualizar_link_planilha(cliente_nome, novo_arquivo["webContentLink"])
        st.success("Imagem enviada e link atualizado!")

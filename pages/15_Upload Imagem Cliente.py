import streamlit as st
import pandas as pd
import io
import requests
from PIL import Image
from io import BytesIO
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ========== CONFIG ==========

PLANILHA_URL = st.secrets["PLANILHA_URL"]
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

# ========== AUTENTICAÇÃO ==========

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

st.set_page_config(page_title="Upload de Imagem para o Google Drive", layout="wide")
st.title("📸 Upload de Imagem para o Google Drive")
st.markdown("Selecione o cliente abaixo para visualizar, substituir ou excluir a imagem:")

nomes_clientes = carregar_nomes_clientes()
cliente_nome = st.selectbox("🔍 Nome do cliente", nomes_clientes, label_visibility="visible")

# Tentativa de localizar imagem atual
extensoes_possiveis = ["jpg", "jpeg", "png"]
arquivo_drive = None
for ext in extensoes_possiveis:
    tentativa_nome = f"{cliente_nome.strip().lower()}.{ext}"
    arquivo_drive = buscar_arquivo_drive(tentativa_nome)
    if arquivo_drive:
        nome_arquivo = tentativa_nome
        break

col1, col2 = st.columns([1.2, 1.8])
with col1:
    if arquivo_drive:
        link_imagem = f"https://drive.google.com/uc?export=view&id={arquivo_drive['id']}"
        try:
            response = requests.get(link_imagem)
            img = Image.open(BytesIO(response.content))
            st.image(img, width=300, caption="📸 Imagem atual")
        except:
            st.warning("❌ Erro ao carregar a imagem do cliente.")
        if st.button("🗑️ Excluir imagem", use_container_width=True):
            deletar_arquivo_drive(arquivo_drive["id"])
            st.success("Imagem excluída com sucesso!")
    else:
        st.info("Nenhuma imagem encontrada para este cliente.")

with col2:
    st.markdown("📤 **Substituir ou enviar nova imagem**")
    nova_imagem = st.file_uploader("Selecione uma imagem", type=["jpg", "jpeg", "png"])
    if nova_imagem:
        if arquivo_drive:
            deletar_arquivo_drive(arquivo_drive["id"])

        # Detecta extensão e tipo MIME automaticamente
        extensao = nova_imagem.name.split(".")[-1].lower()
        nome_arquivo = f"{cliente_nome.strip().lower()}.{extensao}"
        imagem_bytes = nova_imagem.read()
        mimetype = nova_imagem.type or "image/jpeg"

        # Faz upload para o Drive
        media = MediaIoBaseUpload(io.BytesIO(imagem_bytes), mimetype=mimetype)
        file_metadata = {"name": nome_arquivo, "parents": [PASTA_ID]}
        novo_arquivo = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webContentLink"
        ).execute()

        # Torna o arquivo público
        try:
            drive_service.permissions().create(
                fileId=novo_arquivo['id'],
                body={"role": "reader", "type": "anyone"},
            ).execute()
        except Exception as e:
            st.warning("⚠️ Imagem enviada, mas não foi possível torná-la pública. Verifique as permissões da pasta no Google Drive.")

        # Atualiza link na planilha
        link_final = f"https://drive.google.com/uc?export=view&id={novo_arquivo['id']}"
        atualizar_link_planilha(cliente_nome, link_final)
        st.success("✅ Imagem enviada e link atualizado com sucesso!")

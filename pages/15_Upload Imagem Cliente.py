import streamlit as st
import pandas as pd
import os
import pickle
import tempfile
import json

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

st.set_page_config(page_title="Upload de Imagem do Cliente", page_icon="📸")
st.markdown("# 📸 Upload de Imagem do Cliente")

# ========= CONFIG =========
PLANILHA_URL = st.secrets["PLANILHA_URL"]
SHEET_ID = PLANILHA_URL.split("/")[5]
ABA = "clientes_status"
PASTA_DRIVE_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
TOKEN_FILE = "token_drive.pkl"
CLIENT_SECRET_FILE = "client_secret.json"

# ========= GERA ARQUIVO client_secret.json DO OAUTH =========
if not os.path.exists(CLIENT_SECRET_FILE):
    with open(CLIENT_SECRET_FILE, "w") as f:
        json.dump({
            "web": {
                "client_id": st.secrets["GOOGLE_OAUTH"]["client_id"],
                "client_secret": st.secrets["GOOGLE_OAUTH"]["client_secret"],
                "redirect_uris": st.secrets["GOOGLE_OAUTH"]["redirect_uris"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/v1/certs"
            }
        }, f)

# ========= AUTENTICAÇÃO OAUTH =========
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/spreadsheets']

def autenticar_oauth():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_FILE, SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)

    drive_service = build('drive', 'v3', credentials=creds)
    sheets_service = build('sheets', 'v4', credentials=creds)
    return drive_service, sheets_service

drive_service, sheets_service = autenticar_oauth()

# ========= CLIENTES =========
@st.cache_data(ttl=3600)
def carregar_lista_clientes():
    csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&sheet={ABA}"
    df = pd.read_csv(csv_url)
    return df

try:
    df_clientes = carregar_lista_clientes()
    col_cliente = [col for col in df_clientes.columns if col.lower() == "cliente"][0]
    nomes_clientes = df_clientes[col_cliente].dropna().sort_values().unique().tolist()
    cliente = st.selectbox("Selecione o cliente:", nomes_clientes)
except Exception as e:
    st.error(f"Erro ao carregar lista de clientes: {e}")
    st.stop()

# ========= GOOGLE DRIVE =========
def buscar_imagem_existente(nome_cliente):
    query = f"'{PASTA_DRIVE_ID}' in parents and name contains '{nome_cliente}' and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id, name, webViewLink)").execute()
    files = results.get("files", [])
    return files[0] if files else None

def fazer_upload_drive(file, filename):
    temp_file = tempfile.NamedTemporaryFile(delete=False)
    temp_file.write(file.read())
    temp_file.close()

    file_metadata = {
        "name": filename,
        "parents": [PASTA_DRIVE_ID]
    }
    media = MediaFileUpload(temp_file.name, mimetype="image/png", resumable=True)
    result = drive_service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()
    os.remove(temp_file.name)
    return result["id"], result["webViewLink"]

def substituir_imagem_cliente(cliente_nome, arquivo_novo):
    existente = buscar_imagem_existente(cliente_nome)
    if existente:
        drive_service.files().delete(fileId=existente["id"]).execute()
    file_id, link = fazer_upload_drive(arquivo_novo, f"{cliente_nome}.png")
    atualizar_link_na_planilha(cliente_nome, link)
    return file_id, link

# ========= ATUALIZAÇÃO NA PLANILHA =========
def atualizar_link_na_planilha(cliente_nome, novo_link):
    valores = df_clientes[col_cliente].fillna("").tolist()
    try:
        index = valores.index(cliente_nome)
        linha = index + 2  # índice começa em 0 + cabeçalho
        body = {
            "values": [[novo_link]]
        }
        range_ = f"{ABA}!C{linha}"
        sheets_service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=range_,
            valueInputOption="RAW",
            body=body
        ).execute()
    except ValueError:
        st.warning(f"Cliente '{cliente_nome}' não encontrado para atualizar link.")

# ========= UI =========
uploaded_file = st.file_uploader("Selecione a imagem do cliente (JPG ou PNG):", type=["jpg", "jpeg", "png"])

imagem_atual = buscar_imagem_existente(cliente)
if imagem_atual:
    st.markdown("**Imagem atual do cliente:**")
    st.image(f"https://drive.google.com/uc?id={imagem_atual['id']}", width=300)
    st.markdown(f"[🔗 Abrir no Drive]({imagem_atual['webViewLink']})", unsafe_allow_html=True)
else:
    st.info("Nenhuma imagem encontrada para este cliente.")

if uploaded_file and cliente:
    if st.button("📸 Substituir imagem"):
        try:
            _, link = substituir_imagem_cliente(cliente, uploaded_file)
            st.success("✅ Imagem enviada com sucesso!")
            st.markdown(f"[🔗 Ver no Drive]({link})", unsafe_allow_html=True)
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao fazer upload: {e}")

if st.button("🚫 Excluir imagem"):
    existente = buscar_imagem_existente(cliente)
    if existente:
        drive_service.files().delete(fileId=existente["id"]).execute()
        atualizar_link_na_planilha(cliente, "")
        st.success("✅ Imagem excluída com sucesso.")
        st.rerun()
    else:
        st.warning("Nenhuma imagem encontrada para este cliente.")

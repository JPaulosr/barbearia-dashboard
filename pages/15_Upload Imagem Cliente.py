import streamlit as st
import pandas as pd
import os
import pickle
import tempfile

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

st.set_page_config(page_title="Upload de Imagem do Cliente", page_icon="📸")
st.markdown("# 📸 Upload de Imagem do Cliente")

# ========= CONFIG =========
CLIENT_SECRET_FILE = "/mnt/data/client_secret.json"  # Caminho corrigido
TOKEN_FILE = "token_drive.pkl"
SCOPES = ['https://www.googleapis.com/auth/drive.file']
PASTA_DRIVE_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/edit?usp=sharing"

# ========= AUTENTICAÇÃO =========
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

    service = build('drive', 'v3', credentials=creds)
    return service

drive_service = autenticar_oauth()

# ========= CLIENTES =========
@st.cache_data(ttl=3600)
def carregar_lista_clientes():
    sheet_id = PLANILHA_URL.split("/")[5]
    aba = "clientes_status"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={aba}"
    df = pd.read_csv(csv_url)
    return df

try:
    df_clientes = carregar_lista_clientes()
    coluna_nome = [col for col in df_clientes.columns if col.lower() == "cliente"]
    if not coluna_nome:
        st.error("❌ Coluna 'Cliente' não encontrada na planilha.")
        st.stop()
    nomes_clientes = df_clientes[coluna_nome[0]].dropna().sort_values().unique().tolist()
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
    drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    os.remove(temp_file.name)

def substituir_imagem_cliente(cliente_nome, arquivo_novo):
    existente = buscar_imagem_existente(cliente_nome)
    if existente:
        drive_service.files().delete(fileId=existente["id"]).execute()
    fazer_upload_drive(arquivo_novo, f"{cliente_nome}.png")

# ========= UI =========
uploaded_file = st.file_uploader("Selecione a imagem do cliente (JPG ou PNG):", type=["jpg", "jpeg", "png"])

# Preview da imagem atual (se existir)
imagem_atual = buscar_imagem_existente(cliente)
if imagem_atual:
    st.markdown("**Imagem atual do cliente:**")
    st.image(f"https://drive.google.com/uc?id={imagem_atual['id']}", width=300)
else:
    st.info("Nenhuma imagem encontrada para este cliente.")

if uploaded_file and cliente:
    if st.button("📸 Substituir imagem"):
        try:
            substituir_imagem_cliente(cliente, uploaded_file)
            st.success("✅ Imagem enviada com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao fazer upload: {e}")

if st.button("🚫 Excluir imagem"):
    existente = buscar_imagem_existente(cliente)
    if existente:
        drive_service.files().delete(fileId=existente["id"]).execute()
        st.success("✅ Imagem excluída com sucesso.")
        st.rerun()
    else:
        st.warning("Nenhuma imagem encontrada para este cliente.")

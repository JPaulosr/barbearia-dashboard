import streamlit as st
import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import tempfile

st.set_page_config(page_title="Upload de Imagem do Cliente", page_icon="📸")
st.markdown("# 📸 Upload de Imagem do Cliente")

# ===============================
# Autenticação com o Google Drive via st.secrets
# ===============================
@st.cache_resource
def autenticar_drive():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)
    return service

drive_service = autenticar_drive()

# ===============================
# Dados da Planilha
# ===============================
@st.cache_data(ttl=3600)
def carregar_lista_clientes():
    url = st.secrets["PLANILHA_URL"]
    sheet_id = url.split("/")[5]
    aba = "clientes_status"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={aba}"
    df = pd.read_csv(csv_url)
    return df

try:
    df_clientes = carregar_lista_clientes()

    # Detecta automaticamente a coluna 'Cliente', ignorando maiúsculas/minúsculas
    coluna_nome = [col for col in df_clientes.columns if col.lower() == "cliente"]
    if not coluna_nome:
        st.error("❌ Coluna 'Cliente' não encontrada na aba 'clientes_status'.")
        st.stop()

    nomes_clientes = df_clientes[coluna_nome[0]].dropna().sort_values().unique().tolist()
    cliente = st.selectbox("Selecione o cliente:", nomes_clientes)
except Exception as e:
    st.error(f"Erro ao carregar lista de clientes: {e}")
    st.stop()

# ===============================
# Upload e Envio da Imagem
# ===============================
uploaded_file = st.file_uploader("Selecione a imagem do cliente (JPG ou PNG):", type=["jpg", "jpeg", "png"])

# ID da pasta no Drive compartilhado com você:
PASTA_DRIVE_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

def buscar_imagem_existente(nome_cliente):
    query = f"'{PASTA_DRIVE_ID}' in parents and name contains '{nome_cliente}' and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None

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
    existente_id = buscar_imagem_existente(cliente_nome)
    if existente_id:
        drive_service.files().delete(fileId=existente_id).execute()
    fazer_upload_drive(arquivo_novo, f"{cliente_nome}.png")

if uploaded_file and cliente:
    if st.button("📸 Substituir imagem"):
        try:
            substituir_imagem_cliente(cliente, uploaded_file)
            st.success("✅ Imagem enviada com sucesso!")
        except Exception as e:
            st.error(f"Erro ao fazer upload: {e}")

# ===============================
# Excluir imagem
# ===============================
if st.button("🚫 Excluir imagem"):
    existente_id = buscar_imagem_existente(cliente)
    if existente_id:
        drive_service.files().delete(fileId=existente_id).execute()
        st.success("✅ Imagem excluída com sucesso.")
    else:
        st.warning("Nenhuma imagem encontrada para este cliente.")

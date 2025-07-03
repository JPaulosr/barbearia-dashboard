import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials
import gspread
from gspread_dataframe import get_as_dataframe
import pandas as pd
import io
import json

st.set_page_config(page_title="Upload de Imagem", layout="wide")
st.title("📸 Upload de Imagem do Cliente")

PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

# === CREDENCIAIS DO SECRETS ===
@st.cache_resource
def carregar_credenciais():
    infos = st.secrets["GCP_SERVICE_ACCOUNT"]
    return Credentials.from_service_account_info(infos)

# === CONECTAR AO DRIVE ===
@st.cache_resource
def conectar_drive():
    scopes = ["https://www.googleapis.com/auth/drive"]
    credenciais = carregar_credenciais().with_scopes(scopes)
    service = build("drive", "v3", credentials=credenciais)
    return service

# === ATUALIZAR O LINK NA PLANILHA ===
def atualizar_link_na_planilha(nome_cliente, link):
    planilha_id = st.secrets["PLANILHA_URL"]["url"].split("/")[5]
    aba_nome = "clientes_status"
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    credenciais = carregar_credenciais().with_scopes(scopes)
    gc = gspread.authorize(credenciais)
    aba = gc.open_by_key(planilha_id).worksheet(aba_nome)
    dados = aba.get_all_records()
    df = pd.DataFrame(dados)

    if "Foto_URL" not in df.columns:
        df["Foto_URL"] = ""

    df["cliente_formatado"] = df["Cliente"].astype(str).str.strip().str.lower()
    nome_input = nome_cliente.strip().lower()
    idx = df.index[df["cliente_formatado"] == nome_input].tolist()

    if idx:
        aba.update_cell(idx[0] + 2, df.columns.get_loc("Foto_URL") + 1, link)
    else:
        st.error(f"❌ Cliente '{nome_cliente}' não encontrado na planilha.")

# === CARREGAR NOMES DE CLIENTES ===
def carregar_lista_clientes():
    planilha_id = st.secrets["PLANILHA_URL"]["url"].split("/")[5]
    aba_nome = "Base de Dados"
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets"]
    credenciais = carregar_credenciais().with_scopes(scopes)
    gc = gspread.authorize(credenciais)
    aba = gc.open_by_key(planilha_id).worksheet(aba_nome)
    df = get_as_dataframe(aba).dropna(how="all")
    return sorted(df["Cliente"].dropna().unique().tolist())

# === INTERFACE ===
lista_clientes = carregar_lista_clientes()
uploaded_file = st.file_uploader("📤 Envie a imagem do cliente", type=["jpg", "jpeg", "png"])
nome_cliente = st.selectbox("🧍 Nome do Cliente (para nomear o arquivo)", options=lista_clientes)
drive_service = conectar_drive()

if uploaded_file and nome_cliente:
    st.image(uploaded_file, caption="Pré-visualização", width=200)
    if st.button("Salvar imagem no Google Drive e atualizar planilha", type="primary"):
        if "upload_feito" not in st.session_state:
            st.session_state.upload_feito = False

        if not st.session_state.upload_feito:
            try:
                nome_arquivo = f"{nome_cliente.lower().replace(' ', '_')}.jpg"
                img_bytes = io.BytesIO(uploaded_file.getvalue())
                media = MediaIoBaseUpload(img_bytes, mimetype="image/jpeg", resumable=False)
                file_metadata = {
                    "name": nome_arquivo,
                    "parents": [PASTA_ID]
                }
                file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
                file_id = file.get("id")
                url = f"https://drive.google.com/uc?id={file_id}"
                atualizar_link_na_planilha(nome_cliente, url)
                st.session_state.upload_feito = True
                st.success("✅ Imagem enviada com sucesso e planilha atualizada!")
                st.markdown(f"[🔗 Ver imagem no Drive]({url})")
            except Exception as e:
                st.error(f"Erro ao enviar: {e}")
        else:
            st.warning("A imagem já foi enviada. Atualize a página se quiser reenviar.")
else:
    st.info("Envie uma imagem e selecione o nome do cliente para continuar.")

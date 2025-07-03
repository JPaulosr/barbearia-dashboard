import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials
import io
import gspread
from gspread_dataframe import get_as_dataframe
import pandas as pd

st.set_page_config(page_title="Upload de Imagem", layout="wide")
st.title("📸 Upload de Imagem do Cliente")

# === CONFIGURAÇÃO ===
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"

# Conecta com o Google Drive
@st.cache_resource
def conectar_drive():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=scopes)
    service = build("drive", "v3", credentials=credenciais)
    return service

# Conecta com a planilha e carrega os nomes dos clientes
@st.cache_data
def carregar_clientes():
    planilha_id = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
    aba_nome = "clientes_status"
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    gc = gspread.authorize(credenciais)
    aba = gc.open_by_key(planilha_id).worksheet(aba_nome)
    dados = aba.get_all_records()
    df = pd.DataFrame(dados)
    return df["Cliente"].dropna().unique().tolist(), aba, df

# Atualiza o link da imagem no Google Sheets
def atualizar_link_na_planilha(nome_cliente, link, aba, df):
    if "Foto_URL" not in df.columns:
        df["Foto_URL"] = ""
    idx = df.index[df["Cliente"] == nome_cliente].tolist()
    if idx:
        aba.update_cell(idx[0]+2, df.columns.get_loc("Foto_URL")+1, link)

drive_service = conectar_drive()
clientes_lista, aba_clientes, df_clientes = carregar_clientes()

uploaded_file = st.file_uploader("📤 Envie a imagem do cliente", type=["jpg", "jpeg", "png"])
nome_cliente = st.selectbox("🧍 Nome do Cliente (para nomear o arquivo)", sorted(clientes_lista))

if uploaded_file and nome_cliente:
    st.image(uploaded_file, caption="Pré-visualização", width=200)
    if st.button("Salvar imagem no Google Drive e atualizar planilha"):
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
            atualizar_link_na_planilha(nome_cliente, url, aba_clientes, df_clientes)
            st.success("✅ Imagem enviada com sucesso e planilha atualizada!")
            st.markdown(f"[🔗 Ver imagem no Drive]({url})")
        except Exception as e:
            st.error(f"Erro ao enviar: {e}")
else:
    st.info("Envie uma imagem e selecione o nome do cliente para continuar.")

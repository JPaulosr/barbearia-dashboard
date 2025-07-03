import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.service_account import Credentials
import io
import gspread
import pandas as pd

st.set_page_config(page_title="Upload de Imagem", layout="wide")
st.title("📸 Upload de Imagem do Cliente")

PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
PLANILHA_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_NOME = "clientes_status"

# Conexão com Google APIs
@st.cache_resource
def conectar_credenciais():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets"
    ]
    credenciais = Credentials.from_service_account_info(info, scopes=scopes)
    return credenciais

# Corrigir automaticamente o cabeçalho da aba
def corrigir_cabecalho_se_preciso(gc):
    aba = gc.open_by_key(PLANILHA_ID).worksheet(ABA_NOME)
    valores = aba.get_all_values()
    if valores[0][0].strip().lower() != "cliente":
        aba.delete_rows(1)
        novo_cabecalho = ["Cliente", "Telefone", "Status", "Foto_URL"]
        aba.insert_row(novo_cabecalho, 1)
        st.warning("⚠️ Cabeçalho estava incorreto e foi corrigido.")

# Carrega a lista de clientes
def carregar_lista_clientes():
    creds = conectar_credenciais()
    gc = gspread.authorize(creds)
    corrigir_cabecalho_se_preciso(gc)
    aba = gc.open_by_key(PLANILHA_ID).worksheet(ABA_NOME)
    df = pd.DataFrame(aba.get_all_records())
    return sorted(df["Cliente"].dropna().unique().tolist())

# Atualiza o link da imagem na planilha
def atualizar_link_na_planilha(nome_cliente, link):
    creds = conectar_credenciais()
    gc = gspread.authorize(creds)
    aba = gc.open_by_key(PLANILHA_ID).worksheet(ABA_NOME)
    df = pd.DataFrame(aba.get_all_records())

    if "Foto_URL" not in df.columns:
        df["Foto_URL"] = ""

    df["cliente_formatado"] = df["Cliente"].astype(str).str.strip().str.lower()
    nome_input = nome_cliente.strip().lower()
    idx = df.index[df["cliente_formatado"] == nome_input].tolist()

    if idx:
        aba.update_cell(idx[0] + 2, df.columns.get_loc("Foto_URL") + 1, link)
    else:
        st.error(f"❌ Cliente '{nome_cliente}' não encontrado na planilha. Verifique o nome.")

# Upload da imagem
uploaded_file = st.file_uploader("📤 Envie a imagem do cliente", type=["jpg", "jpeg", "png"])

try:
    lista_clientes = carregar_lista_clientes()
except Exception as e:
    st.error(f"Erro ao carregar lista de clientes: {e}")
    st.stop()

nome_cliente = st.selectbox("🧍 Nome do Cliente (para nomear o arquivo)", options=lista_clientes)
drive_service = build("drive", "v3", credentials=conectar_credenciais())

if uploaded_file and nome_cliente:
    st.image(uploaded_file, caption="Pré-visualização", width=200)
    if st.button("Salvar imagem no Google Drive e atualizar planilha", type="primary"):
        try:
            nome_arquivo = f"{nome_cliente.lower().replace(' ', '_')}.jpg"
            img_bytes = io.BytesIO(uploaded_file.getvalue())
            media = MediaIoBaseUpload(img_bytes, mimetype="image/jpeg", resumable=False)
            file_metadata = {"name": nome_arquivo, "parents": [PASTA_ID]}
            file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
            url = f"https://drive.google.com/uc?id={file.get('id')}"
            atualizar_link_na_planilha(nome_cliente, url)
            st.success("✅ Imagem enviada com sucesso e planilha atualizada!")
            st.markdown(f"[🔗 Ver imagem no Drive]({url})")
        except Exception as e:
            st.error(f"Erro ao enviar: {e}")
else:
    st.info("Envie uma imagem e selecione o nome do cliente para continuar.")

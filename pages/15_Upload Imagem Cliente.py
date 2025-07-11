import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials

st.set_page_config(page_title="📸 Upload de Imagem Cliente", layout="wide")

st.title("📸 Upload de Imagem para o Google Drive")
st.info("1️⃣ Autentique sua conta Google para salvar no seu próprio Drive")

# ========== CREDENCIAIS ==========
client_id = st.secrets["GOOGLE_OAUTH"]["client_id"]
client_secret = st.secrets["GOOGLE_OAUTH"]["client_secret"]
redirect_uri = st.secrets["GOOGLE_OAUTH"]["redirect_uris"][0]

# ========= FLUXO DE AUTENTICAÇÃO =========
flow = Flow.from_client_config(
    {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri]
        }
    },
    scopes=["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/spreadsheets"]
)
flow.redirect_uri = redirect_uri

# ========= ETAPA 1 – LINK DE AUTORIZAÇÃO =========
auth_url, _ = flow.authorization_url(
    access_type='offline',
    include_granted_scopes='true',
    prompt='consent'
)

st.markdown(f"[Clique aqui para autorizar o app com sua conta Google]({auth_url})")

auth_code = st.text_input("Cole o código que você recebeu aqui:")

# ========= ETAPA 2 – AUTENTICAÇÃO E UPLOAD =========
uploaded_file = st.file_uploader("Selecione a imagem do cliente (JPG ou PNG)", type=["jpg", "jpeg", "png"])
nome_cliente = st.text_input("Nome do cliente (como aparece na planilha)")

if st.button("Fazer upload"):

    if not auth_code or not uploaded_file or not nome_cliente:
        st.warning("Preencha todos os campos e envie uma imagem.")
        st.stop()

    try:
        # Troca código pelo token
        flow.fetch_token(code=auth_code)
        credentials = flow.credentials

        # Cria serviço do Drive
        service = build("drive", "v3", credentials=credentials)

        # Lê o arquivo como binário
        file_data = io.BytesIO(uploaded_file.read())

        # Prepara upload
        file_metadata = {"name": f"{nome_cliente}.jpg", "parents": [st.secrets["FOLDER_ID"]]}
        media = MediaIoBaseUpload(file_data, mimetype=uploaded_file.type)

        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        file_id = uploaded_file.get("id")
        file_link = f"https://drive.google.com/uc?export=download&id={file_id}"

        st.success(f"Imagem enviada com sucesso! Link: {file_link}")
        st.image(file_link, width=200)

        # ========== Atualiza planilha ==========
        gc = gspread.service_account_from_dict(st.secrets["GSHEETS_SERVICE_ACCOUNT"])
        sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE")
        ws = sh.worksheet("clientes_status")

        df = pd.DataFrame(ws.get_all_records())

        if nome_cliente not in df['Cliente'].values:
            st.error("Cliente não encontrado na planilha.")
        else:
            row_idx = df[df['Cliente'] == nome_cliente].index[0] + 2  # +2 porque planilha começa em 1 e tem cabeçalho
            ws.update_cell(row_idx, 3, file_link)
            st.success("Link salvo na planilha com sucesso!")

    except Exception as e:
        st.error(f"Erro ao autenticar ou fazer upload: {e}")

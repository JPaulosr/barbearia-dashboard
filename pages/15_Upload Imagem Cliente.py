import streamlit as st
import requests
import io
from PIL import Image
from urllib.parse import urlencode
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

# ========== CONFIGS ==========
CLIENT_ID = st.secrets["OAUTH_CLIENT_ID"]
CLIENT_SECRET = st.secrets["OAUTH_CLIENT_SECRET"]
REDIRECT_URI = st.secrets["OAUTH_REDIRECT_URI"]
FOLDER_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
PLANILHA_ID = st.secrets["PLANILHA_URL"].split("/")[5]

SCOPE = "https://www.googleapis.com/auth/drive.file"

# ========== PLANILHA (usando conta de serviço só para leitura e escrita) ==========
cred_sheets = Credentials.from_service_account_info(
    st.secrets["GCP_SERVICE_ACCOUNT"],
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
sheets_service = build("sheets", "v4", credentials=cred_sheets)

@st.cache_data(ttl=300)
def carregar_nomes_clientes():
    sheet = sheets_service.spreadsheets().values().get(
        spreadsheetId=PLANILHA_ID,
        range="clientes_status!A2:A"
    ).execute()
    valores = sheet.get("values", [])
    return sorted([linha[0] for linha in valores if linha])

def atualizar_link_planilha(nome_cliente, link_imagem):
    valores = sheets_service.spreadsheets().values().get(
        spreadsheetId=PLANILHA_ID,
        range="clientes_status!A2:C"
    ).execute().get("values", [])
    for idx, linha in enumerate(valores):
        if linha[0].strip().lower() == nome_cliente.strip().lower():
            sheets_service.spreadsheets().values().update(
                spreadsheetId=PLANILHA_ID,
                range=f"clientes_status!C{idx + 2}",
                valueInputOption="RAW",
                body={"values": [[link_imagem]]}
            ).execute()
            break

# ========== FUNÇÕES DE AUTENTICAÇÃO ==========
def gerar_link_autenticacao():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent"
    }
    return f"https://accounts.google.com/o/oauth2/auth?{urlencode(params)}"

def trocar_codigo_por_token(auth_code):
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": auth_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    response = requests.post(token_url, data=data)
    return response.json()

def upload_para_drive(access_token, file_bytes, nome_arquivo, mimetype):
    headers = {"Authorization": f"Bearer {access_token}"}
    metadata = {
        "name": nome_arquivo,
        "parents": [FOLDER_ID]
    }
    files = {
        "data": ("metadata", io.BytesIO(str(metadata).encode()), "application/json"),
        "file": (nome_arquivo, file_bytes, mimetype)
    }
    upload_url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
    response = requests.post(upload_url, headers=headers, files=files)
    return response.json()

# ========== INTERFACE ==========
st.set_page_config("Upload de Imagem Cliente", layout="wide")
st.title("📸 Upload de Imagem com Google OAuth")
st.markdown("1️⃣ Clique no link abaixo para autenticar com sua conta Google:")

st.markdown(f"[👉 Autenticar com Google]({gerar_link_autenticacao()})")

auth_code = st.text_input("2️⃣ Cole aqui o código de autorização gerado pelo Google:")

if auth_code:
    token_info = trocar_codigo_por_token(auth_code)

    if "access_token" in token_info:
        st.success("✅ Autenticação concluída com sucesso!")
        access_token = token_info["access_token"]

        nomes_clientes = carregar_nomes_clientes()
        cliente_nome = st.selectbox("🧍 Nome do cliente", nomes_clientes)

        imagem = st.file_uploader("📤 Selecione a imagem do cliente", type=["jpg", "jpeg", "png"])

        if cliente_nome and imagem:
            extensao = imagem.name.split(".")[-1].lower()
            mimetype = imagem.type
            nome_arquivo = f"{cliente_nome.strip().lower()}.{extensao}"
            file_bytes = imagem.read()

            resultado = upload_para_drive(access_token, file_bytes, nome_arquivo, mimetype)

            if "id" in resultado:
                link_final = f"https://drive.google.com/uc?export=view&id={resultado['id']}"
                atualizar_link_planilha(cliente_nome, link_final)
                st.image(Image.open(io.BytesIO(file_bytes)), width=300, caption="Imagem enviada")
                st.success(f"✅ Imagem enviada e planilha atualizada com sucesso!")
                st.markdown(f"[🔗 Ver imagem no Drive]({link_final})")
            else:
                st.error("❌ Erro ao fazer upload. Resposta da API:")
                st.json(resultado)
        elif not imagem:
            st.info("📎 Envie uma imagem para continuar.")
        elif not cliente_nome:
            st.info("🔍 Selecione um cliente.")
    else:
        st.error("❌ Código de autenticação inválido ou expirado.")
        st.json(token_info)

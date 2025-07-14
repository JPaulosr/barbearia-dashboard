import streamlit as st
import pandas as pd
import requests
import cloudinary
import cloudinary.uploader
import cloudinary.api
from io import BytesIO
from PIL import Image

# ----------- CONFIG -----------
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Planilha Google Sheets
PLANILHA_URL = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/edit?usp=sharing"
SHEET_ID = PLANILHA_URL.split("/")[5]
ABA_CLIENTES = "clientes_status"

# Conta de serviço para acessar Google Sheets
credenciais_dict = {
    "type": "service_account",
    "project_id": "barbearia-dashboard",
    "private_key_id": "7c71bcbfaa1a8d935e1474fcabbe0c7c7ea8cae5",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhki...\n-----END PRIVATE KEY-----\n",
    "client_email": "streamlit-reader@barbearia-dashboard.iam.gserviceaccount.com",
    "client_id": "102292204018013167995",
    "token_uri": "https://oauth2.googleapis.com/token",
}

# Cloudinary
cloudinary.config(
    cloud_name="db8ipmete",
    api_key="144536432264916",
    api_secret="eVwo_kpkphpGDi4djTzNYGC5qJQ"
)

PASTA_CLOUDINARY = "Fotos clientes"

# ----------- FUNÇÕES -----------
def carregar_clientes_status():
    creds = service_account.Credentials.from_service_account_info(credenciais_dict)
    service = build('sheets', 'v4', credentials=creds)
    sheet = service.spreadsheets()
    result = sheet.values().get(spreadsheetId=SHEET_ID, range=ABA_CLIENTES).execute()
    valores = result.get("values", [])
    df = pd.DataFrame(valores[1:], columns=valores[0])
    return df

def imagem_existe(nome_arquivo):
    try:
        cloudinary.api.resource(f"{PASTA_CLOUDINARY}/{nome_arquivo}")
        return True
    except:
        return False

def deletar_imagem(nome_arquivo):
    try:
        cloudinary.uploader.destroy(f"{PASTA_CLOUDINARY}/{nome_arquivo}")
        return True
    except:
        return False

def gerar_url_imagem(nome_arquivo):
    return f"https://res.cloudinary.com/{cloudinary.config().cloud_name}/image/upload/{PASTA_CLOUDINARY}/{nome_arquivo}"

# ----------- INTERFACE -----------
st.title("📸 Upload Imagem Cliente")
st.caption("Envie ou substitua a imagem do cliente. O nome do arquivo será *nome_cliente.jpg*.")

# Carregar nomes de clientes
df_status = carregar_clientes_status()
nomes_clientes = sorted(df_status["Nome"].dropna().unique())
nome = st.selectbox("Selecione o cliente", nomes_clientes, placeholder="Digite para buscar...")

if nome:
    nome_arquivo = nome.lower().replace(" ", "_") + ".jpg"
    url = gerar_url_imagem(nome_arquivo)
    imagem_existe_flag = imagem_existe(nome_arquivo)

    col1, col2 = st.columns([1, 1])

    if imagem_existe_flag:
        col1.success("Imagem já existe para este cliente.")
        col1.image(url, width=200, caption="Imagem atual")

        if col2.button("🗑️ Deletar imagem"):
            if deletar_imagem(nome_arquivo):
                st.success("Imagem deletada com sucesso!")
            else:
                st.error("Erro ao deletar imagem.")

    uploaded_file = st.file_uploader("Selecione uma nova imagem para enviar", type=["jpg", "jpeg", "png"])

    if uploaded_file:
        imagem = Image.open(uploaded_file)
        st.image(imagem, width=200, caption="Prévia da nova imagem")

        if not imagem_existe_flag or st.button("🔁 Substituir imagem existente"):
            with st.spinner("Enviando imagem para o Cloudinary..."):
                buffer = BytesIO()
                imagem.save(buffer, format="JPEG")
                buffer.seek(0)
                resposta = cloudinary.uploader.upload(buffer, public_id=f"{PASTA_CLOUDINARY}/{nome_arquivo}", overwrite=True)
                if resposta.get("secure_url"):
                    st.success("Imagem enviada com sucesso!")
                    st.image(resposta["secure_url"], width=200)
                else:
                    st.error("Erro no upload da imagem.")

import streamlit as st
import cloudinary
import cloudinary.uploader
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from PIL import Image

# ===== Configuração Cloudinary =====
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

# ===== Planilha Google Sheets =====
PLANILHA_URL = st.secrets["PLANILHA_URL"]
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(st.secrets["GCP_SERVICE_ACCOUNT"], scopes=SCOPE)
gc = gspread.authorize(creds)
sheet = gc.open_by_url(PLANILHA_URL).worksheet("clientes_status")

# ===== Interface =====
st.title("📷 Upload Imagem Cliente")
st.markdown("Envie ou substitua a imagem do cliente. O nome do arquivo será `nome_cliente.jpg`.")

# Lista de clientes
clientes = sheet.col_values(1)
clientes = sorted([c for c in clientes if c.strip() and c.lower() not in ["brasileiro", "boliviano", "menino"]])
cliente = st.selectbox("Selecione o cliente", clientes)
nome_arquivo = f"{cliente}.jpg"

# Verificar se já existe link
linhas = sheet.get_all_values()
links = {linha[0]: linha[2] if len(linha) > 2 else "" for linha in linhas}
link_existente = links.get(cliente, "")

# Mostrar imagem existente
if link_existente:
    st.markdown("**Prévia atual:**")
    st.image(link_existente, width=250)

# ===== Upload =====
imagem = st.file_uploader("Escolher nova imagem", type=["jpg", "jpeg"])
if imagem:
    with st.spinner("Enviando imagem..."):
        resultado = cloudinary.uploader.upload(imagem, public_id=nome_arquivo, overwrite=True, resource_type="image")
        link_novo = resultado["secure_url"]

        # Atualizar planilha
        celulas = sheet.col_values(1)
        if cliente in celulas:
            row = celulas.index(cliente) + 1
            sheet.update_cell(row, 3, link_novo)
            st.success("Imagem enviada com sucesso!")
            st.image(link_novo, width=250)
        else:
            st.warning("Cliente não encontrado na planilha.")

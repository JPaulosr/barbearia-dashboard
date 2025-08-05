import os
import requests
import pandas as pd
import cloudinary
import cloudinary.api
import gspread
from PIL import Image
from io import BytesIO
from google.oauth2.service_account import Credentials
import streamlit as st

# ============ CONFIGURAÇÕES ============

# Pasta onde salvar as imagens
PASTA_LOCAL = "imagens_clientes"
os.makedirs(PASTA_LOCAL, exist_ok=True)

# Logo padrão (não será salvo)
LOGO_PADRAO = "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png"
PASTA_CLOUDINARY = "Fotos clientes"

# Config Cloudinary
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

# Conectar à planilha
def carregar_clientes_status():
    creds = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_url(st.secrets["PLANILHA_URL"])
    aba = spreadsheet.worksheet("clientes_status")
    dados = aba.get_all_records()
    return pd.DataFrame(dados)

df_status = carregar_clientes_status()
df_status.columns = df_status.columns.str.strip()
clientes = df_status['Cliente'].dropna().unique()

# Baixar imagens
def baixar_imagem_para_disco(nome_cliente, url):
    nome_arquivo = nome_cliente.lower().replace(" ", "_") + ".jpg"
    caminho = os.path.join(PASTA_LOCAL, nome_arquivo)

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            img.save(caminho)
            print(f"✅ Imagem salva: {caminho}")
        else:
            print(f"⚠️ Erro {response.status_code} ao baixar {nome_cliente}")
    except Exception as e:
        print(f"❌ Falha em {nome_cliente}: {e}")

# Lógica principal
for nome in clientes:
    nome_arquivo = nome.lower().replace(" ", "_") + ".jpg"
    url = None

    # 1. Tenta Cloudinary
    try:
        recurso = cloudinary.api.resource(f"{PASTA_CLOUDINARY}/{nome_arquivo}")
        url = recurso['secure_url']
    except:
        # 2. Tenta URL da planilha
        linha = df_status[df_status['Cliente'] == nome]
        if not linha.empty and linha['Foto'].values[0]:
            url_planilha = linha['Foto'].values[0]
            if "drive.google.com" in url_planilha and "id=" in url_planilha:
                id_img = url_planilha.split("id=")[-1].split("&")[0]
                url = f"https://drive.google.com/uc?id={id_img}"
            else:
                url = url_planilha

    # 3. Se tiver URL, baixa
    if url and LOGO_PADRAO not in url:
        baixar_imagem_para_disco(nome, url)
    else:
        print(f"📎 {nome} não possui imagem válida. Ignorado.")

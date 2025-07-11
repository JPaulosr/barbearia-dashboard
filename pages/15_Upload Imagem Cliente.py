import streamlit as st
import pandas as pd
import gspread
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(page_title="Upload de Imagem do Cliente", layout="wide")
st.title("📸 Upload de Imagem do Cliente")

# Autenticar via OAuth2 (Drive pessoal)
@st.cache_resource
def autenticar_drive():
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret.json",
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    creds = flow.run_local_server(port=0)
    return build("drive", "v3", credentials=creds)

# Carregar clientes do Google Sheets
@st.cache_data
def carregar_lista_clientes():
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        credenciais = st.secrets["GCP_SERVICE_ACCOUNT"]
        gc = gspread.service_account_from_dict(credenciais)
        aba = gc.open_by_url(st.secrets["PLANILHA_URL"]["url"]).worksheet("clientes_status")
        df = pd.DataFrame(aba.get_all_records())
        return sorted(df["Cliente"].dropna().unique())
    except Exception as e:
        st.error(f"Erro ao carregar lista de clientes: {e}")
        return []

# Função para upload
def upload_imagem_drive(caminho_arquivo, nome_cliente):
    try:
        servico = autenticar_drive()
        pasta_id = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
        nome_arquivo = f"{nome_cliente}.jpg"

        # Apaga arquivos anteriores com o mesmo nome
        resultados = servico.files().list(q=f"name='{nome_arquivo}' and trashed=false and '{pasta_id}' in parents",
                                          fields="files(id)").execute()
        for item in resultados.get("files", []):
            servico.files().delete(fileId=item["id"]).execute()

        # Faz upload
        metadata = {"name": nome_arquivo, "parents": [pasta_id]}
        media = MediaFileUpload(caminho_arquivo, resumable=True)
        arquivo = servico.files().create(body=metadata, media_body=media, fields="id").execute()

        # Permissões
        servico.permissions().create(fileId=arquivo["id"], body={"type": "anyone", "role": "reader"}).execute()
        return f"https://drive.google.com/uc?export=download&id={arquivo['id']}"
    except Exception as e:
        st.error(f"Erro ao fazer upload: {e}")
        return None

# Função para atualizar link na planilha
def atualizar_link_foto(nome_cliente, link):
    try:
        credenciais = st.secrets["GCP_SERVICE_ACCOUNT"]
        gc = gspread.service_account_from_dict(credenciais)
        aba = gc.open_by_url(st.secrets["PLANILHA_URL"]["url"]).worksheet("clientes_status")
        dados = aba.get_all_records()
        for i, linha in enumerate(dados):
            if linha.get("Cliente") == nome_cliente:
                aba.update_cell(i + 2, 3, link)  # Coluna C = Foto
                return True
        return False
    except Exception as e:
        st.error(f"Erro ao atualizar planilha: {e}")
        return False

# Interface
clientes = carregar_lista_clientes()
cliente_selecionado = st.selectbox("Selecione o cliente:", clientes)

arquivo = st.file_uploader("Selecione a imagem do cliente (JPG ou PNG):", type=["jpg", "jpeg", "png"])

col1, col2 = st.columns(2)

with col1:
    if st.button("💾 Substituir imagem"):
        if cliente_selecionado and arquivo:
            try:
                caminho_temp = f"temp_{cliente_selecionado}.jpg"
                with open(caminho_temp, "wb") as f:
                    f.write(arquivo.read())
                link = upload_imagem_drive(caminho_temp, cliente_selecionado)
                os.remove(caminho_temp)

                if link:
                    atualizado = atualizar_link_foto(cliente_selecionado, link)
                    if atualizado:
                        st.success("✅ Imagem enviada e planilha atualizada!")
                    else:
                        st.warning("Imagem enviada, mas cliente não encontrado na planilha.")
            except Exception as e:
                st.error(f"Erro inesperado: {e}")
        else:
            st.warning("Selecione um cliente e uma imagem primeiro.")

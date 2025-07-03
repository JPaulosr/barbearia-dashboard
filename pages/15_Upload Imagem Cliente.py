import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(page_title="Upload de Imagem do Cliente", layout="wide")
st.markdown("## 📸 Upload de Imagem do Cliente")

# Função para carregar a lista de clientes da aba "clientes_status"
@st.cache_data(show_spinner=False)
def carregar_lista_clientes():
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"]["url"])
        aba = planilha.worksheet("clientes_status")

        valores = aba.get_all_values()
        if len(valores) <= 1:
            return []

        dados = aba.get_all_records()
        df = pd.DataFrame(dados)
        return sorted(df["Cliente"].dropna().unique())

    except Exception as e:
        st.error(f"Erro ao carregar lista de clientes: {e}")
        return []

# Função para fazer upload da imagem no Google Drive
def upload_imagem_drive(caminho_arquivo, nome_cliente):
    try:
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        servico = build("drive", "v3", credentials=credenciais)

        pasta_id = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"  # Pasta pública

        nome_arquivo = f"{nome_cliente}.jpg"

        metadata = {
            "name": nome_arquivo,
            "parents": [pasta_id]
        }
        media = MediaFileUpload(caminho_arquivo, resumable=True)
        arquivo = servico.files().create(body=metadata, media_body=media, fields="id").execute()

        return True, arquivo.get("id")

    except Exception as e:
        return False, str(e)

# Interface
clientes = carregar_lista_clientes()
cliente_selecionado = st.selectbox("Selecione o cliente:", clientes)

# Mostrar imagem existente (via requests + PIL)
if cliente_selecionado:
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"]["url"])
        aba = planilha.worksheet("clientes_status")
        dados = aba.get_all_records()

        for linha in dados:
            if linha.get("Cliente") == cliente_selecionado:
                link_foto = linha.get("Foto")
                if link_foto:
                    try:
                        response = requests.get(link_foto)
                        img = Image.open(BytesIO(response.content))
                        st.image(img, caption=f"Foto de {cliente_selecionado}", use_container_width=False)
                    except Exception as erro_img:
                        st.warning("❌ Link encontrado, mas não foi possível carregar a imagem.")
                        st.text(f"Erro: {erro_img}")
                else:
                    st.info("Nenhuma imagem cadastrada para este cliente.")
                break
    except Exception as e:
        st.warning(f"Erro ao buscar imagem: {e}")

# Upload manual
arquivo = st.file_uploader("Selecione a imagem do cliente (JPG ou PNG):", type=["jpg", "jpeg", "png"])

if st.button("💾 Enviar imagem"):
    if cliente_selecionado and arquivo:
        try:
            caminho_temp = f"temp_{cliente_selecionado}.jpg"
            with open(caminho_temp, "wb") as f:
                f.write(arquivo.read())

            sucesso, resposta = upload_imagem_drive(caminho_temp, cliente_selecionado)
            os.remove(caminho_temp)

            if sucesso:
                link_imagem = f"https://drive.google.com/uc?export=download&id={resposta}"

                # Atualizar a planilha com o link
                credenciais = Credentials.from_service_account_info(
                    st.secrets["GCP_SERVICE_ACCOUNT"],
                    scopes=["https://www.googleapis.com/auth/spreadsheets"]
                )
                cliente = gspread.authorize(credenciais)
                planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"]["url"])
                aba = planilha.worksheet("clientes_status")
                dados = aba.get_all_records()

                for i, linha in enumerate(dados):
                    if linha.get("Cliente") == cliente_selecionado:
                        aba.update_cell(i + 2, 3, link_imagem)  # Coluna C (Foto)
                        break

                st.success("Imagem enviada e salva com sucesso!")
            else:
                st.error(f"Erro no upload: {resposta}")

        except Exception as erro:
            st.error(f"Erro inesperado: {erro}")
    else:
        st.warning("Selecione um cliente e uma imagem antes de enviar.")

import streamlit as st
import pandas as pd
import gspread
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import os
import requests
from PIL import Image
from io import BytesIO
import pickle

st.set_page_config(page_title="Upload de Imagem do Cliente", layout="wide")
st.title("📸 Upload de Imagem do Cliente")

# === Autenticação via OAuth 2.0 ===
@st.cache_resource
def autenticar_drive():
    SCOPES = ["https://www.googleapis.com/auth/drive", "https://www.googleapis.com/auth/spreadsheets"]
    creds = None
    token_path = "token_drive.pkl"

    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = Credentials.from_authorized_user_info(pickle.load(token), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = Flow.from_client_secrets_file(
                "client_secret.json",
                scopes=SCOPES,
                redirect_uri="https://barbearia-dashboard.streamlit.app"
            )
            auth_url, _ = flow.authorization_url(prompt="consent")
            st.markdown(f"[🔐 Clique aqui para autorizar acesso ao Google Drive]({auth_url})")
            st.stop()

        # Salvar as credenciais
        with open(token_path, "wb") as token:
            pickle.dump(creds.to_json(), token)

    return creds

# === Carrega lista de clientes da aba 'clientes_status' ===
@st.cache_data(show_spinner=False)
def carregar_lista_clientes():
    try:
        creds = autenticar_drive()
        cliente_gspread = gspread.authorize(creds)
        planilha = cliente_gspread.open_by_url(st.secrets["PLANILHA_URL"]["url"])
        aba = planilha.worksheet("clientes_status")
        dados = aba.get_all_records()
        df = pd.DataFrame(dados)
        return sorted(df["Cliente"].dropna().unique())
    except Exception as e:
        st.error(f"Erro ao carregar lista de clientes: {e}")
        return []

# === Upload da imagem ===
def upload_imagem_drive(caminho_arquivo, nome_cliente):
    try:
        creds = autenticar_drive()
        servico = build("drive", "v3", credentials=creds)

        pasta_id = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"
        nome_arquivo = f"{nome_cliente}.jpg"

        metadata = {"name": nome_arquivo, "parents": [pasta_id]}
        media = MediaFileUpload(caminho_arquivo, resumable=True)
        arquivo = servico.files().create(body=metadata, media_body=media, fields="id").execute()

        # Tornar o arquivo público
        permissao = {"type": "anyone", "role": "reader"}
        servico.permissions().create(fileId=arquivo["id"], body=permissao).execute()

        return True, arquivo.get("id")
    except Exception as e:
        return False, str(e)

# === Excluir imagem do Drive ===
def excluir_imagem_drive(nome_cliente):
    try:
        creds = autenticar_drive()
        servico = build("drive", "v3", credentials=creds)
        nome_arquivo = f"{nome_cliente}.jpg"
        resultado = servico.files().list(q=f"name='{nome_arquivo}' and trashed=false", spaces='drive', fields="files(id)").execute()
        arquivos = resultado.get("files", [])
        if arquivos:
            servico.files().delete(fileId=arquivos[0]["id"]).execute()
            return True
        return False
    except:
        return False

# === Interface Streamlit ===
clientes = carregar_lista_clientes()
cliente_selecionado = st.selectbox("Selecione o cliente:", clientes)

imagem_existente = None
if cliente_selecionado:
    try:
        creds = autenticar_drive()
        cliente_gspread = gspread.authorize(creds)
        planilha = cliente_gspread.open_by_url(st.secrets["PLANILHA_URL"]["url"])
        aba = planilha.worksheet("clientes_status")
        dados = aba.get_all_records()

        for linha in dados:
            if linha.get("Cliente") == cliente_selecionado:
                link_foto = linha.get("Foto")
                imagem_existente = link_foto
                if link_foto:
                    try:
                        response = requests.get(link_foto)
                        img = Image.open(BytesIO(response.content))
                        st.image(img, caption=f"Foto de {cliente_selecionado}", use_container_width=False)
                    except:
                        st.warning("❌ Link encontrado, mas não foi possível carregar a imagem.")
                else:
                    st.info("Nenhuma imagem cadastrada para este cliente.")
                break
    except Exception as e:
        st.warning(f"Erro ao buscar imagem: {e}")

arquivo = st.file_uploader("Selecione a imagem do cliente (JPG ou PNG):", type=["jpg", "jpeg", "png"])
col1, col2 = st.columns(2)

with col1:
    if st.button("💾 Substituir imagem"):
        if cliente_selecionado and arquivo:
            try:
                caminho_temp = f"temp_{cliente_selecionado}.jpg"
                with open(caminho_temp, "wb") as f:
                    f.write(arquivo.read())
                sucesso, resposta = upload_imagem_drive(caminho_temp, cliente_selecionado)
                os.remove(caminho_temp)

                if sucesso:
                    link_imagem = f"https://drive.google.com/uc?export=download&id={resposta}"

                    creds = autenticar_drive()
                    cliente_gspread = gspread.authorize(creds)
                    planilha = cliente_gspread.open_by_url(st.secrets["PLANILHA_URL"]["url"])
                    aba = planilha.worksheet("clientes_status")
                    dados = aba.get_all_records()

                    for i, linha in enumerate(dados):
                        if linha.get("Cliente") == cliente_selecionado:
                            aba.update_cell(i + 2, 3, link_imagem)  # Coluna C (Foto)
                            break

                    st.success("Imagem substituída com sucesso!")
                else:
                    st.error(f"Erro no upload: {resposta}")
            except Exception as erro:
                st.error(f"Erro inesperado: {erro}")
        else:
            st.warning("Selecione um cliente e uma imagem antes de enviar.")

with col2:
    if st.button("🚫 Excluir imagem"):
        if cliente_selecionado and imagem_existente:
            apagado = excluir_imagem_drive(cliente_selecionado)
            if apagado:
                try:
                    creds = autenticar_drive()
                    cliente_gspread = gspread.authorize(creds)
                    planilha = cliente_gspread.open_by_url(st.secrets["PLANILHA_URL"]["url"])
                    aba = planilha.worksheet("clientes_status")
                    dados = aba.get_all_records()
                    for i, linha in enumerate(dados):
                        if linha.get("Cliente") == cliente_selecionado:
                            aba.update_cell(i + 2, 3, "")
                            break
                    st.success("Imagem excluída com sucesso!")
                except:
                    st.warning("Imagem excluída do Drive, mas não da planilha.")
            else:
                st.warning("Imagem não encontrada no Drive para excluir.")
        else:
            st.info("Este cliente não possui imagem para excluir.")

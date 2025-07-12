import streamlit as st
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import os
import pandas as pd
import gspread

# ===== VARIÁVEIS =====
CLIENT_ID = st.secrets["GOOGLE_OAUTH"]["client_id"]
CLIENT_SECRET = st.secrets["GOOGLE_OAUTH"]["client_secret"]
REDIRECT_URI = st.secrets["GOOGLE_OAUTH"]["redirect_uris"][0]
PASTA_ID = "1-OrY7dPYJeXu3WVo-PVn8tV0tbxPtnWS"  # pasta do seu Drive
PLANILHA_URL = st.secrets["PLANILHA_URL"]

# ===== AUTENTICAÇÃO GOOGLE =====
def iniciar_autenticacao():
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": [REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ],
    )
    flow.redirect_uri = REDIRECT_URI
    auth_url, _ = flow.authorization_url(prompt="consent")
    return flow, auth_url

def trocar_codigo_por_token(flow, codigo):
    flow.fetch_token(code=codigo)
    return flow

# ===== FUNÇÕES DE DRIVE E PLANILHA =====
def listar_arquivos(drive):
    arquivos = drive.files().list(q=f"'{PASTA_ID}' in parents and trashed = false").execute()
    return arquivos.get("files", [])

def upload_imagem(drive, nome_arquivo, imagem):
    arquivos_existentes = listar_arquivos(drive)
    for arq in arquivos_existentes:
        if arq["name"] == nome_arquivo:
            drive.files().delete(fileId=arq["id"]).execute()

    media = MediaIoBaseUpload(io.BytesIO(imagem.read()), mimetype="image/jpeg")
    novo_arquivo = drive.files().create(
        body={"name": nome_arquivo, "parents": [PASTA_ID]},
        media_body=media,
        fields="id"
    ).execute()
    link_publico = f"https://drive.google.com/uc?id={novo_arquivo['id']}"
    return link_publico

def atualizar_link_na_planilha(nome_cliente, link, flow):
    try:
        gc = gspread.authorize(flow.credentials)
        sh = gc.open_by_url(PLANILHA_URL)
        aba = sh.worksheet("clientes_status")

        nomes = aba.col_values(1)
        if nome_cliente in nomes:
            row_index = nomes.index(nome_cliente) + 1
            aba.update_cell(row_index, 3, link)
        else:
            st.warning("Cliente não encontrado na planilha.")
    except Exception as e:
        st.error(f"Erro ao atualizar planilha: {e}")

def excluir_imagem(drive, nome_arquivo):
    arquivos = listar_arquivos(drive)
    for arq in arquivos:
        if arq["name"] == nome_arquivo:
            drive.files().delete(fileId=arq["id"]).execute()
            return True
    return False

# ===== INTERFACE =====
st.title("📷 Upload Imagem Cliente")
st.markdown("Faça upload da imagem do cliente. O nome do arquivo será salvo como `nome_cliente.jpg`.")

flow = None
if "flow" not in st.session_state:
    flow, auth_url = iniciar_autenticacao()
    st.session_state["flow"] = flow
    st.markdown(f"[🔐 Clique aqui para autenticar com Google]({auth_url})")
    codigo = st.text_input("Cole aqui o código de autenticação:")
    if codigo:
        try:
            flow = trocar_codigo_por_token(flow, codigo)
            st.session_state["flow"] = flow
            st.success("Autenticação realizada com sucesso!")
            st.rerun()
        except Exception as e:
            st.error(f"Erro na autenticação: {e}")
    st.stop()

flow = st.session_state["flow"]
drive = build("drive", "v3", credentials=flow.credentials)

# ===== CLIENTES DA PLANILHA =====
try:
    gc = gspread.authorize(flow.credentials)
    aba = gc.open_by_url(PLANILHA_URL).worksheet("clientes_status")
    nomes = aba.col_values(1)
    nomes = sorted(list(set(n for n in nomes if n.strip() and n.lower() not in ["brasileiro", "boliviano", "menino"])))
except Exception as e:
    st.error(f"Erro ao carregar clientes: {e}")
    st.stop()

nome_cliente = st.selectbox("Selecione o cliente", nomes)
nome_arquivo = f"{nome_cliente}.jpg"
arquivos = listar_arquivos(drive)

# ===== PRÉVIA SE EXISTE IMAGEM =====
link_existente = None
for arq in arquivos:
    if arq["name"] == nome_arquivo:
        link_existente = f"https://drive.google.com/uc?id={arq['id']}"
        break

if link_existente:
    st.image(link_existente, width=250)
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🗑️ Excluir imagem"):
            if excluir_imagem(drive, nome_arquivo):
                st.success("Imagem excluída.")
                st.rerun()
    with col2:
        imagem = st.file_uploader("Substituir imagem", type=["jpg", "jpeg"])
        if imagem:
            link = upload_imagem(drive, nome_arquivo, imagem)
            atualizar_link_na_planilha(nome_cliente, link, flow)
            st.success("Imagem substituída com sucesso.")
            st.image(link, width=250)
else:
    imagem = st.file_uploader("Escolher imagem", type=["jpg", "jpeg"])
    if imagem:
        link = upload_imagem(drive, nome_arquivo, imagem)
        atualizar_link_na_planilha(nome_cliente, link, flow)
        st.success("Imagem enviada com sucesso.")
        st.image(link, width=250)

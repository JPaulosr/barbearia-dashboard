import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import os

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
            return [], aba

        dados = aba.get_all_records()
        df = pd.DataFrame(dados)
        return sorted(df["Cliente"].dropna().unique()), aba

    except Exception as e:
        st.error(f"Erro ao carregar lista de clientes: {e}")
        return [], None

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

        link_imagem = f"https://drive.google.com/uc?id={arquivo.get('id')}"
        return True, link_imagem

    except Exception as e:
        return False, str(e)

# Função para atualizar o link da imagem na planilha
def atualizar_link_imagem(aba, nome_cliente, link):
    try:
        dados = aba.get_all_records()
        for idx, row in enumerate(dados):
            if row.get("Cliente", "").strip().lower() == nome_cliente.strip().lower():
                colunas = aba.row_values(1)
                if "Foto" not in colunas:
                    aba.update_cell(1, len(colunas)+1, "Foto")
                    colunas.append("Foto")
                coluna_foto_idx = colunas.index("Foto") + 1
                aba.update_cell(idx + 2, coluna_foto_idx, link)
                return True
        return False
    except Exception as e:
        st.error(f"Erro ao atualizar link da imagem na planilha: {e}")
        return False

# Interface
clientes, aba_clientes = carregar_lista_clientes()
cliente_selecionado = st.selectbox("Selecione o cliente:", clientes)

# Mostrar imagem atual do cliente (se existir)
if cliente_selecionado and aba_clientes is not None:
    dados = aba_clientes.get_all_records()
    df = pd.DataFrame(dados)
    linha_cliente = df[df["Cliente"].str.lower() == cliente_selecionado.lower()]
    if not linha_cliente.empty and "Foto" in linha_cliente.columns:
        link_imagem = linha_cliente["Foto"].values[0]
        if isinstance(link_imagem, str) and link_imagem.strip():
            st.image(link_imagem, caption=f"Foto de {cliente_selecionado}", width=200)

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
                atualizado = atualizar_link_imagem(aba_clientes, cliente_selecionado, resposta)
                if atualizado:
                    st.success("Imagem enviada e link atualizado com sucesso!")
                    st.image(resposta, caption="Pré-visualização", width=200)
                else:
                    st.warning("Upload feito, mas cliente não encontrado na planilha para atualizar o link.")
            else:
                st.error(f"Erro no upload: {resposta}")

        except Exception as erro:
            st.error(f"Erro inesperado: {erro}")
    else:
        st.warning("Selecione um cliente e uma imagem antes de enviar.")

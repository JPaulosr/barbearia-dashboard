import streamlit as st
import pandas as pd
import cloudinary
import cloudinary.uploader
import cloudinary.api
import requests
from io import BytesIO
from PIL import Image
from google.oauth2.service_account import Credentials
import gspread
import base64

st.set_page_config(page_title="Upload Imagem Cliente")
st.markdown("""
    <h1 style='text-align: center;'>📸 Upload Imagem Cliente</h1>
    <p style='text-align: center;'>Envie ou substitua a imagem do cliente. O nome do arquivo será <code>nome_cliente.jpg</code>.</p>
""", unsafe_allow_html=True)

# =============== CONFIGURAR CLOUDINARY ===============
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

# =============== FUNÇÃO PARA CARREGAR PLANILHA CLIENTES ===============
def carregar_clientes_status():
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"])
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_url(st.secrets["PLANILHA_URL"])
    aba = spreadsheet.worksheet("clientes_status")
    dados = aba.get_all_records()
    return pd.DataFrame(dados), aba

df_status, aba_status = carregar_clientes_status()
nomes_clientes = df_status['Nome'].dropna().unique().tolist()

# =============== SELEÇÃO COM AUTOCOMPLETE ===============
nome_cliente = st.selectbox("Selecione o cliente", sorted(nomes_clientes), placeholder="Digite para buscar...")

nome_arquivo = nome_cliente.lower().replace(" ", "_") + ".jpg"
pasta = "Fotos clientes"

# =============== FUNÇÃO PARA VERIFICAR SE IMAGEM EXISTE ===============
def imagem_existe(nome):
    try:
        response = cloudinary.api.resource(f"{pasta}/{nome}")
        return True, response['secure_url']
    except:
        return False, None

# =============== VERIFICAR SE JÁ EXISTE ===============
existe, url_existente = imagem_existe(nome_arquivo)

# =============== MOSTRAR PRÉVIA SE EXISTIR ===============
if existe:
    st.image(url_existente, width=250, caption="Imagem atual do cliente")
    st.warning("Este cliente já possui uma imagem cadastrada.")

# =============== UPLOAD DE NOVA IMAGEM ===============
arquivo = st.file_uploader("Envie a nova imagem", type=['jpg', 'jpeg', 'png'])

# =============== SUBSTITUIÇÃO COM CONFIRMAÇÃO ===============
if arquivo is not None:
    if existe:
        if not st.checkbox("Confirmo que desejo substituir a imagem existente."):
            st.stop()

    if st.button("📤 Enviar imagem"):
        try:
            resultado = cloudinary.uploader.upload(arquivo,
                folder=pasta,
                public_id=nome_arquivo.replace(".jpg", ""),
                overwrite=True,
                resource_type="image"
            )
            url = resultado['secure_url']

            # Atualiza a planilha
            idx = df_status[df_status['Nome'] == nome_cliente].index[0]
            aba_status.update_cell(idx + 2, df_status.columns.get_loc("Link") + 1, url)

            st.success("Imagem enviada com sucesso!")
            st.image(url, width=300)
        except Exception as e:
            st.error(f"Erro ao enviar imagem: {e}")

# =============== BOTÃO DELETAR ===============
if existe:
    if st.button("🗑️ Deletar imagem"):
        try:
            cloudinary.uploader.destroy(f"{pasta}/{nome_arquivo.replace('.jpg', '')}", resource_type="image")
            st.success("Imagem deletada com sucesso.")
            st.experimental_rerun()
        except:
            st.error("Erro ao deletar imagem.")

# =============== GALERIA DE PRÉ-VISUALIZAÇÕES ===============
st.markdown("---")
st.subheader("🖼️ Galeria de imagens salvas")

colunas = st.columns(5)
contador = 0

for i, nome in enumerate(sorted(nomes_clientes)):
    nome_arquivo = nome.lower().replace(" ", "_") + ".jpg"
    existe, url = imagem_existe(nome_arquivo)
    if existe:
        with colunas[contador % 5]:
            st.image(url, width=100, caption=nome)
        contador += 1

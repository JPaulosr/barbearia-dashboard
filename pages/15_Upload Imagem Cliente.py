import streamlit as st
import pandas as pd
import cloudinary
import cloudinary.uploader
import cloudinary.api
import gspread
from io import BytesIO
from PIL import Image
from google.oauth2.service_account import Credentials

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

# =============== CONECTAR À PLANILHA =================
def carregar_clientes_status():
    creds = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_url(st.secrets["PLANILHA_URL"])
    aba = spreadsheet.worksheet("clientes_status")
    dados = aba.get_all_records()
    return pd.DataFrame(dados), aba

df_status, aba_status = carregar_clientes_status()
df_status.columns = df_status.columns.str.strip()

if 'Cliente' not in df_status.columns:
    st.error("A coluna 'Cliente' não foi encontrada na aba 'clientes_status'.")
    st.stop()

nomes_clientes = df_status['Cliente'].dropna().unique().tolist()

# =============== SELEÇÃO DO CLIENTE ===============
nome_cliente = st.selectbox("Selecione o cliente", sorted(nomes_clientes), placeholder="Digite para buscar...")
nome_arquivo = nome_cliente.lower().replace(" ", "_") + ".jpg"
pasta = "Fotos clientes"

# =============== VERIFICAR SE IMAGEM EXISTE ===============
def imagem_existe(nome):
    try:
        # Tenta encontrar no Cloudinary
        response = cloudinary.api.resource(f"{pasta}/{nome}")
        return True, response['secure_url']
    except:
        # Fallback: usa link da planilha se houver
        url_fallback = df_status.loc[df_status['Cliente'] == nome_cliente, 'Foto'].values
        if len(url_fallback) > 0 and url_fallback[0]:
            return True, url_fallback[0]
        return False, None

existe, url_existente = imagem_existe(nome_arquivo)

# =============== MOSTRAR IMAGEM SE EXISTIR ===============
if existe:
    st.image(url_existente, width=250, caption="Imagem atual do cliente")
    st.warning("Este cliente já possui uma imagem cadastrada.")

# =============== UPLOAD DE NOVA IMAGEM ===============
arquivo = st.file_uploader("Envie a nova imagem", type=['jpg', 'jpeg', 'png'])

if arquivo is not None:
    if existe and not st.checkbox("Confirmo que desejo substituir a imagem existente."):
        st.stop()

    if st.button("📤 Enviar imagem"):
        try:
            resultado = cloudinary.uploader.upload(
                arquivo,
                folder=pasta,
                public_id=nome_arquivo.replace(".jpg", ""),
                overwrite=True,
                resource_type="image"
            )
            url = resultado['secure_url']

            # Atualiza a planilha com novo link
            idx = df_status[df_status['Cliente'] == nome_cliente].index[0]
            aba_status.update_cell(idx + 2, df_status.columns.get_loc("Foto") + 1, url)

            st.success("Imagem enviada com sucesso!")
            st.image(url, width=300)
        except Exception as e:
            st.error(f"Erro ao enviar imagem: {e}")

# =============== BOTÃO DELETAR ===============
if existe and st.button("🗑️ Deletar imagem"):
    try:
        cloudinary.uploader.destroy(f"{pasta}/{nome_arquivo.replace('.jpg', '')}", resource_type="image")
        st.success("Imagem deletada do Cloudinary com sucesso.")
        st.experimental_rerun()
    except:
        st.error("Erro ao deletar imagem.")

# =============== GALERIA ===============
st.markdown("---")
st.subheader("🖼️ Galeria de imagens salvas")

colunas = st.columns(5)
contador = 0

for nome in sorted(nomes_clientes):
    nome_arquivo = nome.lower().replace(" ", "_") + ".jpg"
    existe, url = imagem_existe(nome_arquivo)
    if existe:
        with colunas[contador % 5]:
            st.image(url, width=100, caption=nome)
        contador += 1

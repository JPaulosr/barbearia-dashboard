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

# Remove clientes vazios
nomes_clientes = sorted([nome for nome in df_status['Cliente'].dropna() if nome.strip() != ""])

# =============== SELEÇÃO DO CLIENTE ===============
nome_cliente = st.selectbox("Selecione o cliente", nomes_clientes, placeholder="Digite para buscar...")
nome_arquivo = nome_cliente.lower().replace(" ", "_") + ".jpg"
pasta = "Fotos clientes"

# =============== VERIFICAR SE IMAGEM EXISTE ===============
def imagem_existe(nome):
    try:
        response = cloudinary.api.resource(f"{pasta}/{nome}")
        return True, response['secure_url']
    except:
        url_fallback = df_status.loc[df_status['Cliente'] == nome_cliente, 'Foto'].values
        if len(url_fallback) > 0 and url_fallback[0]:
            url = url_fallback[0]
            if "drive.google.com" in url and "id=" in url:
                id_img = url.split("id=")[-1].split("&")[0]
                url = f"https://drive.google.com/uc?id={id_img}"
            return True, url
        return False, None

existe, url_existente = imagem_existe(nome_arquivo)

# =============== MOSTRAR IMAGEM SE EXISTIR ===============
if existe:
    st.image(url_existente, width=250, caption="Imagem atual do cliente")
    st.warning("Este cliente já possui uma imagem cadastrada.")
else:
    st.info("Este cliente ainda não possui imagem cadastrada.")

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

        nomes_planilha = aba_status.col_values(1)
        linha_cliente = None
        for i, nome in enumerate(nomes_planilha, start=1):
            if nome.strip().lower() == nome_cliente.strip().lower():
                linha_cliente = i
                break

        if linha_cliente:
            col_foto = df_status.columns.get_loc("Foto") + 1
            aba_status.update_cell(linha_cliente, col_foto, "")
            st.success("Link da imagem removido da planilha com sucesso.")
        else:
            st.warning("Cliente não encontrado na planilha para limpar o link.")

        st.experimental_rerun()
    except Exception as e:
        st.error(f"Erro ao deletar imagem: {e}")

# =============== GALERIA ===============
st.markdown("---")
st.subheader("🖼️ Galeria de imagens salvas")

colunas = st.columns(5)
contador = 0

for nome in nomes_clientes:
    nome_arquivo = nome.lower().replace(" ", "_") + ".jpg"
    try:
        response = cloudinary.api.resource(f"{pasta}/{nome_arquivo}")
        url = response['secure_url']
    except:
        url = df_status.loc[df_status['Cliente'] == nome, 'Foto'].values
        if len(url) > 0 and url[0]:
            url = url[0]
            if "drive.google.com" in url and "id=" in url:
                id_img = url.split("id=")[-1].split("&")[0]
                url = f"https://drive.google.com/uc?id={id_img}"
        else:
            url = None

    if url:
        with colunas[contador % 5]:
            st.image(url, width=100, caption=nome)
        contador += 1

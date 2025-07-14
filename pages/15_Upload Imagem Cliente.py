import streamlit as st
import cloudinary
import cloudinary.uploader
import pandas as pd
import requests
from io import BytesIO
from PIL import Image
from st_aggrid import AgGrid

# 🔐 Configurações da API Cloudinary (a partir do st.secrets)
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

# 📊 Carregar lista de clientes
def carregar_clientes():
    url = st.secrets["PLANILHA_URL"]
    sheet_id = url.split("/d/")[1].split("/")[0]
    aba = "clientes_status"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={aba}"
    df = pd.read_csv(csv_url)
    df = df[df["Cliente"].notna()]
    df = df.drop_duplicates(subset=["Cliente"])
    return df

# 🔄 Verifica se já existe uma imagem com o nome do cliente
def imagem_existe(nome_arquivo):
    try:
        response = cloudinary.api.resource(f"Fotos clientes/{nome_arquivo}")
        return response.get("secure_url")
    except cloudinary.exceptions.NotFound:
        return None

# ⬆️ Upload de imagem para Cloudinary
def upload_imagem(imagem, nome_arquivo):
    return cloudinary.uploader.upload(
        imagem,
        public_id=f"Fotos clientes/{nome_arquivo}",
        overwrite=True,
        resource_type="image"
    )

# ❌ Excluir imagem do Cloudinary
def deletar_imagem(nome_arquivo):
    return cloudinary.uploader.destroy(f"Fotos clientes/{nome_arquivo}")

# 📸 Mostrar imagem a partir da URL
def mostrar_imagem(url):
    response = requests.get(url)
    if response.status_code == 200:
        img = Image.open(BytesIO(response.content))
        st.image(img, caption="Imagem atual", use_column_width=True)

# ========== UI ========== #
st.title("📸 Upload Imagem Cliente")
st.caption("Envie ou substitua a imagem do cliente. O nome do arquivo será `nome_cliente.jpg`.")

clientes_df = carregar_clientes()
nomes_clientes = sorted(clientes_df["Cliente"].unique())

nome_cliente = st.selectbox("Selecione o cliente", nomes_clientes, index=None, placeholder="Digite para buscar...")

if nome_cliente:
    nome_arquivo = f"{nome_cliente}.jpg"
    url_existente = imagem_existe(nome_arquivo)

    if url_existente:
        st.success("Imagem já existente:")
        mostrar_imagem(url_existente)
        substituir = st.checkbox("🔁 Substituir imagem existente?")
    else:
        substituir = True

    uploaded_file = st.file_uploader("Escolher nova imagem", type=["jpg", "jpeg"])

    if uploaded_file and substituir:
        resultado = upload_imagem(uploaded_file, nome_arquivo)
        st.success("Imagem enviada com sucesso!")
        mostrar_imagem(resultado["secure_url"])

    if url_existente:
        if st.button("🗑️ Deletar imagem existente"):
            deletar_imagem(nome_arquivo)
            st.warning("Imagem deletada.")

# ========== Galeria ========== #
st.divider()
st.subheader("🖼️ Galeria de Imagens")

def listar_imagens():
    try:
        resultado = cloudinary.api.resources(type="upload", prefix="Fotos clientes/", resource_type="image")
        return resultado.get("resources", [])
    except Exception as e:
        st.error(f"Erro ao listar imagens: {e}")
        return []

galeria = listar_imagens()
if galeria:
    for img in galeria:
        col1, col2 = st.columns([1, 4])
        with col1:
            st.image(img["secure_url"], use_column_width=True)
        with col2:
            st.markdown(f"**{img['public_id'].split('/')[-1]}**")
            st.caption(f"Última modificação: {img['created_at'][:10]}")
else:
    st.info("Nenhuma imagem encontrada na pasta 'Fotos clientes'.")

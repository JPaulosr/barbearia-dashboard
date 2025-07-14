import streamlit as st
import cloudinary
import cloudinary.uploader
import pandas as pd
from io import BytesIO
import requests

st.set_page_config(page_title="Upload Imagem Cliente", page_icon="📸")

st.title("📸 Upload Imagem Cliente")
st.markdown("Envie ou substitua a imagem do cliente. O nome do arquivo será `nome_cliente.jpg`.")

# ================================
# Configurar Cloudinary com st.secrets
# ================================
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

# ================================
# Carregar lista de clientes (da aba clientes_status)
# ================================
@st.cache_data
def carregar_clientes():
    url = st.secrets["PLANILHA_URL"]
    sheet_id = url.split("/d/")[1].split("/")[0]
    aba = "clientes_status"
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={aba}"
    df = pd.read_csv(csv_url)
    clientes = sorted(df['Cliente'].dropna().unique())
    return clientes

clientes = carregar_clientes()
cliente_selecionado = st.selectbox("Selecione o cliente", clientes)

# ================================
# Upload da imagem
# ================================
imagem = st.file_uploader("Escolher nova imagem", type=["jpg", "jpeg"])

if imagem and cliente_selecionado:
    nome_arquivo = cliente_selecionado.strip().lower().replace(" ", "_") + ".jpg"
    
    if st.button("📤 Enviar imagem"):
        try:
            resultado = cloudinary.uploader.upload(
                imagem,
                public_id=nome_arquivo,
                overwrite=True,
                resource_type="image",
                folder="Fotos clientes"
            )
            url = resultado["secure_url"]
            st.success(f"✅ Imagem enviada com sucesso!")
            st.image(url, caption="Prévia da imagem", use_column_width=True)
            st.markdown(f"📎 **URL da imagem:** {url}")
        except Exception as e:
            st.error(f"Erro ao enviar imagem: {e}")

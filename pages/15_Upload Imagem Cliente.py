import streamlit as st
import pandas as pd
import gspread
import cloudinary
import cloudinary.uploader
from google.oauth2.service_account import Credentials
from PIL import Image
from io import BytesIO
import requests
import os

st.set_page_config(page_title="Upload Imagem Cliente", layout="wide")
st.title("📸 Upload Imagem Cliente")

# =============== CONFIGURAÇÕES ===============
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(st.secrets["GCP_SERVICE_ACCOUNT"], scopes=SCOPES)
gc = gspread.authorize(creds)
planilha = gc.open_by_url(st.secrets["PLANILHA_URL"])
aba_clientes = planilha.worksheet("clientes_status")
df = pd.DataFrame(aba_clientes.get_all_records())
df.columns = df.columns.str.strip()

# =============== INTERFACE ===============
clientes = df["Cliente"].dropna().unique().tolist()
cliente_escolhido = st.selectbox("Selecione o cliente", sorted(clientes))

# Nome formatado para uso no Cloudinary
nome_formatado = cliente_escolhido.lower().strip().replace(" ", "_") + ".jpg"
pasta = "Fotos clientes"

# Verifica se cliente já possui imagem
url_cloudinary = None
try:
    resource = cloudinary.api.resource(f"{pasta}/{nome_formatado}")
    url_cloudinary = resource["secure_url"]
except:
    pass

# Mostra imagem atual
if url_cloudinary:
    st.image(url_cloudinary, caption="Imagem atual do cliente", width=200)
    st.info("Este cliente já possui uma imagem cadastrada.")

# Upload de nova imagem
st.markdown("#### Envie a nova imagem")
upload = st.file_uploader("Drag and drop file here", type=["jpg", "jpeg", "png"])

# Deletar imagem existente
if url_cloudinary:
    if st.button("🗑️ Deletar imagem"):
        try:
            cloudinary.uploader.destroy(f"{pasta}/{nome_formatado}")
            st.success("Imagem deletada do Cloudinary com sucesso.")

            # ======= ATUALIZAÇÃO NA PLANILHA =======
            try:
                nomes_planilha = aba_clientes.col_values(1)  # Assumindo que a coluna A tem os nomes
                linha_cliente = None
                for i, nome in enumerate(nomes_planilha, start=1):
                    if nome.strip().lower() == cliente_escolhido.strip().lower():
                        linha_cliente = i
                        break

                if linha_cliente:
                    col_foto = df.columns.get_loc("Foto") + 1  # Posição real da coluna "Foto"
                    aba_clientes.update_cell(linha_cliente, col_foto, "")
                    st.success("✅ Link da imagem removido da planilha com sucesso.")
                else:
                    st.warning("⚠️ Cliente não encontrado na planilha para limpar o link.")
            except Exception as e:
                st.error(f"Erro ao deletar link da planilha: {e}")

            st.experimental_rerun()
        except Exception as e:
            st.error(f"Erro ao deletar imagem: {e}")

# Enviar imagem nova para Cloudinary
if upload is not None:
    try:
        cloudinary.uploader.upload(upload, public_id=f"{pasta}/{nome_formatado}", overwrite=True)
        url_nova = cloudinary.CloudinaryImage(f"{pasta}/{nome_formatado}").build_url(secure=True)

        # Atualiza a célula correspondente
        nomes_planilha = aba_clientes.col_values(1)
        linha_cliente = None
        for i, nome in enumerate(nomes_planilha, start=1):
            if nome.strip().lower() == cliente_escolhido.strip().lower():
                linha_cliente = i
                break

        if linha_cliente:
            col_foto = df.columns.get_loc("Foto") + 1
            aba_clientes.update_cell(linha_cliente, col_foto, url_nova)
            st.success("✅ Imagem enviada e link atualizado com sucesso!")
            st.experimental_rerun()
        else:
            st.warning("⚠️ Cliente não encontrado na planilha para atualizar link.")
    except Exception as e:
        st.error(f"Erro ao fazer upload da imagem: {e}")

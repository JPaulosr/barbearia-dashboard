import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import cloudinary
import cloudinary.uploader

# ===== CONFIGURAÇÕES =====
PLANILHA_URL = st.secrets["PLANILHA_URL"]

# ===== AUTENTICAÇÃO GOOGLE VIA CONTA DE SERVIÇO =====
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]
credentials = ServiceAccountCredentials.from_json_keyfile_dict(
    st.secrets["GCP_SERVICE_ACCOUNT"], scopes=scope
)

# ===== CONECTA À PLANILHA =====
try:
    gc = gspread.authorize(credentials)
    aba = gc.open_by_url(PLANILHA_URL).worksheet("clientes_status")
    nomes = aba.col_values(1)
    nomes = sorted(list(set(n for n in nomes if n.strip() and n.lower() not in ["brasileiro", "boliviano", "menino"])))
except Exception as e:
    st.error(f"Erro ao carregar clientes: {e}")
    st.stop()

# ===== CONFIGURAÇÃO CLOUDINARY =====
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

def upload_imagem_cloudinary(imagem, nome_cliente):
    resultado = cloudinary.uploader.upload(
        imagem,
        public_id=nome_cliente,
        overwrite=True,
        resource_type="image"
    )
    return resultado["secure_url"]

def excluir_imagem_cloudinary(nome_cliente):
    try:
        cloudinary.uploader.destroy(nome_cliente, resource_type="image")
        return True
    except Exception as e:
        st.error(f"Erro ao excluir imagem: {e}")
        return False

def atualizar_link_na_planilha(nome_cliente, link):
    try:
        nomes = aba.col_values(1)
        if nome_cliente in nomes:
            row_index = nomes.index(nome_cliente) + 1
            aba.update_cell(row_index, 3, link)
        else:
            st.warning("Cliente não encontrado na planilha.")
    except Exception as e:
        st.error(f"Erro ao atualizar planilha: {e}")

# ===== INTERFACE =====
st.title("📷 Upload Imagem Cliente")
st.markdown("Faça upload da imagem do cliente. O nome do arquivo será salvo como `nome_cliente.jpg` no Cloudinary.")

nome_cliente = st.selectbox("Selecione o cliente", nomes)
link_existente = f"https://res.cloudinary.com/{st.secrets['CLOUDINARY']['cloud_name']}/image/upload/{nome_cliente}.jpg"

# ===== PRÉVIA DA IMAGEM EXISTENTE =====
st.markdown("### Prévia atual:")
st.image(link_existente, width=250)

col1, col2 = st.columns(2)

with col1:
    if st.button("🗑️ Excluir imagem"):
        if excluir_imagem_cloudinary(nome_cliente):
            st.success("Imagem excluída com sucesso.")
            aba.update_cell(nomes.index(nome_cliente)+1, 3, "")
            st.experimental_rerun()

with col2:
    imagem = st.file_uploader("Substituir imagem", type=["jpg", "jpeg"])
    if imagem:
        link = upload_imagem_cloudinary(imagem, nome_cliente)
        atualizar_link_na_planilha(nome_cliente, link)
        st.success("Imagem atualizada com sucesso!")
        st.image(link, width=250)

import streamlit as st
import pandas as pd
import cloudinary
import cloudinary.uploader
import cloudinary.api
from io import BytesIO
from PIL import Image
from st_aggrid import AgGrid
from google.oauth2 import service_account
import gspread

# --- Configurar Cloudinary ---
cloudinary.config(
    cloud_name="db8ipmete",
    api_key="144536432264916",
    api_secret="eVwo_kpkphpGDi4djTzNYGC5qJQ"
)

# --- Carregar planilha clientes_status via Google Sheets ---
def carregar_clientes_status():
    escopo = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]

    credenciais_dict = {
        "type": "service_account",
        "project_id": "barbearia-dashboard",
        "private_key_id": "7c71bcbfaa1a8d935e1474fcabbe0c7c7ea8cae5",
        "private_key": """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC8pdM0rUTx9rd7
... (chave privada completa) ...
-----END PRIVATE KEY-----""",
        "client_email": "streamlit-reader@barbearia-dashboard.iam.gserviceaccount.com",
        "client_id": "102292204018013167995",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/streamlit-reader@barbearia-dashboard.iam.gserviceaccount.com"
    }

    creds = service_account.Credentials.from_service_account_info(credenciais_dict, scopes=escopo)
    cliente = gspread.authorize(creds)
    planilha = cliente.open_by_url("https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/edit?usp=sharing")
    aba = planilha.worksheet("clientes_status")
    dados = aba.get_all_records()
    return pd.DataFrame(dados), aba

df_status, aba_status = carregar_clientes_status()

# --- Verificar se imagem já existe no Cloudinary ---
def imagem_existe(nome_arquivo):
    try:
        cloudinary.api.resource(f"Fotos clientes/{nome_arquivo}")
        return True
    except cloudinary.exceptions.NotFound:
        return False
    except Exception as e:
        st.error(f"Erro ao verificar imagem: {e}")
        return False

# --- Excluir imagem do Cloudinary ---
def excluir_imagem(nome_arquivo):
    try:
        cloudinary.uploader.destroy(f"Fotos clientes/{nome_arquivo}", resource_type="image")
        return True
    except Exception as e:
        st.error(f"Erro ao excluir imagem: {e}")
        return False

# --- Atualizar link na planilha ---
def atualizar_link(cliente, url):
    try:
        celulas = aba_status.findall(cliente)
        for c in celulas:
            if aba_status.cell(c.row, 1).value == cliente:
                aba_status.update_cell(c.row, 4, url)  # Coluna 4 = link imagem
                break
    except Exception as e:
        st.warning(f"Erro ao atualizar link da imagem: {e}")

# --- UI principal ---
st.header("📸 Upload Imagem Cliente")
st.caption("Envie ou substitua a imagem do cliente. O nome do arquivo será `nome_cliente.jpg`.")

clientes = sorted(df_status["Cliente"].dropna().unique().tolist())
cliente = st.selectbox("Selecione o cliente", clientes)

imagem = st.file_uploader("Escolher nova imagem", type=["jpg", "jpeg"])

nome_arquivo = f"{cliente}.jpg"
caminho_cloud = f"Fotos clientes/{nome_arquivo}"

if imagem and cliente:
    if imagem_existe(nome_arquivo):
        st.warning("⚠️ Já existe uma imagem com esse nome.")
        confirmar = st.checkbox("Deseja substituir a imagem existente?")
        if confirmar:
            resultado = cloudinary.uploader.upload(imagem, public_id=caminho_cloud, overwrite=True, resource_type="image")
            st.success("Imagem substituída com sucesso!")
            st.image(resultado["secure_url"], width=300)
            atualizar_link(cliente, resultado["secure_url"])
    else:
        resultado = cloudinary.uploader.upload(imagem, public_id=caminho_cloud, overwrite=False, resource_type="image")
        st.success("Imagem enviada com sucesso!")
        st.image(resultado["secure_url"], width=300)
        atualizar_link(cliente, resultado["secure_url"])

# --- Botão para excluir imagem existente ---
st.divider()
st.subheader("🗑️ Excluir imagem de cliente")

cliente_excluir = st.selectbox("Cliente para excluir imagem", clientes, key="excluir")
nome_excluir = f"{cliente_excluir}.jpg"

if imagem_existe(nome_excluir):
    if st.button("Excluir imagem"):
        sucesso = excluir_imagem(nome_excluir)
        if sucesso:
            st.success("Imagem excluída com sucesso!")
else:
    st.info("Esse cliente ainda não possui imagem salva.")

# --- Galeria com preview das imagens ---
st.divider()
st.subheader("🖼️ Galeria de Clientes com Imagem")

imagens = []
for cliente in clientes:
    nome_img = f"{cliente}.jpg"
    try:
        dados = cloudinary.api.resource(f"Fotos clientes/{nome_img}")
        imagens.append((cliente, dados["secure_url"]))
    except:
        continue

colunas = st.columns(4)
for i, (nome, url) in enumerate(imagens):
    with colunas[i % 4]:
        st.image(url, caption=nome, width=150)

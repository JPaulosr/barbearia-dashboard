import streamlit as st
import pandas as pd
import cloudinary
import cloudinary.api
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="📷 Galeria de Clientes", layout="wide")

# ============ CONFIGURAR CLOUDINARY ============
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

# ============ LOGO PADRÃO ===============
LOGO_PADRAO = "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png"
PASTA_CLOUDINARY = "Fotos clientes"

# ============ CONECTAR PLANILHA ============
def carregar_clientes_status():
    creds = Credentials.from_service_account_info(
        st.secrets["GCP_SERVICE_ACCOUNT"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_url(st.secrets["PLANILHA_URL"])
    aba = spreadsheet.worksheet("clientes_status")
    dados = aba.get_all_records()
    return pd.DataFrame(dados)

df_status = carregar_clientes_status()
df_status.columns = df_status.columns.str.strip()
clientes = sorted(df_status['Cliente'].dropna().unique())

# ============ CAIXA DE BUSCA ============
busca = st.text_input("🔎 Buscar cliente por nome").strip().lower()
clientes_filtrados = [c for c in clientes if busca in c.lower()] if busca else clientes

# ============ EXIBIR GALERIA ============
st.markdown("### 🖼️ Galeria de Imagens dos Clientes")
colunas = st.columns(6)
contador = 0

for nome in clientes_filtrados:
    nome_arquivo = nome.lower().replace(" ", "_") + ".jpg"
    url = None

    # Tenta pegar do Cloudinary
    try:
        recurso = cloudinary.api.resource(f"{PASTA_CLOUDINARY}/{nome_arquivo}")
        url = recurso['secure_url']
    except:
        # Se não achar, tenta pegar da planilha
        linha = df_status[df_status['Cliente'] == nome]
        if not linha.empty and linha['Foto'].values[0]:
            url_planilha = linha['Foto'].values[0]
            if "drive.google.com" in url_planilha and "id=" in url_planilha:
                id_img = url_planilha.split("id=")[-1].split("&")[0]
                url = f"https://drive.google.com/uc?id={id_img}"
            else:
                url = url_planilha

    with colunas[contador % 6]:
        st.image(url if url else LOGO_PADRAO, width=120, caption=nome)
    contador += 1

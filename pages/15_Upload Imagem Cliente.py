import streamlit as st
import pandas as pd
import requests
import cloudinary
import cloudinary.uploader
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Migrar Imagens para Cloudinary")
st.title("📤 Migrar Imagens da Planilha para Cloudinary")

# ========== CONFIGURAÇÕES ==========
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

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

df, aba = carregar_clientes_status()
df.columns = df.columns.str.strip()

if 'Cliente' not in df.columns or 'Foto' not in df.columns:
    st.error("A planilha precisa ter as colunas 'Cliente' e 'Foto'.")
    st.stop()

# ========== INICIAR MIGRAÇÃO ==========
st.warning("Essa ferramenta vai migrar todas as imagens da planilha para o Cloudinary. Somente execute uma vez.")

if st.button("🚀 Iniciar migração para Cloudinary"):
    total = 0
    migrados = 0
    erros = 0

    for idx, row in df.iterrows():
        nome = row['Cliente']
        url = row['Foto']

        if not nome or not url:
            continue

        # Ignora se já está no Cloudinary
        if "res.cloudinary.com" in url:
            continue

        # Converte link do Google Drive
        if "drive.google.com" in url and "id=" in url:
            id_img = url.split("id=")[-1].split("&")[0]
            url = f"https://drive.google.com/uc?id={id_img}"

        try:
            response = requests.get(url)
            response.raise_for_status()
            content = response.content

            nome_arquivo = nome.lower().replace(" ", "_") + ".jpg"
            resultado = cloudinary.uploader.upload(
                content,
                folder="Fotos clientes",
                public_id=nome_arquivo.replace(".jpg", ""),
                overwrite=True,
                resource_type="image"
            )

            novo_link = resultado['secure_url']
            aba.update_cell(idx + 2, df.columns.get_loc("Foto") + 1, novo_link)
            migrados += 1
        except Exception as e:
            st.error(f"Erro com '{nome}': {e}")
            erros += 1

        total += 1

    st.success(f"✅ Migração concluída: {migrados} de {total} clientes atualizados com sucesso.")
    if erros > 0:
        st.warning(f"{erros} imagens apresentaram erro. Veja os detalhes acima.")

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(page_title="Galeria de Clientes", layout="wide")
st.title("🖼️ Galeria de Clientes")

# Função para carregar os dados da planilha
def carregar_dados():
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"]["url"])
        aba = planilha.worksheet("clientes_status")
        dados = aba.get_all_records()
        return pd.DataFrame(dados), aba
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame(), None

# Carregar dados da planilha
df, aba_clientes = carregar_dados()

if df.empty or "Foto" not in df.columns:
    st.info("Nenhuma imagem encontrada.")
else:
    # Filtro por nome
    nomes = df["Cliente"].dropna().unique()
    nome_filtrado = st.selectbox("Filtrar por cliente:", ["Todos"] + sorted(nomes.tolist()))

    if nome_filtrado != "Todos":
        df = df[df["Cliente"] == nome_filtrado]

    fotos_validas = df.dropna(subset=["Foto"])

    if fotos_validas.empty:
        st.warning("Nenhuma imagem disponível para esse filtro.")
    else:
        cols = st.columns(3)
        for i, (idx, row) in enumerate(fotos_validas.iterrows()):
            with cols[i % 3]:
                try:
                    response = requests.get(row["Foto"])
                    img = Image.open(BytesIO(response.content))
                    st.image(img, caption=row["Cliente"], use_container_width=True)
                except:
                    st.error(f"Erro ao carregar imagem de {row['Cliente']}")
                    continue

                # Ações
                with st.expander(f"🛠 Ações para {row['Cliente']}"):
                    if st.button(f"❌ Excluir imagem - {idx}", key=f"excluir_{idx}"):
                        # Atualizar planilha e remover o link da imagem
                        cell = aba_clientes.find(str(row["Cliente"]))
                        if cell:
                            col_foto = df.columns.get_loc("Foto") + 1
                            aba_clientes.update_cell(cell.row, col_foto, "")
                            st.success("Imagem excluída. Recarregue a página para atualizar.")

                    nova_foto = st.text_input(f"🔁 Substituir link da imagem - {row['Cliente']}", key=f"edit_{idx}")
                    if nova_foto:
                        cell = aba_clientes.find(str(row["Cliente"]))
                        if cell:
                            col_foto = df.columns.get_loc("Foto") + 1
                            aba_clientes.update_cell(cell.row, col_foto, nova_foto)
                            st.success("Imagem substituída. Recarregue a página para atualizar.")

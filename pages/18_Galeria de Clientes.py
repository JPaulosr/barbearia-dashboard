import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
from PIL import Image
from io import BytesIO

st.set_page_config(page_title="Galeria de Clientes", layout="wide")

st.markdown("""
    <h2 style="color:#FFD700;">🖼️ Galeria de Clientes</h2>
    <hr style="border: 1px solid #444;">
""", unsafe_allow_html=True)

# === Função para carregar dados ===
def carregar_dados():
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"],
            scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"])
        aba = planilha.worksheet("clientes_status")
        dados = aba.get_all_records()
        return pd.DataFrame(dados), aba
    except Exception as e:
        st.error(f"❌ Erro ao carregar dados: {e}")
        return pd.DataFrame(), None

# Botão para atualizar galeria
if st.button("🔄 Recarregar Galeria"):
    st.experimental_rerun()

# Carregamento
df, aba_clientes = carregar_dados()

if df.empty or "Foto" not in df.columns:
    st.warning("⚠️ Nenhuma imagem encontrada.")
else:
    nomes = df["Cliente"].dropna().unique()
    nome_filtrado = st.selectbox("🔍 Buscar cliente:", ["Todos"] + sorted(nomes.tolist()))

    if nome_filtrado != "Todos":
        df = df[df["Cliente"] == nome_filtrado]

    fotos_validas = df.dropna(subset=["Foto"])

    if fotos_validas.empty:
        st.info("📭 Nenhuma imagem disponível para esse filtro.")
    else:
        cols = st.columns(3)
        for i, (idx, row) in enumerate(fotos_validas.iterrows()):
            with cols[i % 3]:
                try:
                    response = requests.get(row["Foto"])
                    img = Image.open(BytesIO(response.content))
                    st.image(img, caption=row["Cliente"], use_container_width=True)
                except:
                    st.error(f"❌ Erro ao carregar imagem de {row['Cliente']}")
                    continue

                with st.expander(f"⚙️ Gerenciar imagem"):
                    if st.button("🗑️ Excluir imagem", key=f"excluir_{idx}"):
                        try:
                            cell = aba_clientes.find(str(row["Cliente"]))
                            if cell:
                                col_foto = df.columns.get_loc("Foto") + 1
                                aba_clientes.update_cell(cell.row, col_foto, "")
                                st.success("✅ Imagem excluída. Clique em 🔄 para atualizar.")
                        except:
                            st.error("Erro ao excluir imagem.")

                    nova_foto = st.text_input("🔁 Substituir link da imagem", key=f"edit_{idx}")
                    if nova_foto:
                        try:
                            cell = aba_clientes.find(str(row["Cliente"]))
                            if cell:
                                col_foto = df.columns.get_loc("Foto") + 1
                                aba_clientes.update_cell(cell.row, col_foto, nova_foto)
                                st.success("✅ Link atualizado. Clique em 🔄 para ver a nova imagem.")
                        except:
                            st.error("Erro ao atualizar link da imagem.")

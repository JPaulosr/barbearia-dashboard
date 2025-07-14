import streamlit as st
import pandas as pd
import gspread
import requests
from PIL import Image
from io import BytesIO
from google.oauth2.service_account import Credentials
import cloudinary
import cloudinary.uploader
from streamlit_searchbox import st_searchbox

st.set_page_config(page_title="Galeria de Clientes", layout="wide")
st.title("🌞 Galeria de Clientes")

# ========== CONFIGURAR CLOUDINARY ==========
cloudinary.config(
    cloud_name=st.secrets["CLOUDINARY"]["cloud_name"],
    api_key=st.secrets["CLOUDINARY"]["api_key"],
    api_secret=st.secrets["CLOUDINARY"]["api_secret"]
)

# ========== CARREGAR DADOS ==========
def carregar_dados():
    try:
        escopos = ["https://www.googleapis.com/auth/spreadsheets"]
        credenciais = Credentials.from_service_account_info(
            st.secrets["GCP_SERVICE_ACCOUNT"], scopes=escopos
        )
        cliente = gspread.authorize(credenciais)
        planilha = cliente.open_by_url(st.secrets["PLANILHA_URL"])
        aba = planilha.worksheet("clientes_status")
        dados = aba.get_all_records()
        return pd.DataFrame(dados), aba
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame(), None

# ========== EXIBIR GALERIA ==========
df, aba_clientes = carregar_dados()

if df.empty or "Foto" not in df.columns:
    st.info("Nenhuma imagem encontrada.")
else:
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    nomes = sorted(df["Cliente"].dropna().unique())

    # Função de busca para autocomplete
    def search_clientes(termo):
        return [nome for nome in nomes if termo.lower() in nome.lower()]

    nome_filtrado = st_searchbox(
        search_function=search_clientes,
        placeholder="Digite o nome do cliente...",
        label="🔎 Buscar cliente",
        key="busca_cliente"
    )

    if nome_filtrado:
        df = df[df["Cliente"].str.strip().str.lower() == nome_filtrado.strip().lower()]

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

                with st.expander(f"🛠 Ações para {row['Cliente']}"):
                    if st.button(f"❌ Excluir imagem", key=f"excluir_{idx}"):
                        try:
                            cell = aba_clientes.find(str(row["Cliente"]).strip())
                            if cell:
                                col_foto = df.columns.get_loc("Foto") + 1
                                aba_clientes.update_cell(cell.row, col_foto, "")
                                st.success("✅ Imagem removida da planilha.")

                            if "res.cloudinary.com" in row["Foto"]:
                                nome_img = row["Foto"].split("/")[-1].split(".")[0]
                                public_id = f"Fotos clientes/{nome_img}"
                                cloudinary.uploader.destroy(public_id)
                                st.success("✅ Imagem deletada do Cloudinary com sucesso.")

                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao deletar imagem: {e}")

                    nova_foto = st.text_input("🔄 Substituir link da imagem", key=f"edit_{idx}")
                    if nova_foto:
                        try:
                            cell = aba_clientes.find(str(row["Cliente"]).strip())
                            if cell:
                                col_foto = df.columns.get_loc("Foto") + 1
                                aba_clientes.update_cell(cell.row, col_foto, nova_foto)
                                st.success("✅ Imagem substituída com sucesso.")
                                st.experimental_rerun()
                        except Exception as e:
                            st.error(f"❌ Erro ao substituir imagem: {e}")

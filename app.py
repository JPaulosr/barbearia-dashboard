import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(layout="wide")
st.title("📊 Dashboard da Barbearia")

@st.cache_data
def carregar_dados():
    caminho = "Modelo_Barbearia_Automatizado (10).xlsx"

    if not os.path.exists(caminho):
        st.error(f"❌ Arquivo '{caminho}' não encontrado. Suba ele para o repositório.")
        st.stop()

    try:
        # Lista as abas disponíveis no Excel
        abas = pd.ExcelFile(caminho).sheet_names
        st.write("📑 Abas encontradas na planilha:")
        st.write(abas)

        # Pausa aqui para você ver no app qual é o nome correto da aba
        return pd.DataFrame()

    except Exception as e:
        st.error(f"❌ Erro ao abrir o arquivo Excel: {e}")
        st.stop()

# Carrega os dados (ainda vazio, só debug por enquanto)
df = carregar_dados()

# Espera o nome correto da aba para continuar
if df.empty:
    st.warning("⏳ Aguardando definição do nome correto da aba para carregar os dados.")
else:
    # Aqui virá o restante da lógica após descobrir a aba correta
    pass

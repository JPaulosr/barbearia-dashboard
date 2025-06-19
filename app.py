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
        st.error(f"❌ Arquivo '{caminho}' não encontrado.")
        st.stop()

    try:
        df = pd.read_excel(caminho, sheet_name="Base de Dados")
        df.columns = [str(col).strip() for col in df.columns]

        st.write("🧾 Colunas encontradas na aba 'Base de Dados':")
        st.write(df.columns.tolist())  # Mostra os nomes reais

        return df

    except Exception as e:
        st.error(f"❌ Erro inesperado ao carregar os dados: {e}")
        st.stop()

# Carregar dados
df = carregar_dados()

if df.empty:
    st.warning("⏳ Nenhum dado carregado.")
else:
    st.warning("👆 Copie o nome exato da coluna de data que aparecer acima e me mande aqui.")

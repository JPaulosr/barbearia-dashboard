import streamlit as st
import pandas as pd
from streamlit_extras.switch_page_button import switch_page

st.set_page_config(layout="wide")
st.title("🧑‍💼 Funcionários")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    return df

df = carregar_dados()

# Lista de funcionários únicos
funcionarios_disponiveis = sorted(df["Funcionário"].dropna().unique())
funcionario_escolhido = st.selectbox("👥 Escolha um funcionário", funcionarios_disponiveis)

if st.button("➡ Ver detalhes"):
    st.session_state["funcionario"] = funcionario_escolhido
    switch_page("DetalhesFuncionario")

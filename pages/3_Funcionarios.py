import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("🧑‍💼 Funcionários")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    return df

df = carregar_dados()

# Lista de funcionários
funcionarios = sorted(df["Funcionário"].dropna().unique())
funcionario_escolhido = st.selectbox("👥 Escolha um funcionário", funcionarios)

if st.button("➡ Ver detalhes"):
    # Salva o nome do funcionário na sessão
    st.session_state["funcionario"] = funcionario_escolhido
    st.success("Funcionário selecionado com sucesso!")
    st.info("👉 Agora clique na aba **DetalhesFuncionario** no menu lateral para ver os dados completos.")

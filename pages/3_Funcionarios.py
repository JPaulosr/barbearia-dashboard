import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("🧑‍💼 Funcionários")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    return df

df = carregar_dados()

# Lista de funcionários
funcionarios = sorted(df["Funcionário"].dropna().unique())
funcionario_escolhido = st.selectbox("👥 Escolha um funcionário", funcionarios)

if st.button("➡ Ver detalhes"):
    st.session_state["funcionario"] = funcionario_escolhido
    st.success("Funcionário selecionado com sucesso!")
    st.info("👉 Agora clique na aba **DetalhesFuncionario** no menu lateral para ver os dados completos.")

    # Mostra um resumo rápido abaixo
    st.subheader("📋 Resumo do Funcionário Selecionado")

    df_func = df[df["Funcionário"] == funcionario_escolhido]

    # Ajuste de atendimentos
    limite = pd.to_datetime("2025-05-10")
    antes = df_func[df_func["Data"] <= limite]
    depois = df_func[df_func["Data"] > limite]
    depois_unicos = depois.drop_duplicates(subset=["Cliente", "Data"])
    total_atendimentos = len(antes) + len(depois_unicos)
    receita_total = df_func["Valor"].sum()

    col1, col2 = st.columns(2)
    col1.metric("🧾 Receita total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    col2.metric("👥 Atendimentos únicos", f"{total_atendimentos}")

import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("🧑‍🔧 Funcionários - Receita Total")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    return df

df = carregar_dados()

# Agrupamento por funcionário
ranking = df.groupby("Funcionário")["Valor"].sum().reset_index()
ranking = ranking.sort_values(by="Valor", ascending=False)
ranking["Valor Formatado"] = ranking["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.subheader("📋 Receita total por funcionário")
st.dataframe(ranking[["Funcionário", "Valor Formatado"]], use_container_width=True)

# Navegar para detalhes
funcionarios = ranking["Funcionário"].tolist()

if "funcionario" in st.session_state:
    valor_padrao = st.session_state["funcionario"]
else:
    valor_padrao = "Selecione..."

filtro = st.selectbox("🔎 Ver detalhamento de um funcionário", ["Selecione..."] + funcionarios, index=["Selecione..."] + funcionarios.index(valor_padrao) if valor_padrao in funcionarios else 0)

if filtro != "Selecione...":
    if st.button("➡ Ver detalhes"):
        st.session_state["funcionario"] = filtro
        st.switch_page("pages/4_DetalhesFuncionario.py")
else:
    st.warning("⚠️ Nenhum funcionário selecionado.")

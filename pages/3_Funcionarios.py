import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("👨‍🔧 Funcionários - Receita Total")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano-Mês"] = df["Data"].dt.to_period("M")
    return df

df = carregar_dados()

# Filtro por mês
meses_disponiveis = df["Ano-Mês"].dropna().sort_values().astype(str).unique().tolist()
mes_selecionado = st.multiselect("📅 Filtrar por mês (opcional)", meses_disponiveis)

if mes_selecionado:
    df = df[df["Ano-Mês"].astype(str).isin(mes_selecionado)]

# Agrupamento por funcionário
ranking = df.groupby("Funcionário")["Valor"].sum().reset_index()
ranking = ranking.sort_values(by="Valor", ascending=False)
ranking["Valor Formatado"] = ranking["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.subheader("📋 Receita total por funcionário")
st.dataframe(ranking[["Funcionário", "Valor Formatado"]], use_container_width=True)

valor_total = ranking["Valor"].sum()
valor_total_formatado = f"R$ {valor_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
st.markdown(f"### 💰 Valor total no período selecionado: {valor_total_formatado}")

# Navegar para detalhes
funcionarios = ranking["Funcionário"].tolist()
valor_padrao = st.session_state.get("funcionario", "Selecione...")
opcoes = ["Selecione..."] + funcionarios

try:
    index_padrao = opcoes.index(valor_padrao)
except ValueError:
    index_padrao = 0

filtro = st.selectbox("🔍 Ver detalhamento de um funcionário", opcoes, index=index_padrao)

if st.button("➥ Ver detalhes"):
    st.session_state["funcionario"] = filtro
    st.switch_page("pages/4_DetalhesFuncionario.py")

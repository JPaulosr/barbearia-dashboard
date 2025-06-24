import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("👥 Clientes - Receita Total")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.strftime('%b')
    return df

df = carregar_dados()

# Limpa nomes genéricos
nomes_excluir = ["boliviano", "brasileiro", "menino"]
def limpar_nome(nome):
    nome_limpo = unidecode(str(nome).lower())
    return not any(generico in nome_limpo for generico in nomes_excluir)

df = df[df["Cliente"].apply(limpar_nome)]

clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
st.subheader("🔍 Ver detalhamento de um cliente")
cliente_escolhido = st.selectbox("📌 Escolha um cliente", clientes_disponiveis)

if st.button("➡️ Ver detalhes"):
    st.session_state["cliente"] = cliente_escolhido
    st.switch_page("2_DetalhesCliente")

# Resumo das informações
st.markdown("""
### 📅 Histórico de atendimentos;
### 📊 Receita mensal por mês e ano;
### 🥧 Receita por tipo (Produto ou Serviço);
### 🧑‍🔧 Distribuição de atendimentos por funcionário (gráfico de pizza);
### 📋 Uma tabela com total de atendimentos, quantidade de combos e atendimentos simples.
""")

import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("👥 Clientes - Receita Total")

# Filtros
ano = st.selectbox("📅 Filtrar por ano", options=[2023, 2024, 2025], index=2)
funcionarios = st.multiselect("👥 Filtrar por funcionário", ["JPaulo", "Vinicius"], default=["JPaulo", "Vinicius"])

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
df = df[df["Ano"] == ano]

# Filtra funcionários
df = df[df["Funcionário"].isin(funcionarios)]

# Remove nomes genéricos
nomes_excluir = ["boliviano", "brasileiro", "menino"]
def limpar_nome(nome):
    nome_limpo = unidecode(str(nome).lower())
    return not any(generico in nome_limpo for generico in nomes_excluir)

df = df[df["Cliente"].apply(limpar_nome)]

# Agrupa por Cliente + Data para contagem correta de atendimentos e tipo (combo/simples)
agrupado = df.groupby(["Cliente", "Data"]).agg(
    Qtd_Serviços=('Serviço', 'count'),
    Qtd_Produtos=('Tipo', lambda x: (x == "Produto").sum()),
    Valor_Total=('Valor', 'sum')
).reset_index()

# Identifica combos e simples por cliente e data
agrupado["Qtd_Combo"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
agrupado["Qtd_Simples"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

@st.cache_data
def consolidar_clientes(df):
    resumo = df.groupby("Cliente").agg(
        Qtd_Serviços=("Qtd_Serviços", "sum"),
        Qtd_Produtos=("Qtd_Produtos", "sum"),
        Qtd_Atendimento=("Data", "count"),
        Qtd_Combo=("Qtd_Combo", "sum"),
        Qtd_Simples=("Qtd_Simples", "sum"),
        Valor_Total=("Valor_Total", "sum")
    ).reset_index()
    resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(".", "x").replace(",", ".").replace("x", ","))
    resumo = resumo.sort_values(by="Valor_Total", ascending=False).reset_index(drop=True)
    return resumo

resumo_geral = consolidar_clientes(agrupado)

# Pesquisa por nome
st.subheader("🔍 Ver detalhamento de um cliente")
cliente_escolhido = st.selectbox("📌 Escolha um cliente", resumo_geral["Cliente"].tolist())

if st.button("➡ Ver detalhes"):
    st.session_state["cliente"] = cliente_escolhido
    st.switch_page("pages/2_DetalhesCliente.py")

# Descrição informativa do que será exibido
st.markdown("""
### 📅 Histórico de atendimentos;
### 📊 Receita mensal por mês e ano;
### 🥧 Receita por tipo (Produto ou Serviço);
### 🧑‍🔧 Distribuição de atendimentos por funcionário (gráfico de pizza);
### 📋 Uma tabela com total de atendimentos, quantidade de combos e atendimentos simples.
""")

import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("\U0001F3C6 Top 20 Clientes")

# Filtros
ano = st.selectbox("\U0001F4C5 Filtrar por ano", options=[2023, 2024, 2025], index=2)
funcionarios = st.multiselect("\U0001F465 Filtrar por funcionário", ["JPaulo", "Vinicius"], default=["JPaulo", "Vinicius"])

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
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
def top_20_por(df):
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
    resumo["Posição"] = resumo.index + 1
    return resumo

resumo_geral = top_20_por(agrupado)

# Pesquisa por nome
st.subheader("\U0001F3AF Top 20 Clientes - Geral")
filtro = st.text_input("\U0001F50D Pesquisar cliente", "")
resumo_filtrado = resumo_geral[resumo_geral["Cliente"].str.contains(filtro, case=False)]

st.dataframe(resumo_filtrado[["Posição", "Cliente", "Qtd_Serviços", "Qtd_Produtos", "Qtd_Atendimento", "Qtd_Combo", "Qtd_Simples", "Valor_Formatado"]], use_container_width=True)

# Gráfico dos Top 5 - Barras
st.subheader("\U0001F4CA Top 5 por Receita")
top5 = resumo_geral.head(5)
fig = px.bar(top5, x="Cliente", y="Valor_Total", title="Top 5 Clientes por Receita", text_auto='.2s')
st.plotly_chart(fig, use_container_width=True)

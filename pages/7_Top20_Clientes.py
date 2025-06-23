import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(page_title="Top 20 Clientes", layout="wide")
st.title("🏆 Top 20 Clientes")

@st.cache_data

def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

df = df[df["Cliente"].notna()]

# Corrige nomes de funcionários para evitar erros de acentuação
df["Funcionario_Normalizado"] = df["Funcionário"].apply(lambda x: unidecode(str(x)).strip())

# Filtros
anos = sorted(df["Ano"].dropna().unique(), reverse=True)
anos = [int(a) for a in anos if not pd.isna(a)]
ano = st.selectbox("📅 Filtrar por ano", anos)

lista_funcionarios = sorted(df["Funcionario_Normalizado"].unique())
funcionarios_selecionados = st.multiselect("🧑‍🔧 Filtrar por funcionário", lista_funcionarios, default=lista_funcionarios)

# Aplica filtros
df_filtrado = df[(df["Ano"] == ano) & (df["Funcionario_Normalizado"].isin(funcionarios_selecionados))]

# Remove nomes genéricos
def nome_valido(nome):
    nome = str(nome).lower().strip()
    return nome not in ["boliviano", "brasileiro", "menino"]

df_filtrado = df_filtrado[df_filtrado["Cliente"].apply(nome_valido)]

# Remove duplicidades por Cliente + Data para contagem única de atendimento
df_visitas = df_filtrado.drop_duplicates(subset=["Cliente", "Data"])

# Se não houver colunas necessárias, para tudo
if df_visitas.empty or not all(col in df_visitas.columns for col in ["Cliente", "Serviço", "Valor"]):
    st.warning("⚠ Dados insuficientes para gerar a análise.")
    st.stop()

# Função principal de cálculo
def top_20_por(df):
    atendimentos = df.drop_duplicates(subset=["Cliente", "Data"])

    resumo = atendimentos.groupby("Cliente").agg(
        Qtd_Serviços=("Serviço", "count"),
        Qtd_Produtos=("Produto", "sum"),
        Qtd_Atendimento=("Cliente", "count"),
        Qtd_Combo=("Combo", "sum"),
        Qtd_Simples=("Simples", "sum"),
        Valor_Total=("Valor", "sum")
    ).reset_index()

    resumo = resumo.sort_values(by="Valor_Total", ascending=False).head(20)
    resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(".", "X").replace(",", ".").replace("X", ","))
    return resumo

resumo_geral = top_20_por(df_visitas)

# Interface
st.subheader("🏅 Top 20 Clientes - Geral")
cliente_default = resumo_geral["Cliente"].iloc[0] if not resumo_geral.empty else ""
st.selectbox("", resumo_geral["Cliente"], index=0 if not resumo_geral.empty else None)
st.dataframe(resumo_geral, use_container_width=True)

# Campo de pesquisa
st.subheader("🔍 Pesquisar cliente")
consulta = st.text_input("Digite um nome (ou parte dele)")

if consulta:
    filtro = resumo_geral["Cliente"].str.lower().str.contains(consulta.lower())
    st.dataframe(resumo_geral[filtro], use_container_width=True)

# Gráfico Top 5
st.subheader("📊 Top 5 por Receita")
top5 = resumo_geral.head(5)
if not top5.empty:
    fig = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado", title="Top 5 Clientes por Receita")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Sem dados para exibir o gráfico.")

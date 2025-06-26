import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🏆 Top 20 Clientes")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.strftime('%b')
    return df

# === Filtros iniciais
ano = st.selectbox("📅 Filtrar por ano", options=[2023, 2024, 2025], index=2)
funcionarios = st.multiselect("👥 Filtrar por funcionário", ["JPaulo", "Vinicius"], default=["JPaulo", "Vinicius"])

df = carregar_dados()
df = df[df["Ano"] == ano]
df = df[df["Funcionário"].isin(funcionarios)]

# === Remove nomes genéricos para ranking
nomes_excluir = ["boliviano", "brasileiro", "menino"]
def limpar_nome(nome):
    nome_limpo = unidecode(str(nome).lower())
    return not any(generico in nome_limpo for generico in nomes_excluir)

df_ranking = df[df["Cliente"].apply(limpar_nome)]

# === Agrupamento Cliente + Data
agrupado = df_ranking.groupby(["Cliente", "Data"]).agg(
    Qtd_Serviços=('Serviço', 'count'),
    Qtd_Produtos=('Tipo', lambda x: (x == "Produto").sum()),
    Valor_Total=('Valor', 'sum')
).reset_index()

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

    def categoria_cliente(valor):
        if valor > 200:
            return "🥇 VIP"
        elif valor >= 50:
            return "🥈 Frequente"
        else:
            return "🥉 Novato"
    
    resumo["Categoria"] = resumo["Valor_Total"].apply(categoria_cliente)
    resumo = resumo.sort_values(by="Valor_Total", ascending=False).reset_index(drop=True)
    resumo["Posição"] = resumo.index + 1
    return resumo

resumo_geral = top_20_por(agrupado)

# === Filtros dinâmicos
st.subheader("🎯 Top 20 Clientes - Geral")
filtro_nome = st.text_input("🔍 Pesquisar cliente", "")
resumo_filtrado = resumo_geral[resumo_geral["Cliente"].str.contains(filtro_nome, case=False)]

categorias_disponiveis = resumo_geral["Categoria"].unique().tolist()
filtro_categoria = st.multiselect("🏅 Filtrar por categoria", categorias_disponiveis, default=categorias_disponiveis)
resumo_filtrado = resumo_filtrado[resumo_filtrado["Categoria"].isin(filtro_categoria)]

# === Exibição da tabela
st.dataframe(resumo_filtrado[[ "Posição", "Cliente", "Qtd_Serviços", "Qtd_Produtos", "Qtd_Atendimento", "Qtd_Combo", "Qtd_Simples", "Valor_Formatado", "Categoria" ]], use_container_width=True)

# === Gráfico Top 5
st.subheader("📊 Top 5 Clientes por Receita")
if filtro_nome and len(resumo_filtrado) == 1:
    cliente = resumo_filtrado.iloc[0]["Cliente"]
    df_cliente = df[df["Cliente"].str.lower() == cliente.lower()]
    grafico_detalhado = df_cliente.groupby(["Serviço", "Mês_Nome"])["Valor"].sum().reset_index()
    fig = px.bar(
        grafico_detalhado,
        x="Serviço",
        y="Valor",
        color="Mês_Nome",
        barmode="group",
        text_auto=True,
        title=f"Receita por Serviço e Mês - {cliente}",
        labels={"Valor": "Receita (R$)"}
    )
else:
    top5 = resumo_filtrado.head(5)
    fig = px.bar(
        top5,
        y="Cliente",
        x="Valor_Total",
        orientation="h",
        title="Top 5 Clientes por Receita",
        text=top5["Valor_Total"].apply(lambda x: f"R$ {x:,.0f}".replace(",", "v").replace(".", ",").replace("v", ".")),
        color="Cliente"
    )

st.plotly_chart(fig, use_container_width=True)

# === Comparativo entre dois clientes
st.subheader("⚖️ Comparar dois clientes")
clientes_disponiveis = resumo_filtrado["Cliente"].tolist()
col1, col2 = st.columns(2)
c1 = col1.selectbox("👤 Cliente 1", clientes_disponiveis)
c2 = col2.selectbox("👤 Cliente 2", clientes_disponiveis, index=1 if len(clientes_disponiveis) > 1 else 0)

df_c1 = df[df["Cliente"] == c1]
df_c2 = df[df["Cliente"] == c2]

def resumo_cliente(df_cliente):
    total = df_cliente["Valor"].sum()
    servicos = df_cliente["Serviço"].nunique()
    media = df_cliente.groupby("Data")["Valor"].sum().mean()
    servicos_detalhados = df_cliente["Serviço"].value_counts().rename("Quantidade")
    return pd.Series({
        "Total Receita": f"R$ {total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."),
        "Serviços Distintos": servicos,
        "Tique Médio": f"R$ {media:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    }), servicos_detalhados

if c1 == c2:
    st.warning("Selecione dois clientes diferentes para comparar.")
else:
    resumo1, servicos1 = resumo_cliente(df_c1)
    resumo2, servicos2 = resumo_cliente(df_c2)

    resumo_geral_comp = pd.concat([resumo1.rename(c1), resumo2.rename(c2)], axis=1)
    servicos_comparativo = pd.concat([servicos1.rename(c1), servicos2.rename(c2)], axis=1).fillna(0).astype(int)

    st.dataframe(resumo_geral_comp, use_container_width=True)
    st.markdown("**Serviços Realizados por Tipo**")
    st.dataframe(servicos_comparativo, use_container_width=True)

# === Detalhamento individual
st.subheader("🔍 Ver detalhamento de um cliente")
cliente_escolhido = st.selectbox("📌 Escolha um cliente", clientes_disponiveis)

if st.button("➡ Ver detalhes"):
    st.session_state["cliente"] = cliente_escolhido
    st.switch_page("pages/2_DetalhesCliente.py")

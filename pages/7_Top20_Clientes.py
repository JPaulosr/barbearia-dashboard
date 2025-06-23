import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🏆 Top 20 Clientes")

@st.cache_data

def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# Filtros
anos = sorted(df["Ano"].dropna().unique())
funcionarios = sorted(df["Funcionário"].dropna().unique())

col1, col2 = st.columns(2)
with col1:
    ano_filtro = st.selectbox("📅 Filtrar por ano", anos, index=len(anos)-1)
with col2:
    funcionario_filtro = st.multiselect("🧑‍🔧 Filtrar por funcionário", funcionarios, default=funcionarios)

# Filtro
df_filtrado = df[(df["Ano"] == ano_filtro) & (df["Funcionário"].isin(funcionario_filtro))]

# Função para gerar o top 20

def top_20_por(atendimentos):
    # Ajuste das visitas únicas
    df_antigo = atendimentos[atendimentos["Data"] < pd.to_datetime("2025-05-11")].copy()
    df_antigo["Visita"] = 1

    df_novo = atendimentos[atendimentos["Data"] >= pd.to_datetime("2025-05-11")].drop_duplicates(subset=["Cliente", "Data"]).copy()
    df_novo["Visita"] = 1

    df_visitas = pd.concat([df_antigo, df_novo])

    # Agrupamento
    resumo = df_visitas.groupby("Cliente").agg({
        "Serviço": "count",
        "Produto": lambda x: x.notna().sum(),
        "Visita": "sum",
        "Combo": lambda x: x.notna().sum(),
        "Simples": lambda x: x.notna().sum(),
        "Valor": "sum"
    }).rename(columns={
        "Serviço": "Qtd Serviços",
        "Produto": "Qtd Produtos",
        "Visita": "Qtd Atendimento",
        "Combo": "Qtd Combo",
        "Simples": "Qtd Simples",
        "Valor": "Valor Total"
    }).reset_index()

    # Remove nomes genéricos
    nomes_invalidos = ["boliviano", "brasileiro", "menino", "menino boliviano"]
    normalizar = lambda s: str(s).lower().strip()
    resumo = resumo[~resumo["Cliente"].apply(normalizar).isin(nomes_invalidos)]

    resumo = resumo.sort_values(by="Valor Total", ascending=False).head(20)
    resumo.insert(0, "Posição", range(1, len(resumo) + 1))
    resumo["Valor Total"] = resumo["Valor Total"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    return resumo

# Exibe os top 20
st.subheader("🥇 Top 20 Clientes - Geral")
resumo_geral = top_20_por(df_filtrado)
st.dataframe(resumo_geral, use_container_width=True)

# Pesquisa dinâmica por nome
st.subheader("🔎 Pesquisar cliente")
consulta = st.text_input("Digite parte do nome:").lower()
if consulta:
    encontrados = resumo_geral[resumo_geral["Cliente"].str.lower().str.contains(consulta)]
    st.dataframe(encontrados, use_container_width=True)

# Gráfico dos top 5
st.subheader("📊 Top 5 Clientes - Receita")
top5 = resumo_geral.head(5)
fig = px.bar(top5, x="Cliente", y="Valor Total", text="Valor Total", labels={"Valor Total": "Receita (R$)"})
st.plotly_chart(fig, use_container_width=True)

# Comparativo entre dois clientes
st.subheader("⚖ Comparativo entre dois clientes")
opcoes = resumo_geral["Cliente"].tolist()
col1, col2 = st.columns(2)

with col1:
    cliente1 = st.selectbox("Cliente 1", opcoes)
with col2:
    cliente2 = st.selectbox("Cliente 2", opcoes, index=1 if len(opcoes) > 1 else 0)

comparativo = resumo_geral[resumo_geral["Cliente"].isin([cliente1, cliente2])].set_index("Cliente")
st.dataframe(comparativo, use_container_width=True)

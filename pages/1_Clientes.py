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

# Gráfico dinâmico
st.subheader("\U0001F4CA Top 5 por Receita")
if filtro and len(resumo_filtrado) == 1:
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
    top5 = resumo_geral.head(5)
    fig = px.bar(top5, x="Cliente", y="Valor_Total", title="Top 5 Clientes por Receita", text_auto='.2s')

st.plotly_chart(fig, use_container_width=True)

# === Comparativo entre dois clientes ===
st.subheader("⚖️ Comparar dois clientes")

clientes_disponiveis = resumo_geral["Cliente"].tolist()
col1, col2 = st.columns(2)
c1 = col1.selectbox("\U0001F464 Cliente 1", clientes_disponiveis)
c2 = col2.selectbox("\U0001F464 Cliente 2", clientes_disponiveis, index=1 if len(clientes_disponiveis) > 1 else 0)

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

resumo1, servicos1 = resumo_cliente(df_c1)
resumo2, servicos2 = resumo_cliente(df_c2)

resumo_geral_comp = pd.concat([resumo1.rename(c1), resumo2.rename(c2)], axis=1)
servicos_comparativo = pd.concat([servicos1.rename(c1), servicos2.rename(c2)], axis=1).fillna(0).astype(int)

st.dataframe(resumo_geral_comp, use_container_width=True)
st.markdown("**Serviços Realizados por Tipo**")
st.dataframe(servicos_comparativo, use_container_width=True)

# === Navegar para detalhamento ===
st.subheader("\U0001F50D Ver detalhamento de um cliente")
cliente_escolhido = st.selectbox("\U0001F4CC Escolha um cliente", clientes_disponiveis)

if st.button("➡ Ver detalhes"):
    st.session_state["cliente"] = cliente_escolhido
    st.switch_page("/2_DetalhesCliente")

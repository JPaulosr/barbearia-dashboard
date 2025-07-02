import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧴 Produtos - Análise Financeira")

@st.cache_data

def carregar_dados():
    url_base = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv"
    df_base = pd.read_csv(url_base + "&sheet=Base%20de%20Dados")
    df_despesas = pd.read_csv(url_base + "&sheet=Despesas")

    df_base["Data"] = pd.to_datetime(df_base["Data"], errors='coerce')
    df_despesas["Data"] = pd.to_datetime(df_despesas["Data"], errors='coerce')
    return df_base, df_despesas

df_base, df_despesas = carregar_dados()

# === FILTROS ===
df_base["Ano"] = df_base["Data"].dt.year
df_despesas["Ano"] = df_despesas["Data"].dt.year
anos_disponiveis = sorted(df_base["Ano"].dropna().unique())
ano_selecionado = st.selectbox("🗕️ Escolha o Ano", anos_disponiveis, index=len(anos_disponiveis)-1)

# === FILTRO MENSAL OPCIONAL ===
meses_dict = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
meses_disponiveis = sorted(df_base[df_base["Ano"] == ano_selecionado]["Data"].dt.month.unique())
mes_selecionado = st.selectbox("🗖️ Filtrar por Mês (opcional)", options=["Todos"] + [meses_dict[m] for m in meses_disponiveis])

# === FILTRAGEM DE DADOS ===
df_produtos = df_base[(df_base["Tipo"] == "Produto") & (df_base["Ano"] == ano_selecionado)].copy()
df_produtos["Mês"] = df_produtos["Data"].dt.month

if mes_selecionado != "Todos":
    mes_num = [k for k, v in meses_dict.items() if v == mes_selecionado][0]
    df_produtos = df_produtos[df_produtos["Mês"] == mes_num]

df_despesas_prod = df_despesas[(df_despesas["Ano"] == ano_selecionado)].copy()
if mes_selecionado != "Todos":
    df_despesas_prod = df_despesas_prod[df_despesas_prod["Data"].dt.month == mes_num]

# Receita bruta total com produtos
receita_total = df_produtos["Valor (R$)"].sum()

# Filtrar despesas relacionadas a produtos
palavras_chave = ["produto", "barbeador", "pomada", "gel", "cera", "pó"]
df_despesas_prod = df_despesas_prod[df_despesas_prod["Descrição"].str.lower().str.contains('|'.join(palavras_chave))].copy()
custo_total = df_despesas_prod["Valor (R$)"].sum()

lucro_bruto = receita_total - custo_total
margem = lucro_bruto / receita_total * 100 if receita_total > 0 else 0

# === RESUMO ===
st.subheader("📊 Resumo Financeiro de Produtos")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Receita Bruta", f"R$ {receita_total:,.2f}")
col2.metric("Custo dos Produtos", f"R$ {custo_total:,.2f}")
col3.metric("Lucro Bruto", f"R$ {lucro_bruto:,.2f}")
col4.metric("Margem Bruta", f"{margem:.1f}%")

# === EVOLUÇÃO MENSAL ===
st.subheader("📈 Evolução Mensal")
df_mensal = df_produtos.groupby(df_produtos["Data"].dt.to_period("M")).agg({"Valor (R$)": "sum"}).reset_index()
df_mensal["Data"] = df_mensal["Data"].dt.to_timestamp()
df_mensal = df_mensal.rename(columns={"Valor (R$)": "Receita"})
df_mensal["Custo"] = df_despesas_prod.groupby(df_despesas_prod["Data"].dt.to_period("M"))["Valor (R$)"].sum().reset_index(drop=True)
df_mensal["Lucro"] = df_mensal["Receita"] - df_mensal["Custo"]

fig = px.bar(df_mensal, x="Data", y=["Receita", "Custo", "Lucro"], barmode="group",
             title="Evolução Mensal: Receita x Custo x Lucro com Produtos")
fig.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig, use_container_width=True)

# === PRODUTOS MAIS VENDIDOS ===
st.subheader("🏆 Produtos Mais Vendidos")
top_produtos = df_produtos["Serviço"].value_counts().reset_index()
top_produtos.columns = ["Produto", "Quantidade"]
top_produtos["Receita"] = top_produtos["Produto"].map(df_produtos.groupby("Serviço")["Valor (R$)"].sum())
top_produtos = top_produtos.sort_values("Receita", ascending=False)

top_produtos["% Receita"] = (top_produtos["Receita"] / receita_total * 100).round(1)
top_produtos["Classificação"] = pd.qcut(top_produtos["% Receita"], q=[0, .8, .95, 1], labels=["C", "B", "A"])

st.dataframe(top_produtos, use_container_width=True)

# === PIZZA DE RECEITA POR PRODUTO ===
st.subheader("🥧 Receita por Produto (Top 10)")
fig_pizza = px.pie(top_produtos.head(10), names="Produto", values="Receita", title="Distribuição da Receita por Produto")
fig_pizza.update_traces(textposition='inside', textinfo='percent+label')
st.plotly_chart(fig_pizza, use_container_width=True)

# === CLIENTES QUE COMPRARAM MAIS PRODUTOS ===
st.subheader("👤 Clientes que Mais Compram Produtos")
clientes = df_produtos.groupby("Cliente").agg({"Valor (R$)": "sum", "Serviço": "count"}).reset_index()
clientes.columns = ["Cliente", "Total gasto", "Qtd produtos"]
clientes = clientes.sort_values("Total gasto", ascending=False).head(15)
st.dataframe(clientes, use_container_width=True)

# === VISUALIZAÇÃO DE MARGEM ===
st.subheader("📈 Margem Bruta Mensal com Produtos")
df_mensal["Margem"] = (df_mensal["Lucro"] / df_mensal["Receita"] * 100).round(1)
fig2 = px.line(df_mensal, x="Data", y="Margem", markers=True, title="Margem Bruta Mensal (%)")
fig2.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig2, use_container_width=True)

with st.expander("🔍 Ver dados brutos"):
    st.dataframe(df_produtos, use_container_width=True)
    st.dataframe(df_despesas_prod, use_container_width=True)

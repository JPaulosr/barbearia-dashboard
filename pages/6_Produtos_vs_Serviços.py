import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("✂️ Serviços - Análise Financeira")

@st.cache_data
def carregar_dados():
    url_base = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv"
    df_base = pd.read_csv(url_base + "&sheet=Base%20de%20Dados")
    df_despesas = pd.read_csv(url_base + "&sheet=Despesas")

    df_base.columns = df_base.columns.str.strip()
    df_despesas.columns = df_despesas.columns.str.strip()

    df_base["Data"] = pd.to_datetime(df_base["Data"], errors='coerce')
    df_despesas["Data"] = pd.to_datetime(df_despesas["Data"], errors='coerce')
    return df_base, df_despesas

df_base, df_despesas = carregar_dados()

# === FILTROS ===
df_base["Ano"] = df_base["Data"].dt.year
anos_disponiveis = sorted(df_base["Ano"].dropna().unique())
ano_selecionado = st.selectbox("🗕️ Escolha o Ano", anos_disponiveis, index=len(anos_disponiveis)-1)

meses_dict = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
meses_disponiveis = sorted(df_base[df_base["Ano"] == ano_selecionado]["Data"].dt.month.unique())
mes_selecionado = st.selectbox("🗖️ Filtrar por Mês (opcional)", options=["Todos"] + [meses_dict[m] for m in meses_disponiveis])

# === FILTRAGEM DE SERVIÇOS ===
df_servicos = df_base[
    (df_base["Ano"] == ano_selecionado) &
    (df_base["Tipo"] == "Serviço")
].copy()

df_servicos["Mês"] = df_servicos["Data"].dt.month

if mes_selecionado != "Todos":
    mes_num = [k for k, v in meses_dict.items() if v == mes_selecionado][0]
    df_servicos = df_servicos[df_servicos["Mês"] == mes_num]

# Conversão de valores
def converter_para_float(valor):
    if isinstance(valor, str):
        valor = valor.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(valor)
    except:
        return 0.0

df_servicos["Valor"] = df_servicos["Valor"].apply(converter_para_float)

# RESUMO FINANCEIRO
receita_total = df_servicos["Valor"].sum()
custo_total = 0  # normalmente serviços não têm custo direto registrado
lucro_bruto = receita_total - custo_total
margem = lucro_bruto / receita_total * 100 if receita_total > 0 else 0

# === RESUMO ===
st.subheader("📊 Resumo Financeiro de Serviços")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Receita Bruta", f"R$ {receita_total:,.2f}")
col2.metric("Custo", f"R$ {custo_total:,.2f}")
col3.metric("Lucro Bruto", f"R$ {lucro_bruto:,.2f}")
col4.metric("Margem Bruta", f"{margem:.1f}%")

# === EVOLUÇÃO MENSAL ===
st.subheader("📈 Evolução Mensal")
df_mensal = df_servicos.groupby(df_servicos["Data"].dt.to_period("M")).agg({"Valor": "sum"}).reset_index()
df_mensal["Data"] = df_mensal["Data"].dt.to_timestamp()
df_mensal = df_mensal.rename(columns={"Valor": "Receita"})

df_mensal["Custo"] = 0
df_mensal["Lucro"] = df_mensal["Receita"]

# Garantir tipos numéricos
df_mensal["Receita"] = pd.to_numeric(df_mensal["Receita"], errors="coerce").fillna(0)
df_mensal["Lucro"] = pd.to_numeric(df_mensal["Lucro"], errors="coerce").fillna(0)

fig = px.bar(df_mensal, x="Data", y=["Receita", "Lucro"], barmode="group",
             title="Evolução Mensal: Receita x Lucro com Serviços")
fig.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig, use_container_width=True)

# === MARGEM MENSAL ===
st.subheader("📈 Margem Bruta Mensal com Serviços")
df_mensal["Margem"] = (df_mensal["Lucro"] / df_mensal["Receita"] * 100).replace([float("inf"), -float("inf")], 0).fillna(0).round(1)
fig2 = px.line(df_mensal, x="Data", y="Margem", markers=True, title="Margem Bruta Mensal (%)")
fig2.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig2, use_container_width=True)

# === SERVIÇOS MAIS VENDIDOS ===
st.subheader("🏆 Serviços Mais Vendidos")
top_servicos = df_servicos["Serviço"].value_counts().reset_index()
top_servicos.columns = ["Serviço", "Quantidade"]
top_servicos["Receita"] = top_servicos["Serviço"].map(df_servicos.groupby("Serviço")["Valor"].sum())
top_servicos["% Receita"] = (top_servicos["Receita"] / receita_total * 100).round(1)
top_servicos["Classificação"] = pd.qcut(top_servicos["% Receita"], q=[0, .8, .95, 1], labels=["C", "B", "A"])

st.dataframe(top_servicos, use_container_width=True)

# === PIZZA DE RECEITA POR SERVIÇO ===
st.subheader("🥧 Receita por Serviço (Top 10)")
fig_pizza = px.pie(top_servicos.head(10), names="Serviço", values="Receita", title="Distribuição da Receita por Serviço")
fig_pizza.update_traces(textposition='inside', textinfo='percent+label')
st.plotly_chart(fig_pizza, use_container_width=True)

# === CLIENTES QUE MAIS CONSOMEM SERVIÇOS ===
st.subheader("👤 Clientes que Mais Consomem Serviços")
clientes = df_servicos.groupby("Cliente").agg({"Valor": "sum", "Serviço": "count"}).reset_index()
clientes.columns = ["Cliente", "Total gasto", "Qtd serviços"]
clientes = clientes.sort_values("Total gasto", ascending=False).head(15)
st.dataframe(clientes, use_container_width=True)

# === DADOS BRUTOS ===
with st.expander("🔍 Ver dados brutos"):
    st.dataframe(df_servicos, use_container_width=True)

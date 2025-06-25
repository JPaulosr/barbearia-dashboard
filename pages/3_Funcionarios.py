import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("\U0001F9D1‍\U0001F4BC Detalhes do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    return df

df = carregar_dados()

# === Lista de funcionários ===
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

# === Filtro por ano ===
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("\U0001F4C5 Filtrar por ano", anos)

# === Seleção de funcionário ===
funcionario_escolhido = st.selectbox("\U0001F4CB Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionário"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)]

# === Normalizar nomes para filtrar genéricos ===
nomes_excluir = ["boliviano", "brasileiro", "menino"]
def limpar_nome(nome):
    nome_limpo = unidecode(str(nome).lower())
    return not any(g in nome_limpo for g in nomes_excluir)

df_func = df_func[df_func["Cliente"].apply(limpar_nome)]

# === Histórico de atendimentos ===
st.subheader("\U0001F4C5 Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

# === Receita mensal com lógica de datas ===
st.subheader("\U0001F4CA Receita Mensal por Mês e Ano")
data_referencia = pd.to_datetime("2025-05-11")
df_func["AnoMes"] = df_func["Data"].dt.to_period("M").astype(str)

# Lógica corrigida para agrupamento correto
antes_ref = df_func[df_func["Data"] < data_referencia].copy()
apos_ref = df_func[df_func["Data"] >= data_referencia].copy()

antes_ref["Grupo"] = antes_ref["Data"].astype(str) + "_" + antes_ref["Cliente"]
apos_ref["Grupo"] = apos_ref["Data"].dt.strftime("%Y-%m-%d") + "_" + apos_ref["Cliente"]
apos_ref = apos_ref.drop_duplicates(subset=["Grupo"])

df_mensal = pd.concat([antes_ref, apos_ref])
receita_mensal = df_mensal.groupby("AnoMes")["Valor"].sum().reset_index()
receita_mensal["Valor Formatado"] = receita_mensal["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

fig_mensal = px.bar(receita_mensal, x="AnoMes", y="Valor", text="Valor Formatado", labels={"Valor": "Receita (R$)", "AnoMes": "Ano-Mês"})
fig_mensal.update_layout(height=400, template="plotly_white")
fig_mensal.update_traces(textposition="outside")
st.plotly_chart(fig_mensal, use_container_width=True)

# === Receita por tipo ===
if df_func["Tipo"].nunique() > 1:
    st.subheader("\U0001F967 Receita por Tipo (Produto ou Serviço)")
    por_tipo = df_func.groupby("Tipo")["Valor"].sum().reset_index()
    fig_tipo = px.pie(por_tipo, names="Tipo", values="Valor", hole=0.3)
    fig_tipo.update_traces(textinfo="percent+label")
    st.plotly_chart(fig_tipo, use_container_width=True)

# === Tabela resumo com lógica de datas ===
st.subheader("\U0001F4CB Resumo de Atendimentos")
df_func["Grupo"] = df_func["Data"].dt.strftime("%Y-%m-%d") + "_" + df_func["Cliente"]
df_unicos = df_func.drop_duplicates(subset=["Grupo"])

qtd_combo = df_unicos.groupby("Grupo")["Serviço"].count().gt(1).sum()
qtd_total = len(df_unicos)
qtd_simples = qtd_total - qtd_combo
tique_medio = df_unicos.groupby("Grupo")["Valor"].sum().mean()

resumo = pd.DataFrame({
    "Total Atendimentos": [qtd_total],
    "Combos": [qtd_combo],
    "Simples": [qtd_simples],
    "Tique Médio": [f"R$ {tique_medio:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")]
})
st.dataframe(resumo, use_container_width=True)

# === Gráfico de distribuição por cliente (top 10 em barras) ===
st.subheader("\U0001F465 Distribuição de Atendimentos por Cliente")
atend_cliente = df_unicos["Cliente"].value_counts().reset_index()
atend_cliente.columns = ["Cliente", "Atendimentos"]
top_10_clientes = atend_cliente.head(10)
fig_clientes = px.bar(top_10_clientes, x="Cliente", y="Atendimentos", text="Atendimentos", labels={"Atendimentos": "Nº Atendimentos"})
fig_clientes.update_traces(textposition="outside")
fig_clientes.update_layout(height=400, template="plotly_white")
st.plotly_chart(fig_clientes, use_container_width=True)

# === Serviços mais executados ===
st.subheader("\U0001F488 Serviços mais executados")
servicos = df_func["Serviço"].value_counts().reset_index()
servicos.columns = ["Serviço", "Quantidade"]
st.dataframe(servicos, use_container_width=True)

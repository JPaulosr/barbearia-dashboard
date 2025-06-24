import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧑‍💼 Detalhes do Funcionário")

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
funcionarios = df["Funcionario"].dropna().unique().tolist()
funcionarios.sort()

# === Filtro por ano ===
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("📅 Filtrar por ano", anos)

# === Seleção de funcionário ===
funcionario_escolhido = st.selectbox("📋 Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionario"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)]

# === Histórico de atendimentos ===
st.subheader("📅 Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

# === Receita mensal ===
st.subheader("📊 Receita Mensal por Mês e Ano")
df_func["AnoMes"] = df_func["Data"].dt.to_period("M")
mensal = df_func.groupby("AnoMes")["Valor"].sum().reset_index()
mensal["AnoMes"] = mensal["AnoMes"].astype(str)
fig_mensal = px.bar(mensal, x="AnoMes", y="Valor", labels={"Valor": "Receita (R$)", "AnoMes": "Ano-Mês"})
fig_mensal.update_layout(height=400, template="plotly_white")
st.plotly_chart(fig_mensal, use_container_width=True)

# === Receita por tipo ===
st.subheader("🥧 Receita por Tipo (Produto ou Serviço)")
por_tipo = df_func.groupby("Tipo")["Valor"].sum().reset_index()
fig_tipo = px.pie(por_tipo, names="Tipo", values="Valor", hole=0.3)
fig_tipo.update_traces(textinfo="percent+label")
st.plotly_chart(fig_tipo, use_container_width=True)

# === Tabela resumo ===
st.subheader("📋 Resumo de Atendimentos")
qtd_total = len(df_func)
qtd_combo = df_func["Serviço"].str.lower().str.contains("combo").sum()
qtd_simples = qtd_total - qtd_combo
tique_medio = df_func.groupby("Data")["Valor"].sum().mean()
resumo = pd.DataFrame({
    "Total Atendimentos": [qtd_total],
    "Combos": [qtd_combo],
    "Simples": [qtd_simples],
    "Tique Médio": [f"R$ {tique_medio:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")]
})
st.dataframe(resumo, use_container_width=True)

# === Gráfico de distribuição por cliente ===
st.subheader("👥 Distribuição de Atendimentos por Cliente")
atend_cliente = df_func["Cliente"].value_counts().reset_index()
atend_cliente.columns = ["Cliente", "Atendimentos"]
fig_clientes = px.pie(atend_cliente, names="Cliente", values="Atendimentos", hole=0.4)
fig_clientes.update_traces(textinfo="label+percent")
st.plotly_chart(fig_clientes, use_container_width=True)

# === Serviços mais executados ===
st.subheader("💈 Serviços mais executados")
servicos = df_func["Serviço"].value_counts().reset_index()
servicos.columns = ["Serviço", "Quantidade"]
st.dataframe(servicos, use_container_width=True)

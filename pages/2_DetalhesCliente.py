import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Mês_Ano"] = df["Data"].dt.strftime("%Y-%m")
    return df

df = carregar_dados()

# === Filtro de cliente (com fallback da sessão)
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

# Filtra dados do cliente
df_cliente = df[df["Cliente"] == cliente]

# 📅 Histórico de atendimentos
st.subheader(f"📅 Histórico de atendimentos - {cliente}")
st.dataframe(df_cliente.sort_values("Data", ascending=False), use_container_width=True)

# 📊 Receita mensal por mês e ano
st.subheader("📊 Receita mensal")
receita_mensal = df_cliente.groupby("Mês_Ano")["Valor"].sum().reset_index()
fig_receita = px.bar(
    receita_mensal,
    x="Mês_Ano",
    y="Valor",
    text_auto=True,
    labels={"Valor": "Receita (R$)", "Mês_Ano": "Mês"},
)
fig_receita.update_layout(height=350)
st.plotly_chart(fig_receita, use_container_width=True)

# 📊 Receita por tipo (substitui gráfico de pizza por barras)
st.subheader("📊 Receita por Tipo")
por_tipo = df_cliente.groupby("Tipo")["Valor"].sum().reset_index()
fig_tipo = px.bar(
    por_tipo,
    x="Tipo",
    y="Valor",
    text="Valor",
    labels={"Valor": "Receita (R$)", "Tipo": "Tipo"},
    color="Tipo"
)
fig_tipo.update_traces(texttemplate="R$ %{text:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."), textposition="outside")
fig_tipo.update_layout(showlegend=False, height=300)
st.plotly_chart(fig_tipo, use_container_width=True)

# 📊 Atendimentos por funcionário (substitui gráfico de pizza por barras)
st.subheader("📊 Atendimentos por Funcionário")
por_func = df_cliente["Funcionário"].value_counts().reset_index()
por_func.columns = ["Funcionário", "Atendimentos"]
fig_func = px.bar(
    por_func,
    x="Funcionário",
    y="Atendimentos",
    text="Atendimentos",
    color="Funcionário"
)
fig_func.update_traces(textposition="outside")
fig_func.update_layout(showlegend=False, height=300)
st.plotly_chart(fig_func, use_container_width=True)

# 📋 Tabela resumo
st.subheader("📋 Resumo de Atendimentos")
resumo = df_cliente.groupby("Data").agg(
    Qtd_Serviços=("Serviço", "count"),
    Qtd_Produtos=("Tipo", lambda x: (x == "Produto").sum())
).reset_index()

# Determina se foi combo ou simples
resumo["Qtd_Combo"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
resumo["Qtd_Simples"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

# Resultado final
resumo_final = pd.DataFrame({
    "Total Atendimentos": [resumo.shape[0]],
    "Qtd Combos": [resumo["Qtd_Combo"].sum()],
    "Qtd Simples": [resumo["Qtd_Simples"].sum()]
})
st.dataframe(resumo_final, use_container_width=True)

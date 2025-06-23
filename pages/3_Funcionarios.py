import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Funcionário")

# Verifica se foi passado algum funcionário
if "funcionario" not in st.session_state or st.session_state["funcionario"] == "Selecione...":
    st.warning("⚠️ Nenhum funcionário selecionado.")
    st.stop()

funcionario = st.session_state["funcionario"]

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()
df = df[df["Funcionário"] == funcionario]

st.subheader(f"📊 Resumo do Funcionário: {funcionario}")

# ➕ Receita total
valor_total = df["Valor"].sum()
valor_formatado = f"R$ {valor_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
st.markdown(f"### 💰 Receita Total: **{valor_formatado}**")

# Receita mensal
receita_mensal = df.groupby(["Ano", "Mês"])["Valor"].sum().reset_index()
receita_mensal["Ano-Mês"] = receita_mensal["Ano"].astype(str) + "-" + receita_mensal["Mês"].astype(str).str.zfill(2)

fig = px.bar(receita_mensal, x="Ano-Mês", y="Valor", text_auto='.2s', title="Receita Mensal")
st.plotly_chart(fig, use_container_width=True)

# Serviços e Produtos
tipo_resumo = df.groupby("Tipo")["Valor"].sum().reset_index()
fig2 = px.pie(tipo_resumo, names="Tipo", values="Valor", title="Distribuição: Produtos vs Serviços")
st.plotly_chart(fig2, use_container_width=True)

# Tabela detalhada
st.subheader("📋 Tabela detalhada")
st.dataframe(df[["Data", "Cliente", "Serviço", "Tipo", "Valor"]].sort_values(by="Data", ascending=False), use_container_width=True)

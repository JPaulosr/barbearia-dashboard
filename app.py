import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(layout="wide")
st.title("📊 Dashboard da Barbearia")

@st.cache_data
def carregar_dados():
    caminho = "Modelo_Barbearia_Automatizado (10).xlsx"

    if not os.path.exists(caminho):
        st.error(f"❌ Arquivo '{caminho}' não encontrado. Suba ele para o repositório.")
        st.stop()

    try:
        df = pd.read_excel(caminho, sheet_name="Base de Dados")
        df.columns = [str(col).strip() for col in df.columns]

        if 'Data' not in df.columns:
            st.error("❌ Erro: a coluna 'Data' não foi encontrada na planilha.")
            st.write("Colunas disponíveis:", df.columns.tolist())
            st.stop()

        df['Ano'] = pd.to_datetime(df['Data'], errors='coerce').dt.year
        df['Mês'] = pd.to_datetime(df['Data'], errors='coerce').dt.month

        return df

    except Exception as e:
        st.error(f"❌ Erro inesperado ao carregar os dados: {e}")
        st.stop()

# Carregar dados
df = carregar_dados()

# Filtro lateral por ano
anos = sorted(df['Ano'].dropna().unique())
ano_selecionado = st.sidebar.selectbox("📅 Filtrar por Ano", options=["Todos"] + list(anos))

if ano_selecionado != "Todos":
    df = df[df["Ano"] == ano_selecionado]

# Gráfico de Receita por Ano
st.subheader("📊 Receita por Ano")
receita_ano = df.groupby("Ano")["Valor"].sum().reset_index()
fig_ano = px.bar(
    receita_ano,
    x="Ano",
    y="Valor",
    labels={"Valor": "Total Faturado"},
    text_auto=True
)
fig_ano.update_layout(
    xaxis_title="Ano",
    yaxis_title="Receita Total (R$)",
    template="plotly_white"
)
st.plotly_chart(fig_ano, use_container_width=True)

# Gráfico de Receita por Mês
st.subheader("📅 Receita por Mês")

df['Ano-Mês'] = pd.to_datetime(df['Data'], errors='coerce').dt.to_period('M').astype(str)
receita_mes = df.groupby("Ano-Mês")["Valor"].sum().reset_index()

fig_mes = px.bar(
    receita_mes,
    x="Ano-Mês",
    y="Valor",
    labels={"Valor": "Faturamento Mensal"},
    text_auto=True
)
fig_mes.update_layout(
    xaxis_title="Mês",
    yaxis_title="Receita (R$)",
    template="plotly_white",
    xaxis_tickangle=-45
)
st.plotly_chart(fig_mes, use_container_width=True)

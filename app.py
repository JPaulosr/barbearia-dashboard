import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(layout="wide")
st.title("📊 Dashboard da Barbearia")

@st.cache_data
def carregar_dados():
    try:
        caminho = "Modelo_Barbearia_Automatizado (10).xlsx"
        if not os.path.exists(caminho):
            st.error(f"❌ Arquivo '{caminho}' não encontrado.")
            st.stop()

        df = pd.read_excel(caminho)

        # Corrige os nomes das colunas
        df.columns = [str(col).strip() for col in df.columns]

        if 'Data' not in df.columns:
            st.error("❌ Erro: a coluna 'Data' não foi encontrada na planilha.")
            st.stop()

        df['Ano'] = pd.to_datetime(df['Data'], errors='coerce').dt.year
        df['Mês'] = pd.to_datetime(df['Data'], errors='coerce').dt.month

        return df

    except Exception as e:
        st.error(f"❌ Erro inesperado ao carregar os dados: {e}")
        st.stop()

df = carregar_dados()

# Filtros
anos = sorted(df['Ano'].dropna().unique())
ano_selecionado = st.sidebar.selectbox("📅 Filtrar por Ano", options=["Todos"] + list(anos))

if ano_selecionado != "Todos":
    df = df[df["Ano"] == ano_selecionado]

# Gráfico de Receita por Ano
st.subheader("Receita por Ano")
receita_ano = df.groupby("Ano")["Valor"].sum().reset_index()
fig = px.bar(receita_ano, x="Ano", y="Valor", labels={"Valor": "Total Faturado"}, text_auto=True)
fig.update_layout(
    xaxis_title="Ano",
    yaxis_title="Receita Total (R$)",
    template="plotly_white"
)
st.plotly_chart(fig, use_container_width=True)

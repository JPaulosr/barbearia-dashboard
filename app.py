import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Dashboard da Barbearia", layout="wide")
st.title("💈 Dashboard da Barbearia")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx")
    df.columns = [str(col).strip().lower() for col in df.columns]
    if 'data' not in df.columns:
        st.error("Erro: a coluna 'Data' não foi encontrada na planilha.")
        st.stop()
    df['ano'] = pd.to_datetime(df['data'], errors='coerce').dt.year
    df['mês'] = pd.to_datetime(df['data'], errors='coerce').dt.month
    return df

df = carregar_dados()

st.markdown("### Receita por Ano")
receita_por_ano = df.groupby("ano")["valor"].sum().reset_index()
fig = px.bar(receita_por_ano, x="ano", y="valor", text_auto='.2s')
st.plotly_chart(fig, use_container_width=True)
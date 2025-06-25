
import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("🏦 Resumo Financeiro do Salão")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    return df

df = carregar_dados()

# Filtro por ano
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos)
df_ano = df[df["Ano"] == ano]

# Receita bruta por funcionário
receita_func = df_ano.groupby("Funcionário")["Valor"].sum().to_dict()
receita_jpaulo = receita_func.get("JPaulo", 0)
receita_vinicius = receita_func.get("Vinicius", 0)

# Receita do salão: 100% JPaulo + 50% Vinicius
receita_salao = receita_jpaulo + (receita_vinicius * 0.5)

# Entradas
st.subheader("📥 Receita do Salão")
st.markdown(f"- Receita JPaulo (100%): **R$ {receita_jpaulo:,.2f}**".replace(",", "v").replace(".", ",").replace("v", "."))
st.markdown(f"- Receita Vinicius (50%): **R$ {receita_vinicius * 0.5:,.2f}**".replace(",", "v").replace(".", ",").replace("v", "."))
st.markdown(f"**➡️ Receita Total do Salão:** R$ {receita_salao:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# Despesas fixas (editáveis)
st.subheader("📤 Despesas Fixas")
col1, col2, col3 = st.columns(3)
aluguel = col1.number_input("Aluguel", min_value=0.0, value=800.0, step=50.0)
agua = col2.number_input("Água", min_value=0.0, value=120.0, step=10.0)
luz = col3.number_input("Luz", min_value=0.0, value=200.0, step=10.0)
produtos = st.number_input("Produtos e materiais", min_value=0.0, value=300.0, step=50.0)

total_despesas = aluguel + agua + luz + produtos

# Resultado
st.subheader("📈 Resultado Financeiro")
lucro = receita_salao - total_despesas
st.metric("Lucro do Salão", f"R$ {lucro:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

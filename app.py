
import streamlit as st
import pandas as pd
import plotly.express as px

# --- CARREGAR DADOS ---
@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx")
    df['Ano'] = pd.to_datetime(df['Data']).dt.year
    df['Mês'] = pd.to_datetime(df['Data']).dt.month
    return df

df = carregar_dados()

# --- FILTROS ---
st.title("Dashboard da Barbearia")

col1, col2, col3, col4 = st.columns(4)
anos = ["Todos"] + sorted(df["Ano"].dropna().unique().astype(str).tolist())
servicos = ["Todos"] + sorted(df["Serviço"].dropna().unique())
contas = ["Todos"] + sorted(df["Conta"].dropna().unique())
funcionarios = ["Todos"] + sorted(df["Funcionário"].dropna().unique())

ano_selecionado = col1.selectbox("Ano", anos)
funcionario_selecionado = col2.selectbox("Funcionário", funcionarios)
servico_selecionado = col3.selectbox("Serviço", servicos)
conta_selecionada = col4.selectbox("Forma de Pagamento", contas)

df_filtrado = df.copy()
if ano_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Ano"] == int(ano_selecionado)]
if funcionario_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Funcionário"] == funcionario_selecionado]
if servico_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Serviço"] == servico_selecionado]
if conta_selecionada != "Todos":
    df_filtrado = df_filtrado[df_filtrado["Conta"] == conta_selecionada]

# --- GRÁFICO ANUAL ---
st.subheader("📊 Receita por Ano")
df_ano = df_filtrado.groupby("Ano")["Valor"].sum().reset_index()
fig = px.bar(df_ano, x="Ano", y="Valor", labels={"Valor": "Receita"}, text_auto=True)
st.plotly_chart(fig, use_container_width=True)

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Dashboard da Barbearia", layout="wide")

# --- CARREGAR DADOS ---
@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx")

    # Normalizar nomes de colunas
    df.columns = df.columns.str.strip()

    if 'Data' not in df.columns:
        st.error("Erro: a coluna 'Data' não foi encontrada na planilha.")
        st.stop()

    try:
        df['Ano'] = pd.to_datetime(df['Data'], errors='coerce').dt.year
        df['Mês'] = pd.to_datetime(df['Data'], errors='coerce').dt.month
    except Exception as e:
        st.error(f"Erro ao converter a coluna 'Data': {e}")
        st.stop()

    return df

df = carregar_dados()

# --- BARRA LATERAL DE FILTROS ---
st.sidebar.header("Filtros")
ano_selecionado = st.sidebar.selectbox("Ano", options=["Todos"] + sorted(df['Ano'].dropna().unique().tolist()))
func_selecionado = st.sidebar.selectbox("Funcionário", options=["Todos"] + sorted(df['Funcionário'].dropna().unique().tolist()))
servico_selecionado = st.sidebar.selectbox("Serviço", options=["Todos"] + sorted(df['Serviço'].dropna().unique().tolist()))
conta_selecionada = st.sidebar.selectbox("Forma de Pagamento", options=["Todos"] + sorted(df['Conta'].dropna().unique().tolist()))

# --- APLICAR FILTROS ---
df_filtrado = df.copy()

if ano_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado['Ano'] == ano_selecionado]
if func_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado['Funcionário'] == func_selecionado]
if servico_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado['Serviço'] == servico_selecionado]
if conta_selecionada != "Todos":
    df_filtrado = df_filtrado[df_filtrado['Conta'] == conta_selecionada]

# --- TÍTULO ---
st.title("📊 Dashboard da Barbearia")

# --- GRÁFICO DE RECEITA POR ANO ---
st.subheader("Receita por Ano")
receita_ano = df_filtrado.groupby("Ano")["Valor"].sum().reset_index()
fig_ano = px.bar(receita_ano, x="Ano", y="Valor", text_auto='.2f', color_discrete_sequence=["#3399FF"])
fig_ano.update_layout(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
st.plotly_chart(fig_ano, use_container_width=True)

# --- TOP CLIENTES (opcional) ---
st.subheader("Top 20 Clientes")
if "Cliente" in df_filtrado.columns:
    top_clientes = (
        df_filtrado.groupby("Cliente")["Valor"]
        .sum()
        .sort_values(ascending=False)
        .head(20)
        .reset_index()
    )
    for i, row in top_clientes.iterrows():
        st.markdown(f"- **{row['Cliente']}** — R$ {row['Valor']:.2f}")
else:
    st.warning("Coluna 'Cliente' não encontrada na planilha.")

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
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month.astype(int)
    df["Mês_Ano"] = df["Data"].dt.to_period("M").astype(str)
    return df

df = carregar_dados()

# Obter nome do cliente via session_state (vindo da página anterior)
cliente = st.session_state.get("cliente")

if not cliente:
    st.warning("Nenhum cliente selecionado. Volte à tela anterior e escolha um cliente.")
    st.stop()

st.subheader(f"📅 Histórico de atendimentos - {cliente}")
historico = df[df["Cliente"] == cliente].sort_values("Data", ascending=False)

st.dataframe(
    historico[
        ["Data", "Serviço", "Valor", "Conta", "Cliente", "Combo", "Funcionário", "Fase", "Tipo", "Ano", "Mês", "Mês_Ano"]
    ],
    use_container_width=True
)

# Receita mensal
st.subheader("📊 Receita mensal")
mensal = (
    historico.groupby("Mês_Ano")["Valor"]
    .sum()
    .reset_index()
    .sort_values("Mês_Ano")
)
fig = px.bar(
    mensal,
    x="Mês_Ano",
    y="Valor",
    labels={"Valor": "Receita (R$)", "Mês_Ano": "Mês"},
    text_auto=".2s"
)
fig.update_layout(height=400, template="plotly_dark")
st.plotly_chart(fig, use_container_width=True)

# Atendimento por funcionário
st.subheader("👥 Distribuição por funcionário")
contagem_func = (
    historico["Funcionário"].value_counts()
    .reset_index()
    .rename(columns={"index": "Funcionário", "Funcionário": "Atendimentos"})
)
st.dataframe(contagem_func, use_container_width=True)

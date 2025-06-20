import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# Recupera o nome do cliente via session_state
cliente = st.session_state.get("cliente", "")

if not cliente:
    st.warning("⚠ Nenhum cliente selecionado.")
    st.stop()

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# Filtra só os dados do cliente
df_cli = df[df["Cliente"] == cliente]

st.subheader(f"📈 Receita mensal por tipo de serviço - {cliente}")
servico_mes = df_cli.groupby(["Ano", "Mês", "Serviço"])["Valor"].sum().reset_index()

# Formata nome do mês
meses_nome = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}
servico_mes["MêsNome"] = servico_mes["Mês"].map(meses_nome)
servico_mes["Ano-Mês"] = servico_mes["Ano"].astype(str) + "-" + servico_mes["MêsNome"]

# Gráfico de linha com marcadores
fig = px.line(
    servico_mes,
    x="Ano-Mês",
    y="Valor",
    color="Serviço",
    markers=True,
    labels={"Valor": "Faturamento"}
)
fig.update_layout(
    xaxis_title="Mês",
    yaxis_title="Receita (R$)",
    template="plotly_white",
    xaxis_tickangle=-45
)
st.plotly_chart(fig, use_container_width=True)

# Tabela de atendimentos por funcionário
st.subheader("🧑‍🔧 Quantas vezes foi atendido por cada funcionário")

atendimentos = df_cli.groupby("Funcionário").size().reset_index(name="Quantidade")
st.dataframe(atendimentos, use_container_width=True)

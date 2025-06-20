import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# Agora pega do session_state
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

df_cli = df[df["Cliente"] == cliente]

st.subheader(f"📊 Receita mensal por tipo de serviço - {cliente}")
servico_mes = df_cli.groupby(["Ano", "Mês", "Serviço"])["Valor"].sum().reset_index()

meses_nome = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}
servico_mes["MêsNome"] = servico_mes["Mês"].map(meses_nome)
servico_mes["Ano-Mês"] = servico_mes["Ano"].astype(str) + "-" + servico_mes["MêsNome"]

fig = px.bar(
    servico_mes,
    x="Ano-Mês",
    y="Valor",
    color="Serviço",
    barmode="stack",
    text_auto=".2s",
    labels={"Valor": "Faturamento"}
)
fig.update_layout(
    xaxis_title="Mês",
    yaxis_title="R$",
    template="plotly_white",
    xaxis_tickangle=-45
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("🧑‍🔧 Quantas vezes foi atendido por cada funcionário")
atendimentos = df_cli.groupby("Funcionário").size().reset_index(name="Quantidade")
st.dataframe(atendimentos, use_container_width=True)

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Funcionário")

# Pega o nome do funcionário via session_state
funcionario = st.session_state.get("funcionario", "")

if not funcionario:
    st.warning("⚠ Nenhum funcionário selecionado.")
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

# Filtra os dados do funcionário selecionado
df_func = df[df["Funcionário"] == funcionario]

st.subheader(f"📊 Receita mensal separada por tipo de serviço - {funcionario}")
servico_mes = df_func.groupby(["Ano", "Mês", "Serviço"])["Valor"].sum().reset_index()

# Formatação de meses
meses_nome = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}
servico_mes["MêsNome"] = servico_mes["Mês"].map(meses_nome)
servico_mes["Ano-Mês"] = servico_mes["Ano"].astype(str) + "-" + servico_mes["MêsNome"]

# Gráfico facetado
fig = px.bar(
    servico_mes,
    x="Ano-Mês",
    y="Valor",
    color="Serviço",
    facet_col="Serviço",
    text_auto=".2s",
    labels={"Valor": "Faturamento"},
    height=400
)
fig.update_layout(
    xaxis_title="Mês",
    yaxis_title="Receita (R$)",
    template="plotly_white"
)
st.plotly_chart(fig, use_container_width=True)

# Tabela de clientes únicos atendidos (1 por dia)
st.subheader("🧑‍🤝‍🧑 Clientes atendidos (visitas únicas)")

atendimentos_unicos = df_func.drop_duplicates(subset=["Cliente", "Data"])
clientes = atendimentos_unicos.groupby("Cliente").size().reset_index(name="Qtd Atendimentos")
clientes = clientes.sort_values(by="Qtd Atendimentos", ascending=False)

total = len(atendamentos_unicos)

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.month.map({
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    })
    return df

df = carregar_dados()

# Filtro por funcionário com fallback do session_state
funcionarios_disponiveis = sorted(df["Funcionário"].dropna().unique())
funcionario_default = st.session_state.get("funcionario", funcionarios_disponiveis[0])
funcionario = st.selectbox("👤 Selecione o funcionário", funcionarios_disponiveis, index=funcionarios_disponiveis.index(funcionario_default))

# Filtro por ano
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos, index=0)

# Filtra dados
df_func = df[(df["Funcionário"] == funcionario) & (df["Ano"] == ano)]

# Receita mensal
st.subheader("📈 Receita Mensal")
receita_mensal = df_func.groupby(["Mês", "Mês_Nome"])["Valor"].sum().reset_index().sort_values("Mês")
fig = px.bar(
    receita_mensal,
    x="Mês_Nome",
    y="Valor",
    text_auto=True,
    labels={"Valor": "Receita (R$)", "Mês_Nome": "Mês"}
)
fig.update_layout(height=350)
st.plotly_chart(fig, use_container_width=True)

# Total de atendimentos
st.subheader("📋 Total de Atendimentos")
qtd_atendimentos = df_func.drop_duplicates(subset=["Cliente", "Data"]).shape[0]
st.metric(label="Atendimentos Únicos", value=qtd_atendimentos)

# Combo vs Simples
st.subheader("🔀 Combo vs Simples")
agrupado = df_func.groupby(["Cliente", "Data"]).agg(Qtd_Serviços=("Serviço", "count")).reset_index()
agrupado["Combo"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
agrupado["Simples"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

resumo = pd.DataFrame({
    "Total Atendimentos": [agrupado.shape[0]],
    "Qtd Combos": [agrupado["Combo"].sum()],
    "Qtd Simples": [agrupado["Simples"].sum()]
})
st.dataframe(resumo, use_container_width=True)

st.markdown("---")
st.markdown("⬅️ Use o menu lateral para acessar outras seções.")

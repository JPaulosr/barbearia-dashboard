import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧑‍� Detalhes do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mes"] = df["Data"].dt.month
    df["MesNome"] = df["Data"].dt.strftime('%b')
    return df

df = carregar_dados()

funcionarios_disponiveis = sorted(df["Funcionário"].dropna().unique())
funcionario = st.selectbox("💼 Escolha um funcionário", funcionarios_disponiveis)
df_func = df[df["Funcionário"] == funcionario]

# 📅 Histórico de atendimentos
st.subheader("\ud83d\udcc5 Histórico de Atendimentos")
st.dataframe(df_func[["Data", "Cliente", "Serviço", "Tipo", "Valor"]].sort_values("Data"), use_container_width=True)

# 📊 Receita mensal
st.subheader("\ud83d\udcca Receita Mensal")
graf_mensal = df_func.groupby(["Ano", "MesNome"])["Valor"].sum().reset_index()
fig_mensal = px.bar(graf_mensal, x="MesNome", y="Valor", color="Ano", barmode="group", text_auto=True, title="Receita por Mês")
st.plotly_chart(fig_mensal, use_container_width=True)

# 🥧 Receita por tipo
st.subheader("\ud83e\udd67 Receita por Tipo de Atendimento")
por_tipo = df_func.groupby("Tipo")["Valor"].sum().reset_index()
fig_tipo = px.pie(por_tipo, names="Tipo", values="Valor", title="Distribuição de Receita: Produto vs Serviço")
st.plotly_chart(fig_tipo, use_container_width=True)

# 📋 Combos e simples
st.subheader("\ud83d\udccb Quantitativo de Atendimentos")
agrupar = df_func.groupby(["Cliente", "Data"]).agg(Qtd_Serviços=('Serviço', 'count')).reset_index()
agrupar["Combo"] = agrupar["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
agrupar["Simples"] = agrupar["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

total_atendimentos = agrupar.shape[0]
total_combos = agrupar["Combo"].sum()
total_simples = agrupar["Simples"].sum()

st.metric("Total de Atendimentos", total_atendimentos)
st.metric("Combos Realizados", total_combos)
st.metric("Atendimentos Simples", total_simples)

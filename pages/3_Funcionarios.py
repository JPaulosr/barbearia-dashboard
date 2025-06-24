import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧑‍� Detalhamento do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mes"] = df["Data"].dt.strftime('%b')
    return df

df = carregar_dados()

st.subheader("👨‍🔧 Escolha um funcionário")
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionario = st.selectbox("Funcionário", funcionarios)
df_func = df[df["Funcionário"] == funcionario]

# 📅 Histórico de atendimentos
st.subheader("📅 Histórico de atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False)[["Data", "Cliente", "Serviço", "Tipo", "Valor"]], use_container_width=True)

# 📊 Receita mensal
st.subheader("📊 Receita mensal")
receita_mensal = df_func.groupby(["Ano", "Mes"])["Valor"].sum().reset_index()
fig1 = px.bar(receita_mensal, x="Mes", y="Valor", color="Ano", barmode="group", text_auto=True)
st.plotly_chart(fig1, use_container_width=True)

# 🥧 Receita por tipo
st.subheader("🥧 Receita por tipo de atendimento")
tipo = df_func.groupby("Tipo")["Valor"].sum().reset_index()
fig2 = px.pie(tipo, names="Tipo", values="Valor", hole=0.4)
st.plotly_chart(fig2, use_container_width=True)

# 💼 Resumo
st.subheader("📋 Resumo geral")
resumo = df_func.copy()
resumo_diario = resumo.groupby("Data").agg(
    Atendimentos=("Cliente", "count"),
    Receita=("Valor", "sum")
).reset_index()

resumo_total = pd.DataFrame({
    "Total de Atendimentos": [resumo_diario["Atendimentos"].sum()],
    "Receita Total": [f"R$ {resumo_diario['Receita'].sum():,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")]
})
st.dataframe(resumo_total, use_container_width=True)

# ✔ Extras: combos e simples
st.subheader("🔍 Quantidade de combos e simples")
df_contagem = df_func.groupby(["Cliente", "Data"]).agg(Qtd_Servicos=('Serviço', 'count')).reset_index()
df_contagem["Combo"] = df_contagem["Qtd_Servicos"].apply(lambda x: 1 if x > 1 else 0)
df_contagem["Simples"] = df_contagem["Qtd_Servicos"].apply(lambda x: 1 if x == 1 else 0)

resumo_combo_simples = pd.DataFrame({
    "Total Combos": [df_contagem["Combo"].sum()],
    "Total Simples": [df_contagem["Simples"].sum()]
})
st.dataframe(resumo_combo_simples, use_container_width=True)

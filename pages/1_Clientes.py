import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.strftime('%b')
    return df

df = carregar_dados()

cliente = st.session_state.get("cliente", None)
if not cliente:
    st.error("Cliente não selecionado. Volte e selecione um cliente na tela anterior.")
    st.stop()

st.subheader(f"📊 Histórico de Atendimentos - {cliente}")
df_cliente = df[df["Cliente"].str.lower() == cliente.lower()]

# Receita mensal
receita_mensal = df_cliente.groupby(["Ano", "Mês_Nome"])['Valor'].sum().reset_index()
fig1 = px.bar(receita_mensal, x="Mês_Nome", y="Valor", color="Ano", barmode="group", text_auto=True, title="Receita Mensal")
st.plotly_chart(fig1, use_container_width=True)

# Receita por tipo
receita_tipo = df_cliente.groupby("Tipo")["Valor"].sum().reset_index()
fig2 = px.pie(receita_tipo, names="Tipo", values="Valor", title="Receita por Tipo")
st.plotly_chart(fig2, use_container_width=True)

# Distribuição por funcionário
st.subheader("🧑‍🔧 Atendimentos por Funcionário")
atend_func = df_cliente.groupby("Funcionário")["Data"].count().reset_index().rename(columns={"Data": "Qtd Atendimentos"})
fig3 = px.pie(atend_func, names="Funcionário", values="Qtd Atendimentos", title="Distribuição de Atendimentos")
st.plotly_chart(fig3, use_container_width=True)

# Tabela com Combo e Simples
agrupado = df_cliente.groupby(["Cliente", "Data"]).agg(
    Qtd_Serviços=('Serviço', 'count')
).reset_index()
agrupado["Combo"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
agrupado["Simples"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

tabela_combo_simples = agrupado.groupby("Cliente").agg(
    Total_Atendimentos=("Data", "count"),
    Qtd_Combo=("Combo", "sum"),
    Qtd_Simples=("Simples", "sum")
).reset_index()

st.subheader("📋 Resumo de Atendimentos")
st.dataframe(tabela_combo_simples, use_container_width=True)

st.markdown("""
---
⬅️ Volte para a página anterior para selecionar outro cliente.
""")

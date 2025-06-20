import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(layout="wide")
st.title("📊 Dashboard da Barbearia")

@st.cache_data
def carregar_dados():
    caminho = "Modelo_Barbearia_Automatizado (10).xlsx"

    if not os.path.exists(caminho):
        st.error(f"❌ Arquivo '{caminho}' não encontrado.")
        st.stop()

    try:
        # Lê receitas
        df = pd.read_excel(caminho, sheet_name="Base de Dados")
        df.columns = [str(col).strip() for col in df.columns]

        if 'Data' not in df.columns:
            st.error("Coluna 'Data' não encontrada em Base de Dados.")
            st.stop()

        df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
        df['Ano'] = df['Data'].dt.year
        df['Mês'] = df['Data'].dt.month

        # Lê despesas
        despesas = pd.read_excel(caminho, sheet_name="Despesas")
        despesas.columns = [str(col).strip() for col in despesas.columns]

        if 'Data' not in despesas.columns or 'Valor' not in despesas.columns:
            st.error("Colunas 'Data' ou 'Valor' não encontradas na aba Despesas.")
            st.stop()

        despesas['Data'] = pd.to_datetime(despesas['Data'], errors='coerce')
        despesas['Ano'] = despesas['Data'].dt.year
        despesas['Mês'] = despesas['Data'].dt.month

        return df, despesas

    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        st.stop()

# Carrega dados
df, despesas = carregar_dados()

# === Receita Líquida por Ano ===
st.subheader("📊 Receita Líquida por Ano")

# Receita bruta
receita_ano = df.groupby("Ano")["Valor"].sum().reset_index(name="Receita")
# Despesa total
despesa_ano = despesas.groupby("Ano")["Valor"].sum().reset_index(name="Despesas")
# Junta e calcula líquida
resultado_ano = pd.merge(receita_ano, despesa_ano, on="Ano", how="left").fillna(0)
resultado_ano["Líquido"] = resultado_ano["Receita"] - resultado_ano["Despesas"]
resultado_ano["Texto"] = resultado_ano["Líquido"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

fig_ano = px.bar(
    resultado_ano,
    x="Ano",
    y="Líquido",
    text="Texto",
    labels={"Líquido": "Receita Líquida"},
)
fig_ano.update_layout(
    xaxis_title="Ano",
    yaxis_title="Receita Líquida (R$)",
    template="plotly_white"
)
st.plotly_chart(fig_ano, use_container_width=True)

# === Receita Líquida por Mês ===
st.subheader("📅 Receita Líquida por Mês")

anos_disponiveis = sorted(df["Ano"].dropna().unique())
ano_filtro = st.selectbox("🔎 Selecione o Ano", anos_disponiveis)

# Agrupamentos
df_mes = df[df["Ano"] == ano_filtro].groupby("Mês")["Valor"].sum().reset_index(name="Receita")
dp_mes = despesas[despesas["Ano"] == ano_filtro].groupby("Mês")["Valor"].sum().reset_index(name="Despesas")

resultado_mes = pd.merge(df_mes, dp_mes, on="Mês", how="left").fillna(0)
resultado_mes["Líquido"] = resultado_mes["Receita"] - resultado_mes["Despesas"]

# Mês nome + formatação
meses_nome = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
resultado_mes["Mês"] = resultado_mes["Mês"].map(meses_nome)
resultado_mes["Texto"] = resultado_mes["Líquido"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

fig_mes = px.bar(
    resultado_mes,
    x="Mês",
    y="Líquido",
    text="Texto",
    labels={"Líquido": "Receita Líquida"},
)
fig_mes.update_layout(
    xaxis_title="Mês",
    yaxis_title="Receita Líquida (R$)",
    template="plotly_white"
)
st.plotly_chart(fig_mes, use_container_width=True)

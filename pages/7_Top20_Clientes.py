import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("🏆 Top 20 Clientes")

@st.cache_data

def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df = df[df["Cliente"].notna()]
    return df

df = carregar_dados()

# === Filtros ===
anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("📅 Filtrar por ano", anos)
funcionarios = df["Funcionário"].dropna().unique().tolist()
selec_func = st.multiselect("👤 Filtrar por funcionário", funcionarios, default=funcionarios)

# Aplica filtros
mascara = (df["Ano"] == ano) & (df["Funcionário"].isin(selec_func))
df_filtrado = df[mascara]

# Remove nomes genéricos
nomes_excluir = ["boliviano", "brasileiro", "menino"]
df_filtrado = df_filtrado[~df_filtrado["Cliente"].str.lower().isin(nomes_excluir)]

# Função para gerar top 20 clientes
def top_20_por(df_base):
    atendimentos = df_base.copy()
    atendimentos["Cliente"] = atendimentos["Cliente"].astype(str)

    resumo = atendimentos.groupby("Cliente").agg({
        "Serviço": "count",
        "Produto": lambda x: x.notna().sum(),
        "Data": lambda x: len(set(zip(x.dt.date, atendimentos.loc[x.index, "Cliente"]))),
        "Combo": lambda x: (x == True).sum(),
        "Simples": lambda x: (x == True).sum(),
        "Valor": "sum",
    }).rename(columns={
        "Serviço": "Qtd_Serviços",
        "Produto": "Qtd_Produtos",
        "Data": "Qtd_Atendimento",
        "Combo": "Qtd_Combo",
        "Simples": "Qtd_Simples",
        "Valor": "Valor_Total"
    }).reset_index()

    resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    resumo = resumo.sort_values(by="Valor_Total", ascending=False).reset_index(drop=True)
    resumo.index += 1
    resumo.insert(0, "Posição", resumo.index)
    return resumo

# === Tabela principal ===
st.subheader("🥈 Top 20 Clientes - Geral")
resumo_geral = top_20_por(df_filtrado)
nome_busca = st.selectbox("🔎 Pesquisar cliente", [""] + resumo_geral["Cliente"].tolist())

if nome_busca:
    st.dataframe(resumo_geral[resumo_geral["Cliente"] == nome_busca], use_container_width=True)
else:
    st.dataframe(resumo_geral.head(20), use_container_width=True)

# === Gráfico Top 5 ===
st.subheader("📊 Top 5 por Receita")
top5 = resumo_geral.head(5)
fig = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado", labels={"Valor_Total": "Receita (R$)"})
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

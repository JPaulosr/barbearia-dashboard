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
    df["Ano"] = df["Data"].dt.year.astype("Int64")
    return df

df = carregar_dados()

# Remove nomes genéricos
nomes_invalidos = ["boliviano", "brasileiro", "menino"]
df = df[~df["Cliente"].str.lower().isin(nomes_invalidos)]

# Corrige atendimentos únicos por Cliente + Data a partir de 11/05/2025
limite = pd.to_datetime("2025-05-11")
df_antes = df[df["Data"] < limite]
df_depois = df[df["Data"] >= limite].drop_duplicates(subset=["Cliente", "Data"])
df_visitas = pd.concat([df_antes, df_depois])

# Filtros
anos = sorted(df["Ano"].dropna().unique())
ano = st.selectbox("📅 Filtrar por ano", anos, index=len(anos)-1)
df_visitas = df_visitas[df_visitas["Ano"] == ano]

# Filtra por funcionário
todos_funcionarios = sorted(df_visitas["Funcionário"].dropna().unique())
funcionarios_sel = st.multiselect("👤 Filtrar por funcionário", todos_funcionarios, default=todos_funcionarios)
df_visitas = df_visitas[df_visitas["Funcionário"].isin(funcionarios_sel)]

# --- Função para gerar Top 20 ---
def top_20_por(df):
    atendimentos = df.copy()
    resumo = atendimentos.groupby("Cliente").agg(
        Qtd_Serviços=("Serviço", "count"),
        Qtd_Produtos=("Produto", "sum"),
        Qtd_Atendimento=("Cliente", "count"),
        Qtd_Combo=("Combo", "sum"),
        Qtd_Simples=("Simples", "sum"),
        Valor_Total=("Valor", "sum")
    ).reset_index()

    resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    resumo = resumo.sort_values(by="Valor_Total", ascending=False).head(20).reset_index(drop=True)
    resumo.index += 1
    resumo.insert(0, "Posição", resumo.index)
    return resumo

# Gera Top 20 geral (JPaulo + Vinicius ou filtrado)
resumo_geral = top_20_por(df_visitas)
st.subheader("🥈 Top 20 Clientes - Geral")
cliente_default = resumo_geral["Cliente"].iloc[0] if not resumo_geral.empty else ""
st.selectbox("", [f"{func}" for func in funcionarios_sel], disabled=True)
st.dataframe(resumo_geral, use_container_width=True)

# Filtro por nome
st.subheader("🔍 Pesquisar cliente")
nome_busca = st.text_input("Digite um nome (ou parte dele)")
if nome_busca:
    resultado = resumo_geral[resumo_geral["Cliente"].str.lower().str.contains(nome_busca.lower())]
    st.dataframe(resultado, use_container_width=True)

# Gráfico Top 5
st.subheader("📊 Top 5 por Receita")
top5 = resumo_geral.head(5)
fig = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado",
             labels={"Valor_Total": "Valor (R$)"},
             title="Top 5 Clientes por Receita")
fig.update_traces(textposition="outside")
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

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
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# === Filtros ===
anos = sorted(df["Ano"].dropna().unique(), reverse=True)
anoselecionado = st.selectbox("📅 Filtrar por ano", anos)
df = df[df["Ano"] == anoselecionado]

funcionarios = sorted(df["Funcionário"].dropna().unique())
funcs = st.multiselect("🧑‍🔧 Filtrar por funcionário", funcionarios, default=funcionarios)
df_filtrado = df[df["Funcionário"].isin(funcs)]

# Remove nomes genéricos
nomes_invalidos = ["boliviano", "brasileiro", "menino"]
df_filtrado = df_filtrado[~df_filtrado["Cliente"].str.lower().isin(nomes_invalidos)]

# === Função para calcular top 20 clientes ===
def top_20_por(df):
    if df.empty:
        return pd.DataFrame(columns=[
            "Cliente", "Qtd_Serviços", "Qtd_Produtos", "Qtd_Atendimento",
            "Qtd_Combo", "Qtd_Simples", "Valor_Total", "Valor_Formatado", "Posição"])

    # Remove duplicidade por visita
    visitas = df.drop_duplicates(subset=["Cliente", "Data"])

    resumo = visitas.groupby("Cliente").agg(
        Qtd_Serviços=("Serviço", "count"),
        Qtd_Produtos=("Produto", lambda x: (x.notna() & (x != "")).sum()),
        Qtd_Atendimento=("Data", "count"),
        Qtd_Combo=("Tipo", lambda x: (x == "Combo").sum()),
        Qtd_Simples=("Tipo", lambda x: (x == "Simples").sum()),
        Valor_Total=("Valor", "sum")
    ).reset_index()

    resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    resumo = resumo.sort_values(by="Valor_Total", ascending=False).reset_index(drop=True)
    resumo["Posição"] = resumo.index + 1
    return resumo

resumo_geral = top_20_por(df_filtrado)

st.subheader("🥈 Top 20 Clientes - Geral")
st.dataframe(resumo_geral, use_container_width=True)

# Filtro dinâmico por nome
digito = st.text_input("🔍 Pesquisar cliente", placeholder="Digite um nome (ou parte dele)").strip().lower()
if digito:
    resumo_geral = resumo_geral[resumo_geral["Cliente"].apply(lambda x: digito in unidecode(x.lower()))]
    st.dataframe(resumo_geral, use_container_width=True)

# Gráfico dos 5 primeiros
st.subheader("📊 Top 5 por Receita")
top5 = resumo_geral.head(5)
fig = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado", color="Cliente")
fig.update_layout(showlegend=False, yaxis_title="Receita (R$)", xaxis_title="Cliente")
st.plotly_chart(fig, use_container_width=True)

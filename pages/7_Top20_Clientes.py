import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("🏆 Top 20 Clientes")

# ===== Carregar dados da planilha =====
@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = df.columns.str.strip()
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# ========== Filtros ==========
st.sidebar.markdown("📅 **Filtrar por ano**")
ano_selecionado = st.sidebar.selectbox("Ano", sorted(df["Ano"].dropna().unique(), reverse=True), index=0)

st.sidebar.markdown("🧑‍🔧 **Filtrar por funcionário**")
funcionarios_unicos = sorted(df["Funcionário"].dropna().unique())
funcionarios = st.sidebar.multiselect("Funcionários", funcionarios_unicos, default=funcionarios_unicos)

# ======= Filtra dados =========
df_visitas = df.copy()
df_visitas = df_visitas[df_visitas["Ano"] == ano_selecionado]
df_visitas = df_visitas[df_visitas["Funcionário"].isin(funcionarios)]

# Remove nomes genéricos
nomes_remover = ["boliviano", "brasileiro", "menino"]
normalizar = lambda nome: unidecode(str(nome).lower().strip())
df_visitas = df_visitas[~df_visitas["Cliente"].apply(lambda x: normalizar(x) in nomes_remover)]

# Agrupamento por cliente
def top_20_por(df):
    atendimentos = df.drop_duplicates(subset=["Cliente", "Data"])
    resumo = atendimentos.groupby("Cliente").agg(
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

resumo_geral = top_20_por(df_visitas)

# ===== Campo de busca dinâmica =====
busca = st.text_input("🔍 Pesquisar cliente", placeholder="Digite um nome (ou parte dele)").strip().lower()
if busca:
    resumo_geral = resumo_geral[resumo_geral["Cliente"].str.lower().str.contains(busca)]

# ===== Exibição da Tabela =====
st.subheader("🥈 Top 20 Clientes - Geral")
filtro_func = ", ".join(funcionarios) if funcionarios else "Todos"
st.markdown(f"**{filtro_func}**")

colunas_exibir = [
    "Posição", "Cliente", "Qtd_Serviços", "Qtd_Produtos", "Qtd_Atendimento",
    "Qtd_Combo", "Qtd_Simples", "Valor_Total", "Valor_Formatado"
]
st.dataframe(resumo_geral[colunas_exibir], use_container_width=True)

# ===== Gráfico Top 5 Clientes por Receita =====
st.subheader("📊 Top 5 Clientes por Receita")
top5 = resumo_geral.head(5)
fig = px.bar(
    top5,
    x="Cliente",
    y="Valor_Total",
    text="Valor_Formatado",
    labels={"Valor_Total": "Receita Total (R$)"},
    title="Top 5 Clientes por Faturamento",
)
fig.update_traces(marker_color="royalblue", textposition="outside")
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

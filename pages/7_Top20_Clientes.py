import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🏆 Top 20 Clientes")

@st.cache_data

def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# Filtros
st.sidebar.markdown("### 📅 Filtros")
anos = sorted(df["Ano"].dropna().unique())
ano_sel = st.sidebar.selectbox("Ano", anos, index=len(anos)-1)
meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
mes_map = {i+1: m for i, m in enumerate(meses)}
mes_inv = {v: k for k, v in mes_map.items()}
mes_sel = st.sidebar.multiselect("Mês (opcional)", meses, default=meses)
mes_numeros = [mes_inv[m] for m in mes_sel]

# Filtro de funcionário
todos_func = sorted(df["Funcionário"].dropna().unique())
func_sel = st.sidebar.multiselect("Funcionário (opcional)", todos_func, default=todos_func)

# Remove nomes genéricos
nomes_invalidos = ["boliviano", "brasileiro", "menino"]
normaliza = lambda x: ''.join(e for e in str(x).lower() if e.isalnum())
df = df[~df["Cliente"].apply(lambda x: normaliza(x) in [normaliza(n) for n in nomes_invalidos])]

# Aplica filtros
df_filtrado = df[(df["Ano"] == ano_sel) & (df["Mês"].isin(mes_numeros)) & (df["Funcionário"].isin(func_sel))]

# Função de agregação

def top_20_por(df_base, funcionario=None):
    if funcionario:
        df_base = df_base[df_base["Funcionário"] == funcionario]

    atendimentos = df_base.drop_duplicates(subset=["Cliente", "Data"])
   resumo = atendimentos.groupby("Cliente").agg({
    "Serviço": "count",
    "Produto?": lambda x: (x == "Sim").sum(),
    "Valor": "sum",
    "Combo": lambda x: x.notna().sum(),
    "Simples?": lambda x: (x == "Sim").sum(),
}).rename(columns={
    "Serviço": "Qtd_Serviços",
    "Produto?": "Qtd_Produtos",
    "Valor": "Valor_Total",
    "Combo": "Qtd_Combo",
    "Simples?": "Qtd_Simples"
}).reset_index()


    resumo = resumo.sort_values("Valor_Total", ascending=False).head(20)
    resumo["Valor Total"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    return resumo.drop(columns=["Valor_Total"])

# Pesquisa dinâmica
st.sidebar.markdown("### 🔎 Pesquisar Cliente")
filtro_nome = st.sidebar.text_input("Filtrar por nome")

# Mostra Top 20 Geral
st.subheader("🏅 Top 20 Clientes - Geral")
resumo_geral = top_20_por(df_filtrado)
if filtro_nome:
    resumo_geral = resumo_geral[resumo_geral["Cliente"].str.contains(filtro_nome, case=False, na=False)]
st.dataframe(resumo_geral, use_container_width=True)

# Gráfico Geral
fig1 = px.bar(resumo_geral, x="Cliente", y="Valor Total", title="Top 20 Clientes - Geral", text_auto=True)
fig1.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig1, use_container_width=True)

# Top 20 por JPaulo
st.subheader("🧔 Top 20 Clientes - JPaulo")
resumo_jpaulo = top_20_por(df_filtrado, funcionario="JPaulo")
if filtro_nome:
    resumo_jpaulo = resumo_jpaulo[resumo_jpaulo["Cliente"].str.contains(filtro_nome, case=False, na=False)]
st.dataframe(resumo_jpaulo, use_container_width=True)
fig2 = px.bar(resumo_jpaulo, x="Cliente", y="Valor Total", title="Top 20 - JPaulo", text_auto=True)
fig2.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig2, use_container_width=True)

# Top 20 por Vinicius
st.subheader("✂️ Top 20 Clientes - Vinicius")
resumo_vinicius = top_20_por(df_filtrado, funcionario="Vinicius")
if filtro_nome:
    resumo_vinicius = resumo_vinicius[resumo_vinicius["Cliente"].str.contains(filtro_nome, case=False, na=False)]
st.dataframe(resumo_vinicius, use_container_width=True)
fig3 = px.bar(resumo_vinicius, x="Cliente", y="Valor Total", title="Top 20 - Vinicius", text_auto=True)
fig3.update_layout(xaxis_tickangle=-45)
st.plotly_chart(fig3, use_container_width=True)

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("💈 Produtos vs Serviços - Análise Financeira")

@st.cache_data
def carregar_dados():
    url_base = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv"
    df_base = pd.read_csv(url_base + "&sheet=Base%20de%20Dados")
    df_despesas = pd.read_csv(url_base + "&sheet=Despesas")
    df_base.columns = df_base.columns.str.strip()
    df_despesas.columns = df_despesas.columns.str.strip()
    df_base["Data"] = pd.to_datetime(df_base["Data"], errors='coerce')
    df_despesas["Data"] = pd.to_datetime(df_despesas["Data"], errors='coerce')
    return df_base, df_despesas

df_base, df_despesas = carregar_dados()

def converter_para_float(valor):
    if isinstance(valor, str):
        valor = valor.replace("R$", "").replace(".", "").replace(",", ".").strip()
    try:
        return float(valor)
    except:
        return 0.0

# === FILTROS ===
df_base["Ano"] = df_base["Data"].dt.year
df_despesas["Ano"] = df_despesas["Data"].dt.year
anos_disponiveis = sorted(df_base["Ano"].dropna().unique())
ano_selecionado = st.selectbox("🗓️ Ano", anos_disponiveis, index=len(anos_disponiveis)-1)

meses_dict = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
meses_disponiveis = sorted(df_base[df_base["Ano"] == ano_selecionado]["Data"].dt.month.unique())
mes_selecionado = st.selectbox("📅 Mês (opcional)", options=["Todos"] + [meses_dict[m] for m in meses_disponiveis])

# === FILTRAR DADOS ===
df_base["Valor"] = df_base["Valor"].apply(converter_para_float)
df_despesas["Valor"] = df_despesas["Valor"].apply(converter_para_float)

palavras_produto = ["pomada", "gel", "cera", "pó", "barbeador", "produto"]
df_produtos = df_base[
    (df_base["Ano"] == ano_selecionado) &
    (df_base["Serviço"].str.lower().str.contains('|'.join(palavras_produto), na=False))
].copy()

df_servicos = df_base[
    (df_base["Ano"] == ano_selecionado) &
    (df_base["Tipo"] == "Serviço")
].copy()

if mes_selecionado != "Todos":
    mes_num = [k for k, v in meses_dict.items() if v == mes_selecionado][0]
    df_produtos = df_produtos[df_produtos["Data"].dt.month == mes_num]
    df_servicos = df_servicos[df_servicos["Data"].dt.month == mes_num]
    df_despesas = df_despesas[df_despesas["Data"].dt.month == mes_num]

# === PRODUTOS ===
st.header("🧴 Produtos")
df_desp_prod = df_despesas[df_despesas["Descrição"].str.lower().str.contains('|'.join(palavras_produto), na=False)]
receita_prod = df_produtos["Valor"].sum()
custo_prod = df_desp_prod["Valor"].sum()
lucro_prod = receita_prod - custo_prod
margem_prod = (lucro_prod / receita_prod * 100) if receita_prod > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Receita", f"R$ {receita_prod:,.2f}")
col2.metric("Custo", f"R$ {custo_prod:,.2f}")
col3.metric("Lucro", f"R$ {lucro_prod:,.2f}")
col4.metric("Margem", f"{margem_prod:.1f}%")

df_mensal_prod = df_produtos.groupby(df_produtos["Data"].dt.to_period("M"))["Valor"].sum().reset_index()
df_mensal_prod["Data"] = df_mensal_prod["Data"].dt.to_timestamp()
df_mensal_prod = df_mensal_prod.rename(columns={"Valor": "Receita"})
df_mensal_prod["Custo"] = df_desp_prod.groupby(df_desp_prod["Data"].dt.to_period("M"))["Valor"].sum().reset_index(drop=True)
df_mensal_prod["Custo"] = pd.to_numeric(df_mensal_prod["Custo"], errors="coerce").fillna(0)
df_mensal_prod["Lucro"] = df_mensal_prod["Receita"] - df_mensal_prod["Custo"]

fig = px.bar(df_mensal_prod, x="Data", y=["Receita", "Custo", "Lucro"], barmode="group", title="📊 Produtos: Receita x Custo x Lucro")
st.plotly_chart(fig, use_container_width=True)

# === SERVIÇOS ===
st.header("✂️ Serviços")
receita_serv = df_servicos["Valor"].sum()
lucro_serv = receita_serv
margem_serv = 100 if receita_serv > 0 else 0

col5, col6, col7 = st.columns(3)
col5.metric("Receita", f"R$ {receita_serv:,.2f}")
col6.metric("Lucro", f"R$ {lucro_serv:,.2f}")
col7.metric("Margem", f"{margem_serv:.1f}%")

df_mensal_serv = df_servicos.groupby(df_servicos["Data"].dt.to_period("M"))["Valor"].sum().reset_index()
df_mensal_serv["Data"] = df_mensal_serv["Data"].dt.to_timestamp()
df_mensal_serv = df_mensal_serv.rename(columns={"Valor": "Receita"})
df_mensal_serv["Lucro"] = df_mensal_serv["Receita"]

fig2 = px.bar(df_mensal_serv, x="Data", y=["Receita", "Lucro"], barmode="group", title="📈 Serviços: Receita x Lucro")
st.plotly_chart(fig2, use_container_width=True)

# === COMPARATIVO FINAL ===
st.subheader("📌 Comparativo de Receita e Lucro")
df_comp = pd.DataFrame({
    "Categoria": ["Produtos", "Serviços"],
    "Receita": [receita_prod, receita_serv],
    "Lucro": [lucro_prod, lucro_serv]
})
fig3 = px.bar(df_comp, x="Categoria", y=["Receita", "Lucro"], barmode="group", title="📊 Comparativo: Produtos vs Serviços")
st.plotly_chart(fig3, use_container_width=True)

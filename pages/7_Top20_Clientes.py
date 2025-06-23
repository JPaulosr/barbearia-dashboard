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
    df['Data'] = pd.to_datetime(df['Data'], errors='coerce')
    df['Ano'] = df['Data'].dt.year
    df['Mês'] = df['Data'].dt.month
    df = df[df['Cliente'].notna()]  # Remove clientes nulos
    return df

df = carregar_dados()

# Corrige nomes de clientes genéricos
nomes_invalidos = ["boliviano", "menino", "brasileiro"]
normalizar = lambda s: unidecode(str(s).lower().strip())
df = df[~df["Cliente"].apply(lambda x: normalizar(x) in nomes_invalidos)]

# === Filtros ===
ano_sel = st.selectbox("📅 Filtrar por ano", sorted(df["Ano"].dropna().unique(), reverse=True))
func_opcoes = df["Funcionário"].dropna().unique().tolist()
func_sel = st.multiselect("🧍 Filtrar por funcionário", func_opcoes, default=func_opcoes)

# Filtra base
df_filtrado = df[(df["Ano"] == ano_sel) & (df["Funcionário"].isin(func_sel))].copy()

if df_filtrado.empty:
    st.warning("⚠️ Nenhum dado encontrado para os filtros selecionados.")
    st.stop()

# === Função de agrupamento ===
def top_20_por(atendimentos):
    df_visitas = atendimentos.drop_duplicates(subset=["Cliente", "Data"])
    resumo = df_visitas.groupby("Cliente").agg(
        Qtd_Serviços=("Serviço", "count"),
        Qtd_Produtos=("Tipo", lambda x: (x == "Produto").sum()),
        Qtd_Atendimento=("Cliente", "count"),
        Qtd_Combo=("Combo", lambda x: (x.notna() & (x != "")).sum()),
        Qtd_Simples=("Combo", lambda x: (x.isna() | (x == "")).sum()),
        Valor_Total=("Valor", "sum")
    ).reset_index()

    resumo = resumo.sort_values(by="Valor_Total", ascending=False).head(20)
    resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    return resumo

# === Resultado geral ===
st.subheader("🥈 Top 20 Clientes - Geral")
resumo_geral = top_20_por(df_filtrado)
cliente_sel = st.selectbox("", resumo_geral["Cliente"].tolist())
st.dataframe(resumo_geral, use_container_width=True)

# === Pesquisa dinâmica ===
st.subheader("🔍 Pesquisar cliente")
pesquisa = st.text_input("Digite um nome (ou parte dele)").strip().lower()
if pesquisa:
    resultado = resumo_geral[resumo_geral["Cliente"].str.lower().str.contains(pesquisa)]
    st.dataframe(resultado, use_container_width=True)

# === Top 5 em Receita ===
st.subheader("📊 Top 5 por Receita")
if not resumo_geral.empty:
    top5 = resumo_geral.head(5)
    fig_top5 = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado",
                     labels={"Valor_Total": "Receita (R$)"})
    fig_top5.update_layout(template="plotly_dark", xaxis_title="Cliente", yaxis_title="Receita")
    st.plotly_chart(fig_top5, use_container_width=True)
else:
    st.info("ℹ️ Nenhum dado disponível para gerar o Top 5.")

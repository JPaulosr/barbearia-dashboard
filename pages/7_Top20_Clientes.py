import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(page_title="Top 20 Clientes", layout="wide")
st.title("🏆 Top 20 Clientes")

@st.cache_data

def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df = df[df["Cliente"].notna() & (df["Cliente"].str.len() > 1)]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# Remove nomes genéricos
def limpar_nome(nome):
    nome_norm = unidecode(str(nome)).lower().strip()
    if nome_norm in ["boliviano", "brasileiro", "menino"]:
        return None
    return nome

df["Cliente"] = df["Cliente"].apply(limpar_nome)
df = df[df["Cliente"].notna()]

# Ajuste visitas únicas (até 10/05 conta por linha, depois por Cliente + Data)
limite_data = pd.to_datetime("2025-05-10")
df_pre = df[df["Data"] <= limite_data].copy()
df_pos = df[df["Data"] > limite_data].copy()
df_pre["Chave"] = df_pre.index  # cada linha conta

# após 11/05 conta uma vez por cliente + data
df_pos["Chave"] = df_pos["Cliente"].astype(str) + "/" + df_pos["Data"].dt.strftime("%Y-%m-%d")

df_visitas = pd.concat([df_pre, df_pos], ignore_index=True)
df_visitas = df_visitas.drop_duplicates(subset=["Chave", "Funcionário"])

# Filtros de ano e funcionário
anos_disponiveis = sorted(df["Ano"].dropna().astype(int).unique())
ano = st.selectbox("📅 Filtrar por ano", anos_disponiveis)

todos_func = sorted(df["Funcionário"].dropna().unique())
func_selecionados = st.multiselect("🧍‍♂️ Filtrar por funcionário", todos_func, default=todos_func)

# Aplica filtro
df_filtrado = df[df["Ano"] == ano & df["Funcionário"].isin(func_selecionados)]
df_visitas = df_visitas[df_visitas["Ano"] == ano & df_visitas["Funcionário"].isin(func_selecionados)]

# Função para gerar ranking por total

def top_20_por(base):
    atendimentos = base.copy()

    resumo = atendimentos.groupby("Cliente").agg({
        "Serviço": "count",
        "Valor": "sum"
    }).rename(columns={
        "Serviço": "Qtd_Serviços",
        "Valor": "Valor_Total"
    })

    resumo_produtos = atendimentos[atendimentos["Tipo"] == "Produto"].groupby("Cliente").size()
    resumo["Qtd_Produtos"] = resumo_produtos

    resumo["Qtd_Produtos"] = resumo["Qtd_Produtos"].fillna(0).astype(int)

    visitas = df_visitas[df_visitas["Cliente"].isin(resumo.index)]
    resumo["Qtd_Atendimento"] = visitas.groupby("Cliente").size()

    resumo["Qtd_Combo"] = atendimentos[atendimentos["Combo"].notna()].groupby("Cliente").size()
    resumo["Qtd_Simples"] = resumo["Qtd_Serviços"] - resumo["Qtd_Combo"]

    resumo["Qtd_Combo"] = resumo["Qtd_Combo"].fillna(0).astype(int)
    resumo["Qtd_Simples"] = resumo["Qtd_Simples"].fillna(0).astype(int)

    resumo = resumo.fillna(0)
    resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    resumo = resumo.reset_index().sort_values("Valor_Total", ascending=False).head(20)
    resumo.insert(0, "Posição", range(1, len(resumo)+1))
    return resumo

# Tabs
aba = st.selectbox("🥈 Top 20 Clientes - Geral", ["Geral", "JPaulo", "Vinicius"])

if aba == "Geral":
    resumo_geral = top_20_por(df_filtrado)
    st.dataframe(resumo_geral, use_container_width=True)

elif aba == "JPaulo":
    resumo_jp = top_20_por(df_filtrado[df_filtrado["Funcionário"] == "JPaulo"])
    st.dataframe(resumo_jp, use_container_width=True)

elif aba == "Vinicius":
    resumo_vin = top_20_por(df_filtrado[df_filtrado["Funcionário"] == "Vinicius"])
    st.dataframe(resumo_vin, use_container_width=True)

# Pesquisa dinâmica por nome
st.markdown("### 🔍 Pesquisar cliente")
texto_busca = st.text_input("Digite um nome (ou parte dele)")

if texto_busca:
    nome_filtrado = resumo_geral[resumo_geral["Cliente"].str.contains(texto_busca, case=False)]
    st.dataframe(nome_filtrado, use_container_width=True)

# Gráfico dos Top 5
st.markdown("### 📊 Top 5 por Receita")
top5 = resumo_geral.head(5)
fig = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado", color="Cliente", title="Top 5 Clientes por Receita")
st.plotly_chart(fig, use_container_width=True)

# Comparativo
st.markdown("### ⚖ Comparar dois clientes")
opcoes = resumo_geral["Cliente"].tolist()
cliente1 = st.selectbox("Cliente 1", opcoes, index=0)
cliente2 = st.selectbox("Cliente 2", opcoes, index=1 if len(opcoes) > 1 else 0)

if cliente1 and cliente2:
    dados = resumo_geral[resumo_geral["Cliente"].isin([cliente1, cliente2])]
    fig2 = px.bar(dados, x="Cliente", y="Valor_Total", text="Valor_Formatado", color="Cliente", barmode="group")
    st.plotly_chart(fig2, use_container_width=True)

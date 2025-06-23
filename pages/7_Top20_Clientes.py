import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("🏆 Top 20 Clientes")

# === Upload do arquivo ===
uploaded_file = st.file_uploader("📂 Envie a planilha Modelo_Barbearia_Automatizado.xlsx", type=["xlsx"])

@st.cache_data
def carregar_dados(arquivo):
    # Lê a primeira aba automaticamente
    df = pd.read_excel(arquivo)
    df.columns = [str(col).strip() for col in df.columns]

    # Garante que colunas esperadas existam
    colunas_esperadas = {"Cliente", "Data", "Valor"}
    if not colunas_esperadas.issubset(df.columns):
        st.error("Erro: A planilha precisa conter as colunas: Cliente, Data e Valor.")
        return None

    df = df.dropna(subset=["Cliente", "Data", "Valor"])
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Cliente_Normalizado"] = df["Cliente"].apply(lambda x: unidecode(str(x)).lower().strip())
    return df

# Quando o usuário envia o arquivo
if uploaded_file:
    df = carregar_dados(uploaded_file)

    if df is not None:
        # === Filtros ===
        ano = st.selectbox("📅 Filtrar por ano", sorted(df["Ano"].dropna().unique(), reverse=True), index=0)
        func_opcoes = df["Funcionário"].dropna().unique().tolist()
        funcionarios = st.multiselect("🧍‍♂️ Filtrar por funcionário", func_opcoes, default=func_opcoes)

        # Aplica os filtros básicos
        df_filtrado = df[(df["Ano"] == ano) & (df["Funcionário"].isin(funcionarios))]

        # Remove nomes genéricos
        genericos = ["boliviano", "brasileiro", "menino"]
        def is_generico(nome):
            nome_n = unidecode(str(nome)).lower()
            return any(g in nome_n for g in genericos)

        df_filtrado = df_filtrado[~df_filtrado["Cliente"].apply(is_generico)]

        # Agrupa por cliente (visitas únicas)
        df_visitas = df_filtrado.drop_duplicates(subset=["Cliente", "Data"])

        # Função para gerar o top 20
        def top_20_por(df):
            resumo = df.groupby("Cliente").agg(
                Qtd_Serviços=("Serviço", "count") if "Serviço" in df.columns else ("Data", "count"),
                Qtd_Produtos=("Produto", "count") if "Produto" in df.columns else ("Data", "count"),
                Qtd_Atendimento=("Data", "nunique"),
                Qtd_Combo=("Combo", "sum") if "Combo" in df.columns else ("Data", "count"),
                Qtd_Simples=("Simples", "sum") if "Simples" in df.columns else ("Data", "count"),
                Valor_Total=("Valor", "sum")
            ).reset_index()
            resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(".", ","))
            resumo = resumo.sort_values("Valor_Total", ascending=False).reset_index(drop=True)
            resumo.index += 1
            resumo.insert(0, "Posição", resumo.index)
            return resumo

        resumo_geral = top_20_por(df_visitas)

        st.subheader("🥈 Top 20 Clientes - Geral")
        cliente_escolhido = st.selectbox("", resumo_geral["Cliente"].tolist())
        st.dataframe(resumo_geral, use_container_width=True)

        # === Filtro de busca dinâmica ===
        st.subheader("🔍 Pesquisar cliente")
        texto_busca = st.text_input("Digite um nome (ou parte dele)")

        if texto_busca:
            termo = unidecode(texto_busca).lower()
            filtrado = resumo_geral[resumo_geral["Cliente"].apply(lambda x: termo in unidecode(str(x)).lower())]
            st.dataframe(filtrado, use_container_width=True)

        # === Top 5 em gráfico ===
        st.subheader("📊 Top 5 por Receita")
        top5 = resumo_geral.head(5)
        fig = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado", labels={"Valor_Total": "Valor (R$)"})
        fig.update_layout(yaxis_title="Receita Total", xaxis_title="Cliente")
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.warning("❌ Erro ao carregar os dados. Verifique o conteúdo da planilha.")
else:
    st.warning("⚠️ Envie o arquivo Excel para visualizar o ranking.")

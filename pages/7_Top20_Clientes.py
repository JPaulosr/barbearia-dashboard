import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode
import re

st.set_page_config(layout="wide")
st.title("🏆 Top 20 Clientes")

@st.cache_data
def carregar_dados(caminho_arquivo):
    xls = pd.ExcelFile(caminho_arquivo)
    st.write("🗂️ Abas disponíveis:", xls.sheet_names)  # debug opcional

    df = pd.read_excel(xls, sheet_name="Base de Dados", header=0)
    df.columns = [str(col).strip() for col in df.columns]
    st.write("📋 Colunas encontradas:", df.columns.tolist())  # debug opcional

    # Mapeamento flexível
    mapa_colunas = {}
    for col in df.columns:
        nome = unidecode(col.lower().strip())
        if "cliente" in nome:
            mapa_colunas["Cliente"] = col
        elif "data" in nome:
            mapa_colunas["Data"] = col
        elif "valor" in nome:
            mapa_colunas["Valor"] = col

    if not {"Cliente", "Data", "Valor"}.issubset(mapa_colunas):
        st.error("❌ A planilha precisa conter colunas parecidas com: Cliente, Data e Valor.")
        return None

    df = df.rename(columns={
        mapa_colunas["Cliente"]: "Cliente",
        mapa_colunas["Data"]: "Data",
        mapa_colunas["Valor"]: "Valor"
    })

    df = df.dropna(subset=["Cliente", "Data", "Valor"])
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")

    # ✅ CORREÇÃO DA CONVERSÃO DE VALOR
    def limpar_valor(valor):
        if isinstance(valor, str):
            valor = re.sub(r"[^\d,]", "", valor)  # Remove tudo que não é número ou vírgula
            valor = valor.replace(",", ".")
        return pd.to_numeric(valor, errors="coerce")

    df["Valor"] = df["Valor"].apply(limpar_valor)

    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Cliente_Normalizado"] = df["Cliente"].apply(lambda x: unidecode(str(x)).lower().strip())

    return df

# Leitura do arquivo fixo
df = carregar_dados("Modelo_Barbearia_Automatizado (10).xlsx")

if df is not None:
    # Filtro por ano
    ano = st.selectbox("📅 Filtrar por ano", sorted(df["Ano"].dropna().unique(), reverse=True), index=0)

    # Filtro por funcionário
    funcionarios = []
    if "Funcionário" in df.columns:
        func_opcoes = df["Funcionário"].dropna().unique().tolist()
        funcionarios = st.multiselect("🧍‍♂️ Filtrar por funcionário", func_opcoes, default=func_opcoes)

    df_filtrado = df[df["Ano"] == ano]
    if funcionarios:
        df_filtrado = df_filtrado[df_filtrado["Funcionário"].isin(funcionarios)]

    # Remove nomes genéricos
    nomes_ignorar = ["boliviano", "brasileiro", "menino"]
    df_filtrado = df_filtrado[~df_filtrado["Cliente"].apply(
        lambda nome: any(g in unidecode(str(nome)).lower() for g in nomes_ignorar)
    )]

    # Agrupa por atendimento único por cliente + data
    df_visitas = df_filtrado.drop_duplicates(subset=["Cliente", "Data"])

    def top_20_por(df):
        resumo = df.groupby("Cliente").agg(
            Qtd_Atendimentos=("Data", "nunique"),
            Valor_Total=("Valor", "sum")
        ).reset_index()
        resumo["Valor_Formatado"] = resumo["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(".", ","))
        resumo = resumo.sort_values("Valor_Total", ascending=False).reset_index(drop=True)
        resumo.index += 1
        resumo.insert(0, "Posição", resumo.index)
        return resumo

    resumo_geral = top_20_por(df_visitas)

    st.subheader("🥇 Top 20 Clientes - Geral")
    st.dataframe(resumo_geral, use_container_width=True)

    # Busca dinâmica
    st.subheader("🔍 Pesquisar cliente")
    termo = st.text_input("Digite um nome (ou parte dele)").strip().lower()
    if termo:
        termo_normalizado = unidecode(termo)
        filtrado = resumo_geral[resumo_geral["Cliente"].apply(
            lambda nome: termo_normalizado in unidecode(str(nome)).lower()
        )]
        st.dataframe(filtrado, use_container_width=True)

    # Gráfico Top 5
    st.subheader("📊 Top 5 por Receita")
    top5 = resumo_geral.head(5)
    fig = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado", labels={"Valor_Total": "Valor (R$)"})
    fig.update_layout(yaxis_title="Receita Total", xaxis_title="Cliente")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ Não foi possível carregar os dados. Verifique o conteúdo da planilha.")

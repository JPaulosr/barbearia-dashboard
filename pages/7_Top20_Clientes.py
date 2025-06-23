import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode

st.set_page_config(layout="wide")
st.title("🏆 Top 20 Clientes")

uploaded_file = st.file_uploader("📂 Envie a planilha Modelo_Barbearia_Automatizado.xlsx", type=["xlsx"])

@st.cache_data
def carregar_dados(arquivo):
    df = pd.read_excel(arquivo)
    df.columns = [str(col).strip() for col in df.columns]
    
    # Mostra colunas reais para debug
    st.write("🧪 Colunas encontradas:", df.columns.tolist())

    # Tenta mapear colunas mesmo com nomes variados
    mapa_colunas = {}
    for col in df.columns:
        col_n = unidecode(col.lower().strip())
        if "cliente" in col_n:
            mapa_colunas["Cliente"] = col
        elif "data" in col_n:
            mapa_colunas["Data"] = col
        elif "valor" in col_n:
            mapa_colunas["Valor"] = col

    if not {"Cliente", "Data", "Valor"}.issubset(mapa_colunas):
        st.error("❌ A planilha precisa conter colunas com nomes (ou parecidos com): Cliente, Data, Valor.")
        return None

    # Renomeia para padronizar
    df = df.rename(columns={
        mapa_colunas["Cliente"]: "Cliente",
        mapa_colunas["Data"]: "Data",
        mapa_colunas["Valor"]: "Valor"
    })

    df = df.dropna(subset=["Cliente", "Data", "Valor"])
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Cliente_Normalizado"] = df["Cliente"].apply(lambda x: unidecode(str(x)).lower().strip())
    return df

if uploaded_file:
    df = carregar_dados(uploaded_file)

    if df is not None:
        # === Filtros ===
        ano = st.selectbox("📅 Filtrar por ano", sorted(df["Ano"].dropna().unique(), reverse=True), index=0)
        func_opcoes = df["Funcionário"].dropna().unique().tolist() if "Funcionário" in df.columns else []
        funcionarios = st.multiselect("🧍‍♂️ Filtrar por funcionário", func_opcoes, default=func_opcoes) if func_opcoes else []

        # Aplica filtros
        df_filtrado = df[df["Ano"] == ano]
        if funcionarios:
            df_filtrado = df_filtrado[df_filtrado["Funcionário"].isin(funcionarios)]

        # Remove nomes genéricos
        genericos = ["boliviano", "brasileiro", "menino"]
        def is_generico(nome):
            nome_n = unidecode(str(nome)).lower()
            return any(g in nome_n for g in genericos)
        df_filtrado = df_filtrado[~df_filtrado["Cliente"].apply(is_generico)]

        # Agrupa por cliente e dia
        df_visitas = df_filtrado.drop_duplicates(subset=["Cliente", "Data"])

        # Top 20
        def top_20_por(df):
            resumo = df.groupby("Cliente").agg(
                Qtd_Atendimento=("Data", "nunique"),
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
        texto_busca = st.text_input("Digite um nome (ou parte dele)")
        if texto_busca:
            termo = unidecode(texto_busca).lower()
            filtrado = resumo_geral[resumo_geral["Cliente"].apply(lambda x: termo in unidecode(str(x)).lower())]
            st.dataframe(filtrado, use_container_width=True)

        # Gráfico Top 5
        st.subheader("📊 Top 5 por Receita")
        top5 = resumo_geral.head(5)
        fig = px.bar(top5, x="Cliente", y="Valor_Total", text="Valor_Formatado", labels={"Valor_Total": "Valor (R$)"})
        fig.update_layout(yaxis_title="Receita Total", xaxis_title="Cliente")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("⚠️ Erro ao carregar os dados. Verifique a planilha.")
else:
    st.warning("📎 Envie o arquivo Excel para visualizar o ranking.")

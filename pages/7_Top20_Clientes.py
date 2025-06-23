import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Top 20 Clientes - Geral", layout="wide")
st.title("🏆 Top 20 Clientes - Geral")

uploaded_file = st.file_uploader("\n\n📁 Envie a planilha Modelo_Barbearia_Automatizado.xlsx", type="xlsx")

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file, sheet_name="Base de Dados")
        df.columns = [str(col).strip() for col in df.columns]

        obrigatorias = {"Cliente", "Data", "Valor", "Funcionário"}
        if not obrigatorias.issubset(df.columns):
            st.error("A planilha precisa conter as colunas: Cliente, Data, Valor e Funcionário.")
            st.stop()

        # Limpa nomes genéricos
        nomes_excluir = ["boliviano", "brasileiro", "menino"]
        df = df[~df["Cliente"].str.lower().str.contains('|'.join(nomes_excluir))]

        # Converte data e valores
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
        df = df.dropna(subset=["Data"])
        df["Ano"] = df["Data"].dt.year
        df["Mês"] = df["Data"].dt.strftime("%Y-%m")

        # Trata valores
        df["Valor"] = df["Valor"].astype(str).str.replace("R$", "").str.replace(",", ".").str.strip()
        df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")
        df = df.dropna(subset=["Valor"])

        # Filtros
        ano_selecionado = st.selectbox("\U0001F4C5 Filtrar por ano", sorted(df["Ano"].unique(), reverse=True))
        funcionarios = st.multiselect("\U0001F464 Filtrar por funcionário", df["Funcionário"].unique(), default=list(df["Funcionário"].unique()))

        df_filtrado = df[(df["Ano"] == ano_selecionado) & (df["Funcionário"].isin(funcionarios))]

        # Contagem de atendimento único (Cliente + Data)
        atendimentos = df_filtrado.groupby(["Cliente", "Data"]).agg({"Valor": "sum"}).reset_index()
        ranking = atendimentos.groupby("Cliente").agg({
            "Valor": "sum",
            "Data": "nunique"
        }).rename(columns={"Valor": "Valor_Total", "Data": "Qtd_Atendimentos"}).reset_index()

        ranking = ranking.sort_values("Valor_Total", ascending=False).head(20)
        ranking["Posição"] = range(1, len(ranking) + 1)
        ranking["Valor_Formatado"] = ranking["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(".", ","))

        # Cria coluna com valor por mês
        colunas_meses = df_filtrado["Mês"].unique()
        for mes in sorted(colunas_meses):
            valores_mes = df_filtrado[df_filtrado["Mês"] == mes].groupby("Cliente")["Valor"].sum()
            ranking[mes] = ranking["Cliente"].map(valores_mes).fillna(0).astype(float)

        # Organiza colunas
        colunas_ordem = ["Posição", "Cliente", "Qtd_Atendimentos", "Valor_Total", "Valor_Formatado"] + sorted(colunas_meses)
        ranking = ranking[colunas_ordem]

        # Exibe tabela
        st.dataframe(ranking, use_container_width=True)

        # Gráfico
        st.markdown("\n### 📊 Top 10 Clientes por Receita")
        fig = px.bar(ranking.head(10), x="Cliente", y="Valor_Total", text_auto=True)
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")

else:
    st.info("\U0001F4C1 Envie o arquivo Excel para visualizar o ranking.")

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Top 20 Clientes - Geral", layout="wide")
st.title("🏆 Top 20 Clientes - Geral")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]

    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])

    df["Ano"] = df["Data"].dt.year
    df["Mes"] = df["Data"].dt.strftime("%Y-%m")

    # Limpa valores monetários e converte para float
    df["Valor"] = df["Valor"].astype(str).str.replace("R$", "", regex=False).str.replace(",", ".").str.strip()
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

    # Remove nomes genéricos
    nomes_invalidos = ["boliviano", "brasileiro", "menino"]
    def nome_valido(nome):
        if not isinstance(nome, str): return False
        nome_limpo = nome.strip().lower()
        return not any(generico in nome_limpo for generico in nomes_invalidos)

    df = df[df["Cliente"].apply(nome_valido)]

    return df

df = carregar_dados()

st.markdown("### Envie a planilha Modelo_Barbearia_Automatizado.xlsx")

if df.empty:
    st.warning("Nenhum dado encontrado.")
    st.stop()

def agrupar_top20(df):
    df_atendimentos = df.drop_duplicates(subset=["Cliente", "Data"])

    # Cria flags para Produto, Combo e Simples
    df["is_produto"] = df["Tipo"].apply(lambda x: x == "Produto")
    df["is_combo"] = df["Combo"].notna()
    df["is_simples"] = df["Combo"].isna()

    agrupado = df.groupby("Cliente").agg(
        Qtd_Servicos=("Serviço", "count"),
        Qtd_Produtos=("is_produto", "sum"),
        Qtd_Combo=("is_combo", "sum"),
        Qtd_Simples=("is_simples", "sum"),
        Valor_Total=("Valor", "sum")
    ).reset_index()

    # Atendimentos únicos (Cliente + Data)
    atendimentos = df_atendimentos.groupby("Cliente").size().reset_index(name="Qtd_Atendimentos")
    agrupado = pd.merge(agrupado, atendimentos, on="Cliente", how="left")

    agrupado = agrupado.sort_values(by="Valor_Total", ascending=False).head(20)
    agrupado.insert(0, "Posição", range(1, len(agrupado)+1))

    # Receita por mês
    receita_mes = df.groupby(["Cliente", "Mes"]).agg(Valor_Mensal=("Valor", "sum")).reset_index()
    receita_mes_pivot = receita_mes.pivot(index="Cliente", columns="Mes", values="Valor_Mensal").fillna(0)

    resultado = pd.merge(agrupado, receita_mes_pivot, on="Cliente", how="left")
    resultado["Valor_Total_Formatado"] = resultado["Valor_Total"].apply(lambda x: f"R$ {x:,.2f}".replace(".", "v").replace(",", ".").replace("v", ","))

    return resultado

top20 = agrupar_top20(df)

# Mostra a tabela
st.dataframe(top20.drop(columns=["Valor_Total"]), use_container_width=True)

# Gráfico de barras
fig = px.bar(top20, x="Cliente", y="Valor_Total", title="Top 20 Clientes por Receita", text_auto=True)
st.plotly_chart(fig, use_container_width=True)

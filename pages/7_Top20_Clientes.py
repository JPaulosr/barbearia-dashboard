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
    df["Mes"] = df["Data"].dt.to_period("M").astype(str)

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

# Agrupamento por Cliente + Data (para contar atendimentos únicos por dia)
df_atendimentos = df.drop_duplicates(subset=["Cliente", "Data"])

# Filtro de pesquisa dinâmica
cliente_busca = st.text_input("🔍 Filtrar por nome do cliente")
if cliente_busca:
    df = df[df["Cliente"].str.contains(cliente_busca, case=False, na=False)]
    df_atendimentos = df_atendimentos[df_atendimentos["Cliente"].str.contains(cliente_busca, case=False, na=False)]

def agrupar_top20(df, df_atendimentos):
    # Atendimentos por mês baseado em Cliente + Data
    atendimentos_mes = df_atendimentos.groupby(["Cliente", "Mes"]).size().reset_index(name="Atendimentos")
    atendimentos_pivot = atendimentos_mes.pivot(index="Cliente", columns="Mes", values="Atendimentos").fillna(0).reset_index()

    # Conta atendimentos únicos por cliente (Cliente + Data)
    atendimentos_totais = df_atendimentos.groupby("Cliente").size().reset_index(name="Qtd_Atendimentos")

    # Define Combo ou Simples baseado em Cliente + Data
    tipo_atendimento = (
        df.groupby(["Cliente", "Data"])
        .size()
        .reset_index(name="Qtd_Servicos")
        .assign(
            Tipo=lambda x: x["Qtd_Servicos"].apply(lambda q: "Combo" if q > 1 else "Simples")
        )
    )

    # Conta Combos e Simples por cliente
    resumo_combo = tipo_atendimento.groupby(["Cliente", "Tipo"]).size().unstack(fill_value=0).reset_index()
    resumo_combo.columns.name = None
    if "Combo" not in resumo_combo.columns:
        resumo_combo["Combo"] = 0
    if "Simples" not in resumo_combo.columns:
        resumo_combo["Simples"] = 0

    agrupado = df.groupby("Cliente").agg(
        Qtd_Servicos=("Serviço", "count"),
        Qtd_Produtos=("Tipo", lambda x: (x == "Produto").sum()),
        Valor_Total=("Valor", "sum")
    ).reset_index()

    # Junta tudo
    resultado = (
        agrupado
        .merge(atendimentos_totais, on="Cliente", how="left")
        .merge(resumo_combo[["Cliente", "Combo", "Simples"]], on="Cliente", how="left")
        .merge(atendimentos_pivot, on="Cliente", how="left")
    )

    resultado.rename(columns={"Combo": "Qtd_Combo", "Simples": "Qtd_Simples"}, inplace=True)

    resultado["Valor_Total_Formatado"] = resultado["Valor_Total"].apply(
        lambda x: f"R$ {x:,.2f}".replace(".", "v").replace(",", ".").replace("v", ",")
    )
    resultado = resultado.sort_values(by="Valor_Total", ascending=False).head(20)
    resultado.insert(0, "Posição", range(1, len(resultado) + 1))

    return resultado

top20 = agrupar_top20(df, df_atendimentos)

# Mostra a tabela
st.dataframe(top20.drop(columns=["Valor_Total"]), use_container_width=True)

# Gráfico de barras
fig = px.bar(top20, x="Cliente", y="Valor_Total", title="Top 20 Clientes por Receita", text_auto=True)
st.plotly_chart(fig, use_container_width=True)

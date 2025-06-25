import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧑‍🤝‍🧑 Comparativo entre Funcionários")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mês"] = df["Data"].dt.month
    df["Mês_Nome"] = df["Data"].dt.month.map({
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    })
    nomes_ignorar = ["boliviano", "brasileiro", "menino", "menino boliviano"]
    df = df[~df["Cliente"].str.lower().isin(nomes_ignorar)]
    return df

df = carregar_dados()

# Filtro por ano
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("📅 Selecione o Ano", anos, index=0)
df_filtrado = df[df["Ano"] == ano]

# Receita por funcionário por mês
st.subheader("📈 Receita Mensal por Funcionário")
receita_mensal = df_filtrado.groupby(["Funcionário", "Mês", "Mês_Nome"])["Valor"].sum().reset_index()
receita_mensal = receita_mensal.sort_values("Mês")
fig = px.bar(
    receita_mensal,
    x="Mês_Nome",
    y="Valor",
    color="Funcionário",
    barmode="group",
    text_auto=True,
    category_orders={"Mês_Nome": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]}
)
st.plotly_chart(fig, use_container_width=True)

# Total de atendimentos
st.subheader("📋 Total de Atendimentos por Funcionário")
atendimentos = df_filtrado.groupby("Funcionário")["Data"].count().reset_index().rename(columns={"Data": "Qtd Atendimentos"})
st.dataframe(atendimentos, use_container_width=True)

# Combo vs Simples
st.subheader("🔀 Distribuição: Combo vs Simples")
agrupado = df_filtrado.groupby(["Cliente", "Data", "Funcionário"]).agg(Qtd_Serviços=("Serviço", "count")).reset_index()
agrupado["Combo"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
agrupado["Simples"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)
combo_simples = agrupado.groupby("Funcionário").agg(
    Total_Atendimentos=("Data", "count"),
    Qtd_Combo=("Combo", "sum"),
    Qtd_Simples=("Simples", "sum")
).reset_index()
st.dataframe(combo_simples, use_container_width=True)

# Receita total no ano
st.subheader("💰 Receita Total no Ano por Funcionário")
receita_total = df_filtrado.groupby("Funcionário")["Valor"].sum().reset_index()
receita_total["Valor Formatado"] = receita_total["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(receita_total[["Funcionário", "Valor Formatado"]], use_container_width=True)

# Diferença de receita
st.subheader("📊 Diferença de Receita (R$)")
valores = receita_total.set_index("Funcionário")["Valor"].to_dict()
if "JPaulo" in valores and "Vinicius" in valores:
    dif = valores["JPaulo"] - valores["Vinicius"]
    label = "JPaulo ganhou mais" if dif > 0 else "Vinicius ganhou mais"
    st.metric(label=label, value=f"R$ {abs(dif):,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# Receita total por ano
st.subheader("📅 Receita Total por Funcionário em Cada Ano")
por_ano = df.groupby(["Ano", "Funcionário"])["Valor"].sum().unstack().fillna(0).astype(int)
por_ano = por_ano.sort_index(ascending=False)
por_ano_formatado = por_ano.applymap(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(por_ano_formatado, use_container_width=True)

# Top 10 clientes por receita
st.subheader("🏅 Top 10 Clientes por Receita (por Funcionário)")
clientes_por_func = df_filtrado.groupby(["Funcionário", "Cliente"])["Valor"].sum().reset_index()
clientes_por_func = clientes_por_func.sort_values(["Funcionário", "Valor"], ascending=[True, False])
col1, col2 = st.columns(2)
for func, col in zip(["JPaulo", "Vinicius"], [col1, col2]):
    top_clientes = clientes_por_func[clientes_por_func["Funcionário"] == func].head(10).copy()
    top_clientes["Valor Formatado"] = top_clientes["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    col.dataframe(top_clientes[["Cliente", "Valor Formatado"]], use_container_width=True)

# Top 10 clientes por frequência
st.subheader("📈 Top 10 Clientes Atendidos por Funcionário")
df_freq = df_filtrado.drop_duplicates(subset=["Cliente", "Data", "Funcionário"])
clientes_freq = df_freq.groupby(["Funcionário", "Cliente"]).size().reset_index(name="Qtd Atendimentos")
col1, col2 = st.columns(2)
for func, col in zip(["JPaulo", "Vinicius"], [col1, col2]):
    top_freq = clientes_freq[clientes_freq["Funcionário"] == func].sort_values("Qtd Atendimentos", ascending=False).head(10)
    col.dataframe(top_freq, use_container_width=True)
    fig = px.bar(
        top_freq,
        x="Qtd Atendimentos",
        y="Cliente",
        orientation="h",
        title=f"Top 10 - {func}",
        labels={"Qtd Atendimentos": "Atendimentos", "Cliente": "Cliente"},
        text="Qtd Atendimentos"
    )
    fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True)

# Comparativo de clientes em comum
st.subheader("🔄 Clientes Atendidos por Ambos")
df_unico = df_filtrado.drop_duplicates(subset=["Cliente", "Data", "Funcionário"])
clientes_por_func = df_unico.groupby(["Funcionário", "Cliente"]).agg(
    Qtd_Atendimentos=("Data", "count"),
    Receita=("Valor", "sum")
).reset_index()
clientes_pivot = clientes_por_func.pivot(index="Cliente", columns="Funcionário", values=["Qtd_Atendimentos", "Receita"])
clientes_comuns = clientes_pivot.dropna()
clientes_comuns.columns = [f"{a}_{b}" for a, b in clientes_comuns.columns]
clientes_comuns["Total_Receita"] = clientes_comuns[["Receita_JPaulo", "Receita_Vinicius"]].sum(axis=1)
clientes_comuns["Total_Receita_Formatado"] = clientes_comuns["Total_Receita"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)
clientes_comuns = clientes_comuns.sort_values("Total_Receita", ascending=False)
st.dataframe(clientes_comuns[[
    "Qtd_Atendimentos_JPaulo", "Qtd_Atendimentos_Vinicius",
    "Receita_JPaulo", "Receita_Vinicius", "Total_Receita_Formatado"
]], use_container_width=True)

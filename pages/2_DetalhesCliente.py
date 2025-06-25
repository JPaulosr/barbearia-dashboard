import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧑‍🧑‍👩 Comparativo entre Funcionários")

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

    # Remove nomes genéricos
    nomes_ignorar = ["boliviano", "brasileiro", "menino", "menino boliviano"]
    normalizar = lambda s: str(s).lower().strip()
    df = df[~df["Cliente"].apply(lambda x: normalizar(x) in nomes_ignorar)]
    return df

df = carregar_dados()

# === Filtro por ano ===
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("🗕️ Selecione o Ano", anos, index=0)
df_filtrado = df[df["Ano"] == ano]

# === Receita mensal por funcionário ===
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
    category_orders={"Mês_Nome": ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]},
    template="plotly_white"
)
fig.update_layout(margin=dict(t=10, b=10))
st.plotly_chart(fig, use_container_width=True)

# === Atendimentos ===
st.subheader("📋 Total de Atendimentos por Funcionário")
atendimentos = df_filtrado.groupby("Funcionário")["Data"].count().reset_index().rename(columns={"Data": "Qtd Atendimentos"})

col1, col2 = st.columns(2)
for _, row in atendimentos.iterrows():
    if row["Funcionário"] == "JPaulo":
        col1.metric("Atendimentos - JPaulo", row["Qtd Atendimentos"])
    elif row["Funcionário"] == "Vinicius":
        col2.metric("Atendimentos - Vinicius", row["Qtd Atendimentos"])
st.dataframe(atendimentos, use_container_width=True)

# === Combo vs Simples ===
st.subheader("🔀 Distribuição: Combo vs Simples")
agrupado = df_filtrado.groupby(["Cliente", "Data", "Funcionário"]).agg(
    Qtd_Serviços=("Serviço", "count")
).reset_index()
agrupado["Combo"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
agrupado["Simples"] = agrupado["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)

combo_simples = agrupado.groupby("Funcionário").agg(
    Total_Atendimentos=("Data", "count"),
    Qtd_Combo=("Combo", "sum"),
    Qtd_Simples=("Simples", "sum")
).reset_index()

col1, col2 = st.columns(2)
for _, row in combo_simples.iterrows():
    if row["Funcionário"] == "JPaulo":
        col1.metric("Combos - JPaulo", row["Qtd_Combo"])
        col1.metric("Simples - JPaulo", row["Qtd_Simples"])
    elif row["Funcionário"] == "Vinicius":
        col2.metric("Combos - Vinicius", row["Qtd_Combo"])
        col2.metric("Simples - Vinicius", row["Qtd_Simples"])
st.dataframe(combo_simples, use_container_width=True)

# === Receita total no ano ===
st.subheader("💰 Receita Total no Ano por Funcionário")
receita_total = df_filtrado.groupby("Funcionário")["Valor"].sum().reset_index()
receita_total["Valor Formatado"] = receita_total["Valor"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)
st.dataframe(receita_total[["Funcionário", "Valor Formatado"]], use_container_width=True)

# === Diferença entre eles ===
st.subheader("📊 Diferença de Receita (R$)")
valores = receita_total.set_index("Funcionário")["Valor"].to_dict()
if "JPaulo" in valores and "Vinicius" in valores:
    dif = valores["JPaulo"] - valores["Vinicius"]
    label = "JPaulo ganhou mais" if dif > 0 else "Vinicius ganhou mais"
    st.metric(label=label, value=f"R$ {abs(dif):,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === Receita total por funcionário em cada ano ===
st.subheader("🕕 Receita Total por Funcionário em Cada Ano")
receita_ano_func = df.groupby(["Ano", "Funcionário"])["Valor"].sum().reset_index()
receita_ano_func = receita_ano_func.pivot(index="Ano", columns="Funcionário", values="Valor").fillna(0)
receita_ano_func = receita_ano_func.sort_index(ascending=False)
for col in receita_ano_func.columns:
    receita_ano_func[col] = receita_ano_func[col].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(receita_ano_func, use_container_width=True)

# === Clientes em comum ===
st.subheader("🔄 Clientes Atendidos por Ambos")
df_atendimentos_corrigido = df_filtrado.groupby(["Cliente", "Data", "Funcionário"]).agg(
    Receita=("Valor", "sum")
).reset_index()
df_comuns = df_atendimentos_corrigido.groupby(["Cliente", "Funcionário"]).agg(
    Qtd_Atendimentos=("Data", "count"),
    Receita_Total=("Receita", "sum")
).reset_index()
df_pivot = df_comuns.pivot(index="Cliente", columns="Funcionário", values=["Qtd_Atendimentos", "Receita_Total"])
df_pivot = df_pivot.dropna()
df_pivot.columns = [f"{a}_{b}" for a, b in df_pivot.columns]
df_pivot["Total_Receita"] = df_pivot[["Receita_Total_JPaulo", "Receita_Total_Vinicius"]].sum(axis=1)
df_pivot["Total_Receita_Formatado"] = df_pivot["Total_Receita"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)
df_pivot = df_pivot.sort_values("Total_Receita", ascending=False)
st.dataframe(df_pivot[[
    "Qtd_Atendimentos_JPaulo", "Qtd_Atendimentos_Vinicius",
    "Receita_Total_JPaulo", "Receita_Total_Vinicius", "Total_Receita_Formatado"
]], use_container_width=True)

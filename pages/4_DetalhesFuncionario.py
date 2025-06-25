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
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    nomes_ignorar = ["boliviano", "brasileiro", "menino", "menino boliviano"]
    df = df[~df["Cliente"].str.lower().str.strip().isin(nomes_ignorar)]
    return df

df = carregar_dados()

# Filtro por ano
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("🗓️ Selecione o Ano", anos, index=0)
df_filtrado = df[df["Ano"] == ano]

# Receita mensal por funcionário
st.subheader("📈 Receita Mensal por Funcionário")
receita_mensal = df_filtrado.groupby(["Funcionário", "Mês"]).agg(Receita=("Valor", "sum")).reset_index()
meses_nomes = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
receita_mensal["Mês_Nome"] = receita_mensal["Mês"].map(meses_nomes)
receita_mensal = receita_mensal.sort_values("Mês")
fig = px.bar(receita_mensal, x="Mês_Nome", y="Receita", color="Funcionário", barmode="group", text_auto=True,
             category_orders={"Mês_Nome": list(meses_nomes.values())}, template="plotly_white")
st.plotly_chart(fig, use_container_width=True)

# Atendimentos por funcionário
st.subheader("📋 Total de Atendimentos por Funcionário")
atendimentos = df_filtrado.groupby("Funcionário")["Data"].count().reset_index().rename(columns={"Data": "Qtd Atendimentos"})
col1, col2 = st.columns(2)
for _, row in atendimentos.iterrows():
    if row["Funcionário"] == "JPaulo":
        col1.metric("Atendimentos - JPaulo", row["Qtd Atendimentos"])
    elif row["Funcionário"] == "Vinicius":
        col2.metric("Atendimentos - Vinicius", row["Qtd Atendimentos"])
st.dataframe(atendimentos, use_container_width=True)

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

# Clientes em comum (com cálculo correto)
st.subheader("🔄 Clientes Atendidos por Ambos")
df_comuns = df_filtrado.groupby(["Cliente", "Funcionário"]).agg(
    Qtd_Atendimentos=("Data", "nunique"),
    Receita_Total=("Valor", "sum")
).reset_index()

# filtra apenas clientes atendidos por ambos
clientes_ambos = df_comuns["Cliente"].value_counts()
clientes_ambos = clientes_ambos[clientes_ambos == 2].index.tolist()
df_comuns = df_comuns[df_comuns["Cliente"].isin(clientes_ambos)]

df_pivot = df_comuns.pivot(index="Cliente", columns="Funcionário", values=["Qtd_Atendimentos", "Receita_Total"])
df_pivot.columns = [f"{a}_{b}" for a, b in df_pivot.columns]
df_pivot = df_pivot.dropna()

df_pivot["Total_Receita"] = df_pivot[["Receita_Total_JPaulo", "Receita_Total_Vinicius"]].sum(axis=1)
df_pivot["Total_Receita_Formatado"] = df_pivot["Total_Receita"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
df_pivot["Diferença (JPaulo - Vinicius)"] = df_pivot["Receita_Total_JPaulo"] - df_pivot["Receita_Total_Vinicius"]
df_pivot["Diferença Formatada"] = df_pivot["Diferença (JPaulo - Vinicius)"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.dataframe(df_pivot[[
    "Qtd_Atendimentos_JPaulo", "Qtd_Atendimentos_Vinicius",
    "Receita_Total_JPaulo", "Receita_Total_Vinicius",
    "Total_Receita_Formatado", "Diferença Formatada"
]], use_container_width=True)

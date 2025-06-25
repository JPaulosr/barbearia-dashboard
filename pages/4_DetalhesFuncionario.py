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
anos = sorted(df["Ano"].unique(), reverse=True)
ano = st.selectbox("🗓️ Selecione o Ano", anos, index=0)
df_filtrado = df[df["Ano"] == ano]
funcionarios_ano = df_filtrado["Funcionário"].dropna().unique().tolist()

# === Receita mensal por funcionário ===
st.subheader("📈 Receita Mensal por Funcionário")
if len(funcionarios_ano) > 0:
    receita_mensal = df_filtrado.groupby(["Funcionário", "Mês"]).agg(Receita=("Valor", "sum")).reset_index()
    meses_nomes = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
        7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
    }
    receita_mensal["Mês_Nome"] = receita_mensal["Mês"].map(meses_nomes)
    receita_mensal = receita_mensal.sort_values("Mês")
    fig = px.bar(
        receita_mensal,
        x="Mês_Nome",
        y="Receita",
        color="Funcionário",
        barmode="group",
        text_auto=True,
        category_orders={"Mês_Nome": list(meses_nomes.values())},
        template="plotly_white"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Nenhum funcionário com dados para esse ano.")

# === Atendimentos por funcionário ===
st.subheader("📋 Total de Atendimentos por Funcionário")
if len(funcionarios_ano) > 0:
    atendimentos = df_filtrado.groupby("Funcionário")["Data"].count().reset_index().rename(columns={"Data": "Qtd Atendimentos"})
    st.dataframe(atendimentos, use_container_width=True)
    for func in funcionarios_ano:
        total = atendimentos.loc[atendimentos["Funcionário"] == func, "Qtd Atendimentos"].values[0]
        st.metric(f"Atendimentos - {func}", total)
else:
    st.info("Sem atendimentos registrados para esse ano.")

# === Receita total no ano ===
st.subheader("💰 Receita Total no Ano por Funcionário")
if len(funcionarios_ano) > 0:
    receita_total = df_filtrado.groupby("Funcionário")["Valor"].sum().reset_index()
    receita_total["Valor Formatado"] = receita_total["Valor"].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    )
    st.dataframe(receita_total[["Funcionário", "Valor Formatado"]], use_container_width=True)

    if len(funcionarios_ano) == 2:
        valores = receita_total.set_index("Funcionário")["Valor"].to_dict()
        dif = valores[funcionarios_ano[0]] - valores[funcionarios_ano[1]]
        label = f"{funcionarios_ano[0]} ganhou mais" if dif > 0 else f"{funcionarios_ano[1]} ganhou mais"
        st.metric(label=label, value=f"R$ {abs(dif):,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
else:
    st.info("Sem receita registrada para este ano.")

# === Clientes em comum ===
st.subheader("🔄 Clientes Atendidos por Ambos")
if len(funcionarios_ano) == 2:
    df_clientes = df_filtrado.groupby(["Cliente", "Funcionário"]).agg(
        Receita_Total=("Valor", "sum"),
        Qtd_Atendimentos=("Data", "nunique")
    ).reset_index()
    clientes_ambos = df_clientes["Cliente"].value_counts()
    clientes_ambos = clientes_ambos[clientes_ambos == 2].index.tolist()
    df_comuns = df_clientes[df_clientes["Cliente"].isin(clientes_ambos)]

    df_pivot = df_comuns.pivot(index="Cliente", columns="Funcionário", values=["Qtd_Atendimentos", "Receita_Total"])
    df_pivot.columns = [f"{a}_{b}" for a, b in df_pivot.columns]
    df_pivot = df_pivot.dropna()

    df_pivot["Total_Receita"] = df_pivot[[f"Receita_Total_{f}" for f in funcionarios_ano]].sum(axis=1)
    df_pivot["Total_Receita_Formatado"] = df_pivot["Total_Receita"].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    )
    df_pivot["Diferença Formatada"] = (
        df_pivot[f"Receita_Total_{funcionarios_ano[0]}"] - df_pivot[f"Receita_Total_{funcionarios_ano[1]}"]
    ).apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

    st.dataframe(df_pivot[[
        f"Qtd_Atendimentos_{funcionarios_ano[0]}", f"Qtd_Atendimentos_{funcionarios_ano[1]}",
        f"Receita_Total_{funcionarios_ano[0]}", f"Receita_Total_{funcionarios_ano[1]}",
        "Total_Receita_Formatado", "Diferença Formatada"
    ]], use_container_width=True)
else:
    st.info("Clientes em comum só são exibidos quando ambos os funcionários têm dados.")

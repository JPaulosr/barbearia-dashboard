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

# Receita mensal
st.subheader("📈 Receita Mensal por Funcionário")
if len(funcionarios_ano) > 0:
    receita_mensal = df_filtrado.groupby(["Funcionário", "Mês"]).agg(Receita=("Valor", "sum")).reset_index()
    meses_nomes = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}
    receita_mensal["Mês_Nome"] = receita_mensal["Mês"].map(meses_nomes)
    receita_mensal = receita_mensal.sort_values("Mês")
    fig = px.bar(receita_mensal, x="Mês_Nome", y="Receita", color="Funcionário", barmode="group", text_auto=True,
                 category_orders={"Mês_Nome": list(meses_nomes.values())}, template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Nenhum funcionário com dados para esse ano.")

# Atendimentos
st.subheader("📋 Total de Atendimentos por Funcionário")
if len(funcionarios_ano) > 0:
    atendimentos = df_filtrado.groupby("Funcionário")["Data"].count().reset_index().rename(columns={"Data": "Qtd Atendimentos"})
    for func in funcionarios_ano:
        st.metric(f"Atendimentos - {func}", int(atendimentos[atendimentos['Funcionário'] == func]['Qtd Atendimentos']))
    st.dataframe(atendimentos, use_container_width=True)
else:
    st.info("Sem atendimentos registrados para esse ano.")

# Receita total
st.subheader("💰 Receita Total no Ano por Funcionário")
if len(funcionarios_ano) > 0:
    receita_total = df_filtrado.groupby("Funcionário")["Valor"].sum().reset_index()
    receita_total["Valor Formatado"] = receita_total["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    st.dataframe(receita_total[["Funcionário", "Valor Formatado"]], use_container_width=True)

    # Diferença entre dois, se houver
    if len(funcionarios_ano) == 2:
        valores = receita_total.set_index("Funcionário")["Valor"].to_dict()
        dif = valores[funcionarios_ano[0]] - valores[funcionarios_ano[1]]
        label = f"{funcionarios_ano[0]} ganhou mais" if dif > 0 else f"{funcionarios_ano[1]} ganhou mais"
        st.metric(label=label, value=f"R$ {abs(dif):,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
else:
    st.info("Sem receita registrada para este ano.")

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
ano = st.selectbox("🔕️ Selecione o Ano", anos, index=0)
df_filtrado = df[df["Ano"] == ano]

# === Receita mensal por funcionário considerando agrupamento por atendimento ===
st.subheader("📈 Receita Mensal por Funcionário")
df_atendimentos = df_filtrado.groupby(["Cliente", "Data", "Funcionário"]).agg(Receita=("Valor", "sum")).reset_index()
df_atendimentos["Mês"] = df_atendimentos["Data"].dt.month
df_atendimentos["Mês_Nome"] = df_atendimentos["Mês"].map({
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
})

receita_mensal = df_atendimentos.groupby(["Funcionário", "Mês", "Mês_Nome"]).agg(
    Valor=("Receita", "sum")
).reset_index().sort_values("Mês")

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

# === Receita total no ano com base nos atendimentos ===
st.subheader("💰 Receita Total no Ano por Funcionário")
receita_total_corrigida = df_atendimentos.groupby("Funcionário")["Receita"].sum().reset_index()
receita_total_corrigida["Valor Formatado"] = receita_total_corrigida["Receita"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)
st.dataframe(receita_total_corrigida[["Funcionário", "Valor Formatado"]], use_container_width=True)

# === Diferença entre eles ===
st.subheader("📊 Diferença de Receita (R$)")
valores = receita_total_corrigida.set_index("Funcionário")["Receita"].to_dict()
if "JPaulo" in valores and "Vinicius" in valores:
    dif = valores["JPaulo"] - valores["Vinicius"]
    label = "JPaulo ganhou mais" if dif > 0 else "Vinicius ganhou mais"
    st.metric(label=label, value=f"R$ {abs(dif):,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

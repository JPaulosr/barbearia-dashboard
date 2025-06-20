import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# Recupera o nome do cliente via session_state
cliente = st.session_state.get("cliente", "")

if not cliente:
    st.warning("⚠ Nenhum cliente selecionado.")
    st.stop()

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# Filtra só os dados do cliente
df_cli = df[df["Cliente"] == cliente]

st.subheader(f"📊 Receita mensal separada por tipo de serviço - {cliente}")
servico_mes = df_cli.groupby(["Ano", "Mês", "Serviço"])["Valor"].sum().reset_index()

# Nome dos meses e formato do eixo
meses_nome = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}
servico_mes["MêsNome"] = servico_mes["Mês"].map(meses_nome)
servico_mes["Ano-Mês"] = servico_mes["Ano"].astype(str) + "-" + servico_mes["MêsNome"]

# Gráfico: facetado por serviço (pode trocar por outro estilo se quiser)
fig = px.bar(
    servico_mes,
    x="Ano-Mês",
    y="Valor",
    color="Serviço",
    facet_col="Serviço",
    text_auto=".2s",
    labels={"Valor": "Faturamento"},
    height=400
)
fig.update_layout(
    xaxis_title="Mês",
    yaxis_title="Receita (R$)",
    template="plotly_white"
)
st.plotly_chart(fig, use_container_width=True)

# Tabela de atendimentos únicos por Cliente + Data
st.subheader("🧑‍🔧 Quantas vezes foi atendido (visitas únicas)")

# Contagem única por dia de atendimento
atendimentos = df_cli.drop_duplicates(subset=["Cliente", "Data"])
qtd = len(atendimentos)

st.markdown(f"✅ **Total de atendimentos únicos:** `{qtd}`")

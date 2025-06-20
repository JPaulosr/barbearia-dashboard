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

@st.cache_data(ttl=1)
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

# === FILTROS de Ano e Mês ===
anos_disponiveis = sorted(df_cli["Ano"].dropna().unique())
ano_selecionado = st.selectbox("📅 Selecione o ano", anos_disponiveis)

df_ano = df_cli[df_cli["Ano"] == ano_selecionado]

meses_nome = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}
meses_disponiveis = sorted(df_ano["Mês"].dropna().unique())
meses_opcoes = [meses_nome[m] for m in meses_disponiveis]
default_meses = meses_opcoes[-3:] if len(meses_opcoes) >= 3 else meses_opcoes
meses_selecionados = st.multiselect("📆 Filtrar por mês (opcional)", options=meses_opcoes, default=default_meses)
meses_valores = [k for k,v in meses_nome.items() if v in meses_selecionados]

df_filtrado = df_ano[df_ano["Mês"].isin(meses_valores)]

# === Gráfico facetado ===
st.subheader(f"📊 Receita mensal separada por tipo de serviço - {cliente}")
servico_mes = df_filtrado.groupby(["Ano", "Mês", "Serviço"])["Valor"].sum().reset_index()
servico_mes = servico_mes[servico_mes["Valor"] > 0]
servico_mes["MêsNome"] = servico_mes["Mês"].map(meses_nome)
servico_mes["Ano-Mês"] = servico_mes["Ano"].astype(str) + "-" + servico_mes["MêsNome"]
servico_mes["Texto"] = servico_mes["Serviço"] + " - R$ " + servico_mes["Valor"].astype(int).astype(str)

fig = px.bar(
    servico_mes,
    x="Ano-Mês",
    y="Valor",
    color="Serviço",
    facet_col="Serviço",
    text="Texto",
    labels={"Valor": "Faturamento"},
    height=500,
    facet_col_wrap=4
)
fig.update_layout(
    xaxis_title="Mês",
    yaxis_title="Receita (R$)",
    template="plotly_white"
)
st.plotly_chart(fig, use_container_width=True)

# === Atendimento por funcionário com base em visitas únicas ===
st.subheader("🧑‍🔧 Quantas vezes foi atendido por cada funcionário (visitas únicas)")

# Remove registros duplicados por Cliente + Data
atendimentos_unicos = df_filtrado.drop_duplicates(subset=["Cliente", "Data"])

# Agrupa por funcionário
resumo = atendimentos_unicos.groupby("Funcionário").size().reset_index(name="Quantidade")

# Total geral de visitas
total = len(atendimentos_unicos)

# Exibe resumo
st.markdown(f"✅ **Total de atendimentos únicos:** `{total}`")
st.dataframe(resumo, use_container_width=True)

import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Funcionário")

funcionario = st.session_state.get("funcionario", "")

if not funcionario:
    st.warning("⚠ Nenhum funcionário selecionado.")
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
df_func = df[df["Funcionário"] == funcionario]

# === FILTROS ===
anos = sorted(df_func["Ano"].dropna().unique())
ano_selecionado = st.selectbox("📅 Selecione o ano", anos)

df_ano = df_func[df_func["Ano"] == ano_selecionado]

meses_disponiveis = sorted(df_ano["Mês"].dropna().unique())
mes_nome = {
    1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",
    7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"
}
meses_opcoes = [mes_nome[m] for m in meses_disponiveis]
default_meses = meses_opcoes[-3:] if len(meses_opcoes) >= 3 else meses_opcoes
meses_selecionados = st.multiselect("📆 Filtrar por mês (opcional)", options=meses_opcoes, default=default_meses)
meses_valores = [k for k,v in mes_nome.items() if v in meses_selecionados]
df_filtrado = df_ano[df_ano["Mês"].isin(meses_valores)]

# Filtro de serviço
servicos_disponiveis = sorted(df_filtrado["Serviço"].dropna().unique())
servicos_selecionados = st.multiselect("💈 Filtrar por serviço", options=servicos_disponiveis, default=servicos_disponiveis)
df_filtrado = df_filtrado[df_filtrado["Serviço"].isin(servicos_selecionados)]

# === GRÁFICO FACETADO POR SERVIÇO ===
st.subheader(f"📊 Receita mensal por tipo de serviço - {funcionario}")

servico_mes = df_filtrado.groupby(["Ano", "Mês", "Serviço"])["Valor"].sum().reset_index()
servico_mes = servico_mes[servico_mes["Valor"] > 0]
servico_mes["MêsNome"] = servico_mes["Mês"].map(mes_nome)
servico_mes["Ano-Mês"] = servico_mes["Ano"].astype(str) + "-" + servico_mes["MêsNome"]
servico_mes["Texto"] = servico_mes["Serviço"] + " - R$ " + servico_mes["Valor"].astype(int).astype(str)

fig = px.bar(
    servico_mes,
    x="Ano-Mês",
    y="Valor",
    color="Serviço",
    text="Texto",
    facet_col="Serviço",
    facet_col_wrap=4,
    labels={"Valor": "Faturamento"},
    height=500
)
fig.update_layout(
    xaxis_title="Mês",
    yaxis_title="Receita (R$)",
    template="plotly_white"
)
st.plotly_chart(fig, use_container_width=True)

# === ATENDIMENTOS AJUSTADOS ===
st.subheader("🧑‍🤝‍🧑 Clientes atendidos (visitas únicas ajustadas)")

limite = pd.to_datetime("2025-05-10")
antes = df_filtrado[df_filtrado["Data"] <= limite]
depois = df_filtrado[df_filtrado["Data"] > limite]

qtd_antes = len(antes)
depois_unicos = depois.drop_duplicates(subset=["Cliente", "Data"])
qtd_depois = len(depois_unicos)

total = qtd_antes + qtd_depois

clientes = depois_unicos.groupby("Cliente").size().reset_index(name="Qtd Atendimentos")
clientes = clientes.sort_values(by="Qtd Atendimentos", ascending=False)

st.markdown(f"✅ **Total de atendimentos únicos realizados por {funcionario}:** `{total}`")
st.dataframe(clientes, use_container_width=True)

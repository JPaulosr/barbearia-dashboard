import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    return df

df = carregar_dados()
cliente = st.session_state.get("cliente")

if not cliente:
    st.warning("Nenhum cliente selecionado.")
    st.stop()

st.header(f"🔍 Detalhes do cliente: {cliente}")
df_cliente = df[df["Cliente"] == cliente]

# Receita por mês
receita_mensal = df_cliente.groupby(df_cliente["Data"].dt.to_period("M")).agg({"Valor": "sum"}).reset_index()
receita_mensal["Data"] = receita_mensal["Data"].astype(str)
fig1 = px.bar(receita_mensal, x="Data", y="Valor", title="Receita Mensal", text_auto=True)
st.plotly_chart(fig1, use_container_width=True)

# Serviços realizados
servicos = df_cliente["Serviço"].value_counts().reset_index()
servicos.columns = ["Serviço", "Quantidade"]
fig2 = px.pie(servicos, names="Serviço", values="Quantidade", title="Distribuição de Serviços")
st.plotly_chart(fig2, use_container_width=True)

# Tabela de atendimentos
df_cliente["Valor Formatado"] = df_cliente["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(df_cliente[["Data", "Serviço", "Valor Formatado", "Funcionário"]], use_container_width=True)

st.caption("Painel detalhado por cliente | JPaulo")

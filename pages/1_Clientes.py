import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("🧑‍🤝‍🧑 Clientes - Receita Total")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    return df

df = carregar_dados()

# Agrupamento por cliente
ranking = df.groupby("Cliente")["Valor"].sum().reset_index()
ranking = ranking.sort_values(by="Valor", ascending=False)
ranking["Valor Formatado"] = ranking["Valor"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)

# Tabela de clientes
st.subheader("📋 Receita total por cliente")
st.dataframe(ranking[["Cliente", "Valor Formatado"]], use_container_width=True)

# Seleção de cliente
clientes = ranking["Cliente"].tolist()
cliente_escolhido = st.selectbox("🔎 Ver detalhamento de um cliente", clientes)

if st.button("➡ Ver detalhes"):
    st.query_params["cliente"] = cliente_escolhido
    st.switch_page("pages/2_DetalhesCliente.py")

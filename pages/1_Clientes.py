import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧍‍♂️ Clientes - Receita Total")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    return df

df = carregar_dados()

# === Remove nomes genéricos ===
nomes_ignorar = ["boliviano", "brasileiro", "menino", "menino boliviano"]
normalizar = lambda s: str(s).lower().strip()

df = df[~df["Cliente"].apply(lambda x: normalizar(x) in nomes_ignorar)]

# === Agrupamento ===
ranking = df.groupby("Cliente")["Valor"].sum().reset_index()
ranking = ranking.sort_values(by="Valor", ascending=False)
ranking["Valor Formatado"] = ranking["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# === Busca dinâmica ===
st.subheader("🧾 Receita total por cliente")
busca = st.text_input("🔎 Filtrar por nome").lower().strip()

if busca:
    ranking_exibido = ranking[ranking["Cliente"].str.lower().str.contains(busca)]
else:
    ranking_exibido = ranking.copy()

st.dataframe(ranking_exibido[["Cliente", "Valor Formatado"]], use_container_width=True)

# === Top 5 clientes ===
st.subheader("🏆 Top 5 Clientes por Receita")
top5 = ranking.head(5)
fig_top = px.bar(
    top5,
    x="Cliente",
    y="Valor",
    text=top5["Valor"].apply(lambda x: f"R$ {x:,.0f}".replace(",", "v").replace(".", ",").replace("v", ".")),
    labels={"Valor": "Receita (R$)"},
    color="Cliente"
)
fig_top.update_traces(textposition="outside")
fig_top.update_layout(showlegend=False, height=400, template="plotly_white")
st.plotly_chart(fig_top, use_container_width=True)

# === Comparativo entre dois clientes ===
st.subheader("⚖️ Comparar dois clientes")

clientes_disponiveis = ranking["Cliente"].tolist()
col1, col2 = st.columns(2)
c1 = col1.selectbox("👤 Cliente 1", clientes_disponiveis)
c2 = col2.selectbox("👤 Cliente 2", clientes_disponiveis, index=1 if len(clientes_disponiveis) > 1 else 0)

df_c1 = df[df["Cliente"] == c1]
df_c2 = df[df["Cliente"] == c2]

def resumo_cliente(df_cliente):
    total = df_cliente["Valor"].sum()
    servicos = df_cliente["Serviço"].nunique()
    media = df_cliente.groupby("Data")["Valor"].sum().mean()
    return pd.Series({
        "Total Receita": f"R$ {total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."),
        "Serviços Distintos": servicos,
        "Tique Médio": f"R$ {media:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    })

resumo = pd.concat([
    resumo_cliente(df_c1).rename(c1),
    resumo_cliente(df_c2).rename(c2)
], axis=1)

st.dataframe(resumo, use_container_width=True)

# === Navegar para detalhamento ===
st.subheader("🔍 Ver detalhamento de um cliente")
cliente_escolhido = st.selectbox("📌 Escolha um cliente", clientes_disponiveis)

if st.button("➡ Ver detalhes"):
    st.session_state["cliente"] = cliente_escolhido
    st.switch_page("pages/2_DetalhesCliente.py")

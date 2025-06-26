import streamlit as st
import pandas as pd
import os
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧠 Gestão de Clientes")

STATUS_OPTIONS = ["Ativo", "Ignorado", "Inativo"]
STATUS_FILE = "clientes_status.csv"

@st.cache_data
def carregar_base():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

@st.cache_data
def carregar_status():
    if os.path.exists(STATUS_FILE):
        return pd.read_csv(STATUS_FILE)
    else:
        return pd.DataFrame(columns=["Cliente", "Status"])

def salvar_status(df_status):
    df_status.to_csv(STATUS_FILE, index=False)

# Carregar dados principais e status separado
df = carregar_base()
df_clientes = pd.DataFrame({"Cliente": sorted(df["Cliente"].dropna().unique())})
df_status = carregar_status()

# Combinar com status atual
clientes_com_status = df_clientes.merge(df_status, on="Cliente", how="left")
clientes_com_status["Status"] = clientes_com_status["Status"].fillna("Ativo")

st.subheader("📋 Lista de Clientes com Status")
st.markdown("Você pode alterar o status de clientes genéricos, inativos ou que não devem aparecer nos relatórios.")

# Filtro de busca
busca = st.text_input("🔍 Buscar cliente por nome").strip().lower()
clientes_filtrados = clientes_com_status[clientes_com_status["Cliente"].str.lower().str.contains(busca)] if busca else clientes_com_status

novo_status = []
for i, row in clientes_filtrados.iterrows():
    with st.container():
        st.markdown(f"### 👤 {row['Cliente']}")
        status = st.selectbox("Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(row["Status"]), key=f"status_{i}")
        novo_status.append(status)

# Atualizar e salvar
if st.button("💾 Salvar alterações"):
    clientes_filtrados["Status"] = novo_status
    clientes_com_status.update(clientes_filtrados.set_index("Cliente"))
    salvar_status(clientes_com_status[["Cliente", "Status"]].reset_index(drop=True))
    st.success("Status atualizado com sucesso!")

# 📊 Contadores
st.subheader("📈 Resumo por Status")
st.dataframe(clientes_com_status["Status"].value_counts().reset_index().rename(columns={"index": "Status", "Status": "Qtd Clientes"}), use_container_width=True)

# 📊 Gráfico de pizza
fig = px.pie(clientes_com_status, names="Status", title="Distribuição de Clientes por Status")
st.plotly_chart(fig, use_container_width=True)

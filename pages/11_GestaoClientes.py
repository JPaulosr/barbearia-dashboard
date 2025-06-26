import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide")
st.title("🧠 Gestão de Clientes")

STATUS_OPTIONS = ["Ativo", "Ignorado", "Inativo"]
STATUS_FILE = "clientes_status.csv"

@st.cache_data
def carregar_base():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
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

# Ordenar por prioridade de status
status_prioridade = {"Ignorado": 0, "Inativo": 1, "Ativo": 2}
clientes_filtrados["StatusOrd"] = clientes_filtrados["Status"].map(status_prioridade)
clientes_filtrados = clientes_filtrados.sort_values(by=["StatusOrd", "Cliente"])

# Cores por status
cores_status = {
    "Ignorado": "#ffcccc",
    "Inativo": "#ffeeba",
    "Ativo": "#d4edda"
}

novo_status = []
for i, row in clientes_filtrados.iterrows():
    cor = cores_status.get(row["Status"], "#f0f0f0")
    with st.container():
        st.markdown(f"<div style='background-color:{cor}; padding:10px; border-radius:8px'>", unsafe_allow_html=True)
        st.markdown(f"**👤 {row['Cliente']}**")
        status = st.selectbox(f"Status de {row['Cliente']}", STATUS_OPTIONS, index=STATUS_OPTIONS.index(row["Status"]), key=f"status_{i}")
        novo_status.append(status)
        st.markdown("</div>", unsafe_allow_html=True)

# Atualizar e salvar
if st.button("💾 Salvar alterações"):
    clientes_filtrados["Status"] = novo_status
    clientes_com_status.update(clientes_filtrados.set_index("Cliente"))
    salvar_status(clientes_com_status[["Cliente", "Status"]].reset_index(drop=True))
    st.success("Status atualizado com sucesso!")

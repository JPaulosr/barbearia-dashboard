import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
import json
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🧠 Gestão de Clientes")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"
STATUS_OPTIONS = ["Ativo", "Ignorado", "Inativo"]

# === CONEXÃO COM GOOGLE SHEETS USANDO st.secrets
@st.cache_resource
def conectar_sheets():
    info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    planilha = cliente.open_by_key(SHEET_ID)
    return planilha

# === LEITURA DAS ABAS ===
def carregar_base(planilha):
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba, dtype=str).dropna(how="all")
    df.columns = [col.strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

def carregar_status(planilha):
    try:
        aba = planilha.worksheet(STATUS_ABA)
        df_status = get_as_dataframe(aba).dropna(how="all")
        return df_status[["Cliente", "Status"]]
    except:
        return pd.DataFrame(columns=["Cliente", "Status"])

def salvar_status(planilha, df_status):
    aba = planilha.worksheet(STATUS_ABA)
    aba.clear()
    set_with_dataframe(aba, df_status)

# === CARGA DOS DADOS
planilha = conectar_sheets()
df = carregar_base(planilha)
df_clientes = pd.DataFrame({"Cliente": sorted(df["Cliente"].dropna().unique())})
df_status = carregar_status(planilha)

# === COMBINAÇÃO E ORGANIZAÇÃO
clientes_com_status = df_clientes.merge(df_status, on="Cliente", how="left")
clientes_com_status["Status"] = clientes_com_status["Status"].fillna("Ativo")
status_order = {"Ignorado": 0, "Inativo": 1, "Ativo": 2}
clientes_com_status["Ordem"] = clientes_com_status["Status"].map(status_order)
clientes_com_status = clientes_com_status.sort_values("Ordem").reset_index(drop=True)

# === INTERFACE
st.subheader("📋 Lista de Clientes com Status")
st.markdown("Você pode alterar o status de clientes genéricos, inativos ou que não devem aparecer nos relatórios.")

busca = st.text_input("🔍 Buscar cliente por nome").strip().lower()
clientes_filtrados = clientes_com_status[clientes_com_status["Cliente"].str.lower().str.contains(busca)] if busca else clientes_com_status

# === APRESENTAÇÃO COLORIDA
novo_status = []
for i, row in clientes_filtrados.iterrows():
    cor = "#ffcccc" if row["Status"] == "Ignorado" else "#fff2cc" if row["Status"] == "Inativo" else "#ccffcc"
    with st.container():
        st.markdown(f'<div style="background-color:{cor}; padding:12px; border-radius:8px; font-weight:bold">👤 {row["Cliente"]}</div>', unsafe_allow_html=True)
        status = st.selectbox(
            f"Status de {row['Cliente']}",
            STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(row["Status"]),
            key=f"status_{i}"
        )
        novo_status.append(status)

# === SALVAMENTO
if st.button("💾 Salvar alterações"):
    clientes_filtrados["Status"] = novo_status
    clientes_com_status.update(clientes_filtrados.set_index("Cliente"))
    salvar_status(planilha, clientes_com_status[["Cliente", "Status"]].reset_index())
    st.success("Status atualizado com sucesso!")

# === RESUMO
st.subheader("📈 Resumo por Status")
st.dataframe(
    clientes_com_status["Status"].value_counts().reset_index().rename(columns={"index": "Status", "Status": "Qtd Clientes"}),
    use_container_width=True
)

# === GRÁFICO
fig = px.pie(clientes_com_status, names="Status", title="Distribuição de Clientes por Status")
st.plotly_chart(fig, use_container_width=True)

# === DEBUG OPCIONAL (mostra dados reais da aba clientes_status)
with st.expander("🔎 Ver dados salvos na aba 'clientes_status'"):
    st.dataframe(df_status.sort_values("Cliente"), use_container_width=True)

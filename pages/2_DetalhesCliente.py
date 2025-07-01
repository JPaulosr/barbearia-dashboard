import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import datetime

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]

    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month

    # Mês/Ano em português
    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)

    return df

df = carregar_dados()

# === Filtro de cliente (com fallback da sessão)
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

# === COMPARAÇÃO ENTRE CLIENTES ===
with st.expander("🧪 Comparativo entre Clientes", expanded=False):
    col_c1, col_c2 = st.columns(2)
    cliente_1 = col_c1.selectbox("Cliente 1", clientes_disponiveis, key="c1")
    cliente_2 = col_c2.selectbox("Cliente 2", clientes_disponiveis, index=1, key="c2")

    def indicadores(cliente_nome):
        dados = df[df["Cliente"] == cliente_nome].copy()
        meses = dados["Mês_Ano"].nunique()
        gasto_total = dados["Valor"].sum()
        ticket_medio = gasto_total / len(dados) if len(dados) > 0 else 0
        gasto_mensal = gasto_total / meses if meses > 0 else 0
        return {
            "Cliente": cliente_nome,
            "Atendimentos": len(dados),
            "Ticket Médio": round(ticket_medio, 2),
            "Gasto Total": round(gasto_total, 2),
            "Gasto Mensal Médio": round(gasto_mensal, 2),
        }

    df_comp = pd.DataFrame([indicadores(cliente_1), indicadores(cliente_2)])
    st.dataframe(df_comp, use_container_width=True)

# === HISTÓRICO DE ATENDIMENTOS ===
df_cliente = df[df["Cliente"] == cliente]
st.subheader(f"📅 Histórico de atendimentos - {cliente}")
st.dataframe(df_cliente.sort_values("Data", ascending=False).drop(columns=["Data"]).rename(columns={"Data_str": "Data"}), use_container_width=True)

# === RECEITA MENSAL ===
st.subheader("📊 Receita mensal")
receita_mensal = df_cliente.groupby("Mês_Ano")["Valor"].sum().reset_index()
receita_mensal["ordem"] = pd.to_datetime("01/" + receita_mensal["Mês_Ano"], format="%d/%B/%Y", errors="coerce")
receita_mensal = receita_mensal.sort_values("ordem")

fig_receita = px.bar(
    receita_mensal,
    x="Mês_Ano",
    y="Valor",
    text=receita_mensal["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")),
    labels={"Valor": "Receita (R$)", "Mês_Ano": "Mês"},
)
fig_receita.update_traces(textposition="inside")
fig_receita.update_layout(height=400, margin=dict(t=50), uniformtext_minsize=10, uniformtext_mode='show')
st.plotly_chart(fig_receita, use_container_width=True)

# (os outros blocos do código original devem continuar abaixo conforme sua versão completa)

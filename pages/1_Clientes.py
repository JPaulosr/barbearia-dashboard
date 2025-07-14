import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🦽️ Clientes - Receita Total")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
STATUS_ABA = "clientes_status"

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
    df.columns = [col.strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    return df

@st.cache_data
def carregar_status():
    planilha = conectar_sheets()
    aba = planilha.worksheet(STATUS_ABA)
    df_status = get_as_dataframe(aba).dropna(how="all")
    df_status.columns = [col.strip() for col in df_status.columns]
    return df_status[["Cliente", "Status", "Imagem"]]

df = carregar_dados()
df_status = carregar_status()

# === Filtro: manter apenas clientes ativos ===
ativos = df_status[df_status["Status"] == "Ativo"]["Cliente"].unique().tolist()
df = df[df["Cliente"].isin(ativos)]

# === Remove nomes genéricos ===
nomes_ignorar = ["boliviano", "brasileiro", "menino", "menino boliviano"]
normalizar = lambda s: str(s).lower().strip()
df = df[~df["Cliente"].apply(lambda x: normalizar(x) in nomes_ignorar)]

# === Agrupamento ===
ranking = df.groupby("Cliente")["Valor"].sum().reset_index()
ranking = ranking.sort_values(by="Valor", ascending=False)
ranking = ranking[ranking["Cliente"].isin(ativos)]
ranking["Valor Formatado"] = ranking["Valor"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)

# === Indicadores Gerais ===
st.subheader("📊 Resumo de Clientes")
total_clientes = df["Cliente"].nunique()
total_ativos = df_status[df_status["Status"] == "Ativo"]["Cliente"].nunique()
total_inativos = df_status[df_status["Status"] == "Inativo"]["Cliente"].nunique()
total_ignorados = df_status[df_status["Status"] == "Ignorado"]["Cliente"].nunique()
col1, col2, col3, col4 = st.columns(4)
col1.metric("📄 Total únicos na base", total_clientes)
col2.metric("🔵 Ativos", total_ativos)
col3.metric("🔴 Inativos", total_inativos)
col4.metric("🔶 Ignorados", total_ignorados)

# === Busca dinâmica ===
st.subheader("📟 Receita total por cliente")
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

df_c1 = df[df["Cliente"] == c1].copy()
df_c2 = df[df["Cliente"] == c2].copy()

def resumo_cliente(df_cliente):
    total = df_cliente["Valor"].sum()
    servicos = df_cliente["Serviço"].nunique()
    media = df_cliente.groupby("Data")["Valor"].sum().mean()
    servicos_detalhados = df_cliente["Serviço"].value_counts().rename("Quantidade")
    return pd.Series({
        "Total Receita": f"R$ {total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."),
        "Serviços Distintos": servicos,
        "Tique Médio": f"R$ {media:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    }), servicos_detalhados

resumo1, servicos1 = resumo_cliente(df_c1)
resumo2, servicos2 = resumo_cliente(df_c2)

resumo_geral = pd.concat([resumo1.rename(c1), resumo2.rename(c2)], axis=1)
servicos_comparativo = pd.concat([servicos1.rename(c1), servicos2.rename(c2)], axis=1).fillna(0).astype(int)

st.dataframe(resumo_geral, use_container_width=True)
st.markdown("**Serviços Realizados por Tipo**")
st.dataframe(servicos_comparativo, use_container_width=True)

# === Comparativo mensal ===
df_c1["Mês"] = df_c1["Data"].dt.to_period("M").astype(str)
df_c2["Mês"] = df_c2["Data"].dt.to_period("M").astype(str)

df_comp = pd.concat([
    df_c1.groupby("Mês")["Valor"].sum().reset_index().assign(Cliente=c1),
    df_c2.groupby("Mês")["Valor"].sum().reset_index().assign(Cliente=c2)
])

fig_comp = px.bar(df_comp, x="Mês", y="Valor", color="Cliente", barmode="group",
    labels={"Valor": "Receita (R$)"}, title="📊 Receita mensal comparativa")
st.plotly_chart(fig_comp, use_container_width=True)

# === Exibir imagem do cliente ===
st.subheader("🖼️ Imagem dos clientes comparados")
img1 = df_status[df_status["Cliente"] == c1]["Imagem"].values[0] if c1 in df_status["Cliente"].values else ""
img2 = df_status[df_status["Cliente"] == c2]["Imagem"].values[0] if c2 in df_status["Cliente"].values else ""

col1, col2 = st.columns(2)
if img1:
    col1.image(img1, width=120, caption=c1)
if img2:
    col2.image(img2, width=120, caption=c2)

# === Navegar para detalhamento ===
st.subheader("🔍 Ver detalhamento de um cliente")
cliente_escolhido = st.selectbox("📌 Escolha um cliente", clientes_disponiveis)

if st.button("➔ Ver detalhes"):
    st.session_state["cliente"] = cliente_escolhido
    st.switch_page("pages/2_DetalhesCliente.py")

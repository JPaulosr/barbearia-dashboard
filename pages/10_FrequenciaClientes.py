import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📆 Frequência dos Clientes")

# === CONFIG GOOGLE SHEETS ===
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
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

@st.cache_data
def carregar_status():
    try:
        planilha = conectar_sheets()
        aba_status = planilha.worksheet(STATUS_ABA)
        status = get_as_dataframe(aba_status).dropna(how="all")
        status.columns = [str(col).strip() for col in status.columns]
        return status[["Cliente", "Status"]]
    except:
        return pd.DataFrame(columns=["Cliente", "Status"])

# === CARREGAMENTO E PRÉ-PROCESSAMENTO
df = carregar_dados()
df_status = carregar_status()
clientes_validos = df_status[~df_status["Status"].isin(["Inativo", "Ignorado"])]["Cliente"].unique().tolist()
df = df[df["Cliente"].isin(clientes_validos)]
atendimentos = df.drop_duplicates(subset=["Cliente", "Data"])

# === CÁLCULO DE FREQUÊNCIA
frequencia_clientes = []
hoje = pd.Timestamp.today().normalize()

for cliente, grupo in atendimentos.groupby("Cliente"):
    datas = grupo.sort_values("Data")["Data"].tolist()
    if len(datas) < 2:
        continue

    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media_freq = sum(diffs) / len(diffs)
    ultimo_atendimento = datas[-1]
    dias_desde_ultimo = (hoje - ultimo_atendimento).days

    if dias_desde_ultimo <= media_freq:
        status = ("🟢 Em dia", "Em dia")
    elif dias_desde_ultimo <= media_freq * 1.5:
        status = ("🟠 Pouco atrasado", "Pouco atrasado")
    else:
        status = ("🔴 Muito atrasado", "Muito atrasado")

    frequencia_clientes.append({
        "Cliente": cliente,
        "Último Atendimento": ultimo_atendimento.date(),
        "Qtd Atendimentos": len(datas),
        "Frequência Média (dias)": round(media_freq, 1),
        "Dias Desde Último": dias_desde_ultimo,
        "Status": status[0],
        "Status_Label": status[1]
    })

freq_df = pd.DataFrame(frequencia_clientes)

# === FILTRO INTERATIVO
col_filtros, col_tabela, col_graficos = st.columns([1.2, 2.5, 2])

with col_filtros:
    st.markdown("### 🎯 Filtros")

    cliente_opcoes = ["Todos"] + sorted(freq_df["Cliente"].unique().tolist())
    cliente_selecionado = st.selectbox("👤 Cliente", cliente_opcoes)

    if cliente_selecionado != "Todos":
        freq_df = freq_df[freq_df["Cliente"] == cliente_selecionado]

    status_prioridade = {"Muito atrasado": 0, "Pouco atrasado": 1, "Em dia": 2}
    freq_df["OrdemStatus"] = freq_df["Status_Label"].map(status_prioridade)
    freq_df = freq_df.sort_values(["OrdemStatus", "Dias Desde Último"], ascending=[True, False])

with col_tabela:
    st.markdown("### 📋 Tabela de Frequência")
    st.dataframe(freq_df.drop(columns=["Status_Label", "OrdemStatus"]), use_container_width=True)

with col_graficos:
    st.markdown("### 🧮 Indicadores")
    total = freq_df["Cliente"].nunique()
    em_dia = freq_df[freq_df["Status_Label"] == "Em dia"]["Cliente"].nunique()
    pouco = freq_df[freq_df["Status_Label"] == "Pouco atrasado"]["Cliente"].nunique()
    muito = freq_df[freq_df["Status_Label"] == "Muito atrasado"]["Cliente"].nunique()

    st.metric("👥 Clientes ativos", total)
    st.metric("🟢 Em dia", em_dia)
    st.metric("🟠 Pouco atrasado", pouco)
    st.metric("🔴 Muito atrasado", muito)

# === GRÁFICO TOP 20 ATRASADOS
st.divider()
st.subheader("📊 Top 20 Clientes com mais dias sem vir")
top_grafico = freq_df.head(20)
fig = px.bar(
    top_grafico,
    x="Cliente",
    y="Dias Desde Último",
    color="Status_Label",
    labels={"Dias Desde Último": "Dias de ausência", "Status_Label": "Status"},
    text="Dias Desde Último"
)
fig.update_layout(xaxis_tickangle=-45, height=500)
fig.update_traces(textposition="outside")
st.plotly_chart(fig, use_container_width=True)

# === TOP 5 FREQUÊNCIA MÉDIA
st.divider()
st.subheader("🏆 Ranking por Frequência Média")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### ✅ Top 5 Clientes com Melhor Frequência")
    melhores = freq_df.sort_values("Frequência Média (dias)").head(5)
    st.dataframe(melhores[["Cliente", "Frequência Média (dias)"]], use_container_width=True)

with col2:
    st.markdown("### ⚠️ Top 5 Clientes com Pior Frequência")
    piores = freq_df.sort_values("Frequência Média (dias)", ascending=False).head(5)
    st.dataframe(piores[["Cliente", "Frequência Média (dias)"]], use_container_width=True)

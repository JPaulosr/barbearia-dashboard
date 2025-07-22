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

# === PRÉ-PROCESSAMENTO
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
        "Status": status[0],
        "Cliente": cliente,
        "Último Atendimento": ultimo_atendimento.date(),
        "Qtd Atendimentos": len(datas),
        "Frequência Média (dias)": round(media_freq, 1),
        "Dias Desde Último": dias_desde_ultimo,
        "Status_Label": status[1]
    })

freq_df = pd.DataFrame(frequencia_clientes)
freq_df = pd.DataFrame(frequencia_clientes)
freq_df["Último Atendimento"] = pd.to_datetime(freq_df["Último Atendimento"])
freq_df["Último Atendimento"] = freq_df["Último Atendimento"].dt.strftime("%d/%m/%Y")

# === FILTRO POR TEXTO
st.markdown("### 🎯 Filtro de Cliente")
nome_busca = st.text_input("🔍 Digite parte do nome").strip().lower()
if nome_busca:
    freq_df = freq_df[freq_df["Cliente"].str.lower().str.contains(nome_busca)]

# === INDICADORES
st.markdown("### 📊 Indicadores")
col1, col2, col3, col4 = st.columns(4)
col1.metric("👥 Clientes ativos", freq_df["Cliente"].nunique())
col2.metric("🟢 Em dia", freq_df[freq_df["Status_Label"] == "Em dia"]["Cliente"].nunique())
col3.metric("🟠 Pouco atrasado", freq_df[freq_df["Status_Label"] == "Pouco atrasado"]["Cliente"].nunique())
col4.metric("🔴 Muito atrasado", freq_df[freq_df["Status_Label"] == "Muito atrasado"]["Cliente"].nunique())

# === TABELAS POR STATUS
st.divider()
st.markdown("## 🔴 Muito Atrasados")
muito = freq_df[freq_df["Status_Label"] == "Muito atrasado"].drop(columns=["Status_Label"])
st.dataframe(muito, use_container_width=True)

st.markdown("## 🟠 Pouco Atrasados")
pouco = freq_df[freq_df["Status_Label"] == "Pouco atrasado"].drop(columns=["Status_Label"])
st.dataframe(pouco, use_container_width=True)

st.markdown("## 🟢 Em Dia")
emdia = freq_df[freq_df["Status_Label"] == "Em dia"].drop(columns=["Status_Label"])
st.dataframe(emdia, use_container_width=True)

# === GRÁFICO: TOP 20 CLIENTES AUSENTES
st.divider()
st.subheader("📊 Top 20 Clientes com mais dias sem vir")
top_grafico = freq_df.sort_values("Dias Desde Último", ascending=False).head(20)
fig = px.bar(
    top_grafico,
    x="Cliente",
    y="Dias Desde Último",
    color="Status_Label",
    text="Dias Desde Último",
    labels={"Dias Desde Último": "Dias de ausência", "Status_Label": "Status"}
)
fig.update_layout(xaxis_tickangle=-45, height=500)
fig.update_traces(textposition="outside")
st.plotly_chart(fig, use_container_width=True)

# === RANKING DE FREQUÊNCIA
st.divider()
st.subheader("🏆 Ranking por Frequência Média")
col5, col6 = st.columns(2)

with col5:
    st.markdown("### ✅ Top 5 Clientes com Melhor Frequência")
    melhores = freq_df.sort_values("Frequência Média (dias)").head(5)
    st.dataframe(melhores[["Cliente", "Frequência Média (dias)"]], use_container_width=True)

with col6:
    st.markdown("### ⚠️ Top 5 Clientes com Pior Frequência")
    piores = freq_df.sort_values("Frequência Média (dias)", ascending=False).head(5)
    st.dataframe(piores[["Cliente", "Frequência Média (dias)"]], use_container_width=True)

# === NOVO GRÁFICO: TOP 10 POR QUANTIDADE DE ATENDIMENTOS
st.divider()
st.subheader("💪 Top 10 Clientes por Quantidade de Atendimentos")

top_atendimentos = freq_df.sort_values("Qtd Atendimentos", ascending=False).head(10)

fig2 = px.bar(
    top_atendimentos,
    x="Cliente",
    y="Qtd Atendimentos",
    text="Qtd Atendimentos",
    color_discrete_sequence=["#36a2eb"]
)

fig2.update_traces(textposition="outside")
fig2.update_layout(
    xaxis_tickangle=-45,
    height=500,
    yaxis_title="Atendimentos",
    xaxis_title="Cliente"
)

st.plotly_chart(fig2, use_container_width=True)

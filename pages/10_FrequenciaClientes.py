import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📆 Frequência dos Clientes")

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
    base = get_as_dataframe(planilha.worksheet(BASE_ABA)).dropna(how="all")
    base.columns = [str(col).strip() for col in base.columns]
    base["Data"] = pd.to_datetime(base["Data"], errors="coerce")
    base = base.dropna(subset=["Data"])
    return base

@st.cache_data
def carregar_status():
    try:
        planilha = conectar_sheets()
        status = get_as_dataframe(planilha.worksheet(STATUS_ABA)).dropna(how="all")
        status.columns = [str(col).strip() for col in status.columns]
        return status[["Cliente", "Status"]]
    except:
        return pd.DataFrame(columns=["Cliente", "Status"])

df = carregar_dados()
df_status = carregar_status()

# === Remover clientes inativos e ignorados ===
clientes_validos = df_status[~df_status["Status"].isin(["Inativo", "Ignorado"])]["Cliente"].unique().tolist()
df = df[df["Cliente"].isin(clientes_validos)]

# === Agrupar por Cliente e Data (atendimento único)
atendimentos = df.drop_duplicates(subset=["Cliente", "Data"])

# === Cálculo da frequência
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

# === Filtro por status
status_opcoes = ["Todos", "Em dia", "Pouco atrasado", "Muito atrasado"]
status_selecionado = st.selectbox("🔎 Filtrar por status", status_opcoes)

if status_selecionado != "Todos":
    freq_df = freq_df[freq_df["Status_Label"] == status_selecionado]

# === Ordenar e exibir
freq_df = freq_df.sort_values("Dias Desde Último", ascending=False)
st.dataframe(freq_df.drop(columns=["Status_Label"]), use_container_width=True)

# === Gráfico Top 20
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

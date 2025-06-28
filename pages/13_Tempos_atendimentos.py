import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("⏱️ Tempos por Atendimento")

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
    df.columns = [col.strip() for col in df.columns]
    df = df.dropna(subset=["Data"])
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    for col in ["Hora Chegada", "Hora Início", "Hora Saída"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%H:%M:%S", errors="coerce")
    return df

df = carregar_dados()

# === Calcular tempos ===
df_hora = df.dropna(subset=["Hora Chegada", "Hora Início", "Hora Saída"], how="any").copy()
df_hora["Espera (min)"] = (df_hora["Hora Início"] - df_hora["Hora Chegada"]).dt.total_seconds() / 60
df_hora["Atendimento (min)"] = (df_hora["Hora Saída"] - df_hora["Hora Início"]).dt.total_seconds() / 60
df_hora["Tempo Total (min)"] = (df_hora["Hora Saída"] - df_hora["Hora Chegada"]).dt.total_seconds() / 60
df_hora = df_hora.round({"Espera (min)": 1, "Atendimento (min)": 1, "Tempo Total (min)": 1})

# === Insights por atendimento ===
def gerar_insight(row):
    if row["Tempo Total (min)"] >= 70:
        return "🔥 Muito Demorado"
    elif row["Tempo Total (min)"] >= 50:
        return "⏳ Demorado"
    elif row["Tempo Total (min)"] >= 30:
        return "✅ Normal"
    else:
        return "⚡ Rápido"

df_hora["Insight"] = df_hora.apply(gerar_insight, axis=1)

# === Filtros ===
col1, col2, col3 = st.columns(3)
clientes = sorted(df_hora["Cliente"].dropna().unique().tolist())
funcionarios = sorted(df_hora["Funcionário"].dropna().unique().tolist())

cliente_sel = col1.selectbox("👤 Filtrar por Cliente", ["Todos"] + clientes)
func_sel = col2.selectbox("💈 Filtrar por Funcionário", ["Todos"] + funcionarios)
insight_sel = col3.selectbox("🎯 Filtrar por Insight", ["Todos", "🔥 Muito Demorado", "⏳ Demorado", "✅ Normal", "⚡ Rápido"])

if cliente_sel != "Todos":
    df_hora = df_hora[df_hora["Cliente"] == cliente_sel]
if func_sel != "Todos":
    df_hora = df_hora[df_hora["Funcionário"] == func_sel]
if insight_sel != "Todos":
    df_hora = df_hora[df_hora["Insight"] == insight_sel]

# === Ordenação personalizada ===
criterios = {
    "Tempo Total (maior)": "Tempo Total (min)",
    "Tempo Total (menor)": "Tempo Total (min)",
    "Espera (maior)": "Espera (min)",
    "Atendimento (maior)": "Atendimento (min)"
}
criterio_sel = st.selectbox("📌 Ordenar por", list(criterios.keys()), index=0)
asc = True if "menor" in criterio_sel else False
df_ordenado = df_hora.sort_values(by=criterios[criterio_sel], ascending=asc)

# === Tabela rápida ===
st.subheader("📌 Atendimentos Recentes")
st.dataframe(df_ordenado[["Cliente", "Espera (min)", "Atendimento (min)", "Tempo Total (min)"]], use_container_width=True)

# === Tabela completa ===
st.subheader("📋 Tabela de Atendimentos com Insights")
st.dataframe(df_ordenado[["Data", "Cliente", "Funcionário", "Espera (min)", "Atendimento (min)", "Tempo Total (min)", "Insight"]], use_container_width=True)

# === Gráfico de barras ===
st.subheader("📊 Tempo Total por Cliente")
clientes_grafico = df_ordenado.groupby("Cliente")["Tempo Total (min)"].mean().sort_values(ascending=False).head(10).reset_index()
fig = px.bar(clientes_grafico, x="Cliente", y="Tempo Total (min)", text_auto=True, color="Tempo Total (min)")
fig.update_layout(height=400)
st.plotly_chart(fig, use_container_width=True)

# === Indicadores ===
st.subheader("📈 Métricas Gerais")
col1, col2, col3 = st.columns(3)
col1.metric("Média Espera", f"{df_ordenado['Espera (min)'].mean():.1f} min")
col2.metric("Média Atendimento", f"{df_ordenado['Atendimento (min)'].mean():.1f} min")
col3.metric("Média Total", f"{df_ordenado['Tempo Total (min)'].mean():.1f} min")

# === Rodapé ===
st.markdown("---")
st.markdown("Use os filtros acima para explorar insights sobre a duração dos atendimentos e ajustar sua agenda.")

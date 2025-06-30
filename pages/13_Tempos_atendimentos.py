import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos por Atendimento")

@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)

    # Limpeza da coluna Valor
    if "Valor" in df.columns:
        df["Valor"] = df["Valor"].astype(str).str.replace("R$", "", regex=False).str.replace(",", ".", regex=False).str.strip()
        df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce")

    # Conversões de data/hora
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce').dt.date
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')
    return df

# Carrega os dados
df = carregar_dados_google_sheets()
st.markdown(f"<small><i>Registros carregados: {len(df)}</i></small>", unsafe_allow_html=True)

# Cálculo de tempos
df = df.dropna(subset=["Hora Chegada", "Hora Início", "Hora Saída"])
df["Tempo Espera (min)"] = (df["Hora Início"] - df["Hora Chegada"]).dt.total_seconds() / 60
df["Tempo Atendimento (min)"] = (df["Hora Saída"] - df["Hora Início"]).dt.total_seconds() / 60
df["Tempo Total (min)"] = (df["Hora Saída"] - df["Hora Chegada"]).dt.total_seconds() / 60

# Métricas principais
col1, col2, col3 = st.columns(3)
col1.metric("⏳ Tempo Médio de Espera", f"{df['Tempo Espera (min)'].mean():.1f} min")
col2.metric("✂️ Tempo Médio de Atendimento", f"{df['Tempo Atendimento (min)'].mean():.1f} min")
col3.metric("🕒 Tempo Total Médio", f"{df['Tempo Total (min)'].mean():.1f} min")

# Gráfico de distribuição por tipo de serviço
fig = px.box(df, x="Serviço", y="Tempo Atendimento (min)", points="all", title="Duração do Atendimento por Serviço")
st.plotly_chart(fig, use_container_width=True)

# Mostra a base tratada (opcional)
with st.expander("🔍 Ver dados detalhados"):
    st.dataframe(df[["Data", "Cliente", "Serviço", "Tempo Espera (min)", "Tempo Atendimento (min)", "Tempo Total (min)"]])

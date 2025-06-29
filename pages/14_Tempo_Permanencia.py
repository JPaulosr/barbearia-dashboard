import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Tempo de Permanência no Salão", page_icon="🏠", layout="wide")
st.title("🏠 Tempo de Permanência no Salão")

@st.cache_data

def carregar_dados():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce').dt.date
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')
    return df

df = carregar_dados()
df = df.dropna(subset=["Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão"])

# Cálculos de tempo
for col_name, start_col, end_col in [
    ("Tempo Espera (h)", "Hora Chegada", "Hora Início"),
    ("Tempo Atendimento (h)", "Hora Início", "Hora Saída"),
    ("Tempo Pós (h)", "Hora Saída", "Hora Saída do Salão"),
    ("Tempo Total (h)", "Hora Chegada", "Hora Saída do Salão")
]:
    df[col_name] = (df[end_col] - df[start_col]).dt.total_seconds() / 3600
    df[col_name] = df[col_name].round(2)

st.subheader("📊 Distribuição dos Tempos por Cliente")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### Top 10 Permanências Pós-Atendimento")
    top_pos = df.sort_values("Tempo Pós (h)", ascending=False).head(10)
    st.dataframe(top_pos[["Data", "Cliente", "Funcionário", "Tempo Pós (h)", "Tempo Total (h)"]], use_container_width=True)

with col2:
    st.markdown("### Top 10 Permanência Total")
    top_total = df.sort_values("Tempo Total (h)", ascending=False).head(10)
    st.dataframe(top_total[["Data", "Cliente", "Funcionário", "Tempo Total (h)"]], use_container_width=True)

st.subheader("📈 Comparativo Visual")
fig = px.bar(df.sort_values("Tempo Total (h)", ascending=False).head(20),
             x="Cliente", 
             y=["Tempo Espera (h)", "Tempo Atendimento (h)", "Tempo Pós (h)"],
             title="Top 20 Clientes por Tempo Total (Lado a Lado)",
             barmode="group")
st.plotly_chart(fig, use_container_width=True)

st.subheader("📋 Visualizar base completa")
st.dataframe(df[["Data", "Cliente", "Funcionário", "Tempo Espera (h)", "Tempo Atendimento (h)", "Tempo Pós (h)", "Tempo Total (h)"]], use_container_width=True)

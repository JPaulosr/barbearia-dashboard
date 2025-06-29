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
df["Tempo Espera (min)"] = (df["Hora Início"] - df["Hora Chegada"]).dt.total_seconds() / 60
df["Tempo Atendimento (min)"] = (df["Hora Saída"] - df["Hora Início"]).dt.total_seconds() / 60
df["Tempo Pós (min)"] = (df["Hora Saída do Salão"] - df["Hora Saída"]).dt.total_seconds() / 60
df["Tempo Total (min)"] = (df["Hora Saída do Salão"] - df["Hora Chegada"]).dt.total_seconds() / 60

# Formatações
for col in ["Tempo Espera (min)", "Tempo Atendimento (min)", "Tempo Pós (min)", "Tempo Total (min)"]:
    df[col] = df[col].round(1)

st.subheader("📊 Distribuição dos Tempos por Cliente")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### Top 10 Permanências Pós-Atendimento")
    top_pos = df.sort_values("Tempo Pós (min)", ascending=False).head(10)
    st.dataframe(top_pos[["Data", "Cliente", "Funcionário", "Tempo Pós (min)", "Tempo Total (min)"]], use_container_width=True)

with col2:
    st.markdown("### Top 10 Permanência Total")
    top_total = df.sort_values("Tempo Total (min)", ascending=False).head(10)
    st.dataframe(top_total[["Data", "Cliente", "Funcionário", "Tempo Total (min)"]], use_container_width=True)

st.subheader("📈 Comparativo Visual")
fig = px.bar(df.sort_values("Tempo Total (min)", ascending=False).head(20),
             x="Cliente", y=["Tempo Espera (min)", "Tempo Atendimento (min)", "Tempo Pós (min)"],
             title="Top 20 Clientes por Tempo Total (Empilhado)",
             barmode="stack")
st.plotly_chart(fig, use_container_width=True)

st.subheader("📋 Visualizar base completa")
st.dataframe(df[["Data", "Cliente", "Funcionário", "Tempo Espera (min)", "Tempo Atendimento (min)", "Tempo Pós (min)", "Tempo Total (min)"]], use_container_width=True)

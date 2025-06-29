import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️")
st.title("⏱️ Tempos por Atendimento")

# Função para carregar os dados diretamente do Google Sheets com cache
@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce').dt.time
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce').dt.time
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce').dt.time
    return df

# Carregar dados
df = carregar_dados_google_sheets()

df = df.dropna(subset=["Hora Início", "Hora Saída"])

def calcular_duracao(row):
    try:
        inicio = datetime.combine(datetime.today(), row["Hora Início"])
        fim = datetime.combine(datetime.today(), row["Hora Saída"])
        return (fim - inicio).total_seconds() / 60  # minutos
    except:
        return None

# Tempo por atendimento (em minutos)
df["Duração (min)"] = df.apply(calcular_duracao, axis=1)
df_tempo = df.dropna(subset=["Duração (min)"])

st.subheader("🏆 Rankings de Tempo por Atendimento")
col1, col2 = st.columns(2)

with col1:
    top_mais_rapidos = df_tempo.nsmallest(10, "Duração (min)")
    st.markdown("### Mais Rápidos")
    st.dataframe(top_mais_rapidos[["Data", "Cliente", "Funcionário", "Duração (min)"]])

with col2:
    top_mais_lentos = df_tempo.nlargest(10, "Duração (min)")
    st.markdown("### Mais Lentos")
    st.dataframe(top_mais_lentos[["Data", "Cliente", "Funcionário", "Duração (min)"]])

# Gráfico: Tempo médio por tipo de serviço
st.subheader("📊 Tempo Médio por Tipo de Serviço")
if "Tipo" in df_tempo.columns:
    tempo_por_tipo = df_tempo.groupby("Tipo")["Duração (min)"].mean().reset_index()
    fig_tipo = px.bar(tempo_por_tipo, x="Tipo", y="Duração (min)", title="Tempo Médio por Tipo de Serviço")
    st.plotly_chart(fig_tipo, use_container_width=True)

# Gráfico: Tempo médio por cliente
st.subheader("👤 Tempo Médio por Cliente (Top 15)")
tempo_por_cliente = df_tempo.groupby("Cliente")["Duração (min)"].mean().reset_index()
top_clientes = tempo_por_cliente.sort_values("Duração (min)", ascending=False).head(15)
fig_cliente = px.bar(top_clientes, x="Cliente", y="Duração (min)", title="Clientes com Maior Tempo Médio", text_auto=True)
st.plotly_chart(fig_cliente, use_container_width=True)

# Dias mais apertados (tempo médio alto)
st.subheader("📅 Dias com Maior Tempo Médio de Atendimento")
dias_apertados = df_tempo.groupby("Data")["Duração (min)"].mean().reset_index()
dias_apertados = dias_apertados.sort_values("Duração (min)", ascending=False).head(10)
fig_dias = px.bar(dias_apertados, x="Data", y="Duração (min)", title="Top 10 Dias Mais Apertados")
st.plotly_chart(fig_dias, use_container_width=True)

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos por Atendimento")

@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url, skiprows=1)
    df.columns = df.columns.str.strip()

    df["Data_convertida"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df[df["Data_convertida"].notna()].copy()
    df["Data"] = df["Data_convertida"].dt.date
    df.drop(columns=["Data_convertida"], inplace=True)

    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')
    return df

df = carregar_dados_google_sheets()
df = df[df["Funcionário"].notna() & df["Cliente"].notna()]

combo_grouped = df.dropna(subset=["Hora Início", "Hora Saída", "Cliente", "Data", "Funcionário", "Tipo"]).copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data"]).agg({
    "Hora Chegada": "min",
    "Hora Início": "min",
    "Hora Saída": "max",
    "Hora Saída do Salão": "max",
    "Funcionário": "first",
    "Tipo": lambda x: ', '.join(sorted(set(x)))
}).reset_index()

combo_grouped["Duração (min)"] = (combo_grouped["Hora Saída"] - combo_grouped["Hora Início"]).dt.total_seconds() / 60
combo_grouped["Espera (min)"] = (combo_grouped["Hora Início"] - combo_grouped["Hora Chegada"]).dt.total_seconds() / 60
combo_grouped["Data Group"] = pd.to_datetime(combo_grouped["Data"])
combo_grouped["Período do Dia"] = combo_grouped["Hora Início"].dt.hour.apply(
    lambda h: "Manhã" if 6 <= h < 12 else "Tarde" if 12 <= h < 18 else "Noite")

df_tempo = combo_grouped.dropna(subset=["Duração (min)"]).copy()

# Gráfico corrigido: Quantidade por Período do Dia
st.subheader("🌐 Quantidade por Período do Dia")
turno_counts = df_tempo["Período do Dia"].value_counts().reindex(["Manhã", "Tarde", "Noite"], fill_value=0).reset_index()
turno_counts.columns = ["Período", "Quantidade"]
fig_turno = px.bar(turno_counts, x="Período", y="Quantidade", text="Quantidade",
                   color="Período", title="Distribuição de Atendimentos por Período do Dia")
fig_turno.update_traces(textposition="outside")
fig_turno.update_layout(title_x=0.5)
st.plotly_chart(fig_turno, use_container_width=True)

# Dias mais apertados (maior tempo médio de atendimento)
st.subheader("📅 Dias com Maior Tempo Médio de Atendimento")
dias_apertados = df_tempo.groupby("Data")["Duração (min)"].mean().nlargest(5).reset_index()
fig_apertado = px.bar(dias_apertados, x="Data", y="Duração (min)", text="Duração (min)",
                      title="Dias com Maior Tempo Médio por Atendimento")
fig_apertado.update_traces(texttemplate='%{text:.1f}', textposition='outside')
fig_apertado.update_layout(title_x=0.5)
st.plotly_chart(fig_apertado, use_container_width=True)

# Distribuição por faixas de duração
st.subheader("⏳ Distribuição por Faixa de Duração")
bins = [0, 15, 30, 45, 60, 90, 120, 180]
labels = ["0-15min", "15-30min", "30-45min", "45-60min", "60-90min", "90-120min", ">120min"]
df_tempo["Faixa"] = pd.cut(df_tempo["Duração (min)"], bins=bins + [float('inf')], labels=labels, right=False)
dist_faixas = df_tempo["Faixa"].value_counts().sort_index().reset_index()
dist_faixas.columns = ["Faixa", "Quantidade"]
fig_faixa = px.bar(dist_faixas, x="Faixa", y="Quantidade", text="Quantidade", title="Distribuição por Faixas de Duração")
fig_faixa.update_traces(textposition="outside")
fig_faixa.update_layout(title_x=0.5)
st.plotly_chart(fig_faixa, use_container_width=True)

# Dias com maior tempo médio de espera
st.subheader("🚑 Dias com Maior Tempo Médio de Espera")
dias_espera = df_tempo.groupby("Data")["Espera (min)"].mean().nlargest(5).reset_index()
fig_espera = px.bar(dias_espera, x="Data", y="Espera (min)", text="Espera (min)",
                    title="Dias com Maior Tempo Médio de Espera")
fig_espera.update_traces(texttemplate='%{text:.1f}', textposition='outside')
fig_espera.update_layout(title_x=0.5)
st.plotly_chart(fig_espera, use_container_width=True)

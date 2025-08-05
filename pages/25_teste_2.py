
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos por Atendimento")

@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    
    # 👇 ESSENCIAL! pula a primeira linha com agrupamentos
    df = pd.read_csv(url, skiprows=1)

    df.columns = df.columns.str.strip()

    if "Data" not in df.columns:
        st.error("❌ A coluna 'Data' não foi encontrada. Verifique a planilha ou se 'skiprows=1' foi aplicado.")
        st.stop()

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
combo_grouped["Hora Início dt"] = combo_grouped["Hora Início"]
combo_grouped["Data Group"] = pd.to_datetime(combo_grouped["Data"])

combo_grouped = combo_grouped.dropna(subset=["Hora Início"])
combo_grouped["Período do Dia"] = combo_grouped["Hora Início"].dt.hour.apply(
    lambda h: "Manhã" if 6 <= h < 12 else "Tarde" if 12 <= h < 18 else "Noite"
)

df_tempo = combo_grouped.dropna(subset=["Duração (min)"]).copy()

st.subheader("📆 Tempo Trabalhado por Funcionário (Últimos 7 dias)")
hoje = pd.Timestamp.now().normalize()
ultimos_7_dias = hoje - pd.Timedelta(days=6)
df_semana = df_tempo[(df_tempo["Data Group"].dt.date >= ultimos_7_dias.date()) & (df_tempo["Data Group"].dt.date <= hoje.date())]
soma_por_func = df_semana.groupby("Funcionário")["Duração (min)"].sum()
for func, total in soma_por_func.items():
    horas = int(total // 60)
    minutos = int(total % 60)
    st.markdown(f"**{func}** – {horas}h {minutos}min")

st.subheader("💬 Insights automáticos")
mais_lento = df_semana.nlargest(1, "Duração (min)")
mais_espera = df_semana.nlargest(1, "Espera (min)")
if not mais_lento.empty:
    st.markdown(f"📌 Cliente com atendimento mais demorado: **{mais_lento['Cliente'].values[0]}** ({int(mais_lento['Duração (min)'].values[0])} min)")
if not mais_espera.empty:
    st.markdown(f"⌛ Cliente que mais esperou: **{mais_espera['Cliente'].values[0]}** ({int(mais_espera['Espera (min)'].values[0])} min)")

st.subheader("📊 Comparativo de Tempo por Funcionário")
graf_comp = df_semana.groupby("Funcionário")[["Duração (min)", "Espera (min)"]].mean().reset_index()
graf_comp["Duração formatada"] = graf_comp["Duração (min)"].apply(
    lambda x: f"{int(x//60)}h {int(x%60)}min" if pd.notnull(x) else "-"
)
fig = px.bar(graf_comp, x="Funcionário", y="Duração (min)", color="Funcionário", text="Duração formatada",
             title="Tempo Médio por Funcionário (Últimos 7 dias)")
fig.update_traces(textposition="outside")
fig.update_layout(title_x=0.5, margin=dict(t=60))
st.plotly_chart(fig, use_container_width=True)

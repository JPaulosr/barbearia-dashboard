import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos por Atendimento")

# === Função para carregar os dados do Google Sheets ===
@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()

    # Tenta encontrar a linha com a coluna "Data"
    if "Data" not in df.columns:
        for i in range(5):
            temp = pd.read_csv(url, skiprows=i+1)
            temp.columns = temp.columns.str.strip()
            if "Data" in temp.columns:
                df = temp.copy()
                break

    df["Data_convertida"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df[df["Data_convertida"].notna()].copy()
    df["Data"] = df["Data_convertida"].dt.date
    df.drop(columns=["Data_convertida"], inplace=True)

    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')

    return df

# === Carrega os dados ===
df = carregar_dados_google_sheets()
df = df[df["Funcionário"].notna() & df["Cliente"].notna()]

# === Filtros ===
st.subheader("🧃 Filtros")
col1, col2, col3 = st.columns([2, 2, 2])

funcionarios = df["Funcionário"].dropna().unique().tolist()
clientes = df["Cliente"].dropna().unique().tolist()
datas_unicas = sorted(df["Data"].unique(), reverse=True)

with col1:
    filtro_func = st.multiselect("Filtrar por Funcionário", funcionarios, default=funcionarios)
with col2:
    filtro_cli = st.text_input("Buscar Cliente")
with col3:
    filtro_data = st.date_input("Período", value=max(datas_unicas) if datas_unicas else None)

df = df[df["Funcionário"].isin(filtro_func)]
if filtro_cli:
    df = df[df["Cliente"].str.contains(filtro_cli, case=False, na=False)]
if filtro_data:
    df = df[df["Data"] == filtro_data]

# === Agrupar por atendimento único (Cliente + Data) ===
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

# Turno do dia
combo_grouped["Período do Dia"] = combo_grouped["Hora Início"].dt.hour.apply(
    lambda h: "Manhã" if 6 <= h < 12 else "Tarde" if 12 <= h < 18 else "Noite")

df_tempo = combo_grouped.dropna(subset=["Duração (min)"]).copy()

# === Insights Semanais ===
st.subheader("🔍 Insights da Semana")
hoje = pd.Timestamp.now().normalize()
semana = hoje - pd.Timedelta(days=6)
df_semana = df_tempo[(df_tempo["Data Group"].dt.date >= semana.date()) & (df_tempo["Data Group"].dt.date <= hoje.date())]

if df_semana.empty:
    st.info("Nenhum atendimento nos últimos 7 dias.")
else:
    soma_por_func = df_semana.groupby("Funcionário")["Duração (min)"].sum()
    for func, total in soma_por_func.items():
        horas = int(total // 60)
        minutos = int(total % 60)
        st.markdown(f"**{func}** – {horas}h {minutos}min")

    mais_lento = df_semana.nlargest(1, "Duração (min)")
    mais_espera = df_semana.nlargest(1, "Espera (min)")
    if not mais_lento.empty:
        st.markdown(f"📌 Atendimento mais longo: **{mais_lento['Cliente'].values[0]}** ({int(mais_lento['Duração (min)'].values[0])} min)")
    if not mais_espera.empty:
        st.markdown(f"⌛ Maior espera: **{mais_espera['Cliente'].values[0]}** ({int(mais_espera['Espera (min)'].values[0])} min)")

# === Rankings de Tempo ===
st.subheader("🏆 Rankings de Tempo")
col_rank1, col_rank2 = st.columns(2)
with col_rank1:
    st.markdown("### Mais Rápidos")
    st.dataframe(df_tempo.nsmallest(10, "Duração (min)")[["Data", "Cliente", "Funcionário", "Hora Início"]])
with col_rank2:
    st.markdown("### Mais Lentos")
    st.dataframe(df_tempo.nlargest(10, "Duração (min)")[["Data", "Cliente", "Funcionário", "Hora Início"]])

# === Gráfico: Quantidade por Período do Dia ===
st.subheader("📊 Quantidade por Período do Dia")
if df_tempo["Período do Dia"].notna().sum() > 0:
    ordem = ["Manhã", "Tarde", "Noite"]
    turno_counts = df_tempo["Período do Dia"].value_counts().reindex(ordem).fillna(0)
    df_turno = turno_counts.reset_index()
    df_turno.columns = ["Período do Dia", "Quantidade"]

    fig_turno = px.bar(df_turno, x="Período do Dia", y="Quantidade",
                       labels={"Período do Dia": "Turno", "Quantidade": "Qtd Atendimentos"},
                       title="Distribuição de Atendimentos por Turno")
    fig_turno.update_layout(title_x=0.5)
    st.plotly_chart(fig_turno, use_container_width=True)
else:
    st.warning("Não há dados suficientes para o gráfico de períodos do dia.")


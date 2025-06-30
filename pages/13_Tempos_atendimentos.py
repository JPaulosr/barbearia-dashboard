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
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce').dt.date
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')
    return df

df = carregar_dados_google_sheets()
st.markdown(f"<small><i>Registros carregados: {len(df)}</i></small>", unsafe_allow_html=True)

# Filtros interativos na parte superior
st.markdown("### 🎛️ Filtros")
col_f1, col_f2, col_f3 = st.columns(3)

funcionarios = df["Funcionário"].dropna().unique().tolist()
with col_f1:
    funcionario_selecionado = st.multiselect("Filtrar por Funcionário", funcionarios, default=funcionarios)
with col_f2:
    cliente_busca = st.text_input("Buscar Cliente")
with col_f3:
    periodo = st.date_input("Período", [], help="Selecione o intervalo de datas")

df = df[df["Funcionário"].isin(funcionario_selecionado)]
if cliente_busca:
    df = df[df["Cliente"].str.contains(cliente_busca, case=False, na=False)]
if len(periodo) == 2:
    df = df[(df["Data"] >= periodo[0]) & (df["Data"] <= periodo[1])]

combo_grouped = df.dropna(subset=["Hora Início", "Hora Saída", "Cliente", "Data", "Funcionário", "Tipo"]).copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data"]).agg({
    "Hora Chegada": "min",
    "Hora Início": "min",
    "Hora Saída": "max",
    "Hora Saída do Salão": "max",
    "Funcionário": "first",
    "Tipo": lambda x: ', '.join(sorted(set(x)))
}).reset_index()

combos_df = df.groupby(["Cliente", "Data"])["Combo"].agg(lambda x: ', '.join(sorted(set(str(v) for v in x if pd.notnull(v))))).reset_index()
combo_grouped = pd.merge(combo_grouped, combos_df, on=["Cliente", "Data"], how="left")

combo_grouped["Data"] = pd.to_datetime(combo_grouped["Data"]).dt.strftime("%d/%m/%Y")
combo_grouped["Hora Chegada"] = combo_grouped["Hora Chegada"].dt.strftime("%H:%M")
combo_grouped["Hora Início"] = combo_grouped["Hora Início"].dt.strftime("%H:%M")
combo_grouped["Hora Saída"] = combo_grouped["Hora Saída"].dt.strftime("%H:%M")
combo_grouped["Hora Saída do Salão"] = combo_grouped["Hora Saída do Salão"].dt.strftime("%H:%M")

def calcular_duracao(row):
    try:
        inicio = pd.to_datetime(row["Hora Início"], format="%H:%M")
        fim_raw = row["Hora Saída do Salão"] if pd.notnull(row["Hora Saída do Salão"]) and row["Hora Saída do Salão"] != "NaT" else row["Hora Saída"]
        fim = pd.to_datetime(fim_raw, format="%H:%M")
        return (fim - inicio).total_seconds() / 60
    except:
        return None

combo_grouped["Duração (min)"] = combo_grouped.apply(calcular_duracao, axis=1)
combo_grouped["Duração formatada"] = combo_grouped["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else "")
combo_grouped["Espera (min)"] = (pd.to_datetime(combo_grouped["Hora Início"], format="%H:%M") - pd.to_datetime(combo_grouped["Hora Chegada"], format="%H:%M")).dt.total_seconds() / 60
combo_grouped["Categoria"] = combo_grouped["Combo"].apply(lambda x: "Combo" if "+" in str(x) or "," in str(x) else "Simples")
combo_grouped["Hora Início dt"] = pd.to_datetime(combo_grouped["Hora Início"], format="%H:%M", errors='coerce')
combo_grouped["Período do Dia"] = combo_grouped["Hora Início dt"].dt.hour.apply(lambda h: "Manhã" if 6 <= h < 12 else "Tarde" if 12 <= h < 18 else "Noite")

df_tempo = combo_grouped.dropna(subset=["Duração (min)"]).copy()

# NOVAS MÉTRICAS
st.subheader("📌 Novas Métricas de Tempo")

# 1. Tempo médio por funcionário
tempo_func = df_tempo.groupby("Funcionário")["Duração (min)"].mean().reset_index()
tempo_func["Duração formatada"] = tempo_func["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
st.markdown("### 1️⃣ Tempo Médio por Funcionário")
st.dataframe(tempo_func, use_container_width=True)

# 5. Capacidade diária
st.markdown("### 5️⃣ Capacidade Diária de Atendimento")
capacidade_dia = df_tempo.groupby("Data").agg(Quantidade=("Duração (min)", "count"), Total_min=("Duração (min)", "sum")).reset_index()
st.dataframe(capacidade_dia, use_container_width=True)

# 6. Tempo ocioso por dia
st.markdown("### 6️⃣ Tempo Ocioso por Dia")
df_tempo["Hora Início dt"] = pd.to_datetime(df_tempo["Hora Início dt"], errors='coerce')
df_tempo["Hora Saída dt"] = pd.to_datetime(df_tempo["Hora Saída"], format="%H:%M", errors='coerce')
df_tempo = df_tempo.sort_values(["Data", "Hora Início dt"])
df_tempo["Prox Início"] = df_tempo.groupby("Data")["Hora Início dt"].shift(-1)
df_tempo["Gap (min)"] = (df_tempo["Prox Início"] - df_tempo["Hora Saída dt"]).dt.total_seconds() / 60
ocioso_dia = df_tempo.groupby("Data")["Gap (min)"].sum(min_count=1).reset_index().rename(columns={"Gap (min)": "Tempo Ocioso (min)"})
st.dataframe(ocioso_dia, use_container_width=True)

# 7. Comparativo por dia da semana
st.markdown("### 7️⃣ Tempo Médio por Dia da Semana")
df_tempo["Data dt"] = pd.to_datetime(df_tempo["Data"], dayfirst=True, errors='coerce')
df_tempo["Dia da Semana"] = df_tempo["Data dt"].dt.day_name()
tempo_dia_semana = df_tempo.groupby("Dia da Semana")["Duração (min)"].mean().reindex(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]).reset_index()
tempo_dia_semana["Duração formatada"] = tempo_dia_semana["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else "Sem registro")
st.dataframe(tempo_dia_semana, use_container_width=True)

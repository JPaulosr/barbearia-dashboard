import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

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

colunas_necessarias = ["Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão", "Cliente", "Funcionário", "Tipo", "Combo", "Data"]
faltando = [col for col in colunas_necessarias if col not in df.columns]
if faltando:
    st.error(f"As colunas obrigatórias estão faltando: {', '.join(faltando)}")
    st.stop()

st.markdown(f"<small><i>Registros carregados: {len(df)}</i></small>", unsafe_allow_html=True)

st.markdown("### 🎛️ Filtros")
col_f1, col_f2, col_f3 = st.columns(3)
funcionarios = df["Funcionário"].dropna().unique().tolist()
with col_f1:
    funcionario_selecionado = st.multiselect("Filtrar por Funcionário", funcionarios, default=funcionarios)
with col_f2:
    cliente_busca = st.text_input("Buscar Cliente")
with col_f3:
    hoje = datetime.today().date()
    inicio_default = hoje - timedelta(days=30)
    periodo = st.date_input("Período", value=[inicio_default, hoje], help="Selecione o intervalo de datas")

df = df[df["Funcionário"].isin(funcionario_selecionado)]
if cliente_busca:
    df = df[df["Cliente"].str.contains(cliente_busca, case=False, na=False)]
if isinstance(periodo, list) and len(periodo) == 2:
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

combo_grouped["Data"] = pd.to_datetime(combo_grouped["Data"])
combo_grouped["Data Group"] = combo_grouped["Data"]
combo_grouped["Data"] = combo_grouped["Data"].dt.strftime("%d/%m/%Y")

combo_grouped["Hora Chegada"] = combo_grouped["Hora Chegada"].dt.strftime("%H:%M")
combo_grouped["Hora Início"] = combo_grouped["Hora Início"].dt.strftime("%H:%M")
combo_grouped["Hora Saída"] = combo_grouped["Hora Saída"].dt.strftime("%H:%M")
combo_grouped["Hora Saída do Salão"] = combo_grouped["Hora Saída do Salão"].dt.strftime("%H:%M")

def calcular_duracao(row):
    try:
        inicio = pd.to_datetime(row["Hora Início"], format="%H:%M")
        fim = pd.to_datetime(row["Hora Saída"], format="%H:%M")
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
df_tempo["Data Group"] = pd.to_datetime(df_tempo["Data"], format="%d/%m/%Y", errors='coerce')

# 🔢 Tempo Médio por Funcionário
st.subheader("👥 Tempo Médio por Funcionário")
media_funcionario = df_tempo.groupby("Funcionário")["Duração (min)"].mean().reset_index()
media_funcionario["Duração formatada"] = media_funcionario["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_func = px.bar(media_funcionario, x="Funcionário", y="Duração (min)", title="Tempo Médio por Funcionário", text="Duração formatada")
fig_func.update_traces(textposition='outside')
fig_func.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_func, use_container_width=True)

# ⏱️ Comparativo: Duração vs Espera
st.subheader("⏱️ Comparativo: Duração vs Espera")
comparativo = df_tempo.groupby("Cliente")[["Duração (min)", "Espera (min)"]].mean().dropna().reset_index()
fig_comparativo = px.scatter(
    comparativo, x="Espera (min)", y="Duração (min)", text="Cliente",
    title="Comparativo entre Espera e Duração por Cliente",
    labels={"Espera (min)": "Tempo de Espera Médio", "Duração (min)": "Duração Média"}
)
fig_comparativo.update_traces(textposition='top center')
fig_comparativo.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_comparativo, use_container_width=True)

def calcular_ociosidade(df):
    df_ordenado = df.sort_values(by=["Funcionário", "Data Group", "Hora Início dt"]).copy()
    df_ordenado["Próximo Início"] = df_ordenado.groupby(["Funcionário", "Data Group"])["Hora Início dt"].shift(-1)
    df_ordenado["Hora Saída dt"] = pd.to_datetime(df_ordenado["Hora Saída"], format="%H:%M", errors="coerce")
    df_ordenado["Ociosidade (min)"] = (df_ordenado["Próximo Início"] - df_ordenado["Hora Saída dt"]).dt.total_seconds() / 60
    df_ordenado["Ociosidade (min)"] = df_ordenado["Ociosidade (min)"].apply(lambda x: x if x is not None and x > 0 else 0)
    return df_ordenado

df_ocioso = calcular_ociosidade(df_tempo)

# 🔄 Comparativo: Tempo Trabalhado vs Ocioso
st.subheader("📊 Tempo Trabalhado x Tempo Ocioso")
tempo_trabalhado = df_ocioso.groupby("Funcionário")["Duração (min)"].sum()
tempo_ocioso = df_ocioso.groupby("Funcionário")["Ociosidade (min)"].sum()

df_comp = pd.DataFrame({
    "Trabalhado (min)": tempo_trabalhado,
    "Ocioso (min)": tempo_ocioso
})
df_comp["Total (min)"] = df_comp["Trabalhado (min)"] + df_comp["Ocioso (min)"]
df_comp["% Ocioso"] = (df_comp["Ocioso (min)"] / df_comp["Total (min)"] * 100).round(1)
df_comp["Trabalhado (h)"] = df_comp["Trabalhado (min)"].apply(lambda x: f"{int(x//60)}h {int(x%60)}min")
df_comp["Ocioso (h)"] = df_comp["Ocioso (min)"].apply(lambda x: f"{int(x//60)}h {int(x%60)}min")

st.dataframe(df_comp[["Trabalhado (h)", "Ocioso (h)", "% Ocioso"]], use_container_width=True)

fig_bar = px.bar(df_comp.reset_index().melt(id_vars="Funcionário", value_vars=["Trabalhado (min)", "Ocioso (min)"]),
                 x="Funcionário", y="value", color="variable", barmode="group", title="Comparativo de Tempo por Funcionário")
fig_bar.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_bar, use_container_width=True)

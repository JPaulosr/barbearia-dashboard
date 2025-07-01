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

def calcular_ociosidade(df):
    df_ordenado = df.sort_values(by=["Funcionário", "Data Group", "Hora Início dt"]).copy()
    df_ordenado["Próximo Início"] = df_ordenado.groupby(["Funcionário", "Data Group"])["Hora Início dt"].shift(-1)
    df_ordenado["Hora Saída dt"] = pd.to_datetime(df_ordenado["Hora Saída"], format="%H:%M", errors="coerce")
    df_ordenado["Ociosidade (min)"] = (df_ordenado["Próximo Início"] - df_ordenado["Hora Saída dt"]).dt.total_seconds() / 60
    df_ordenado["Ociosidade (min)"] = df_ordenado["Ociosidade (min)"].apply(lambda x: x if x is not None and x > 0 else 0)
    return df_ordenado

df_ocioso = calcular_ociosidade(df_tempo)

st.subheader("🧍 Tempo Ocioso Total por Funcionário (Atendimentos Finalizados)")
ociosidade_por_funcionario = df_ocioso.groupby("Funcionário")["Ociosidade (min)"].sum().reset_index()
ociosidade_por_funcionario["Tempo formatado"] = ociosidade_por_funcionario["Ociosidade (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_ocio = px.bar(ociosidade_por_funcionario, x="Funcionário", y="Ociosidade (min)", text="Tempo formatado", title="Total de Tempo Ocioso por Funcionário")
fig_ocio.update_traces(textposition="outside")
fig_ocio.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_ocio, use_container_width=True)

st.subheader("📅 Dias com Mais Tempo Ocioso (Somando os Funcionários)")
ociosidade_por_dia = df_ocioso.groupby("Data Group")["Ociosidade (min)"].sum().reset_index()
ociosidade_por_dia["Data"] = ociosidade_por_dia["Data Group"].dt.strftime("%d/%m/%Y")
top_dias_ociosos = ociosidade_por_dia.sort_values("Ociosidade (min)", ascending=False).head(10)
fig_ocio_dia = px.bar(top_dias_ociosos, x="Data", y="Ociosidade (min)", title="Top 10 Dias com Maior Tempo Ocioso")
fig_ocio_dia.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_ocio_dia, use_container_width=True)

st.subheader("📋 Tabela Detalhada: Tempo Ocioso por Funcionário e Dia")
tabela_detalhada = df_ocioso.groupby(["Data Group", "Funcionário"])["Ociosidade (min)"].sum().reset_index()
tabela_detalhada["Data"] = tabela_detalhada["Data Group"].dt.strftime("%d/%m/%Y")
tabela_detalhada["Tempo formatado"] = tabela_detalhada["Ociosidade (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
st.dataframe(tabela_detalhada[["Data", "Funcionário", "Tempo formatado"]], use_container_width=True)

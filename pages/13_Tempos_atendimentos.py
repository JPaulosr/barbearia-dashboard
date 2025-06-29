import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos por Atendimento")

# Função para carregar os dados diretamente do Google Sheets com cache
@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    return df

# Carregar dados
df = carregar_dados_google_sheets()

# Filtrar dados a partir de junho de 2025 e com informações completas
df = df[(df["Data"] >= "2025-06-01") & df["Cliente"].notna() & df["Hora Início"].notna() & df["Hora Saída"].notna()]

# Agrupar por Cliente + Data para evitar duplicações de combos
combo_grouped = df.copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data"]).agg({
    "Hora Chegada": "min",
    "Hora Início": "min",
    "Hora Saída": "max",
    "Funcionário": "first",
    "Tipo": lambda x: ', '.join(sorted(set(x))),
}).reset_index()

# Calcular duração do atendimento
def calcular_duracao(row):
    try:
        return (row["Hora Saída"] - row["Hora Início"]).total_seconds() / 60
    except:
        return None

# Calcular tempo de salão
def calcular_tempo_salao(row):
    try:
        return (row["Hora Saída"] - row["Hora Chegada"]).total_seconds() / 60
    except:
        return None

combo_grouped["Duração (min)"] = combo_grouped.apply(calcular_duracao, axis=1)
combo_grouped["Tempo no Salão (min)"] = combo_grouped.apply(calcular_tempo_salao, axis=1)
combo_grouped["Duração formatada"] = combo_grouped["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else "")
combo_grouped["Espera (min)"] = (combo_grouped["Hora Início"] - combo_grouped["Hora Chegada"]).dt.total_seconds() / 60

# Categorizar combos e simples
combo_grouped["Categoria"] = combo_grouped["Tipo"].apply(lambda x: "Combo" if "," in x else "Simples")
df_tempo = combo_grouped.dropna(subset=["Duração (min)"])

st.subheader("🏆 Rankings de Tempo por Atendimento")
col1, col2 = st.columns(2)

with col1:
    top_mais_rapidos = df_tempo.nsmallest(10, "Duração (min)")
    st.markdown("### Mais Rápidos")
    st.dataframe(top_mais_rapidos[["Data", "Cliente", "Funcionário", "Tipo", "Duração formatada"]], use_container_width=True)

with col2:
    top_mais_lentos = df_tempo.nlargest(10, "Duração (min)")
    st.markdown("### Mais Lentos")
    st.dataframe(top_mais_lentos[["Data", "Cliente", "Funcionário", "Tipo", "Duração formatada"]], use_container_width=True)

# Gráfico: Tempo médio por tipo de serviço
st.subheader("📊 Tempo Médio por Tipo de Serviço")
media_tipo = df_tempo.groupby("Categoria")["Duração (min)"].mean().reset_index()
media_tipo["Duração formatada"] = media_tipo["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_tipo = px.bar(media_tipo, x="Categoria", y="Duração (min)", text="Duração formatada", title="Tempo Médio por Tipo de Serviço")
fig_tipo.update_traces(textposition='outside')
st.plotly_chart(fig_tipo, use_container_width=True)

# Gráfico: Tempo médio por cliente
st.subheader("👤 Tempo Médio por Cliente (Top 15)")
tempo_por_cliente = df_tempo.groupby("Cliente")["Duração (min)"].mean().reset_index()
top_clientes = tempo_por_cliente.sort_values("Duração (min)", ascending=False).head(15)
top_clientes["Duração formatada"] = top_clientes["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_cliente = px.bar(top_clientes, x="Cliente", y="Duração (min)", title="Clientes com Maior Tempo Médio", text="Duração formatada")
fig_cliente.update_traces(textposition='outside')
st.plotly_chart(fig_cliente, use_container_width=True)

# Dias mais apertados (tempo médio alto)
st.subheader("📅 Dias com Maior Tempo Médio de Atendimento")
dias_apertados = df_tempo.groupby("Data")["Espera (min)"].mean().reset_index().dropna()
dias_apertados = dias_apertados.sort_values("Espera (min)", ascending=False).head(10)
fig_dias = px.line(dias_apertados, x="Data", y="Espera (min)", title="Top 10 Dias com Maior Tempo de Espera")
st.plotly_chart(fig_dias, use_container_width=True)

# Distribuição por faixas de tempo
st.subheader("📈 Distribuição por Faixa de Duração")
bins = [0, 15, 30, 45, 60, 120, 240]
labels = ["Até 15min", "Até 30min", "Até 45min", "Até 1h", "Até 2h", ">2h"]
df_tempo["Faixa"] = pd.cut(df_tempo["Duração (min)"], bins=bins, labels=labels, include_lowest=True)
faixa_dist = df_tempo["Faixa"].value_counts().sort_index().reset_index()
faixa_dist.columns = ["Faixa", "Qtd"]
fig_faixa = px.bar(faixa_dist, x="Faixa", y="Qtd", title="Distribuição por Faixa de Tempo")
st.plotly_chart(fig_faixa, use_container_width=True)

# Alertas de espera longa
st.subheader("🚨 Clientes com Espera Acima do Normal")
alvo = st.slider("Defina o tempo limite de espera (min):", 5, 60, 20)
atrasados = df_tempo[df_tempo["Espera (min)"] > alvo]
st.dataframe(atrasados[["Data", "Cliente", "Funcionário", "Espera (min)", "Duração formatada"]], use_container_width=True)

# Insights do Dia
st.subheader("🔍 Insights do Dia")
data_hoje = pd.Timestamp.now().normalize()
df_hoje = df_tempo[df_tempo["Data"] == data_hoje]

if not df_hoje.empty:
    media_hoje = df_hoje["Duração (min)"].mean()
    media_mes = df_tempo[df_tempo["Data"].dt.month == data_hoje.month]["Duração (min)"].mean()
    total_minutos = df_hoje["Duração (min)"].sum()
    mais_rapido = df_hoje.nsmallest(1, "Duração (min)")
    mais_lento = df_hoje.nlargest(1, "Duração (min)")

    st.markdown(f"**Média hoje:** {int(media_hoje)} min | **Média do mês:** {int(media_mes)} min")
    st.markdown(f"**Total de minutos trabalhados hoje:** {int(total_minutos)} min")
    st.markdown(f"**Mais rápido do dia:** {mais_rapido['Cliente'].values[0]} ({int(mais_rapido['Duração (min)'].values[0])} min)")
    st.markdown(f"**Mais lento do dia:** {mais_lento['Cliente'].values[0]} ({int(mais_lento['Duração (min)'].values[0])} min)")
else:
    st.markdown("Nenhum atendimento registrado para hoje.")

# Exibir dados de base (opcional)
with st.expander("📋 Visualizar dados consolidados"):
    st.dataframe(df_tempo, use_container_width=True)

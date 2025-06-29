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

# Agrupar por Cliente + Data para consolidar combos
combo_grouped = df.dropna(subset=["Hora Início", "Hora Saída"]).copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data"]).agg({
    "Hora Chegada": "min",
    "Hora Início": "min",
    "Hora Saída": "max",
    "Funcionário": "first",
    "Tipo": lambda x: ', '.join(sorted(set(x))),
}).reset_index()

# Calcular duração e espera
def calcular_duracao(row):
    try:
        return (row["Hora Saída"] - row["Hora Início"]).total_seconds() / 60
    except:
        return None

def calcular_espera(row):
    try:
        return (row["Hora Início"] - row["Hora Chegada"]).total_seconds() / 60
    except:
        return None

combo_grouped["Duração (min)"] = combo_grouped.apply(calcular_duracao, axis=1)
combo_grouped["Espera (min)"] = combo_grouped.apply(calcular_espera, axis=1)
combo_grouped["Duração formatada"] = combo_grouped["Duração (min)"].apply(
    lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else "")
combo_grouped["Categoria"] = combo_grouped["Tipo"].apply(lambda x: "Combo" if "," in x else "Simples")

# Remover linhas sem duração
combo_grouped = combo_grouped.dropna(subset=["Duração (min)"])

st.subheader("🏆 Rankings de Tempo por Atendimento")
col1, col2 = st.columns(2)

with col1:
    top_mais_rapidos = combo_grouped.nsmallest(10, "Duração (min)")
    st.markdown("### Mais Rápidos")
    st.dataframe(top_mais_rapidos[["Data", "Cliente", "Funcionário", "Tipo", "Duração formatada"]], use_container_width=True)

with col2:
    top_mais_lentos = combo_grouped.nlargest(10, "Duração (min)")
    st.markdown("### Mais Lentos")
    st.dataframe(top_mais_lentos[["Data", "Cliente", "Funcionário", "Tipo", "Duração formatada"]], use_container_width=True)

# Gráfico: Tempo médio por tipo (Combo/Simples)
st.subheader("📊 Tempo Médio por Tipo de Serviço")
media_tipo = combo_grouped.groupby("Categoria")["Duração (min)"].mean().reset_index()
media_tipo["Duração formatada"] = media_tipo["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_tipo = px.bar(media_tipo, x="Categoria", y="Duração (min)", text="Duração formatada",
                  title="Tempo Médio por Tipo de Serviço")
fig_tipo.update_traces(textposition='outside')
st.plotly_chart(fig_tipo, use_container_width=True)

# Gráfico: Tempo médio por cliente
st.subheader("👤 Tempo Médio por Cliente (Top 15)")
tempo_por_cliente = combo_grouped.groupby("Cliente")["Duração (min)"].mean().reset_index()
top_clientes = tempo_por_cliente.sort_values("Duração (min)", ascending=False).head(15)
top_clientes["Duração formatada"] = top_clientes["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_cliente = px.bar(top_clientes, x="Cliente", y="Duração (min)", title="Clientes com Maior Tempo Médio", text="Duração formatada")
fig_cliente.update_traces(textposition='outside')
st.plotly_chart(fig_cliente, use_container_width=True)

# Dias com maior tempo médio de espera
st.subheader("📅 Dias com Maior Tempo Médio de Espera")
dias_apertados = combo_grouped.groupby("Data")["Espera (min)"].mean().reset_index()
dias_apertados = dias_apertados.sort_values("Espera (min)", ascending=False).head(10)
fig_dias = px.line(dias_apertados, x="Data", y="Espera (min)", title="Evolução da Espera nos Dias com Maior Tempo Médio")
st.plotly_chart(fig_dias, use_container_width=True)

# Distribuição por faixa de duração
st.subheader("⏳ Distribuição por Faixa de Duração")
bins = [0, 15, 30, 45, 60, 90, 120, 180]
labels = ["Até 15min", "Até 30min", "Até 45min", "Até 1h", "Até 1h30", "Até 2h", "> 2h"]
combo_grouped["Faixa"] = pd.cut(combo_grouped["Duração (min)"], bins=bins + [combo_grouped["Duração (min)"].max()], labels=labels, include_lowest=True)
faixa_counts = combo_grouped["Faixa"].value_counts().sort_index()
fig_faixa = px.bar(x=faixa_counts.index, y=faixa_counts.values, labels={"x": "Faixa de Duração", "y": "Quantidade"}, title="Distribuição de Duração dos Atendimentos")
st.plotly_chart(fig_faixa, use_container_width=True)

# Alertas de espera longa
st.subheader("🚨 Alertas de Espera Longa")
limite = st.slider("Tempo limite de espera (min)", min_value=5, max_value=60, value=30, step=5)
esperas_longas = combo_grouped[combo_grouped["Espera (min)"] > limite]
st.warning(f"{len(esperas_longas)} clientes esperaram mais de {limite} minutos")
st.dataframe(esperas_longas[["Data", "Cliente", "Funcionário", "Espera (min)", "Duração formatada"]], use_container_width=True)

# Insights do dia
st.subheader("🔍 Insights do Dia")
data_hoje = pd.to_datetime(datetime.now().date())
dados_hoje = combo_grouped[combo_grouped["Data"] == data_hoje]
if not dados_hoje.empty:
    media_hoje = dados_hoje["Duração (min)"].mean()
    media_mes = combo_grouped[combo_grouped["Data"].dt.month == data_hoje.month]["Duração (min)"].mean()
    total_dia = dados_hoje["Duração (min)"].sum()
    st.metric("Tempo Médio Hoje", f"{int(media_hoje // 60)}h {int(media_hoje % 60)}min")
    st.metric("Média do Mês", f"{int(media_mes // 60)}h {int(media_mes % 60)}min")
    st.metric("Total Trabalhado Hoje", f"{int(total_dia // 60)}h {int(total_dia % 60)}min")
    st.markdown(f"**Mais rápido:** {dados_hoje.nsmallest(1, 'Duração (min)')['Cliente'].values[0]}")
    st.markdown(f"**Mais lento:** {dados_hoje.nlargest(1, 'Duração (min)')['Cliente'].values[0]}")
else:
    st.info("Nenhum atendimento registrado para hoje.")

# Exibir dados de base (opcional)
with st.expander("📋 Visualizar dados consolidados"):
    st.dataframe(combo_grouped, use_container_width=True)

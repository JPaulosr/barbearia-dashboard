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

# Validação de colunas obrigatórias
colunas_necessarias = ["Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão", "Cliente", "Funcionário", "Tipo", "Combo", "Data"]
faltando = [col for col in colunas_necessarias if col not in df.columns]
if faltando:
    st.error(f"As colunas obrigatórias estão faltando: {', '.join(faltando)}")
    st.stop()

st.markdown(f"<small><i>Registros carregados: {len(df)}</i></small>", unsafe_allow_html=True)
st.markdown("Corrigido: Insights semanais considerarão últimos 7 dias.")

st.markdown("### 🎛️ Filtros")
col_f1, col_f2, col_f3 = st.columns(3)

funcionarios = df["Funcionário"].dropna().unique().tolist()
with col_f1:
    funcionario_selecionado = st.multiselect("Filtrar por Funcionário", funcionarios, default=funcionarios)
with col_f2:
    cliente_busca = st.text_input("Buscar Cliente")
with col_f3:
    periodo = st.date_input("Período", value=None, help="Selecione o intervalo de datas")

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
        fim_raw = row["Hora Saída"] if pd.notnull(row["Hora Saída"]) and row["Hora Saída"] != "NaT" else row["Hora Saída do Salão"]
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
df_tempo["Data Group"] = pd.to_datetime(df_tempo["Data"], format="%d/%m/%Y", errors='coerce')

st.subheader("📋 Visualizar dados consolidados")
st.dataframe(df_tempo, use_container_width=True)

st.subheader("🏆 Rankings de Tempo por Atendimento")
col1, col2 = st.columns(2)
with col1:
    st.markdown("### Mais Rápidos")
    top_mais_rapidos = df_tempo.nsmallest(10, "Duração (min)")
    st.dataframe(top_mais_rapidos[["Data", "Cliente", "Funcionário", "Tipo", "Duração formatada"]], use_container_width=True)
with col2:
    st.markdown("### Mais Lentos")
    top_mais_lentos = df_tempo.nlargest(10, "Duração (min)")
    st.dataframe(top_mais_lentos[["Data", "Cliente", "Funcionário", "Tipo", "Duração formatada"]], use_container_width=True)

st.subheader("📊 Tempo Médio por Tipo de Serviço")
media_tipo = df_tempo.groupby("Categoria")["Duração (min)"].mean().reset_index()
media_tipo["Duração formatada"] = media_tipo["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_tipo = px.bar(media_tipo, x="Categoria", y="Duração (min)", text="Duração formatada", title="Tempo Médio por Tipo de Serviço")
fig_tipo.update_traces(textposition='outside')
fig_tipo.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_tipo, use_container_width=True)

st.subheader("👤 Tempo Médio por Cliente (Top 15)")
tempo_por_cliente = df_tempo.groupby("Cliente")["Duração (min)"].mean().reset_index()
top_clientes = tempo_por_cliente.sort_values("Duração (min)", ascending=False).head(15)
top_clientes["Duração formatada"] = top_clientes["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_cliente = px.bar(top_clientes, x="Cliente", y="Duração (min)", title="Clientes com Maior Tempo Médio", text="Duração formatada")
fig_cliente.update_traces(textposition='outside')
fig_cliente.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_cliente, use_container_width=True)

st.subheader("📈 Distribuição por Faixa de Duração")
bins = [0, 15, 30, 45, 60, 120, 240]
labels = ["Até 15min", "Até 30min", "Até 45min", "Até 1h", "Até 2h", ">2h"]
df_tempo["Faixa"] = pd.cut(df_tempo["Duração (min)"], bins=bins, labels=labels, include_lowest=True)
faixa_dist = df_tempo["Faixa"].value_counts().sort_index().reset_index()
faixa_dist.columns = ["Faixa", "Qtd"]
fig_faixa = px.bar(faixa_dist, x="Faixa", y="Qtd", title="Distribuição por Faixa de Tempo")
fig_faixa.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_faixa, use_container_width=True)

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

st.subheader("🔍 Insights da Semana")
hoje = pd.Timestamp.now().normalize()
ultimos_7_dias = hoje - pd.Timedelta(days=6)

df_semana = df_tempo[
    (df_tempo["Data Group"].dt.date >= ultimos_7_dias.date()) &
    (df_tempo["Data Group"].dt.date <= hoje.date())
]

if not df_semana.empty:
    media_semana = df_semana["Duração (min)"].mean()
    total_minutos = df_semana["Duração (min)"].sum()
    mais_rapido = df_semana.nsmallest(1, "Duração (min)")
    mais_lento = df_semana.nlargest(1, "Duração (min)")

    st.markdown(f"**Semana:** {ultimos_7_dias.strftime('%d/%m')} a {hoje.strftime('%d/%m')}")
    st.markdown(f"**Média da semana:** {int(media_semana)} min")
    st.markdown(f"**Total de minutos trabalhados na semana:** {int(total_minutos)} min")
    st.markdown(f"**Mais rápido da semana:** {mais_rapido['Cliente'].values[0]} ({int(mais_rapido['Duração (min)'].values[0])} min)")
    st.markdown(f"**Mais lento da semana:** {mais_lento['Cliente'].values[0]} ({int(mais_lento['Duração (min)'].values[0])} min)")
else:
    st.markdown("Nenhum atendimento registrado nos últimos 7 dias.")

st.subheader("🏆 Rankings de Tempo por Atendimento")
col1, col2 = st.columns(2)
with col1:
    top_mais_rapidos = df_tempo.nsmallest(10, "Duração (min)")
    st.markdown("### Mais Rápidos")
    st.dataframe(top_mais_rapidos[["Data", "Cliente", "Funcionário", "Tipo", "Hora Início", "Hora Saída", "Duração formatada", "Espera (min)"]], use_container_width=True)
with col2:
    top_mais_lentos = df_tempo.nlargest(10, "Duração (min)")
    st.markdown("### Mais Lentos")
    st.dataframe(top_mais_lentos[["Data", "Cliente", "Funcionário", "Tipo", "Hora Início", "Hora Saída", "Duração formatada", "Espera (min)"]], use_container_width=True)

contagem_turno = df_tempo["Período do Dia"].value_counts().reindex(["Manhã", "Tarde", "Noite"]).reset_index()
contagem_turno.columns = ["Período do Dia", "Quantidade"]
fig_qtd_turno = px.bar(contagem_turno, x="Período do Dia", y="Quantidade", title="Quantidade de Atendimentos por Período do Dia")
fig_qtd_turno.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_qtd_turno, use_container_width=True)

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

st.subheader("📅 Dias com Maior Tempo Médio de Espera")
dias_apertados = df_tempo.groupby("Data Group")["Espera (min)"].mean().reset_index().dropna()
dias_apertados["Data"] = dias_apertados["Data Group"].dt.strftime("%d/%m/%Y")
dias_apertados = dias_apertados.sort_values("Espera (min)", ascending=False).head(10)
dias_apertados = dias_apertados.sort_values("Data Group")
fig_dias = px.bar(dias_apertados, x="Data", y="Espera (min)", title="Top 10 Dias com Maior Tempo de Espera")
fig_dias.update_xaxes(categoryorder='array', categoryarray=dias_apertados["Data"])
fig_dias.update_layout(xaxis_title="Data", yaxis_title="Espera (min)", margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_dias, use_container_width=True)

st.subheader("🕒 Dias com Maior Tempo Médio de Atendimento")
dias_lentos = df_tempo.groupby("Data Group")["Duração (min)"].mean().reset_index().dropna()
dias_lentos["Data"] = dias_lentos["Data Group"].dt.strftime("%d/%m/%Y")
dias_lentos = dias_lentos.sort_values("Duração (min)", ascending=False).head(10)
fig_dias_lentos = px.bar(dias_lentos, x="Data", y="Duração (min)", title="Top 10 Dias com Maior Tempo Total Médio")
fig_dias_lentos.update_traces(text=dias_lentos["Duração (min)"].round(1), textposition='outside')
fig_dias_lentos.update_layout(xaxis_title="Data", yaxis_title="Duração (min)", margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_dias_lentos, use_container_width=True)

st.subheader("📈 Distribuição por Faixa de Duração")
bins = [0, 15, 30, 45, 60, 120, 240]
labels = ["Até 15min", "Até 30min", "Até 45min", "Até 1h", "Até 2h", ">2h"]
df_tempo["Faixa"] = pd.cut(df_tempo["Duração (min)"], bins=bins, labels=labels, include_lowest=True)
faixa_dist = df_tempo["Faixa"].value_counts().sort_index().reset_index()
faixa_dist.columns = ["Faixa", "Qtd"]
fig_faixa = px.bar(faixa_dist, x="Faixa", y="Qtd", title="Distribuição por Faixa de Tempo")
fig_faixa.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_faixa, use_container_width=True) 

def calcular_ociosidade(df):
    df_sorted = df.sort_values(["Funcionário", "Data Group", "Hora Início dt"]).copy()
    df_sorted["Próximo Início"] = df_sorted.groupby("Funcionário")["Hora Início dt"].shift(-1)
    df_sorted["Fim Atual"] = df_sorted["Hora Início dt"] + pd.to_timedelta(df_sorted["Duração (min)"], unit='m')

    df_sorted["Ociosidade (min)"] = (df_sorted["Próximo Início"] - df_sorted["Fim Atual"]).dt.total_seconds() / 60
    df_sorted["Ociosidade (min)"] = df_sorted["Ociosidade (min)"].apply(lambda x: x if x > 0 else 0)
    return df_sorted


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

st.subheader("🚨 Clientes com Espera Acima do Normal")
alvo = st.slider("Defina o tempo limite de espera (min):", 5, 60, 20)
atrasados = df_tempo[df_tempo["Espera (min)"] > alvo]
st.dataframe(atrasados[["Data", "Cliente", "Funcionário", "Espera (min)", "Duração formatada"]], use_container_width=True)

with st.expander("📋 Visualizar dados consolidados"):
    st.dataframe(df_tempo, use_container_width=True)

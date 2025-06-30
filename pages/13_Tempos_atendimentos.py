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

# Aplicar filtros
df = df[df["Funcionário"].isin(funcionario_selecionado)]
if cliente_busca:
    df = df[df["Cliente"].str.contains(cliente_busca, case=False, na=False)]
if len(periodo) == 2:
    df = df[(df["Data"] >= periodo[0]) & (df["Data"] <= periodo[1])]

df['Hora Início Preenchida'] = df['Hora Início']
mask_hora_inicio_nula = df['Hora Início'].isnull() & df['Hora Chegada'].notnull()
df.loc[mask_hora_inicio_nula, 'Hora Início Preenchida'] = df.loc[mask_hora_inicio_nula, 'Hora Chegada']

# Agrupamento correto sem incluir "Serviço" ou "Tipo" na chave
combo_grouped = df.dropna(subset=["Hora Início Preenchida", "Hora Saída", "Cliente", "Data", "Funcionário"]).copy()
combo_grouped = combo_grouped.groupby(["Cliente", "Data", "Funcionário", "Hora Início Preenchida"]).agg({
    "Hora Chegada": "min",
    "Hora Saída": "max",
    "Hora Saída do Salão": "max",
    "Tipo": lambda x: ', '.join(sorted(set(x))),
    "Serviço": lambda x: ', '.join(sorted(set(x)))
}).reset_index(drop=True)

# Merge com colunas auxiliares
df_temp = df.copy()
df_temp['Hora Início Preenchida'] = df_temp['Hora Início']
df_temp.loc[mask_hora_inicio_nula, 'Hora Início Preenchida'] = df_temp.loc[mask_hora_inicio_nula, 'Hora Chegada']

combo_grouped = pd.merge(
    combo_grouped,
    df_temp[["Cliente", "Data", "Funcionário", "Hora Início Preenchida", "Hora Início", "Combo"]],
    on=["Cliente", "Data", "Funcionário", "Hora Início Preenchida"],
    how="left"
)

# Calcular duração e espera corretamente
def calcular_duracao(row):
    try:
        inicio = row["Hora Início"]
        fim = row["Hora Saída do Salão"]
        if pd.isnull(fim):
            fim = row["Hora Saída"]
        if pd.isnull(fim):
            return None
        return (fim - inicio).total_seconds() / 60
    except:
        return None

combo_grouped["Duração (min)"] = combo_grouped.apply(calcular_duracao, axis=1)
combo_grouped["Duração formatada"] = combo_grouped["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min" if pd.notnull(x) else "")
combo_grouped["Espera (min)"] = (combo_grouped["Hora Início"] - combo_grouped["Hora Chegada"]).dt.total_seconds() / 60
combo_grouped["Categoria"] = combo_grouped["Combo"].apply(lambda x: "Combo" if pd.notnull(x) and "+" in str(x) else "Simples")
combo_grouped["Hora Início dt"] = combo_grouped["Hora Início Preenchida"]
combo_grouped["Período do Dia"] = combo_grouped["Hora Início"].dt.hour.apply(lambda h: "Manhã" if 6 <= h < 12 else "Tarde" if 12 <= h < 18 else "Noite")

# Exibir apenas depois de calcular
data_formatada = pd.to_datetime(combo_grouped["Data"])
combo_grouped["Data"] = data_formatada.dt.strftime("%d/%m/%Y")
combo_grouped["Hora Chegada"] = combo_grouped["Hora Chegada"].dt.strftime("%H:%M")
combo_grouped["Hora Início"] = combo_grouped["Hora Início Preenchida"].dt.strftime("%H:%M")
combo_grouped["Hora Saída"] = combo_grouped["Hora Saída"].dt.strftime("%H:%M")
combo_grouped["Hora Saída do Salão"] = combo_grouped["Hora Saída do Salão"].dt.strftime("%H:%M")

# Dados consolidados para visualização final
df_tempo = combo_grouped.dropna(subset=["Duração (min)"]).copy()

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

st.subheader("📅 Dias com Maior Tempo Médio de Atendimento")
dias_apertados = df_tempo.groupby("Data")["Espera (min)"].mean().reset_index().dropna()
dias_apertados = dias_apertados.sort_values("Espera (min)", ascending=False).head(10)
fig_dias = px.bar(dias_apertados, x="Data", y="Espera (min)", title="Top 10 Dias com Maior Tempo de Espera")
fig_dias.update_layout(xaxis_title="Data", yaxis_title="Espera (min)", margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_dias, use_container_width=True)

st.subheader("📈 Distribuição por Faixa de Duração")
bins = [0, 15, 30, 45, 60, 120, 240]
labels = ["Até 15min", "Até 30min", "Até 45min", "Até 1h", "Até 2h", ">2h"]
df_tempo["Faixa"] = pd.cut(df_tempo["Duração (min)"], bins=bins, labels=labels, include_lowest=True)
faixa_dist = df_tempo["Faixa"].value_counts().sort_index().reset_index()
faixa_dist.columns = ["Faixa", "Qtd"]
fig_faixa = px.bar(faixa_dist, x="Faixa", y="Qtd", title="Distribuição por Faixa de Tempo")
fig_faixa.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_faixa, use_container_width=True)

st.subheader("🚨 Clientes com Espera Acima do Normal")
alvo = st.slider("Defina o tempo limite de espera (min):", 5, 60, 20)
atrasados = df_tempo[df_tempo["Espera (min)"] > alvo]
st.dataframe(atrasados[["Data", "Cliente", "Funcionário", "Espera (min)", "Duração formatada"]], use_container_width=True)

st.subheader("🔍 Insights do Dia")
data_hoje = pd.Timestamp.now().normalize().date()
df_hoje = df_tempo[df_tempo["Data"] == data_hoje.strftime("%d/%m/%Y")]

if not df_hoje.empty:
    media_hoje = df_hoje["Duração (min)"].mean()
    media_mes = df_tempo[pd.to_datetime(df_tempo["Data"], dayfirst=True).dt.month == datetime.now().month]["Duração (min)"].mean()
    total_minutos = df_hoje["Duração (min)"].sum()
    mais_rapido = df_hoje.nsmallest(1, "Duração (min)")
    mais_lento = df_hoje.nlargest(1, "Duração (min)")

    st.markdown(f"**Média hoje:** {int(media_hoje)} min | **Média do mês:** {int(media_mes)} min")
    st.markdown(f"**Total de minutos trabalhados hoje:** {int(total_minutos)} min")
    st.markdown(f"**Mais rápido do dia:** {mais_rapido['Cliente'].values[0]} ({int(mais_rapido['Duração (min)'].values[0])} min)")
    st.markdown(f"**Mais lento do dia:** {mais_lento['Cliente'].values[0]} ({int(mais_lento['Duração (min)'].values[0])} min)")
else:
    st.markdown("Nenhum atendimento registrado para hoje.")

with st.expander("📋 Visualizar dados consolidados"):
    st.dataframe(df_tempo, use_container_width=True)

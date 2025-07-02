import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Tempos de Atendimento", page_icon="⏱️", layout="wide")
st.title("⏱️ Tempos de Atendimento")

@st.cache_data
def carregar_dados():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)

    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors="coerce")
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors="coerce")
    df["Funcionário"] = df["Funcionário"].fillna("")
    df["Cliente"] = df["Cliente"].fillna("")

    # Calcula duração em minutos
    df["Duração (min)"] = (df["Hora Saída"] - df["Hora Início"]).dt.total_seconds() / 60
    df["Duração (min)"] = df["Duração (min)"].round(0)

    # Tempo formatado
    def formatar_tempo(minutos):
        if pd.isnull(minutos): return ""
        h = int(minutos // 60)
        m = int(minutos % 60)
        return f"{h}h {m}min" if h > 0 else f"0h {m}min"

    df["Duração formatada"] = df["Duração (min)"].apply(formatar_tempo)
    return df

df = carregar_dados()

# 🎯 FILTROS
st.markdown("### 🧩 Filtros")
col_func, col_cliente, col_data = st.columns([2, 2, 1])

with col_func:
    funcionarios = df["Funcionário"].dropna().unique().tolist()
    funcionarios_selecionados = st.multiselect("Filtrar por Funcionário", funcionarios, default=funcionarios)

with col_cliente:
    cliente_input = st.text_input("Buscar Cliente")

with col_data:
    data_input = st.date_input("Selecionar um dia da semana", value=datetime.today())

# 🗓️ INTERVALO SEMANAL
inicio_semana = data_input - timedelta(days=data_input.weekday())  # segunda
fim_semana = inicio_semana + timedelta(days=6)  # domingo

# 🔍 APLICAR FILTROS
df_filtrado = df[
    (df["Funcionário"].isin(funcionarios_selecionados)) &
    (df["Data"] >= pd.to_datetime(inicio_semana)) &
    (df["Data"] <= pd.to_datetime(fim_semana))
]

if cliente_input:
    df_filtrado = df_filtrado[df_filtrado["Cliente"].str.contains(cliente_input, case=False, na=False)]

# 📊 INSIGHTS
st.markdown("### 🔍 Insights da Semana")
if not df_filtrado.empty:
    media_semana = df_filtrado["Duração (min)"].mean()
    total_minutos = df_filtrado["Duração (min)"].sum()
    mais_rapido = df_filtrado.sort_values("Duração (min)").iloc[0]
    mais_lento = df_filtrado.sort_values("Duração (min)", ascending=False).iloc[0]

    st.write(f"**Semana:** {inicio_semana.strftime('%d/%m')} a {fim_semana.strftime('%d/%m')}")
    st.write(f"**Média da semana:** {round(media_semana)} min")
    st.write(f"**Total de minutos trabalhados na semana:** {int(total_minutos)} min")
    st.write(f"**Mais rápido da semana:** {mais_rapido['Cliente']} ({int(mais_rapido['Duração (min)'])} min)")
    st.write(f"**Mais lento da semana:** {mais_lento['Cliente']} ({int(mais_lento['Duração (min)'])} min)")
else:
    st.warning("Nenhum dado encontrado para os filtros selecionados.")

# 🏆 RANKINGS
st.markdown("### 🏆 Rankings de Tempo por Atendimento")
col_r1, col_r2 = st.columns(2)

with col_r1:
    st.markdown("#### Mais Rápidos")
    top_rapidos = df_filtrado.sort_values("Duração (min)").head(10)
    st.dataframe(top_rapidos[["Data", "Cliente", "Funcionário", "Tipo", "Hora Início", "Hora Saída", "Duração formatada"]], use_container_width=True)

with col_r2:
    st.markdown("#### Mais Lentos")
    top_lentos = df_filtrado.sort_values("Duração (min)", ascending=False).head(10)
    st.dataframe(top_lentos[["Data", "Cliente", "Funcionário", "Tipo", "Hora Início", "Hora Saída", "Duração formatada"]], use_container_width=True)

# 📈 GRÁFICO DISTRIBUTIVO
st.markdown("### 📈 Distribuição por Cliente")
if not df_filtrado.empty:
    top20 = df_filtrado.sort_values("Duração (min)", ascending=False).head(20)

    fig = px.bar(
        top20,
        x="Cliente",
        y="Duração (min)",
        color="Funcionário",
        text="Duração formatada",
        title="Top 20 Clientes com Maior Tempo de Atendimento",
        labels={"Duração (min)": "Minutos"}
    )

    fig.update_traces(textposition="outside")
    fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nenhum dado para exibir no gráfico.")

# 📋 BASE COMPLETA FILTRADA
st.markdown("### 📋 Base Filtrada")
st.dataframe(df_filtrado[[
    "Data", "Cliente", "Funcionário", "Tipo", "Hora Início", "Hora Saída", "Duração formatada"
]], use_container_width=True)

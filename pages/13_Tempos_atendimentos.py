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

# Filtro por funcionário
funcionarios = combo_grouped["Funcionário"].dropna().unique().tolist()
funcionario_selecionado = st.selectbox("Selecione o funcionário:", options=["Todos"] + funcionarios)
combo_filtrado = combo_grouped.copy()
if funcionario_selecionado != "Todos":
    combo_filtrado = combo_filtrado[combo_filtrado["Funcionário"] == funcionario_selecionado]

st.subheader("🏆 Rankings de Tempo por Atendimento")
col1, col2 = st.columns(2)

with col1:
    top_mais_rapidos = combo_filtrado.nsmallest(10, "Duração (min)")
    st.markdown("### Mais Rápidos")
    st.dataframe(top_mais_rapidos[["Data", "Cliente", "Funcionário", "Tipo", "Duração formatada"]], use_container_width=True)

with col2:
    top_mais_lentos = combo_filtrado.nlargest(10, "Duração (min)")
    st.markdown("### Mais Lentos")
    st.dataframe(top_mais_lentos[["Data", "Cliente", "Funcionário", "Tipo", "Duração formatada"]], use_container_width=True)

# Comparação visual JPaulo vs Vinicius
st.subheader("👥 Comparativo JPaulo vs Vinicius (Tempo Médio)")
comp_func = combo_grouped.groupby("Funcionário")["Duração (min)"].mean().reset_index()
fig_comp = px.bar(comp_func, x="Funcionário", y="Duração (min)", title="Tempo Médio por Funcionário")
st.plotly_chart(fig_comp, use_container_width=True)

# Painel por turnos
st.subheader("🕒 Análise por Turnos")
def classificar_turno(hora):
    if pd.isnull(hora): return "Indefinido"
    hora = hora.hour
    if hora < 12:
        return "Manhã"
    elif hora < 18:
        return "Tarde"
    else:
        return "Noite"

combo_filtrado["Turno"] = combo_filtrado["Hora Início"].apply(classificar_turno)
tempo_turno = combo_filtrado.groupby("Turno")["Duração (min)"].mean().reset_index()
fig_turno = px.bar(tempo_turno, x="Turno", y="Duração (min)", title="Tempo Médio por Turno")
st.plotly_chart(fig_turno, use_container_width=True)

# Os gráficos e análises restantes continuam aqui (omitidos para foco)
# ...
1111111111111111111111111111111111111111111111111111111111

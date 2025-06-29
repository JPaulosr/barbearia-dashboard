import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", layout="wide")
st.title("🕰️ Tempos por Atendimento")

# FUNÇÃO DE LEITURA DIRETA DO GOOGLE SHEETS
@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/export?format=csv&id=1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE&gid=0"
    df = pd.read_csv(url)
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors="coerce").dt.time
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors="coerce").dt.time
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors="coerce").dt.time
    return df

df = carregar_dados_google_sheets()
data_unicas = df["Data"].dropna().dt.date.unique()
data_sel = st.sidebar.date_input("Selecione uma data", value=max(data_unicas))
df_dia = df[df["Data"].dt.date == data_sel].copy()

# Calcular tempos
def calcular_tempos(row):
    try:
        chegada = datetime.combine(datetime.today(), row['Hora Chegada'])
        inicio = datetime.combine(datetime.today(), row['Hora Início'])
        saida = datetime.combine(datetime.today(), row['Hora Saída'])
        espera = (inicio - chegada).total_seconds() / 60
        atendimento = (saida - inicio).total_seconds() / 60
        total = (saida - chegada).total_seconds() / 60
        return pd.Series([espera, atendimento, total])
    except:
        return pd.Series([None, None, None])

df_dia[['Espera (min)', 'Atendimento (min)', 'Tempo Total (min)']] = df_dia.apply(calcular_tempos, axis=1)

# INDICADORES
col1, col2, col3, col4 = st.columns(4)
col1.metric("Clientes atendidos", df_dia['Cliente'].nunique())
col2.metric("Média de Espera", f"{df_dia['Espera (min)'].mean():.1f} min" if not df_dia['Espera (min)'].isna().all() else '-')
col3.metric("Média Atendimento", f"{df_dia['Atendimento (min)'].mean():.1f} min" if not df_dia['Atendimento (min)'].isna().all() else '-')
col4.metric("Tempo Total Médio", f"{df_dia['Tempo Total (min)'].mean():.1f} min" if not df_dia['Tempo Total (min)'].isna().all() else '-')

# GRÁFICO TEMPO DE ESPERA POR CLIENTE
st.subheader("🕒 Gráfico - Tempo de Espera por Cliente")
df_espera = df_dia.dropna(subset=['Espera (min)'])
if not df_espera.empty:
    fig = px.bar(df_espera, x='Cliente', y='Espera (min)', color='Funcionario', title='Tempo de Espera por Cliente')
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nenhum atendimento registrado nesta data.")

# RANKINGS
st.subheader("🏆 Rankings do Dia")
col5, col6 = st.columns(2)

mais_rapidos = df_dia.sort_values('Tempo Total (min)').dropna(subset=['Tempo Total (min)']).head(5)
mais_lentos = df_dia.sort_values('Tempo Total (min)', ascending=False).dropna(subset=['Tempo Total (min)']).head(5)

col5.markdown("**Atendimentos Mais Rápidos**")
col5.dataframe(mais_rapidos[['Cliente', 'Tempo Total (min)', 'Funcionario']])

col6.markdown("**Atendimentos Mais Lentos**")
col6.dataframe(mais_lentos[['Cliente', 'Tempo Total (min)', 'Funcionario']])

# TEMPO POR TIPO DE SERVIÇO
st.subheader("📊 Tempo Médio por Tipo de Serviço")
df_serv = df_dia.dropna(subset=['Tempo Total (min)', 'Tipo'])
if not df_serv.empty:
    fig2 = px.box(df_serv, x='Tipo', y='Tempo Total (min)', color='Tipo', title='Distribuição de Tempo por Serviço')
    st.plotly_chart(fig2, use_container_width=True)

# DIAS MAIS APERTADOS
st.subheader("🗓️ Dias Mais Apertados (espera acumulada)")
df_espera_total = df.dropna(subset=['Hora Chegada', 'Hora Início']).copy()
df_espera_total["Espera (min)"] = df_espera_total.apply(lambda row: (datetime.combine(datetime.today(), row['Hora Início']) - datetime.combine(datetime.today(), row['Hora Chegada'])).total_seconds() / 60, axis=1)
df_dias = df_espera_total.groupby(df_espera_total["Data"].dt.date)['Espera (min)'].sum().reset_index()
df_dias = df_dias.sort_values('Espera (min)', ascending=False).head(10)
fig3 = px.bar(df_dias, x='Data', y='Espera (min)', title='Top 10 Dias com Maior Tempo de Espera')
st.plotly_chart(fig3, use_container_width=True)

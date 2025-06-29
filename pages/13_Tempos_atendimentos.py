
import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Tempos por Atendimento", page_icon="⏰", layout="wide")

# === Carregar dados do Google Sheets diretamente ===
url = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSQst0xHL4p03sxJ8eEdEcJ6FgsokNqkWQSn-rhG-GiDUvTLJyxTxFb8kXUOE0QkboceVa-wMsCrFxH/pub?gid=0&single=true&output=csv"
df = pd.read_csv(url)

# === Conversões e tratamento de data/hora ===
df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors="coerce")
df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors="coerce")
df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors="coerce")

# === Sidebar para seleção de data ===
datas_unicas = df["Data"].dropna().dt.date.unique()
datas_ordenadas = sorted(datas_unicas)
data_sel = st.sidebar.date_input("Selecionar data", value=max(datas_ordenadas) if len(datas_ordenadas) > 0 else datetime.today().date())

# === Filtro por data ===
df_dia = df[df["Data"].dt.date == data_sel].copy()

# === Cálculo de tempos ===
df_dia["Espera (min)"] = (df_dia["Hora Início"] - df_dia["Hora Chegada"]).dt.total_seconds() / 60
df_dia["Atendimento (min)"] = (df_dia["Hora Saída"] - df_dia["Hora Início"]).dt.total_seconds() / 60
df_dia["Tempo Total (min)"] = (df_dia["Hora Saída"] - df_dia["Hora Chegada"]).dt.total_seconds() / 60

# === Título ===
st.title("⏰ Tempos por Atendimento")

# === Indicadores ===
col1, col2, col3, col4 = st.columns(4)
col1.metric("Clientes atendidos", len(df_dia))
col2.metric("Média de Espera", f"{df_dia['Espera (min)'].mean():.1f}" if not df_dia.empty else "-")
col3.metric("Média Atendimento", f"{df_dia['Atendimento (min)'].mean():.1f}" if not df_dia.empty else "-")
col4.metric("Tempo Total Médio", f"{df_dia['Tempo Total (min)'].mean():.1f}" if not df_dia.empty else "-")

# === Gráfico ===
st.subheader("🕒 Gráfico - Tempo de Espera por Cliente")
if not df_dia.empty:
    st.bar_chart(data=df_dia, x="Cliente", y="Espera (min)")
else:
    st.info("Nenhum atendimento registrado nesta data.")

# === Tabela ===
st.subheader("📋 Atendimentos do Dia")
colunas = ["Cliente", "Funcionário", "Hora Chegada", "Hora Início", "Hora Saída", "Espera (min)", "Atendimento (min)", "Tempo Total (min)"]
st.dataframe(df_dia[colunas], use_container_width=True)

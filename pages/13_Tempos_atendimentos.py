
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from utils import carregar_dados_google_sheets

st.set_page_config(page_title="Tempos por Atendimento", layout="wide")
st.markdown("## ⏱️ Tempos por Atendimento")

# Carrega dados direto do Google Sheets
df = carregar_dados_google_sheets()

# Converte datas e horas
df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
for coluna in ["Hora Chegada", "Hora Início", "Hora Saída"]:
    df[coluna] = pd.to_datetime(df[coluna], format="%H:%M:%S", errors="coerce")

# Cria colunas de tempo
df["Espera (min)"] = (df["Hora Início"] - df["Hora Chegada"]).dt.total_seconds() / 60
df["Atendimento (min)"] = (df["Hora Saída"] - df["Hora Início"]).dt.total_seconds() / 60
df["Tempo Total (min)"] = (df["Hora Saída"] - df["Hora Chegada"]).dt.total_seconds() / 60

# Define data padrão com segurança
datas_disponiveis = df["Data"].dropna().dt.date.unique()
data_padrao = max(datas_disponiveis) if len(datas_disponiveis) > 0 else pd.to_datetime("today").date()
data_sel = st.sidebar.date_input("Selecionar data", value=data_padrao)

# Filtra os dados
df_dia = df[df["Data"].dt.date == data_sel].copy()
df_dia = df_dia.dropna(subset=["Hora Chegada", "Hora Início", "Hora Saída"], how="any")

# Indicadores
col1, col2, col3, col4 = st.columns(4)
col1.metric("Clientes atendidos", len(df_dia))
col2.metric("Média de Espera", f"{df_dia['Espera (min)'].mean():.0f} min" if not df_dia.empty else "-")
col3.metric("Média Atendimento", f"{df_dia['Atendimento (min)'].mean():.0f} min" if not df_dia.empty else "-")
col4.metric("Tempo Total Médio", f"{df_dia['Tempo Total (min)'].mean():.0f} min" if not df_dia.empty else "-")

# Gráfico
st.markdown("### 🕓 Gráfico - Tempo de Espera por Cliente")
if df_dia.empty:
    st.info("Nenhum atendimento registrado nesta data.")
else:
    fig = px.bar(df_dia, x="Cliente", y="Espera (min)", color="Funcionário", title="Tempo de Espera por Cliente")
    st.plotly_chart(fig, use_container_width=True)

# Tabela
st.markdown("### 📋 Atendimentos do Dia")
colunas_exibir = ["Cliente", "Funcionário", "Hora Chegada", "Hora Início", "Hora Saída", 
                  "Espera (min)", "Atendimento (min)", "Tempo Total (min)"]
st.dataframe(df_dia[colunas_exibir], use_container_width=True)

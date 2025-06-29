
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="⏱️ Tempos por Atendimento", layout="wide")
st.title("⏱️ Tempos por Atendimento")

# URL da aba "Base de Dados" no formato CSV direto
url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"

df = pd.read_csv(url)

# Garantir que colunas de data e hora sejam tratadas corretamente
df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
for col in ["Hora Chegada", "Hora Início", "Hora Saída"]:
    df[col] = pd.to_datetime(df[col], errors="coerce").dt.time

# Filtro por data disponível
datas_unicas = sorted(df["Data"].dropna().unique())
data_sel = st.sidebar.date_input("Selecione uma data", value=max(datas_unicas)).strftime("%Y-%m-%d")

df_hora = df[df["Data"].dt.strftime("%Y-%m-%d") == data_sel].copy()

st.subheader(f"📅 Registros do dia {data_sel}: {len(df_hora)}")

# Calcular tempos (em minutos)
def calcula_tempos(row):
    try:
        chegada = pd.to_datetime(str(row["Hora Chegada"]))
        inicio = pd.to_datetime(str(row["Hora Início"]))
        saida = pd.to_datetime(str(row["Hora Saída"]))
        espera = (inicio - chegada).total_seconds() / 60 if pd.notnull(chegada) and pd.notnull(inicio) else None
        atendimento = (saida - inicio).total_seconds() / 60 if pd.notnull(inicio) and pd.notnull(saida) else None
        total = (saida - chegada).total_seconds() / 60 if pd.notnull(chegada) and pd.notnull(saida) else None
        return pd.Series([espera, atendimento, total])
    except:
        return pd.Series([None, None, None])

df_hora[["Espera (min)", "Atendimento (min)", "Tempo Total (min)"]] = df_hora.apply(calcula_tempos, axis=1)

# Indicadores
col1, col2, col3, col4 = st.columns(4)
col1.metric("Clientes atendidos", df_hora["Cliente"].nunique())
col2.metric("Média de Espera", f"{df_hora['Espera (min)'].mean():.1f}" if df_hora["Espera (min)"].notnull().any() else "-")
col3.metric("Média Atendimento", f"{df_hora['Atendimento (min)'].mean():.1f}" if df_hora["Atendimento (min)"].notnull().any() else "-")
col4.metric("Tempo Total Médio", f"{df_hora['Tempo Total (min)'].mean():.1f}" if df_hora["Tempo Total (min)"].notnull().any() else "-")

# Gráfico
st.subheader("🕒 Gráfico - Tempo de Espera por Cliente")
if df_hora["Espera (min)"].notnull().any():
    fig = px.bar(df_hora.sort_values("Espera (min)", ascending=False), x="Cliente", y="Espera (min)", color="Funcionário", text="Espera (min)")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nenhum atendimento registrado nesta data.")

# Tabela completa
st.subheader("📋 Atendimentos do Dia")
st.dataframe(df_hora[["Cliente", "Funcionário", "Hora Chegada", "Hora Início", "Hora Saída",
                      "Espera (min)", "Atendimento (min)", "Tempo Total (min)"]], use_container_width=True)


# (trecho reduzido – incluiremos só a parte resolvida e corrigida)

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# Correção dos Insights da Semana com base nos últimos 7 dias
hoje = datetime.now().date()
ultimos_7_dias = hoje - timedelta(days=6)

df_semana = df_tempo[(df_tempo["Data Group"].dt.date >= ultimos_7_dias) & (df_tempo["Data Group"].dt.date <= hoje)]

st.subheader("🔍 Insights da Semana")
if not df_semana.empty:
    media_semana = df_semana["Duração (min)"].mean()
    total_minutos = df_semana["Duração (min)"].sum()
    mais_rapido = df_semana.nsmallest(1, "Duração (min)")
    mais_lento = df_semana.nlargest(1, "Duração (min)")

    st.markdown(f"**Últimos 7 dias:** {ultimos_7_dias.strftime('%d/%m')} a {hoje.strftime('%d/%m')}")
    st.markdown(f"**Média da semana:** {int(media_semana)} min")
    st.markdown(f"**Total de minutos trabalhados na semana:** {int(total_minutos)} min")
    st.markdown(f"**Mais rápido da semana:** {mais_rapido['Cliente'].values[0]} ({int(mais_rapido['Duração (min)'].values[0])} min)")
    st.markdown(f"**Mais lento da semana:** {mais_lento['Cliente'].values[0]} ({int(mais_lento['Duração (min)'].values[0])} min)")
else:
    st.markdown("Nenhum atendimento registrado nos últimos 7 dias.")

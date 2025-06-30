# Calcula duração do atendimento
df = carregado.copy()
df = df.dropna(subset=["Hora Chegada", "Hora Início", "Hora Saída"])
df["Tempo Espera"] = (df["Hora Início"] - df["Hora Chegada"]).dt.total_seconds() / 60
df["Tempo Atendimento"] = (df["Hora Saída"] - df["Hora Início"]).dt.total_seconds() / 60
df["Tempo Total"] = (df["Hora Saída"] - df["Hora Chegada"]).dt.total_seconds() / 60

# Exibe métricas
col1, col2, col3 = st.columns(3)
col1.metric("⏳ Tempo Médio de Espera", f"{df['Tempo Espera'].mean():.1f} min")
col2.metric("✂️ Tempo Médio de Atendimento", f"{df['Tempo Atendimento'].mean():.1f} min")
col3.metric("🕒 Tempo Médio Total", f"{df['Tempo Total'].mean():.1f} min")

# Gráfico
fig = px.box(df, y="Tempo Atendimento", points="all", title="Distribuição do Tempo de Atendimento")
st.plotly_chart(fig, use_container_width=True)

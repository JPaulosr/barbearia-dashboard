# IMPORTANTE: Continue daqui com os gráficos, rankings e insights como já estavam definidos,
# pois o df_tempo agora está filtrado corretamente e pronto para uso em todo o painel.

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

st.subheader("🚨 Clientes com Espera Acima do Normal")
alvo = st.slider("Defina o tempo limite de espera (min):", 5, 60, 20)
atrasados = df_tempo[df_tempo["Espera (min)"] > alvo]
st.dataframe(atrasados[["Data", "Cliente", "Funcionário", "Espera (min)", "Duração formatada"]], use_container_width=True)

with st.expander("📋 Visualizar dados consolidados"):
    st.dataframe(df_tempo, use_container_width=True)

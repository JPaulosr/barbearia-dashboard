# Substituir no seu app principal
# Aplicando filtros e atualizando todos os blocos com base em df_tempo_filtrado

# APLICAR FILTROS
st.markdown("### 🎯 Aplicando Filtros ao Painel")
df_tempo_filtrado = df_tempo.copy()

if isinstance(periodo, list) and len(periodo) == 2:
    df_tempo_filtrado = df_tempo_filtrado[
        (df_tempo_filtrado["Data Group"] >= pd.to_datetime(periodo[0])) &
        (df_tempo_filtrado["Data Group"] <= pd.to_datetime(periodo[1]))
    ]

df_tempo_filtrado = df_tempo_filtrado[
    df_tempo_filtrado["Funcionário"].isin(funcionario_selecionado)
]

if cliente_busca:
    df_tempo_filtrado = df_tempo_filtrado[
        df_tempo_filtrado["Cliente"].str.contains(cliente_busca, case=False, na=False)
    ]

# INSIGHTS
st.subheader("🔍 Insights Filtrados")
if not df_tempo_filtrado.empty:
    media_periodo = df_tempo_filtrado["Duração (min)"].mean()
    total_minutos = df_tempo_filtrado["Duração (min)"].sum()
    mais_rapido = df_tempo_filtrado.nsmallest(1, "Duração (min)")
    mais_lento = df_tempo_filtrado.nlargest(1, "Duração (min)")

    st.markdown(f"**Período Selecionado:** {periodo[0].strftime('%d/%m')} a {periodo[1].strftime('%d/%m')}")
    st.markdown(f"**Média no período:** {int(media_periodo)} min")
    st.markdown(f"**Total de minutos:** {int(total_minutos)} min")
    st.markdown(f"**Mais rápido:** {mais_rapido['Cliente'].values[0]} ({int(mais_rapido['Duração (min)'].values[0])} min)")
    st.markdown(f"**Mais lento:** {mais_lento['Cliente'].values[0]} ({int(mais_lento['Duração (min)'].values[0])} min)")
else:
    st.warning("Nenhum atendimento no período selecionado.")

# RANKINGS
st.subheader("🏆 Rankings de Tempo por Atendimento")
col1, col2 = st.columns(2)
with col1:
    top_mais_rapidos = df_tempo_filtrado.nsmallest(10, "Duração (min)")
    st.markdown("### Mais Rápidos")
    st.dataframe(top_mais_rapidos[["Data", "Cliente", "Funcionário", "Tipo", "Hora Início", "Hora Saída", "Duração formatada", "Espera (min)"]], use_container_width=True)
with col2:
    top_mais_lentos = df_tempo_filtrado.nlargest(10, "Duração (min)")
    st.markdown("### Mais Lentos")
    st.dataframe(top_mais_lentos[["Data", "Cliente", "Funcionário", "Tipo", "Hora Início", "Hora Saída", "Duração formatada", "Espera (min)"]], use_container_width=True)

# EXEMPLO DE UM GRÁFICO FILTRADO
st.subheader("📊 Tempo Médio por Tipo de Serviço")
media_tipo = df_tempo_filtrado.groupby("Categoria")["Duração (min)"].mean().reset_index()
media_tipo["Duração formatada"] = media_tipo["Duração (min)"].apply(lambda x: f"{int(x // 60)}h {int(x % 60)}min")
fig_tipo = px.bar(media_tipo, x="Categoria", y="Duração (min)", text="Duração formatada", title="Tempo Médio por Tipo de Serviço")
fig_tipo.update_traces(textposition='outside')
fig_tipo.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_tipo, use_container_width=True)

# Você pode aplicar df_tempo_filtrado nos demais gráficos e análises da mesma forma.

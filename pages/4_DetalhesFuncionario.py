# === Insights do Funcionário ===
st.subheader("📌 Insights do Funcionário")

# Total de atendimentos
total_atendimentos = df_func.shape[0]

# Total de receita
total_receita = df_func["Valor"].sum()

# Receita média por atendimento
ticket_medio_geral = df_func["Valor"].mean()

# Clientes únicos
clientes_unicos = df_func["Cliente"].nunique()

# Dias com mais atendimentos
atend_por_dia = df_func.groupby(df_func["Data"].dt.date).size().reset_index(name="Atendimentos")
dia_mais_cheio = atend_por_dia.sort_values("Atendimentos", ascending=False).head(1)

col1, col2, col3, col4 = st.columns(4)
col1.metric("🔢 Total de atendimentos", total_atendimentos)
col2.metric("👥 Clientes únicos", clientes_unicos)
col3.metric("💰 Receita total", f"R$ {total_receita:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col4.metric("🎫 Ticket médio", f"R$ {ticket_medio_geral:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

if not dia_mais_cheio.empty:
    data_cheia = pd.to_datetime(dia_mais_cheio["Data"].values[0]).strftime("%d/%m/%Y")
    qtd_atend = int(dia_mais_cheio["Atendimentos"].values[0])
    st.info(f"📅 Dia com mais atendimentos: **{data_cheia}** com **{qtd_atend} atendimentos**")

# === Gráfico: Distribuição por dia da semana ===
st.markdown("### 📆 Atendimentos por dia da semana")
dias_semana = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
df_func["DiaSemana"] = df_func["Data"].dt.dayofweek.map(dias_semana)
grafico_semana = df_func.groupby("DiaSemana").size().reset_index(name="Qtd Atendimentos")
grafico_semana = grafico_semana.sort_values(by="Qtd Atendimentos", ascending=False)

fig_dias = px.bar(grafico_semana, x="DiaSemana", y="Qtd Atendimentos",
                  labels={"DiaSemana": "Dia da Semana", "Qtd Atendimentos": "Qtd Atendimentos"},
                  text_auto=True)
fig_dias.update_layout(height=400, template="plotly_white")
st.plotly_chart(fig_dias, use_container_width=True)

# === Média de atendimentos por dia do mês ===
st.markdown("### 📅 Média de atendimentos por dia do mês")
df_func["Dia"] = df_func["Data"].dt.day
media_por_dia = df_func.groupby("Dia").size().reset_index(name="Qtd Atendimentos")
media_por_dia["Média por dia"] = media_por_dia["Qtd Atendimentos"]

fig_dia_mes = px.line(media_por_dia, x="Dia", y="Média por dia", markers=True,
                      labels={"Dia": "Dia do Mês", "Média por dia": "Média de Atendimentos"})
fig_dia_mes.update_layout(height=400, template="plotly_white")
st.plotly_chart(fig_dia_mes, use_container_width=True)

# === Comparativo com a média dos outros funcionários ===
st.markdown("### ⚖️ Comparação com a média dos outros funcionários")
todos_func_mesmo_ano = df[df["Ano"] == ano_escolhido].copy()
media_geral = todos_func_mesmo_ano.groupby("Funcionário")["Valor"].mean().reset_index(name="Ticket Médio")
media_geral["Ticket Médio Formatado"] = media_geral["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.dataframe(media_geral[["Funcionário", "Ticket Médio Formatado"]].sort_values("Ticket Médio", ascending=False), use_container_width=True)

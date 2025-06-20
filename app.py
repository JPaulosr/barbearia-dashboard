# Gráfico de Receita por Mês
st.subheader("📅 Receita por Mês")

anos_disponiveis = sorted(df["Ano"].dropna().unique())
ano_mes_filtro = st.selectbox("🔎 Selecione o Ano para ver a Receita Mensal", anos_disponiveis)

df_filtrado = df[df["Ano"] == ano_mes_filtro]
receita_mes = df_filtrado.groupby("Mês")["Valor"].sum().reset_index()

# Mês com nome e valor formatado
meses_nome = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"
}
receita_mes["Mês"] = receita_mes["Mês"].map(meses_nome)
receita_mes["Valor Formatado"] = receita_mes["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

fig_mes = px.bar(
    receita_mes,
    x="Mês",
    y="Valor",
    text="Valor Formatado",
    labels={"Valor": "Faturamento"},
)
fig_mes.update_layout(
    xaxis_title="Mês",
    yaxis_title="Receita (R$)",
    template="plotly_white"
)
st.plotly_chart(fig_mes, use_container_width=True)

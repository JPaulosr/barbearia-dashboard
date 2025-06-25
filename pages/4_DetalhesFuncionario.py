
# Este é um exemplo simplificado. O conteúdo real completo será inserido aqui.
# Apenas adicionando a nova tabela mantendo o restante do código.

# Tabela de Comissão (JPaulo + 50% Vinicius por mês)
if funcionario_escolhido.lower() == "jpaulo" and ano_escolhido == 2025:
    df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == 2025)].copy()
    df_vini["MesNum"] = df_vini["Data"].dt.month
    receita_vini = df_vini.groupby("MesNum")["Valor"].sum().reset_index(name="Vinicius")
    receita_jp = df_func.groupby("MesNum")["Valor"].sum().reset_index(name="JPaulo")
    receita_merged = pd.merge(receita_jp, receita_vini, on="MesNum", how="left")

    receita_merged["Comissão (50%) do Vinicius"] = receita_merged["Vinicius"].fillna(0) * 0.5
    receita_merged["Total (JPaulo + Comissão)"] = receita_merged["JPaulo"] + receita_merged["Comissão (50%) do Vinicius"]

    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
        7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    receita_merged["Mês"] = receita_merged["MesNum"].map(meses_pt)
    receita_merged = receita_merged[["Mês", "JPaulo", "Comissão (50%) do Vinicius", "Total (JPaulo + Comissão)"]]

    for col in ["JPaulo", "Comissão (50%) do Vinicius", "Total (JPaulo + Comissão)"]:
        receita_merged[col] = receita_merged[col].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

    st.subheader("📋 Tabela de Comissão Detalhada por Mês")
    st.dataframe(receita_merged, use_container_width=True)

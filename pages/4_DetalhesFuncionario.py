# === Receita mensal ===
st.subheader("📊 Receita Mensal por Mês e Ano")

meses_pt = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

df_func["MesNum"] = df_func["Data"].dt.month
df_func["MesNome"] = df_func["MesNum"].map(meses_pt) + df_func["Data"].dt.strftime(" %Y")
receita_jp = df_func.groupby(["MesNum", "MesNome"])["Valor"].sum().reset_index(name="JPaulo")
receita_jp = receita_jp.sort_values("MesNum")

# Comissão real do Vinicius (sem filtro de serviço)
df_com_vinicius = df_despesas[
    (df_despesas["Prestador"] == "Vinicius") &
    (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
    (df_despesas["Ano"] == 2025)
].copy()
df_com_vinicius["MesNum"] = df_com_vinicius["Data"].dt.month
df_com_vinicius = df_com_vinicius.groupby("MesNum")["Valor"].sum().reset_index(name="Comissão (real) do Vinicius")

# Detecta se há filtro
filtro_ativo = bool(tipo_selecionado)

if funcionario_escolhido.lower() == "jpaulo" and ano_escolhido == 2025:
    if not filtro_ativo:
        receita_merged = receita_jp.merge(df_com_vinicius, on="MesNum", how="left").fillna(0)
        receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["Comissão (real) do Vinicius"]

        receita_melt = receita_merged.melt(
            id_vars=["MesNum", "MesNome"],
            value_vars=["JPaulo", "Com_Vinicius"],
            var_name="Tipo", value_name="Valor"
        )
    else:
        receita_merged = receita_jp.copy()
        receita_melt = receita_merged.rename(columns={"JPaulo": "Valor"})
        receita_melt["Tipo"] = "JPaulo"

    receita_melt = receita_melt.sort_values("MesNum")

    fig_mensal_comp = px.bar(receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
                             labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""})
    fig_mensal_comp.update_layout(height=450, template="plotly_white")
    st.plotly_chart(fig_mensal_comp, use_container_width=True)

    if not filtro_ativo:
        receita_merged["Comissão (real) do Vinicius"] = receita_merged["Comissão (real) do Vinicius"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
        receita_merged["JPaulo Formatado"] = receita_merged["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
        receita_merged["Total (JPaulo + Comissão)"] = receita_merged["Com_Vinicius"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

        tabela = receita_merged[["MesNome", "JPaulo Formatado", "Comissão (real) do Vinicius", "Total (JPaulo + Comissão)"]]
        tabela.columns = ["Mês", "Receita JPaulo", "Comissão (real) do Vinicius", "Total (JPaulo + Comissão)"]
        st.dataframe(tabela, use_container_width=True)
else:
    receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    fig_mensal = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                        labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
    fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
    fig_mensal.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_mensal, use_container_width=True)

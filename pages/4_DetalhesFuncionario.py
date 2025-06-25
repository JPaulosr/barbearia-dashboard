# === Receita mensal (condicional por ano e funcionário) ===
st.subheader("📊 Receita Mensal por Mês e Ano")

# Nomes dos meses em português
meses_pt = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

df_func["Mes"] = df_func["Data"].dt.month
df_func["MesNome"] = df_func["Mes"].map(meses_pt)

# Agrupar receita mensal de JPaulo
receita_jp = df_func.groupby(["Mes", "MesNome"])["Valor"].sum().reset_index(name="JPaulo")
receita_jp = receita_jp.sort_values("Mes")

# Verificações de funcionário e ano
if funcionario_escolhido.lower() == "jpaulo":
    if ano_escolhido < 2025:
        # Somente JPaulo - sem Vinicius
        receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(
            lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
        )
        fig_jp = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                        labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
        fig_jp.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
        fig_jp.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig_jp, use_container_width=True)

    elif ano_escolhido == 2025:
        # JPaulo + Vinicius (50%)
        df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == 2025)].copy()
        df_vini["Mes"] = df_vini["Data"].dt.month
        df_vini["MesNome"] = df_vini["Mes"].map(meses_pt)
        receita_vini = df_vini.groupby(["Mes", "MesNome"])["Valor"].sum().reset_index(name="Vinicius")

        receita_merged = pd.merge(receita_jp, receita_vini, on=["Mes", "MesNome"], how="left")
        receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["Vinicius"].fillna(0) * 0.5

        receita_melt = receita_merged.melt(
            id_vars=["Mes", "MesNome"], 
            value_vars=["JPaulo", "Com_Vinicius"], 
            var_name="Tipo", 
            value_name="Valor"
        )
        receita_melt = receita_melt.sort_values("Mes")

        fig_mensal_comp = px.bar(
            receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
            labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""}
        )
        fig_mensal_comp.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
        st.plotly_chart(fig_mensal_comp, use_container_width=True)

else:
    # Funcionário não é JPaulo — exibir gráfico padrão
    receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(
        lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
    )
    receita_jp = receita_jp.sort_values("Mes")

    fig_mensal = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                        labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
    fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
    fig_mensal.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_mensal, use_container_width=True)

# === Receita mensal lado a lado (JPaulo vs JPaulo + Vinicius 50%) ===
st.subheader("\U0001F4CA Receita Mensal por Mês e Ano")

# Criar colunas auxiliares
df_func["Mes"] = df_func["Data"].dt.month
df_func["MesNome"] = df_func["Data"].dt.strftime("%B")
df_func["MesNome"] = pd.Categorical(df_func["MesNome"], categories=[
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
], ordered=True)

# Ajustar nome em português
df_func["MesNome"] = df_func["Data"].dt.strftime("%m - %B").str.capitalize()

# Agrupar receita mensal
receita_jp = df_func.groupby(["Mes", "MesNome"])["Valor"].sum().reset_index(name="JPaulo")

if funcionario_escolhido.lower() == "jpaulo":
    df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == 2025)].copy()
    df_vini["Mes"] = df_vini["Data"].dt.month
    df_vini["MesNome"] = df_vini["Data"].dt.strftime("%m - %B").str.capitalize()

    receita_vini = df_vini.groupby(["Mes", "MesNome"])["Valor"].sum().reset_index(name="Vinicius")
    receita_merged = pd.merge(receita_jp, receita_vini, on=["Mes", "MesNome"], how="left")
    receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["Vinicius"].fillna(0) * 0.5

    receita_melt = receita_merged.melt(id_vars=["Mes", "MesNome"], value_vars=["JPaulo", "Com_Vinicius"],
                                       var_name="Tipo", value_name="Valor")
    receita_melt = receita_melt.sort_values("Mes")

    fig_mensal_comp = px.bar(receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
                              labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""})
    fig_mensal_comp.update_layout(height=450, template="plotly_white")
    st.plotly_chart(fig_mensal_comp, use_container_width=True)

else:
    receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    receita_jp = receita_jp.sort_values("Mes")

    fig_mensal = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                        labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
    fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
    fig_mensal.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_mensal, use_container_width=True)

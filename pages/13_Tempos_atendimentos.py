# -*- coding: utf-8 -*-
# Bloco adicional para: Tempo Trabalhado x Tempo Ocioso
st.subheader("Tempo Trabalhado x Tempo Ocioso")

def calcular_ociosidade(df):
    df_ordenado = df.sort_values(by=["Funcionário", "Data Group", "Hora Início dt"]).copy()
    df_ordenado["Próximo Início"] = df_ordenado.groupby(["Funcionário", "Data Group"])["Hora Início dt"].shift(-1)
    df_ordenado["Hora Saída dt"] = pd.to_datetime(df_ordenado["Hora Saída"], format="%H:%M", errors="coerce")
    df_ordenado["Ociosidade (min)"] = (df_ordenado["Próximo Início"] - df_ordenado["Hora Saída dt"]).dt.total_seconds() / 60
    df_ordenado["Ociosidade (min)"] = df_ordenado["Ociosidade (min)"].apply(lambda x: x if x is not None and x > 0 else 0)
    return df_ordenado

df_ocioso = calcular_ociosidade(df_tempo)

tempo_trabalhado = df_ocioso.groupby("Funcionário")["Duração (min)"].sum()
tempo_ocioso = df_ocioso.groupby("Funcionário")["Ociosidade (min)"].sum()

df_comp = pd.DataFrame({
    "Trabalhado (min)": tempo_trabalhado,
    "Ocioso (min)": tempo_ocioso
})
df_comp["Total (min)"] = df_comp["Trabalhado (min)"] + df_comp["Ocioso (min)"]
df_comp["% Ocioso"] = (df_comp["Ocioso (min)"] / df_comp["Total (min)"] * 100).round(1)
df_comp["Trabalhado (h)"] = df_comp["Trabalhado (min)"].apply(lambda x: f"{int(x//60)}h {int(x%60)}min")
df_comp["Ocioso (h)"] = df_comp["Ocioso (min)"].apply(lambda x: f"{int(x//60)}h {int(x%60)}min")

st.dataframe(df_comp[["Trabalhado (h)", "Ocioso (h)", "% Ocioso"]], use_container_width=True)

fig_bar = px.bar(df_comp.reset_index().melt(id_vars="Funcionário", value_vars=["Trabalhado (min)", "Ocioso (min)"]),
                 x="Funcionário", y="value", color="variable", barmode="group",
                 title="Comparativo de Tempo por Funcionário")
fig_bar.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig_bar, use_container_width=True)

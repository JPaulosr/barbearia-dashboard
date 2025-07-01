import streamlit as st
import pandas as pd
import plotly.express as px
from utils.google_sheets import carregar_dados_google_sheets
from utils.utils import aplicar_filtros

st.set_page_config(layout="wide")
st.title("👨‍💼 Detalhes do Funcionário")

df, df_despesas = carregar_dados_google_sheets()
df["Data"] = pd.to_datetime(df["Data"])
df_despesas["Data"] = pd.to_datetime(df_despesas["Data"])
df["Ano"] = df["Data"].dt.year
df["Mes"] = df["Data"].dt.month
df["Dia"] = df["Data"].dt.day
df["DiaSemana"] = df["Data"].dt.strftime("%a")
df["Semana"] = df["Data"].dt.isocalendar().week

df["DiaSemana"] = df["DiaSemana"].map({
    "Mon": "Seg",
    "Tue": "Ter",
    "Wed": "Qua",
    "Thu": "Qui",
    "Fri": "Sex",
    "Sat": "Sáb",
    "Sun": "Dom"
})

anos_disponiveis = sorted(df["Ano"].unique(), reverse=True)
ano_escolhido = st.selectbox("🗕️ Filtrar por ano", anos_disponiveis)
meses_disponiveis = ["Todos"] + sorted(df[df["Ano"] == ano_escolhido]["Mes"].unique())
mes_filtro = st.selectbox("🗖️ Filtrar por mês", meses_disponiveis)
dias_disponiveis = ["Todos"] + sorted(df[df["Ano"] == ano_escolhido]["Dia"].unique())
dia_filtro = st.selectbox("🗕️ Filtrar por dia", dias_disponiveis)
semanas_disponiveis = df[df["Ano"] == ano_escolhido]["Semana"].unique().tolist()
semanas_disponiveis.sort()
semana_filtro = st.selectbox("📈 Filtrar por semana", ["Todos"] + semanas_disponiveis)
funcionarios_disponiveis = sorted(df["Profissional"].dropna().unique())
funcionario_escolhido = st.selectbox("🧕‍♂️ Escolha um funcionário", funcionarios_disponiveis)

df_func = aplicar_filtros(df, ano_escolhido, mes_filtro, dia_filtro, funcionario_escolhido, semana_filtro)
total_atendimentos = len(df_func)
clientes_unicos = df_func["Cliente"].nunique()
receita_total = df_func["Valor"].sum()
ticket_medio = receita_total / total_atendimentos if total_atendimentos > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("📊 Total de atendimentos", total_atendimentos)
col2.metric("🧑‍🧳 Clientes únicos", clientes_unicos)
col3.metric("💰 Receita total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col4.metric("💳 Ticket médio", f"R$ {ticket_medio:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

if not df_func.empty:
    dia_top = df_func.groupby("Data").size().sort_values(ascending=False).reset_index()
    dia_max = dia_top.iloc[0]["Data"].strftime("%d/%m/%Y")
    qtd_max = dia_top.iloc[0][0]
    st.info(f"🗓️ Dia com mais atendimentos: **{dia_max}** com **{qtd_max} atendimentos**")

st.subheader("🗓️ Atendimentos por dia da semana")
grafico_semana = df_func.groupby("DiaSemana").size().reset_index(name="Qtd Atendimentos").sort_values("DiaSemana", key=lambda x: x.map({"Seg":0, "Ter":1, "Qua":2, "Qui":3, "Sex":4, "Sáb":5, "Dom":6}))
st.bar_chart(grafico_semana.set_index("DiaSemana"), use_container_width=True)

st.subheader("🗖️ Média de atendimentos por dia do mês")
grafico_dia = df_func.groupby("Dia").size().reset_index(name="Média por dia")
fig_dia = px.line(grafico_dia, x="Dia", y="Média por dia")
st.plotly_chart(fig_dia, use_container_width=True)

st.subheader("⚖️ Comparativo com a média dos outros funcionários")
media_geral = df.groupby("Profissional")["Valor"].agg(["count", "sum"]).reset_index()
media_geral["Ticket Médio"] = media_geral["sum"] / media_geral["count"]
media_geral["Ticket Médio Formatado"] = media_geral["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(media_geral[["Profissional", "count", "Ticket Médio Formatado"]].sort_values("Ticket Médio", ascending=False), use_container_width=True)

if funcionario_escolhido.lower() == "vinicius":
    bruto = df_func["Valor"].sum()

    if mes_filtro != "Todos":
        despesas_filtradas = df_despesas[
            (df_despesas["Prestador"] == "Vinicius") &
            (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
            (df_despesas["Ano"] == ano_escolhido) &
            (df_despesas["Data"].dt.month == mes_filtro)
        ]
    else:
        despesas_filtradas = df_despesas[
            (df_despesas["Prestador"] == "Vinicius") &
            (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
            (df_despesas["Ano"] == ano_escolhido)
        ]

    comissao_real = despesas_filtradas["Valor"].sum()
    receita_liquida = comissao_real
    receita_salao = bruto - comissao_real

    comparativo_vinicius = pd.DataFrame({
        "Tipo de Receita": [
            "Receita Bruta de Vinicius",
            "Receita de Vinicius (comissão real)",
            "Valor que ficou para o salão"
        ],
        "Valor": [
            bruto,
            receita_liquida,
            receita_salao
        ]
    })
    comparativo_vinicius["Valor Formatado"] = comparativo_vinicius["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    st.subheader("💸 Receita Real do Vinicius e Lucro para o Salão")
    st.dataframe(comparativo_vinicius[["Tipo de Receita", "Valor Formatado"]], use_container_width=True)

    fig_receita = px.bar(comparativo_vinicius, x="Tipo de Receita", y="Valor", text="Valor Formatado", title="Comparativo de Receita do Vinicius")
    fig_receita.update_traces(textposition="outside")
    st.plotly_chart(fig_receita, use_container_width=True)

    st.subheader("📊 Evolução mensal: Receita Bruta x Comissão x Receita Líquida")
    df_func["AnoMes"] = df_func["Data"].dt.to_period("M")
    bruto_mensal = df_func.groupby("AnoMes")["Valor"].sum().reset_index(name="Receita Bruta")

    despesas_vini = df_despesas[
        (df_despesas["Prestador"] == "Vinicius") &
        (df_despesas["Descrição"].str.contains("comissão", case=False, na=False))
    ].copy()
    despesas_vini["AnoMes"] = despesas_vini["Data"].dt.to_period("M")
    comissao_mensal = despesas_vini.groupby("AnoMes")["Valor"].sum().reset_index(name="Comissão Real")

    comparativo_mensal = pd.merge(bruto_mensal, comissao_mensal, on="AnoMes", how="left").fillna(0)
    comparativo_mensal["Lucro Salão"] = comparativo_mensal["Receita Bruta"] - comparativo_mensal["Comissão Real"]

    fig_comp = px.bar(
        comparativo_mensal.melt(id_vars="AnoMes", value_vars=["Receita Bruta", "Comissão Real", "Lucro Salão"]),
        x="AnoMes", y="value", color="variable",
        title="Comparativo Mensal das Receitas - Vinicius",
        barmode="group"
    )
    st.plotly_chart(fig_comp, use_container_width=True)

st.subheader("🔽 Ticket Médio por Mês")
df_func["AnoMes"] = df_func["Data"].dt.to_period("M")
ticket_mensal = df_func.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")
ticket_mensal["Ticket Médio Formatado"] = ticket_mensal["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(ticket_mensal, use_container_width=True)

st.subheader("📄 Exportar dados filtrados")
st.dataframe(df_func, use_container_width=True)

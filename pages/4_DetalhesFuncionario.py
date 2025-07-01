import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode
from io import BytesIO
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🧑‍💼 Detalhes do Funcionário")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    return df

df = carregar_dados()

@st.cache_data
def carregar_despesas():
    planilha = conectar_sheets()
    aba_desp = planilha.worksheet("Despesas")
    df_desp = get_as_dataframe(aba_desp).dropna(how="all")
    df_desp.columns = [str(col).strip() for col in df_desp.columns]
    df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce")
    df_desp = df_desp.dropna(subset=["Data"])
    df_desp["Ano"] = df_desp["Data"].dt.year.astype(int)
    return df_desp

df_despesas = carregar_despesas()

# === Lista de funcionários ===
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

# === Filtro por ano ===
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("🗕️ Filtrar por ano", anos)

# === Filtros adicionais ===
col_filtros = st.columns(3)

# === Seleção de funcionário ===
funcionario_escolhido = st.selectbox("📋 Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionário"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)].copy()

# Filtro por mês
meses_disponiveis = df_func["Data"].dt.month.unique()
meses_disponiveis.sort()
mes_filtro = col_filtros[0].selectbox("📆 Filtrar por mês", options=["Todos"] + list(meses_disponiveis))
if mes_filtro != "Todos":
    df_func = df_func[df_func["Data"].dt.month == mes_filtro]

# Filtro por dia
dias_disponiveis = df_func["Data"].dt.day.unique()
dias_disponiveis.sort()
dia_filtro = col_filtros[1].selectbox("📅 Filtrar por dia", options=["Todos"] + list(dias_disponiveis))
if dia_filtro != "Todos":
    df_func = df_func[df_func["Data"].dt.day == dia_filtro]

# Filtro por semana
df_func["Semana"] = df_func["Data"].dt.isocalendar().week
semanas_disponiveis = df_func["Semana"].unique().tolist()
# semanas_disponiveis já convertido para lista acima, agora pode ordenar
semanas_disponiveis.sort()
semana_filtro = col_filtros[2].selectbox("🗓️ Filtrar por semana", options=["Todas"] + list(semanas_disponiveis))
if semana_filtro != "Todas":
    df_func = df_func[df_func["Semana"] == semana_filtro]

# === Filtro por tipo de serviço ===
tipos_servico = df_func["Serviço"].dropna().unique().tolist()
tipo_selecionado = st.multiselect("Filtrar por tipo de serviço", tipos_servico)
if tipo_selecionado:
    df_func = df_func[df_func["Serviço"].isin(tipo_selecionado)]

# === Insights do Funcionário ===
st.subheader("📌 Insights do Funcionário")

# KPIs
col1, col2, col3, col4 = st.columns(4)
total_atendimentos = df_func.shape[0]
clientes_unicos = df_func["Cliente"].nunique()
total_receita = df_func["Valor"].sum()
ticket_medio_geral = df_func["Valor"].mean()

col1.metric("🔢 Total de atendimentos", total_atendimentos)
col2.metric("👥 Clientes únicos", clientes_unicos)
col3.metric("💰 Receita total", f"R$ {total_receita:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col4.metric("🎫 Ticket médio", f"R$ {ticket_medio_geral:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

# Dia mais cheio
dia_mais_cheio = df_func.groupby(df_func["Data"].dt.date).size().reset_index(name="Atendimentos").sort_values("Atendimentos", ascending=False).head(1)
if not dia_mais_cheio.empty:
    data_cheia = pd.to_datetime(dia_mais_cheio.iloc[0, 0]).strftime("%d/%m/%Y")
    qtd_atend = int(dia_mais_cheio.iloc[0, 1])
    st.info(f"📅 Dia com mais atendimentos: **{data_cheia}** com **{qtd_atend} atendimentos**")

# Gráfico: Distribuição por dia da semana
st.markdown("### 📆 Atendimentos por dia da semana")
dias_semana = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
df_func["DiaSemana"] = df_func["Data"].dt.dayofweek.map(dias_semana)
grafico_semana = df_func.groupby("DiaSemana").size().reset_index(name="Qtd Atendimentos").sort_values("DiaSemana", key=lambda x: x.map({"Seg":0, "Ter":1, "Qua":2, "Qui":3, "Sex":4, "Sáb":5, "Dom":6}))
fig_dias = px.bar(grafico_semana, x="DiaSemana", y="Qtd Atendimentos", text_auto=True, template="plotly_white")
st.plotly_chart(fig_dias, use_container_width=True)

# Média de atendimentos por dia do mês
st.markdown("### 🗓️ Média de atendimentos por dia do mês")
df_func["Dia"] = df_func["Data"].dt.day
media_por_dia = df_func.groupby("Dia").size().reset_index(name="Média por dia")
fig_dia_mes = px.line(media_por_dia, x="Dia", y="Média por dia", markers=True, template="plotly_white")
st.plotly_chart(fig_dia_mes, use_container_width=True)

# Comparativo com outros funcionários
st.markdown("### ⚖️ Comparativo com a média dos outros funcionários")
todos_func_mesmo_ano = df[df["Ano"] == ano_escolhido].copy()
media_geral = todos_func_mesmo_ano.groupby("Funcionário")["Valor"].mean().reset_index(name="Ticket Médio")
media_geral["Ticket Médio Formatado"] = media_geral["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
media_ordenada = media_geral.sort_values("Ticket Médio", ascending=False)
st.dataframe(media_ordenada[["Funcionário", "Ticket Médio Formatado"]], use_container_width=True)

# === Histórico de atendimentos ===
st.subheader("🗕️ Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

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

# === Comissão real do Vinicius (não depende de filtro)
df_com_vinicius = df_despesas[
    (df_despesas["Prestador"] == "Vinicius") &
    (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
    (df_despesas["Ano"] == 2025)
].copy()
df_com_vinicius["MesNum"] = df_com_vinicius["Data"].dt.month
df_com_vinicius = df_com_vinicius.groupby("MesNum")["Valor"].sum().reset_index(name="Comissão (real) do Vinicius")

if funcionario_escolhido.lower() == "jpaulo" and ano_escolhido == 2025:
    receita_merged = receita_jp.merge(df_com_vinicius, on="MesNum", how="left").fillna(0)
    receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["Comissão (real) do Vinicius"]

    receita_melt = receita_merged.melt(id_vars=["MesNum", "MesNome"], value_vars=["JPaulo", "Com_Vinicius"],
                                       var_name="Tipo", value_name="Valor")
    receita_melt = receita_melt.sort_values("MesNum")

    fig_mensal_comp = px.bar(receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
                             labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""})
    fig_mensal_comp.update_layout(height=450, template="plotly_white")
    st.plotly_chart(fig_mensal_comp, use_container_width=True)

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

# === Receita Bruta vs Comissão ===
if funcionario_escolhido.lower() == "vinicius":
    bruto = df_func["Valor"].sum()
    comissao_real = df_despesas[
        (df_despesas["Prestador"] == "Vinicius") &
        (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
        (df_despesas["Ano"] == ano_escolhido)
    ]["Valor"].sum()

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

elif funcionario_escolhido.lower() == "jpaulo":
    receita_jpaulo = df_func["Valor"].sum()

    receita_vinicius_total = df[
        (df["Funcionário"] == "Vinicius") &
        (df["Ano"] == ano_escolhido)
    ]["Valor"].sum()

    comissao_paga = df_despesas[
        (df_despesas["Prestador"] == "Vinicius") &
        (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
        (df_despesas["Ano"] == ano_escolhido)
    ]["Valor"].sum()

    receita_liquida_vinicius = receita_vinicius_total - comissao_paga
    receita_total_salao = receita_jpaulo + receita_liquida_vinicius

    receita_total = pd.DataFrame({
        "Origem": [
            "Receita JPaulo",
            "Receita Vinicius (líquida)",
            "Comissão paga ao Vinicius (despesa)",
            "Total receita do salão"
        ],
        "Valor": [
            receita_jpaulo,
            receita_liquida_vinicius,
            comissao_paga,
            receita_total_salao
        ]
    })

    receita_total["Valor Formatado"] = receita_total["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    st.subheader("💰 Receita do Salão (JPaulo como dono)")
    st.dataframe(receita_total[["Origem", "Valor Formatado"]], use_container_width=True)

# === Ticket Médio por Mês ===
st.subheader("📉 Ticket Médio por Mês")
data_referencia = pd.to_datetime("2025-05-11")
df_func["Grupo"] = df_func["Data"].dt.strftime("%Y-%m-%d") + "_" + df_func["Cliente"]
antes_ticket = df_func[df_func["Data"] < data_referencia].copy()
antes_ticket["AnoMes"] = antes_ticket["Data"].dt.to_period("M").astype(str)
antes_ticket = antes_ticket.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")

depois_ticket = df_func[df_func["Data"] >= data_referencia].copy()
depois_ticket = depois_ticket.groupby(["Grupo", "Data"])["Valor"].sum().reset_index()
depois_ticket["AnoMes"] = depois_ticket["Data"].dt.to_period("M").astype(str)
depois_ticket = depois_ticket.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")

ticket_mensal = pd.concat([antes_ticket, depois_ticket]).groupby("AnoMes")["Ticket Médio"].mean().reset_index()
ticket_mensal["Ticket Médio Formatado"] = ticket_mensal["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(ticket_mensal, use_container_width=True)

# === Exportar dados ===
st.subheader("📄 Exportar dados filtrados")
buffer = BytesIO()
df_func.to_excel(buffer, index=False, sheet_name="Filtrado", engine="openpyxl")
st.download_button("Baixar Excel com dados filtrados", data=buffer.getvalue(), file_name="dados_filtrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

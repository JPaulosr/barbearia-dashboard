import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode
from io import BytesIO

st.set_page_config(layout="wide")
st.title("\U0001F9D1‍\U0001F4BC Detalhes do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    return df

df = carregar_dados()

# === Lista de funcionários ===
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

# === Filtro por ano ===
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("\U0001F4C5 Filtrar por ano", anos)

# === Seleção de funcionário ===
funcionario_escolhido = st.selectbox("\U0001F4CB Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionário"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)]

# === Filtro por tipo de serviço ===
tipos_servico = df_func["Serviço"].dropna().unique().tolist()
tipo_selecionado = st.multiselect("Filtrar por tipo de serviço", tipos_servico)
if tipo_selecionado:
    df_func = df_func[df_func["Serviço"].isin(tipo_selecionado)]

# === Normalizar nomes para filtrar genéricos ===
nomes_excluir = ["boliviano", "brasileiro", "menino"]
def limpar_nome(nome):
    nome_limpo = unidecode(str(nome).lower())
    return not any(g in nome_limpo for g in nomes_excluir)

# Histórico de atendimentos (sem remover nomes genéricos)
st.subheader("\U0001F4C5 Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

# Receita mensal correta (sem lógica de agrupamento)
st.subheader("\U0001F4CA Receita Mensal por Mês e Ano")
df_func["AnoMes"] = df_func["Data"].dt.to_period("M").astype(str)
receita_mensal = df_func.groupby("AnoMes")["Valor"].sum().reset_index()
receita_mensal["Valor Formatado"] = receita_mensal["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

fig_mensal = px.bar(receita_mensal, x="AnoMes", y="Valor", text="Valor Formatado", labels={"Valor": "Receita (R$)", "AnoMes": "Ano-Mês"})
fig_mensal.update_layout(height=400, template="plotly_white")
fig_mensal.update_traces(textposition="outside")
st.plotly_chart(fig_mensal, use_container_width=True)

# === Distribuição Combo vs Simples ===
st.subheader("\U0001F4D3 Distribuição: Combo vs Simples")
data_referencia = pd.to_datetime("2025-05-11")
df_func["Grupo"] = df_func["Data"].dt.strftime("%Y-%m-%d") + "_" + df_func["Cliente"]
antes = df_func[df_func["Data"] < data_referencia].copy()
depois = df_func[df_func["Data"] >= data_referencia].copy()
antes["Qtd_Serv"] = 1
depois = depois.groupby("Grupo").agg(Data=("Data", "first"), Cliente=("Cliente", "first"), Qtd_Serv=("Serviço", "count")).reset_index()
df_completo = pd.concat([antes[["Grupo", "Data", "Cliente", "Qtd_Serv"]], depois])
df_completo["Combo"] = df_completo["Qtd_Serv"].apply(lambda x: 1 if x > 1 else 0)
df_completo["Simples"] = df_completo["Qtd_Serv"].apply(lambda x: 1 if x == 1 else 0)

pizza = pd.DataFrame({
    "Tipo": ["Combo", "Simples"],
    "Quantidade": [df_completo["Combo"].sum(), df_completo["Simples"].sum()]
})
fig_pizza = px.pie(pizza, names="Tipo", values="Quantidade", hole=0.4)
fig_pizza.update_traces(textinfo="percent+label")
st.plotly_chart(fig_pizza, use_container_width=True)

# === Ticket Médio por Mês (usando df_completo) ===
st.subheader("\U0001F4C9 Ticket Médio por Mês")
df_completo["AnoMes"] = df_completo["Data"].dt.to_period("M").astype(str)
df_valor = df_func.groupby("Grupo")["Valor"].sum().reset_index()
df_completo = df_completo.merge(df_valor, on="Grupo", how="left")
ticket_mensal = df_completo.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")
ticket_mensal["Ticket Médio Formatado"] = ticket_mensal["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(ticket_mensal, use_container_width=True)

# === Exportar dados ===
st.subheader("\U0001F4E5 Exportar dados filtrados")
buffer = BytesIO()
df_func.to_excel(buffer, index=False, sheet_name="Filtrado", engine="openpyxl")
st.download_button("Baixar Excel com dados filtrados", data=buffer.getvalue(), file_name="dados_filtrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

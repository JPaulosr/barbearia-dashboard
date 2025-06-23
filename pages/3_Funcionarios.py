import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
from datetime import datetime

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano-Mês"] = df["Data"].dt.to_period("M").astype(str)
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    return df

df = carregar_dados()

# Recupera funcionário do session_state ou do arquivo temporário
funcionario = st.session_state.get("funcionario")
if not funcionario:
    if os.path.exists("temp_funcionario.json"):
        with open("temp_funcionario.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            funcionario = data.get("funcionario")
        st.session_state["funcionario"] = funcionario

# Alternativa: Selecionar funcionário manualmente
if not funcionario:
    funcionarios_disp = df["Funcionário"].dropna().unique().tolist()
    funcionario = st.selectbox("🧑 Selecione um funcionário", funcionarios_disp)
    st.session_state["funcionario"] = funcionario

if not funcionario:
    st.warning("⚠️ Nenhum funcionário selecionado.")
    st.stop()

# Filtro de mês vindo da session_state
meses_filtrados = st.session_state.get("meses", [])
if meses_filtrados:
    df = df[df["Ano-Mês"].isin(meses_filtrados)]

# Filtra os dados para o funcionário
df_func = df[df["Funcionário"] == funcionario]

# Filtros de ano e mês
st.sidebar.header("🗓️ Filtros de Período")
ano_atual = datetime.today().year
anos = sorted(df_func["Ano"].dropna().unique())
meses = sorted(df_func["Mês"].dropna().unique())

ano_selec = st.sidebar.selectbox("Ano", options=anos, index=anos.index(ano_atual) if ano_atual in anos else 0)
mês_selec = st.sidebar.multiselect("Mês", options=meses, default=meses)

df_func = df_func[(df_func["Ano"] == ano_selec) & (df_func["Mês"].isin(mês_selec))]

# Título e filtros
st.markdown(f"### 📈 Receita mensal total - {funcionario}")

# Filtros opcionais
meses_disp = sorted(df_func["Ano-Mês"].unique())
servicos_disp = sorted(df_func["Serviço"].dropna().unique())

meses_selec = st.multiselect("🕵️ Filtrar por mês (opcional)", meses_disp, default=meses_disp)
servicos_selec = st.multiselect("🧾 Filtrar por serviço", servicos_disp, default=servicos_disp)

df_filt = df_func[
    df_func["Ano-Mês"].isin(meses_selec) & df_func["Serviço"].isin(servicos_selec)
]

# Gráfico de receita mensal total
st.markdown("### 📊 Receita mensal total")

df_agrupado = df_filt.groupby("Ano-Mês")["Valor"].sum().reset_index()
df_agrupado["Valor"] = pd.to_numeric(df_agrupado["Valor"], errors="coerce")
df_agrupado["Valor Formatado"] = df_agrupado["Valor"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)

if not df_agrupado.empty:
    fig = px.bar(
        df_agrupado,
        x="Ano-Mês",
        y="Valor",
        text="Valor Formatado",
        title="📈 Receita mensal total"
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        height=500,
        showlegend=False,
        yaxis_title="Valor (R$)",
        yaxis_tickformat=".2f"
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nenhum dado disponível para os filtros selecionados.")

# Receita e atendimentos por mês
st.markdown("### 💰 Receita total e atendimentos por mês")

df_total_mes = df_filt.groupby("Ano-Mês")["Valor"].sum().reset_index()
df_total_mes.columns = ["Ano-Mês", "Valor"]

df_filt["Data"] = pd.to_datetime(df_filt["Data"])
data_limite = pd.to_datetime("2025-05-11")
antes = df_filt[df_filt["Data"] < data_limite]
depois = df_filt[df_filt["Data"] >= data_limite].drop_duplicates(subset=["Cliente", "Data"])
df_visitas = pd.concat([antes, depois])
df_visitas["Ano-Mês"] = df_visitas["Data"].dt.to_period("M").astype(str)
df_atendimentos_mes = df_visitas.groupby("Ano-Mês")["Cliente"].count().reset_index()
df_atendimentos_mes.columns = ["Ano-Mês", "Qtd Atendimentos"]

df_merged = pd.merge(df_total_mes, df_atendimentos_mes, on="Ano-Mês", how="left")
df_merged["Valor Formatado"] = df_merged["Valor"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)

st.dataframe(df_merged[["Ano-Mês", "Valor Formatado", "Qtd Atendimentos"]], use_container_width=True)

# Linha de receita
fig_line = px.line(df_total_mes, x="Ano-Mês", y="Valor", markers=True, title="📈 Evolução mensal de receita")
fig_line.update_traces(line_color='limegreen')
st.plotly_chart(fig_line, use_container_width=True)

# Receita por tipo de serviço
st.markdown("### 📌 Receita por tipo de serviço")
df_servico = df_filt.groupby("Serviço")["Valor"].sum().reset_index()
df_servico["Valor Formatado"] = df_servico["Valor"].apply(
    lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
)

st.dataframe(df_servico[["Serviço", "Valor Formatado"]], use_container_width=True)

# Clientes atendidos únicos
st.markdown("### 🧑‍⚖️ Clientes atendidos (visitas únicas ajustadas)")

df_ajustado = df_filt.copy()
df_ajustado["Data"] = pd.to_datetime(df_ajustado["Data"])
antes = df_ajustado[df_ajustado["Data"] < data_limite]
depois = df_ajustado[df_ajustado["Data"] >= data_limite].drop_duplicates(subset=["Cliente", "Data"])
df_visitas = pd.concat([antes, depois])

contagem = df_visitas["Cliente"].value_counts().reset_index()
contagem.columns = ["Cliente", "Qtd Atendimentos"]

total_atendimentos = contagem["Qtd Atendimentos"].sum()
st.success(f"✅ Total de atendimentos únicos realizados por {funcionario}: {total_atendimentos}")
st.dataframe(contagem, use_container_width=True)

# Link seguro de retorno
if "funcionario" in st.session_state:
    del st.session_state["funcionario"]
if os.path.exists("temp_funcionario.json"):
    os.remove("temp_funcionario.json")
st.markdown('[⬅️ Voltar para Funcionários](./Funcionarios)')

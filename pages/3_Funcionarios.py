import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Ano-Mês"] = df["Data"].dt.to_period("M").astype(str)
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

if not funcionario:
    st.warning("⚠️ Nenhum funcionário selecionado.")
    st.stop()

# Filtro de mês vindo da session_state
meses_filtrados = st.session_state.get("meses", [])
if meses_filtrados:
    df = df[df["Ano-Mês"].isin(meses_filtrados)]

# Filtra os dados para o funcionário
df_func = df[df["Funcionário"] == funcionario]

# Título e filtros
st.markdown(f"### 📊 Receita mensal por tipo de serviço - {funcionario}")

# Filtros opcionais
meses_disp = sorted(df_func["Ano-Mês"].unique())
servicos_disp = sorted(df_func["Serviço"].dropna().unique())

meses_selec = st.multiselect("📅 Filtrar por mês (opcional)", meses_disp, default=meses_disp)
servicos_selec = st.multiselect("🧾 Filtrar por serviço", servicos_disp, default=servicos_disp)

df_filt = df_func[
    df_func["Ano-Mês"].isin(meses_selec) & df_func["Serviço"].isin(servicos_selec)
]

# Gráfico de receita mensal por tipo de serviço
df_agrupado = df_filt.groupby(["Ano-Mês", "Serviço"])["Valor"].sum().reset_index()

if not df_agrupado.empty:
    fig = px.bar(
        df_agrupado,
        x="Ano-Mês",
        y="Valor",
        color="Serviço",
        barmode="group",
        text_auto=".2s",
        facet_col="Serviço",
    )
    fig.update_layout(height=500, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nenhum dado disponível para os filtros selecionados.")

# Tabela de receita e atendimentos por mês
st.markdown("### 💰 Receita total e atendimentos por mês")

# Receita por mês
df_total_mes = df_filt.groupby("Ano-Mês")["Valor"].sum().reset_index()
df_total_mes.columns = ["Ano-Mês", "Valor"]

# Contagem de atendimentos por mês (ajustada)
df_filt["Data"] = pd.to_datetime(df_filt["Data"])
data_limite = pd.to_datetime("2025-05-11")
antes = df_filt[df_filt["Data"] < data_limite]
depois = df_filt[df_filt["Data"] >= data_limite].drop_duplicates(subset=["Cliente", "Data"])
df_visitas = pd.concat([antes, depois])
df_visitas["Ano-Mês"] = df_visitas["Data"].dt.to_period("M").astype(str)
df_atendimentos_mes = df_visitas.groupby("Ano-Mês")["Cliente"].count().reset_index()
df_atendimentos_mes.columns = ["Ano-Mês", "Qtd Atendimentos"]

# Junta receita + atendimentos
df_merged = pd.merge(df_total_mes, df_atendimentos_mes, on="Ano-Mês", how="left")
df_merged["Valor Formatado"] = df_merged["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.dataframe(df_merged[["Ano-Mês", "Valor Formatado", "Qtd Atendimentos"]], use_container_width=True)

# Gráfico de linha com evolução mensal
if not df_total_mes.empty:
    fig_line = px.line(df_total_mes, x="Ano-Mês", y="Valor", markers=True, title="📈 Evolução mensal de receita")
    fig_line.update_traces(line_color='limegreen')
    st.plotly_chart(fig_line, use_container_width=True)

# Total de atendimentos únicos (ajustado)
st.markdown("### 🧍‍♂️ Clientes atendidos (visitas únicas ajustadas)")

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

# Botão para voltar
if st.button("⬅️ Voltar para Funcionários"):
    if "funcionario" in st.session_state:
        del st.session_state["funcionario"]
    if os.path.exists("temp_funcionario.json"):
        os.remove("temp_funcionario.json")
    st.switch_page("pages/3_Funcionarios.py")

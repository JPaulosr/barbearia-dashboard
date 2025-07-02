import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Tempo de Permanência no Salão", page_icon="🏠", layout="wide")
st.title("🏠 Tempo de Permanência no Salão")

@st.cache_data
def carregar_dados():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)

    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')

    return df

df = carregar_dados()

# Filtra apenas registros com todos os horários preenchidos
df_tempos = df[
    df["Hora Chegada"].notna() &
    df["Hora Início"].notna() &
    df["Hora Saída"].notna() &
    df["Hora Saída do Salão"].notna()
].copy()

# Cálculos de tempo (em minutos)
for col_name, start_col, end_col in [
    ("Tempo Espera (min)", "Hora Chegada", "Hora Início"),
    ("Tempo Atendimento (min)", "Hora Início", "Hora Saída"),
    ("Tempo Pós (min)", "Hora Saída", "Hora Saída do Salão"),
    ("Tempo Total (min)", "Hora Chegada", "Hora Saída do Salão")
]:
    df_tempos[col_name] = (df_tempos[end_col] - df_tempos[start_col]).dt.total_seconds() / 60
    df_tempos[col_name] = df_tempos[col_name].round(0)

# Conversão para formato hh h mm min
def formatar_tempo(minutos):
    if pd.isnull(minutos): return ""
    h = int(minutos // 60)
    m = int(minutos % 60)
    return f"{h}h {m}min" if h > 0 else f"0h {m}min"

for col in ["Tempo Espera (min)", "Tempo Atendimento (min)", "Tempo Pós (min)", "Tempo Total (min)"]:
    df_tempos[col.replace("(min)", "formatado")] = df_tempos[col].apply(formatar_tempo)

# ---------- VISUALIZAÇÕES ----------

st.subheader("📊 Distribuição dos Tempos por Cliente")
col1, col2 = st.columns(2)

with col1:
    st.markdown("### Top 10 Permanências Pós-Atendimento")
    top_pos = df_tempos.sort_values("Tempo Pós (min)", ascending=False).head(10)
    st.dataframe(top_pos[["Data", "Cliente", "Funcionário", "Tempo Pós formatado", "Tempo Total formatado"]], use_container_width=True)

with col2:
    st.markdown("### Top 10 Permanência Total")
    top_total = df_tempos.sort_values("Tempo Total (min)", ascending=False).head(10)
    st.dataframe(top_total[["Data", "Cliente", "Funcionário", "Tempo Total formatado"]], use_container_width=True)

st.subheader("📈 Comparativo Visual")
top20 = df_tempos.sort_values("Tempo Total (min)", ascending=False).head(20)

# Converter os dados para long format
df_long = top20.melt(
    id_vars=["Cliente"], 
    value_vars=["Tempo Espera (min)", "Tempo Atendimento (min)", "Tempo Pós (min)"],
    var_name="Etapa", 
    value_name="Minutos"
)

def min_para_texto(minutos):
    if pd.isnull(minutos): return ""
    h = int(minutos // 60)
    m = int(minutos % 60)
    return f"{h}h {m}min"

df_long["Tempo Formatado"] = df_long["Minutos"].apply(min_para_texto)

fig = px.bar(
    df_long,
    x="Cliente",
    y="Minutos",
    color="Etapa",
    barmode="group",
    text="Tempo Formatado",
    title="Top 20 Clientes por Tempo Total (Lado a Lado)",
    labels={"Minutos": "Minutos", "Cliente": "Cliente"}
)

fig.update_traces(textposition="outside")
fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
st.plotly_chart(fig, use_container_width=True)

st.subheader("📋 Visualizar base completa")
st.dataframe(
    df[["Data", "Cliente", "Funcionário",
        "Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão"]],
    use_container_width=True
)

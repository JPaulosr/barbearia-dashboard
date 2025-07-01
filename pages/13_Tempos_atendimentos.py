import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Produtividade por Funcionário", page_icon="💰", layout="wide")
st.title("💰 Produtividade por Funcionário (R$/hora)")

@st.cache_data
def carregar_dados_google_sheets():
    url = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    df = pd.read_csv(url)
    df.columns = df.columns.str.strip()  # Remove espaços
    st.write("🧾 Colunas da planilha:", df.columns.tolist())
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce').dt.date
    df["Hora Chegada"] = pd.to_datetime(df["Hora Chegada"], errors='coerce')
    df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors='coerce')
    df["Hora Saída"] = pd.to_datetime(df["Hora Saída"], errors='coerce')
    df["Hora Saída do Salão"] = pd.to_datetime(df["Hora Saída do Salão"], errors='coerce')
    df["Valor Total"] = pd.to_numeric(df["Valor"], errors='coerce')  # Verifique se o nome é exatamente "Valor"
    return df

df = carregar_dados_google_sheets()

st.markdown("### 🎛️ Filtros")
col1, col2 = st.columns(2)
funcionarios = df["Funcionário"].dropna().unique().tolist()
with col1:
    funcionario_selecionado = st.multiselect("Funcionário", funcionarios, default=funcionarios)
with col2:
    hoje = datetime.today().date()
    data_inicial = hoje - timedelta(days=30)
    periodo = st.date_input("Período", [data_inicial, hoje])

df = df[df["Funcionário"].isin(funcionario_selecionado)]
if isinstance(periodo, list) and len(periodo) == 2:
    df = df[(df["Data"] >= periodo[0]) & (df["Data"] <= periodo[1])]

df["Hora Início str"] = df["Hora Início"].dt.strftime("%H:%M")
df["Hora Saída str"] = df["Hora Saída"].dt.strftime("%H:%M")
df["Hora Início dt"] = pd.to_datetime(df["Hora Início str"], format="%H:%M", errors='coerce')
df["Hora Saída dt"] = pd.to_datetime(df["Hora Saída str"], format="%H:%M", errors='coerce')
df["Duração (min)"] = (df["Hora Saída dt"] - df["Hora Início dt"]).dt.total_seconds() / 60
df = df.dropna(subset=["Duração (min)", "Valor Total"])

df = df.sort_values(by=["Funcionário", "Data", "Hora Início dt"]).copy()
df["Próximo Início"] = df.groupby(["Funcionário", "Data"])["Hora Início dt"].shift(-1)
df["Ociosidade (min)"] = (df["Próximo Início"] - df["Hora Saída dt"]).dt.total_seconds() / 60
df["Ociosidade (min)"] = df["Ociosidade (min)"].apply(lambda x: x if x and x > 0 else 0)

df_group = df.groupby("Funcionário").agg({
    "Valor Total": "sum",
    "Duração (min)": "sum",
    "Ociosidade (min)": "sum"
}).reset_index()

df_group["Tempo Total (min)"] = df_group["Duração (min)"] + df_group["Ociosidade (min)"]
df_group["R$/h útil"] = (df_group["Valor Total"] / (df_group["Duração (min)"] / 60)).round(2)
df_group["R$/h total"] = (df_group["Valor Total"] / (df_group["Tempo Total (min)"] / 60)).round(2)
df_group["% Ociosidade"] = (df_group["Ociosidade (min)"] / df_group["Tempo Total (min)"] * 100).round(1)

def alerta_produtividade(row):
    if row["R$/h total"] < 30:
        return "⚠️ Baixa Produtividade"
    elif row["% Ociosidade"] > 50:
        return "⏳ Muita Ociosidade"
    else:
        return "✅ OK"

df_group["Alerta"] = df_group.apply(alerta_produtividade, axis=1)

st.subheader("📋 Produtividade por Funcionário")
st.dataframe(df_group[["Funcionário", "Valor Total", "R$/h útil", "R$/h total", "% Ociosidade", "Alerta"]], use_container_width=True)

fig = px.bar(df_group, x="Funcionário", y=["R$/h útil", "R$/h total"], barmode="group",
             title="Comparativo de Receita por Hora (Útil vs Total)")
fig.update_layout(margin=dict(t=60), title_x=0.5)
st.plotly_chart(fig, use_container_width=True)

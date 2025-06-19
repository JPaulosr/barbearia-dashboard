
import streamlit as st
import pandas as pd

st.set_page_config(layout="wide", page_title="Dashboard da Barbearia")

# Carregar dados
df = pd.read_excel("Modelo_Barbearia_Automatizado (10).xlsx", sheet_name="Resumo Anual")

# Filtros
st.title("Dashboard da Barbearia")
col1, col2, col3 = st.columns(3)
anos = ["Todos"] + sorted(df["Ano"].dropna().unique().astype(str).tolist())
funcs = ["Todos"] + sorted(df["Funcionário"].dropna().unique().tolist())

with col1:
    ano = st.selectbox("Ano", anos)

with col2:
    func = st.selectbox("Funcionário", funcs)

# Filtrar
if ano != "Todos":
    df = df[df["Ano"].astype(str) == ano]
if func != "Todos":
    df = df[df["Funcionário"] == func]

# Gráfico de Receita
st.subheader("Receita por Ano")
resumo = df.groupby("Ano").agg({"Total Faturado": "sum"}).reset_index()
st.bar_chart(resumo.set_index("Ano"))

# Top 20 Clientes (exemplo)
st.subheader("Top 20 Clientes (exemplo)")
top20 = [
    {"Cliente": "boliviano", "Valor": 952.76},
    {"Cliente": "fábio jr", "Valor": 182.91},
    {"Cliente": "ronald", "Valor": 170.00},
    {"Cliente": "menino", "Valor": 168.46},
    {"Cliente": "brasileiro", "Valor": 149.78},
    {"Cliente": "gabriel lutador", "Valor": 141.00},
    {"Cliente": "raphael", "Valor": 139.00},
    {"Cliente": "boliviano testura desbotada", "Valor": 125.00},
    {"Cliente": "jardiel", "Valor": 125.00},
    {"Cliente": "mussum", "Valor": 109.76},
    {"Cliente": "josé severino", "Valor": 109.00},
    {"Cliente": "andrade", "Valor": 105.00},
    {"Cliente": "matheus", "Valor": 94.00},
    {"Cliente": "jean", "Valor": 93.16},
    {"Cliente": "gustavo chácara", "Valor": 87.00},
    {"Cliente": "jequisson", "Valor": 80.00},
    {"Cliente": "valteir negao", "Valor": 80.00},
    {"Cliente": "ray guariba", "Valor": 78.21},
    {"Cliente": "miguel", "Valor": 75.00},
    {"Cliente": "gigante", "Valor": 72.00},
]
for cliente in top20:
    st.markdown(f"- **{cliente['Cliente']}** - R$ {cliente['Valor']:.2f}")

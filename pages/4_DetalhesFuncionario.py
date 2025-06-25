
import streamlit as st
import pandas as pd
import plotly.express as px
from io import BytesIO

st.set_page_config(layout="wide")
st.title("🧑‍💼 Detalhes do Funcionário")

@st.cache_data
def carregar_dados():
    df = pd.read_excel("dados_barbearia.xlsx", sheet_name="Base de Dados")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    return df

df = carregar_dados()

funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("📅 Filtrar por ano", anos)

funcionario_escolhido = st.selectbox("📋 Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionário"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)]

tipos_servico = df_func["Serviço"].dropna().unique().tolist()
tipo_selecionado = st.multiselect("Filtrar por tipo de serviço", tipos_servico)
if tipo_selecionado:
    df_func = df_func[df_func["Serviço"].isin(tipo_selecionado)]

st.subheader("📅 Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

st.subheader("📊 Receita Mensal por Mês e Ano")
meses_ordem = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
               "Setembro", "Outubro", "Novembro", "Dezembro"]
meses_pt = {
    "Jan": "Janeiro", "Feb": "Fevereiro", "Mar": "Março", "Apr": "Abril", "May": "Maio", "Jun": "Junho",
    "Jul": "Julho", "Aug": "Agosto", "Sep": "Setembro", "Oct": "Outubro", "Nov": "Novembro", "Dec": "Dezembro"
}

df_func["MesNome"] = df_func["Data"].dt.strftime("%b").str[:3].map(meses_pt)
df_func["MesOrdem"] = df_func["Data"].dt.month
receita_jp = df_func.groupby(["MesNome", "MesOrdem"])["Valor"].sum().reset_index(name="JPaulo")

if funcionario_escolhido.lower() == "jpaulo":
    df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == ano_escolhido)].copy()
    df_vini["MesNome"] = df_vini["Data"].dt.strftime("%b").str[:3].map(meses_pt)
    df_vini["MesOrdem"] = df_vini["Data"].dt.month
    receita_vini = df_vini.groupby(["MesNome", "MesOrdem"])["Valor"].sum().reset_index(name="Vinicius")

    receita_merged = pd.merge(receita_jp, receita_vini, on=["MesNome", "MesOrdem"], how="left")
    receita_merged = receita_merged.sort_values("MesOrdem")
    receita_merged["Comissão (50%) do Vinicius"] = receita_merged["Vinicius"].fillna(0) * 0.5
    receita_merged["Total (JPaulo + Comissão)"] = receita_merged["JPaulo"] + receita_merged["Comissão (50%) do Vinicius"]
    receita_merged["Comissão (50%) do Vinicius"] = receita_merged["Comissão (50%) do Vinicius"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    receita_merged["JPaulo Formatado"] = receita_merged["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    receita_merged["Total (JPaulo + Comissão)"] = receita_merged["Total (JPaulo + Comissão)"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

    tabela = receita_merged[["MesNome", "JPaulo Formatado", "Comissão (50%) do Vinicius", "Total (JPaulo + Comissão)"]]
    tabela.columns = ["Mês", "Receita JPaulo", "Comissão (50%) do Vinicius", "Total (JPaulo + Comissão)"]
    st.dataframe(tabela, use_container_width=True)

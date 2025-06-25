import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode
from io import BytesIO

st.set_page_config(layout="wide")
st.title("\U0001F9D1\u200d\U0001F4BC Detalhes do Funcionário")

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

# === Histórico de atendimentos ===
st.subheader("\U0001F4C5 Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

# === Receita mensal lado a lado (JPaulo vs JPaulo + Vinicius 50%) ===
st.subheader("\U0001F4CA Receita Mensal por Mês e Ano")

meses_ordem = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
meses_pt = {
    "Jan": "Janeiro", "Feb": "Fevereiro", "Mar": "Março", "Apr": "Abril", "May": "Maio", "Jun": "Junho",
    "Jul": "Julho", "Aug": "Agosto", "Sep": "Setembro", "Oct": "Outubro", "Nov": "Novembro", "Dec": "Dezembro"
}

df_func["AnoMes"] = df_func["Data"].dt.to_period("M").astype(str)
df_func["MesNome"] = df_func["Data"].dt.strftime("%b %Y").str[:3].map(meses_pt) + df_func["Data"].dt.strftime(" %Y")
receita_jp = df_func.groupby("MesNome")["Valor"].sum().reset_index(name="JPaulo")

if funcionario_escolhido.lower() == "jpaulo":
    if ano_escolhido == 2025:
        df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == ano_escolhido)].copy()
        df_vini["MesNome"] = df_vini["Data"].dt.strftime("%b").str[:3].map(meses_pt) + df_vini["Data"].dt.strftime(" %Y")
        receita_vini = df_vini.groupby("MesNome")["Valor"].sum().reset_index(name="Vinicius")
        receita_merged = pd.merge(receita_jp, receita_vini, on="MesNome", how="left")
        receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["Vinicius"].fillna(0) * 0.5

        receita_melt = receita_merged.melt(id_vars="MesNome", value_vars=["JPaulo", "Com_Vinicius"], var_name="Tipo", value_name="Valor")
        receita_melt["MesOrdem"] = receita_melt["MesNome"].str.extract(r"^([A-Za-z]+)")[0].map({m: i for i, m in enumerate(meses_ordem)})
        receita_melt = receita_melt.sort_values("MesOrdem")

        fig_mensal_comp = px.bar(receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
                                  labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""})
        fig_mensal_comp.update_layout(height=450, template="plotly_white")
        st.plotly_chart(fig_mensal_comp, use_container_width=True)
    else:
        receita_jp = receita_jp[receita_jp["MesNome"].str.contains(str(ano_escolhido))]
        receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
        receita_jp["MesOrdem"] = receita_jp["MesNome"].str.extract(r"^([A-Za-z]+)")[0].map({m: i for i, m in enumerate(meses_ordem)})
        receita_jp = receita_jp.sort_values("MesOrdem")

        fig_mensal = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado", labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
        fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
        fig_mensal.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig_mensal, use_container_width=True)
else:
    receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    fig_mensal = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado", labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
    fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
    fig_mensal.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_mensal, use_container_width=True)

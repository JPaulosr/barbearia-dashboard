import streamlit as st
import pandas as pd
import plotly.express as px
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

# === Receita mensal ===
st.subheader("\U0001F4CA Receita Mensal por Mês e Ano")

meses_pt = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

df_func["Mes"] = df_func["Data"].dt.month
df_func["MesNome"] = df_func["Mes"].map(meses_pt)
receita_jp = df_func.groupby(["Mes", "MesNome"])["Valor"].sum().reset_index(name="JPaulo")
receita_jp = receita_jp.sort_values("Mes")

if funcionario_escolhido.lower() == "jpaulo":
    if ano_escolhido < 2025:
        receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
        fig_jp = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                        labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
        fig_jp.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
        fig_jp.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(fig_jp, use_container_width=True)
    elif ano_escolhido == 2025:
        df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == 2025)].copy()
        df_vini["Mes"] = df_vini["Data"].dt.month
        df_vini["MesNome"] = df_vini["Mes"].map(meses_pt)
        receita_vini = df_vini.groupby(["Mes", "MesNome"])["Valor"].sum().reset_index(name="Vinicius")

        receita_merged = pd.merge(receita_jp, receita_vini, on=["Mes", "MesNome"], how="left")
        receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["Vinicius"].fillna(0) * 0.5

        receita_melt = receita_merged.melt(id_vars=["Mes", "MesNome"], value_vars=["JPaulo", "Com_Vinicius"],
                                           var_name="Tipo", value_name="Valor")
        receita_melt = receita_melt.sort_values("Mes")

        fig_comp = px.bar(receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
                          labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""})
        fig_comp.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
        st.plotly_chart(fig_comp, use_container_width=True)
else:
    receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    fig_outro = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                       labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
    fig_outro.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
    fig_outro.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_outro, use_container_width=True)

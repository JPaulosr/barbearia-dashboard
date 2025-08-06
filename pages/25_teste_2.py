import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Receita Mensal", layout="wide")
st.title("📊 Receita Mensal por Mês e Ano")

# === Função para carregar dados ===
@st.cache_data
def carregar_dados():
    url_base = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Base%20de%20Dados"
    url_desp = "https://docs.google.com/spreadsheets/d/1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE/gviz/tq?tqx=out:csv&sheet=Despesas"
    base = pd.read_csv(url_base)
    despesas = pd.read_csv(url_desp)
    
    base["Data"] = pd.to_datetime(base["Data"], errors="coerce")
    despesas["Data"] = pd.to_datetime(despesas["Data"], errors="coerce")
    
    base["AnoMes"] = base["Data"].dt.to_period("M")
    base["MesNum"] = base["Data"].dt.month
    base["MesNome"] = base["Data"].dt.strftime('%B %Y')
    
    return base, despesas

base, despesas = carregar_dados()

# === Receita JPaulo ===
df_jpaulo = base[base["Funcionário"] == "JPaulo"]
receita_jpaulo = df_jpaulo.groupby("MesNome")["Valor"].sum().reset_index()
receita_jpaulo["MesNum"] = pd.to_datetime(receita_jpaulo["MesNome"], format='%B %Y').dt.month
receita_jpaulo = receita_jpaulo.rename(columns={"Valor": "Receita_JPaulo"})

# === Comissão paga ao Vinicius ===
comissoes_vinicius = despesas[despesas["Descrição"].str.contains("comissão", case=False) & despesas["Descrição"].str.contains("vinicius", case=False)]
comissoes_vinicius["MesNome"] = comissoes_vinicius["Data"].dt.strftime('%B %Y')
comissoes_vinicius["MesNum"] = comissoes_vinicius["Data"].dt.month
comissoes_mes = comissoes_vinicius.groupby("MesNome")["Valor"].sum().reset_index()
comissoes_mes = comissoes_mes.rename(columns={"Valor": "Comissao_Vinicius"})

# === Receita real do salão ===
receita_total = base.groupby("MesNome")["Valor"].sum().reset_index()
receita_total["MesNum"] = pd.to_datetime(receita_total["MesNome"], format='%B %Y').dt.month
receita_total = receita_total.rename(columns={"Valor": "Receita_Bruta_Total"})

# Merge para calcular Receita líquida do salão
receita_merged = receita_jpaulo.merge(comissoes_mes, on="MesNome", how="outer")
receita_merged = receita_merged.merge(receita_total, on="MesNome", how="outer")
receita_merged["MesNum"] = receita_merged["MesNum_x"].combine_first(receita_merged["MesNum_y"])

receita_merged["Receita_Real_Salao"] = receita_merged["Receita_JPaulo"].fillna(0) + (
    receita_merged["Receita_Bruta_Total"].fillna(0) - receita_merged["Receita_JPaulo"].fillna(0) - receita_merged["Comissao_Vinicius"].fillna(0)
)

# === Corrigir nomes duplicados ===
receita_merged = receita_merged[["MesNome", "MesNum", "Receita_JPaulo", "Comissao_Vinicius", "Receita_Real_Salao"]]

# === Gráfico comparativo ===
df_melt = receita_merged.melt(
    id_vars=["MesNum", "MesNome"],
    value_vars=["Receita_JPaulo", "Receita_Real_Salao"],
    var_name="Tipo", value_name="Valor"
).sort_values("MesNum")

df_melt["Tipo"] = df_melt["Tipo"].replace({
    "Receita_JPaulo": "JPaulo",
    "Receita_Real_Salao": "Com_Vinicius"
})

fig_mensal_comp = px.bar(
    df_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
    labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""}
)
st.plotly_chart(fig_mensal_comp, use_container_width=True, key="plot_mensal_jpaulo")

# === Tabela detalhada ===
tabela = receita_merged.sort_values("MesNum")
tabela["Receita_JPaulo"] = tabela["Receita_JPaulo"].fillna(0).apply(lambda x: f"R$ {x:,.2f}".replace('.', ','))
tabela["Comissao_Vinicius"] = tabela["Comissao_Vinicius"].fillna(0).apply(lambda x: f"R$ {x:,.2f}".replace('.', ','))
tabela["Receita_Real_Salao"] = tabela["Receita_Real_Salao"].fillna(0).apply(lambda x: f"R$ {x:,.2f}".replace('.', ','))

st.dataframe(
    tabela[["MesNome", "Receita_JPaulo", "Comissao_Vinicius", "Receita_Real_Salao"]].rename(columns={
        "MesNome": "Mês",
        "Receita_JPaulo": "Receita JPaulo",
        "Comissao_Vinicius": "Comissão paga ao Vinicius",
        "Receita_Real_Salao": "Receita Real do Salão"
    }),
    use_container_width=True,
    hide_index=True
)

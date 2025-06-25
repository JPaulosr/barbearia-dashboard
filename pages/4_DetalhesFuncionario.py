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

# === Histórico de atendimentos ===
st.subheader("\U0001F4C5 Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

# === Receita mensal ===
st.subheader("\U0001F4CA Receita Mensal por Mês e Ano")
df_func["AnoMes"] = df_func["Data"].dt.to_period("M").astype(str)
receita_mensal = df_func.groupby("AnoMes")["Valor"].sum().reset_index()
receita_mensal["Valor Formatado"] = receita_mensal["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

fig_mensal = px.bar(receita_mensal, x="AnoMes", y="Valor", text="Valor Formatado", labels={"Valor": "Receita (R$)", "AnoMes": "Ano-Mês"})
fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
fig_mensal.update_traces(textposition="outside", cliponaxis=False)
st.plotly_chart(fig_mensal, use_container_width=True)

# === Se funcionário for Vinicius, mostrar bruto e líquido ===
if funcionario_escolhido.lower() == "vinicius":
    bruto = df_func["Valor"].sum()
    liquido = bruto * 0.5
    comparativo_vinicius = pd.DataFrame({
        "Tipo de Receita": ["Bruta (100%)", "Líquida (50%)"],
        "Valor": [bruto, liquido]
    })
    comparativo_vinicius["Valor Formatado"] = comparativo_vinicius["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    st.subheader("\U0001F4B8 Receita Bruta vs Líquida (Vinicius)")
    st.dataframe(comparativo_vinicius[["Tipo de Receita", "Valor Formatado"]], use_container_width=True)

# === Exportar dados ===
st.subheader("\U0001F4E5 Exportar dados filtrados")
buffer = BytesIO()
df_func.to_excel(buffer, index=False, sheet_name="Filtrado", engine="openpyxl")
st.download_button("Baixar Excel com dados filtrados", data=buffer.getvalue(), file_name="dados_filtrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import plotly.express as px
import io

st.set_page_config(layout="wide")
st.title("📊 Resultado Financeiro Total do Salão")

# === CONFIGURAÇÃO GOOGLE SHEETS ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_bases():
    planilha = conectar_sheets()
    df_base = get_as_dataframe(planilha.worksheet("Base de Dados")).dropna(how="all")
    df_desp = get_as_dataframe(planilha.worksheet("Despesas")).dropna(how="all")

    df_base.columns = df_base.columns.str.strip()
    df_base["Data"] = pd.to_datetime(df_base["Data"], errors="coerce")
    df_base = df_base.dropna(subset=["Data"])
    df_base["Ano"] = df_base["Data"].dt.year
    df_base["Mês"] = df_base["Data"].dt.month

    df_desp.columns = df_desp.columns.str.strip()
    df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce")
    df_desp = df_desp.dropna(subset=["Data"])
    df_desp["Ano"] = df_desp["Data"].dt.year
    df_desp["Mês"] = df_desp["Data"].dt.month

    return df_base, df_desp

# === CARREGAR DADOS
df, df_despesas = carregar_bases()

anos = sorted(df["Ano"].dropna().unique(), reverse=True)
ano = st.selectbox("🗓️ Selecione o Ano", anos)

df_ano = df[df["Ano"] == ano]
df_desp_ano = df_despesas[df_despesas["Ano"] == ano]

# === CÁLCULOS GERAIS
receita_total = df_ano["Valor"].sum()
despesas_total = df_desp_ano["Valor"].sum()
lucro_total = receita_total - despesas_total

st.subheader("📊 Resultado Consolidado do Salão")
col1, col2, col3 = st.columns(3)
col1.metric("Receita Total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("Despesas Totais", f"R$ {despesas_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col3.metric("Lucro Total", f"R$ {lucro_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.divider()

# === RECEITA POR FUNCIONÁRIO
st.subheader("👤 Receita por Funcionário")
df_func = df_ano.groupby("Funcionário")["Valor"].sum().reset_index().sort_values(by="Valor", ascending=False)
st.dataframe(df_func.rename(columns={"Valor": "Receita (R$)"}), use_container_width=True)

# === GRÁFICO DE BARRAS – Receita por Funcionário (Plotly)
st.subheader("📊 Receita por Funcionário (Gráfico)")
fig_bar = px.bar(
    df_func,
    x="Funcionário",
    y="Valor",
    text_auto=".2s",
    title="Receita por Funcionário",
    labels={"Valor": "Receita (R$)"},
)
fig_bar.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="white"),
    title_x=0.5
)
st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# === GRÁFICO DE LINHA – Receita vs Despesa por Mês
st.subheader("📈 Evolução Mensal de Receita e Despesas")

# Receita mensal
receita_mensal = df_ano.groupby("Mês")["Valor"].sum().reset_index(name="Receita")
# Despesa mensal
despesa_mensal = df_desp_ano.groupby("Mês")["Valor"].sum().reset_index(name="Despesa")

# Juntar e preparar
df_mensal = pd.merge(receita_mensal, despesa_mensal, on="Mês", how="outer").fillna(0).sort_values("Mês")
df_mensal["Mês"] = df_mensal["Mês"].apply(lambda x: f"{x:02d}")
df_melt = df_mensal.melt(id_vars="Mês", value_vars=["Receita", "Despesa"], var_name="Tipo", value_name="Valor")

fig_linha = px.line(
    df_melt,
    x="Mês",
    y="Valor",
    color="Tipo",
    markers=True,
    title="Receita vs Despesas por Mês",
    labels={"Valor": "R$", "Mês": "Mês"}
)
fig_linha.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="white"),
    title_x=0.5
)
st.plotly_chart(fig_linha, use_container_width=True)

st.divider()

# === EXPORTAÇÃO EXCEL
st.subheader("📤 Exportar Resultado")

df_export = pd.DataFrame({
    "Ano": [ano],
    "Receita Total": [receita_total],
    "Despesas Totais": [despesas_total],
    "Lucro Total": [lucro_total]
})
df_func_export = df_func.rename(columns={"Valor": "Receita por Funcionário (R$)"}).copy()

output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_export.to_excel(writer, index=False, sheet_name='Resumo Financeiro')
    df_func_export.to_excel(writer, index=False, sheet_name='Receita por Funcionário')
    df_mensal.to_excel(writer, index=False, sheet_name='Mensal (Receita e Despesa)')
    writer.save()
    dados_excel = output.getvalue()

st.download_button(
    label="⬇️ Baixar Excel (.xlsx)",
    data=dados_excel,
    file_name=f"financeiro_salao_{ano}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

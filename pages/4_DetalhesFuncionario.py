
import streamlit as st
import pandas as pd
import plotly.express as px
from unidecode import unidecode
from io import BytesIO
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("🧑‍💼 Detalhes do Funcionário")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data
def carregar_dados():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    return df

@st.cache_data
def carregar_despesas():
    planilha = conectar_sheets()
    aba_desp = planilha.worksheet("Despesas")
    df_desp = get_as_dataframe(aba_desp).dropna(how="all")
    df_desp.columns = [str(col).strip() for col in df_desp.columns]
    df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce")
    df_desp = df_desp.dropna(subset=["Data"])
    df_desp["Ano"] = df_desp["Data"].dt.year.astype(int)
    return df_desp

df = carregar_dados()
df_despesas = carregar_despesas()

funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("🗕️ Filtrar por ano", anos)
funcionario_escolhido = st.selectbox("📋 Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionário"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)]

tipos_servico = df_func["Serviço"].dropna().unique().tolist()
tipo_selecionado = st.multiselect("Filtrar por tipo de serviço", tipos_servico)
if tipo_selecionado:
    df_func = df_func[df_func["Serviço"].isin(tipo_selecionado)]

st.subheader("📊 Receita Mensal por Mês e Ano")

meses_pt = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
df_func["MesNum"] = df_func["Data"].dt.month
df_func["MesNome"] = df_func["MesNum"].map(meses_pt) + df_func["Data"].dt.strftime(" %Y")
receita_jp = df_func.groupby(["MesNum", "MesNome"])["Valor"].sum().reset_index(name="JPaulo")
receita_jp = receita_jp.sort_values("MesNum")

# apenas incluir comissão se não houver filtro
if funcionario_escolhido.lower() == "jpaulo" and ano_escolhido == 2025 and not tipo_selecionado:
    df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == 2025)].copy()
    df_vini["MesNum"] = df_vini["Data"].dt.month
    df_vini["MesNome"] = df_vini["MesNum"].map(meses_pt) + df_vini["Data"].dt.strftime(" %Y")

    df_com_vinicius = df_despesas[
        (df_despesas["Prestador"] == "Vinicius") &
        (df_despesas["Descrição"].str.contains("comissão", case=False, na=False)) &
        (df_despesas["Ano"] == 2025)
    ].copy()
    df_com_vinicius["MesNum"] = df_com_vinicius["Data"].dt.month
    df_com_vinicius = df_com_vinicius.groupby("MesNum")["Valor"].sum().reset_index(name="ComissaoVinicius")

    receita_merged = receita_jp.merge(df_com_vinicius, on="MesNum", how="left").fillna(0)
    receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["ComissaoVinicius"]

    receita_melt = receita_merged.melt(id_vars=["MesNum", "MesNome"], value_vars=["JPaulo", "Com_Vinicius"],
                                       var_name="Tipo", value_name="Valor")
else:
    receita_melt = receita_jp.copy()
    receita_melt["Tipo"] = "JPaulo"
    receita_melt.rename(columns={"JPaulo": "Valor"}, inplace=True)

fig = px.bar(receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
             labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""})
fig.update_layout(height=450, template="plotly_white")
st.plotly_chart(fig, use_container_width=True)

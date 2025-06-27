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

# === CONFIGURAÇÃO GOOGLE SHEETS ===
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

df = carregar_dados()

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

df_despesas = carregar_despesas()

# === Lista de funcionários ===
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

# === Filtro por ano ===
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("🗕️ Filtrar por ano", anos)

# === Seleção de funcionário ===
funcionario_escolhido = st.selectbox("🗏️ Escolha um funcionário", funcionarios)
df_func = df[(df["Funcionário"] == funcionario_escolhido) & (df["Ano"] == ano_escolhido)]

# === Filtro por tipo de serviço ===
tipos_servico = df_func["Serviço"].dropna().unique().tolist()
tipo_selecionado = st.multiselect("Filtrar por tipo de serviço", tipos_servico)
if tipo_selecionado:
    df_func = df_func[df_func["Serviço"].isin(tipo_selecionado)]

# === Histórico de atendimentos ===
st.subheader("🗕️ Histórico de Atendimentos")
st.dataframe(df_func.sort_values("Data", ascending=False), use_container_width=True)

# === Receita mensal ===
st.subheader("📊 Receita Mensal por Mês e Ano")

meses_pt = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

df_func["MesNum"] = df_func["Data"].dt.month
df_func["MesNome"] = df_func["MesNum"].map(meses_pt) + df_func["Data"].dt.strftime(" %Y")
receita_jp = df_func.groupby(["MesNum", "MesNome"])["Valor"].sum().reset_index(name="JPaulo")
receita_jp = receita_jp.sort_values("MesNum")

if funcionario_escolhido.lower() == "jpaulo" and ano_escolhido == 2025:
    comissao_real = df_despesas[
        (df_despesas["Prestador"] == "Vinicius") &
        (df_despesas["Ano"] == 2025) &
        (df_despesas["Descrição"].str.contains("comiss", case=False, na=False))
    ]["Valor"].sum()

    valor_jp = df_func["Valor"].sum()
    total = valor_jp + comissao_real

    tabela_resumo = pd.DataFrame({
        "Origem": ["Receita Bruta JPaulo", "Comissão paga ao Vinicius", "Total"],
        "Valor": [valor_jp, comissao_real, total]
    })
    tabela_resumo["Valor Formatado"] = tabela_resumo["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    st.subheader("💰 Receita JPaulo: Própria + Comissão do Vinicius")
    st.dataframe(tabela_resumo[["Origem", "Valor Formatado"]], use_container_width=True)

# (continua normalmente com ticket médio, exportação, etc.)

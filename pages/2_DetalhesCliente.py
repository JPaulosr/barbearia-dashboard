import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import datetime

st.set_page_config(layout="wide")
st.title("📌 Detalhamento do Cliente")

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

    # Padroniza os nomes das colunas
    df.columns = [str(col).strip().title() for col in df.columns]

    # Renomeia para uso interno padrão
    df.rename(columns={"Funcionário": "Profissional"}, inplace=True)

    # Conversão de datas
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month

    # Nomes dos meses em português
    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }

    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)

    # Ordenar corretamente os meses
    df["Mês_Ano"] = pd.Categorical(
        df["Mês_Ano"],
        categories=sorted(df["Mês_Ano"].unique(), key=lambda x: (int(x.split("/")[1]), list(meses_pt.values()).index(x.split("/")[0]) + 1)),
        ordered=True
    )

    return df

# === INÍCIO ===
df = carregar_dados()

# === Filtro de cliente ===
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

# === DADOS DO CLIENTE ===
dados_cliente = df[df["Cliente"] == cliente].sort_values("Data")

if not dados_cliente.empty:
    col1, col2, col3, col4 = st.columns(4)

    # VIP
    vip = "Sim ⭐" if dados_cliente["Valor"].mean() >= 70 else "Não"
    col1.metric("🥇 Cliente VIP", vip)

    # Mais atendido por
    if "Profissional" in dados_cliente.columns and not dados_cliente["Profissional"].dropna().empty:
        funcionario_mais = dados_cliente["Profissional"].mode()[0]
    else:
        funcionario_mais = "Indisponível"
    col2.metric("🧑‍🎨 Mais atendido por", funcionario_mais)

    # Intervalo entre visitas
    datas = dados_cliente["Data"].drop_duplicates().sort_values()
    if len(datas) > 1:
        intervalo_medio = (datas.diff().dropna().dt.days.mean()).round(1)
        col3.metric("📅 Intervalo entre visitas", f"{intervalo_medio} dias")
    else:
        col3.metric("📅 Intervalo entre visitas", "Indisponível")

    # Ticket médio
    ticket = dados_cliente["Valor"].mean()
    col4.metric("💵 Ticket Médio", f"R$ {ticket:,.2f}".replace(".", ","))

    # Receita mensal
    receita_mensal = dados_cliente.groupby("Mês_Ano")["Valor"].sum().reset_index()
    fig = px.bar(receita_mensal, x="Mês_Ano", y="Valor", text="Valor", labels={"Valor": "Receita (R$)", "Mês_Ano": "Mês"})
    fig.update_traces(texttemplate="R$ %{text:.2f}", textposition="outside")
    fig.update_layout(title="📊 Receita mensal", xaxis_title="Mês", yaxis_title="Receita", height=400)
    st.plotly_chart(fig, use_container_width=True)

else:
    st.warning("Nenhum dado encontrado para este cliente.")

# === COMPARATIVO ENTRE CLIENTES ===
with st.expander("🧪 Comparativo entre Clientes", expanded=False):
    col_c1, col_c2 = st.columns(2)
    cliente_1 = col_c1.selectbox("Cliente 1", clientes_disponiveis, key="c1")
    cliente_2 = col_c2.selectbox("Cliente 2", clientes_disponiveis, index=1, key="c2")

    def indicadores(cliente_nome):
        dados = df[df["Cliente"] == cliente_nome].copy()
        meses = dados["Mês_Ano"].nunique()
        gasto_total = dados["Valor"].sum()
        ticket_medio = gasto_total / len(dados) if len(dados) > 0 else 0
        gasto_mensal = gasto_total / meses if meses > 0 else 0
        return {
            "Cliente": cliente_nome,
            "Atendimentos": len(dados),
            "Ticket Médio": round(ticket_medio, 2),
            "Gasto Total": round(gasto_total, 2),
            "Gasto Mensal Médio": round(gasto_mensal, 2),
        }

    df_comp = pd.DataFrame([indicadores(cliente_1), indicadores(cliente_2)])
    st.dataframe(df_comp, use_container_width=True)

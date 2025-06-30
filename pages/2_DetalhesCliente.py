
import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

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
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Mês_Ano"] = df["Data"].dt.strftime("%B/%Y").str.capitalize()
    return df

df = carregar_dados()

clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

df_cliente = df[df["Cliente"] == cliente]

# 📅 Histórico com horário completo
st.subheader(f"📅 Histórico de atendimentos - {cliente}")
df_exibicao = df_cliente[["Data", "Serviço"]].sort_values("Data", ascending=False).copy()
df_exibicao["Data"] = df_exibicao["Data"].dt.strftime("%d/%m/%Y %H:%M")
st.dataframe(df_exibicao, use_container_width=True)

# 📊 Receita mensal
st.subheader("📊 Receita mensal")
df_cliente["Mês_Ano"] = df_cliente["Data"].dt.strftime("%B/%Y").str.capitalize()
receita_mensal = df_cliente.groupby("Mês_Ano")["Valor"].sum().reset_index()
fig_receita = px.bar(
    receita_mensal,
    x="Mês_Ano",
    y="Valor",
    text=receita_mensal["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")),
    labels={"Valor": "Receita (R$)", "Mês_Ano": "Mês"},
)
fig_receita.update_traces(textposition="inside")
fig_receita.update_layout(height=400, margin=dict(t=50))
st.plotly_chart(fig_receita, use_container_width=True)

# 📊 Receita por Serviço e Produto
st.subheader("📊 Receita por Serviço e Produto")
df_tipos = df_cliente[["Serviço", "Tipo", "Valor"]].copy()
receita_geral = df_tipos.groupby(["Serviço", "Tipo"])["Valor"].sum().reset_index()
fig_receita_tipos = px.bar(
    receita_geral,
    x="Serviço",
    y="Valor",
    color="Tipo",
    text=receita_geral["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")),
    labels={"Valor": "Receita (R$)", "Serviço": "Item"},
    barmode="group"
)
fig_receita_tipos.update_traces(textposition="outside")
fig_receita_tipos.update_layout(height=450, margin=dict(t=80))
st.plotly_chart(fig_receita_tipos, use_container_width=True)

# 📊 Atendimentos por Funcionário
st.subheader("📊 Atendimentos por Funcionário")
atendimentos_unicos = df_cliente.drop_duplicates(subset=["Cliente", "Data", "Funcionário"])
atendimentos_por_funcionario = atendimentos_unicos["Funcionário"].value_counts().reset_index()
atendimentos_por_funcionario.columns = ["Funcionário", "Qtd Atendimentos"]
st.dataframe(atendimentos_por_funcionario, use_container_width=True)

# 📋 Resumo de Atendimentos
st.subheader("📋 Resumo de Atendimentos")
resumo = df_cliente.groupby("Data").agg(
    Qtd_Serviços=("Serviço", "count"),
    Qtd_Produtos=("Tipo", lambda x: (x == "Produto").sum())
).reset_index()
resumo["Qtd_Combo"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x > 1 else 0)
resumo["Qtd_Simples"] = resumo["Qtd_Serviços"].apply(lambda x: 1 if x == 1 else 0)
resumo_final = pd.DataFrame({
    "Total Atendimentos": [resumo.shape[0]],
    "Qtd Combos": [resumo["Qtd_Combo"].sum()],
    "Qtd Simples": [resumo["Qtd_Simples"].sum()]
})
st.dataframe(resumo_final, use_container_width=True)

# 📈 Frequência + Insights
st.subheader("📈 Frequência de Atendimento")
data_corte = pd.to_datetime("2025-05-11")
df_antes = df_cliente[df_cliente["Data"] < data_corte].copy()
df_depois = df_cliente[df_cliente["Data"] >= data_corte].drop_duplicates(subset=["Data"]).copy()
df_freq = pd.concat([df_antes, df_depois]).sort_values("Data")
datas = df_freq["Data"].tolist()

if len(datas) < 2:
    st.info("Cliente possui apenas um atendimento. Frequência não aplicável.")
else:
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media_freq = sum(diffs) / len(diffs)
    ultimo_atendimento = datas[-1]
    dias_desde_ultimo = (pd.Timestamp.today().normalize() - ultimo_atendimento).days
    status = "🟢 Em dia" if dias_desde_ultimo <= media_freq else "🟠 Pouco atrasado" if dias_desde_ultimo <= media_freq * 1.5 else "🔴 Muito atrasado"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📅 Último Atendimento", ultimo_atendimento.strftime("%d/%m/%Y"))
    col2.metric("📊 Frequência Média", f"{media_freq:.1f} dias")
    col3.metric("⏱️ Dias Desde Último", dias_desde_ultimo)
    col4.metric("📌 Status", status)

    # Insights adicionais
    st.subheader("💡 Insights do Cliente")
    total_atendimentos = resumo.shape[0]
    tipo_mais_comum = "Simples" if resumo["Qtd_Simples"].sum() >= resumo["Qtd_Combo"].sum() else "Combo"
    st.markdown(
        f"- Este cliente já teve **{total_atendimentos} atendimentos**.\n"
        f"- O tipo mais comum foi: **{tipo_mais_comum}**.\n"
        f"- A frequência média é de **{media_freq:.1f} dias**, com o último atendimento há **{dias_desde_ultimo} dias**.\n"
        f"- Status atual: **{status.replace('🟢 ', '').replace('🟠 ', '').replace('🔴 ', '')}**"
    )

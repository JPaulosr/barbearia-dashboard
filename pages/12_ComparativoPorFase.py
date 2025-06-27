import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import plotly.express as px
import io

st.set_page_config(layout="wide")
st.title("📆 Comparativo Mensal por Fase")

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

    # Padronizar nomes antigos de fases
    df_base["Fase"] = df_base["Fase"].replace({
        "Funcionário": "Dono + funcionário",
        "Dono Salão": "Dono (sozinho)"
    })

    df_desp.columns = df_desp.columns.str.strip()
    df_desp["Data"] = pd.to_datetime(df_desp["Data"], errors="coerce")
    df_desp = df_desp.dropna(subset=["Data"])
    df_desp["Ano"] = df_desp["Data"].dt.year
    df_desp["Mês"] = df_desp["Data"].dt.month

    return df_base, df_desp

df, df_despesas = carregar_bases()

meses = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

mes_nome = st.selectbox("📅 Selecione o mês para comparação", list(meses.values()), index=11)
mes_num = [k for k, v in meses.items() if v == mes_nome][0]

# Filtrar por mês
df_mes = df[df["Mês"] == mes_num]
df_desp_mes = df_despesas[df_despesas["Mês"] == mes_num]

# Tabela comparativa por ano e fase
tabela = []
for (ano, fase), grupo in df_mes.groupby(["Ano", "Fase"]):
    receita = grupo["Valor"].sum()
    # Despesas associadas à fase
    if fase == "Autônomo (prestador)":
        desp = df_desp_mes[df_desp_mes["Descrição"].str.lower().str.contains("neto|produto", na=False)]
    elif fase == "Dono (sozinho)":
        desp = df_desp_mes[~df_desp_mes["Descrição"].str.lower().str.contains("vinicius|neto", na=False)]
    elif fase == "Dono + funcionário":
        desp = df_desp_mes[~df_desp_mes["Descrição"].str.lower().str.contains("neto", na=False)]
    else:
        desp = df_desp_mes.copy()

    desp = desp[desp["Ano"] == ano]
    total_desp = desp["Valor"].sum()
    lucro = receita - total_desp
    tabela.append({"Ano": ano, "Fase": fase, "Receita": receita, "Despesa": total_desp, "Lucro": lucro})

st.subheader(f"📊 Comparativo de {mes_nome}")
df_tabela = pd.DataFrame(tabela).sort_values(by=["Ano", "Fase"])
st.dataframe(df_tabela, use_container_width=True)

# Gráfico
fig = px.bar(df_tabela, x="Ano", y="Lucro", color="Fase", barmode="group",
             title=f"Lucro por Fase no mês de {mes_nome}", labels={"Lucro": "Lucro (R$)"})
fig.update_layout(
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    font=dict(color="white"),
    title_x=0.5
)
st.plotly_chart(fig, use_container_width=True)

# Exportação
st.subheader("📤 Exportar Resultado")
output = io.BytesIO()
with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
    df_tabela.to_excel(writer, index=False, sheet_name=f"{mes_nome}")
    writer.save()
    dados_excel = output.getvalue()

st.download_button(
    label="⬇️ Baixar Excel (.xlsx)",
    data=dados_excel,
    file_name=f"comparativo_fases_{mes_nome.lower()}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


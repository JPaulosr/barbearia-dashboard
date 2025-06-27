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
DESPESAS_ABA = "Despesas"

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
def carregar_comissoes():
    planilha = conectar_sheets()
    aba = planilha.worksheet(DESPESAS_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    df = df[df["Descrição"].str.contains("vinicius", case=False, na=False)]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Ano"] = df["Data"].dt.year.astype(int)
    df["Mes"] = df["Data"].dt.month
    df["Valor"] = df["Valor"].astype(str).replace("R\\$", "", regex=True).str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)
    return df

comissoes_vinicius = carregar_comissoes()

# === Lista de funcionários ===
funcionarios = df["Funcionário"].dropna().unique().tolist()
funcionarios.sort()

# === Filtro por ano ===
anos = sorted(df["Ano"].dropna().unique().tolist(), reverse=True)
ano_escolhido = st.selectbox("🗕️ Filtrar por ano", anos)

# === Seleção de funcionário ===
funcionario_escolhido = st.selectbox("📋 Escolha um funcionário", funcionarios)
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
    df_vini = df[(df["Funcionário"] == "Vinicius") & (df["Ano"] == 2025)].copy()
    df_vini["MesNum"] = df_vini["Data"].dt.month
    df_vini["MesNome"] = df_vini["MesNum"].map(meses_pt) + df_vini["Data"].dt.strftime(" %Y")
    receita_vini = df_vini.groupby(["MesNum", "MesNome"])["Valor"].sum().reset_index(name="Vinicius")

    comissoes_filtradas = comissoes_vinicius[comissoes_vinicius["Ano"] == 2025]
    comissoes_mensais = comissoes_filtradas.groupby("Mes")["Valor"].sum().reset_index()
    comissoes_mensais.columns = ["MesNum", "ComissaoVinicius"]

    receita_merged = pd.merge(receita_jp, receita_vini, on=["MesNum", "MesNome"], how="left")
    receita_merged = pd.merge(receita_merged, comissoes_mensais, on="MesNum", how="left")
    receita_merged["Com_Vinicius"] = receita_merged["JPaulo"] + receita_merged["ComissaoVinicius"].fillna(0)

    receita_melt = receita_merged.melt(id_vars=["MesNum", "MesNome"], value_vars=["JPaulo", "Com_Vinicius"],
                                       var_name="Tipo", value_name="Valor")
    receita_melt = receita_melt.sort_values("MesNum")

    fig_mensal_comp = px.bar(receita_melt, x="MesNome", y="Valor", color="Tipo", barmode="group", text_auto=True,
                              labels={"Valor": "Receita (R$)", "MesNome": "Mês", "Tipo": ""})
    fig_mensal_comp.update_layout(height=450, template="plotly_white")
    st.plotly_chart(fig_mensal_comp, use_container_width=True)

    receita_merged["Comissao Formatada"] = receita_merged["ComissaoVinicius"].fillna(0).apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    receita_merged["JPaulo Formatado"] = receita_merged["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    receita_merged["Total Formatado"] = receita_merged["Com_Vinicius"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

    tabela = receita_merged[["MesNome", "JPaulo Formatado", "Comissao Formatada", "Total Formatado"]]
    tabela.columns = ["Mês", "Receita JPaulo", "Comissão do Vinicius", "Total (JPaulo + Comissão)"]
    st.dataframe(tabela, use_container_width=True)
else:
    receita_jp["Valor Formatado"] = receita_jp["JPaulo"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
    fig_mensal = px.bar(receita_jp, x="MesNome", y="JPaulo", text="Valor Formatado",
                        labels={"JPaulo": "Receita (R$)", "MesNome": "Mês"})
    fig_mensal.update_layout(height=450, template="plotly_white", margin=dict(t=40, b=20))
    fig_mensal.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(fig_mensal, use_container_width=True)

# === Ticket Médio por Mês
st.subheader("📉 Ticket Médio por Mês")
data_referencia = pd.to_datetime("2025-05-11")
df_func["Grupo"] = df_func["Data"].dt.strftime("%Y-%m-%d") + "_" + df_func["Cliente"]
antes_ticket = df_func[df_func["Data"] < data_referencia].copy()
antes_ticket["AnoMes"] = antes_ticket["Data"].dt.to_period("M").astype(str)
antes_ticket = antes_ticket.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")

depois_ticket = df_func[df_func["Data"] >= data_referencia].copy()
depois_ticket = depois_ticket.groupby(["Grupo", "Data"])["Valor"].sum().reset_index()
depois_ticket["AnoMes"] = depois_ticket["Data"].dt.to_period("M").astype(str)
depois_ticket = depois_ticket.groupby("AnoMes")["Valor"].mean().reset_index(name="Ticket Médio")

ticket_mensal = pd.concat([antes_ticket, depois_ticket]).groupby("AnoMes")["Ticket Médio"].mean().reset_index()
ticket_mensal["Ticket Médio Formatado"] = ticket_mensal["Ticket Médio"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
st.dataframe(ticket_mensal, use_container_width=True)

# === Exportar dados ===
st.subheader("📤 Exportar dados filtrados")
buffer = BytesIO()
df_func.to_excel(buffer, index=False, sheet_name="Filtrado", engine="openpyxl")
st.download_button("Baixar Excel com dados filtrados", data=buffer.getvalue(), file_name="dados_filtrados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

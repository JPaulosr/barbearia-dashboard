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
    df.columns = [str(col).strip() for col in df.columns]
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Data_str"] = df["Data"].dt.strftime("%d/%m/%Y")
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month

    # Meses em português
    meses_pt = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    df["Mês_Ano"] = df["Data"].dt.month.map(meses_pt) + "/" + df["Data"].dt.year.astype(str)
    return df

df = carregar_dados()

# === Filtro de cliente (com fallback da sessão)
clientes_disponiveis = sorted(df["Cliente"].dropna().unique())
cliente_default = st.session_state.get("cliente") if "cliente" in st.session_state else clientes_disponiveis[0]
cliente = st.selectbox("👤 Selecione o cliente para detalhamento", clientes_disponiveis, index=clientes_disponiveis.index(cliente_default))

# === COMPARAÇÃO ENTRE CLIENTES ===
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

# Filtra dados do cliente selecionado
df_cliente = df[df["Cliente"] == cliente]

# 📅 Histórico de atendimentos
st.subheader(f"📅 Histórico de atendimentos - {cliente}")
st.dataframe(df_cliente.sort_values("Data", ascending=False).drop(columns=["Data"]).rename(columns={"Data_str": "Data"}), use_container_width=True)

# 📊 Receita mensal
st.subheader("📊 Receita mensal")
receita_mensal = df_cliente.groupby("Mês_Ano")["Valor"].sum().reset_index()
fig_receita = px.bar(
    receita_mensal,
    x="Mês_Ano",
    y="Valor",
    text=receita_mensal["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")),
    labels={"Valor": "Receita (R$)", "Mês_Ano": "Mês"},
)
fig_receita.update_traces(textposition="inside")
fig_receita.update_layout(height=400, margin=dict(t=50), uniformtext_minsize=10, uniformtext_mode='show')
st.plotly_chart(fig_receita, use_container_width=True)

# === Corrige tipo da coluna de duração se existir
df_cliente["Duração (min)"] = pd.to_numeric(df_cliente.get("Duração (min)"), errors="coerce")

# === Receita por Serviço e Produto
st.subheader("📊 Receita por Serviço e Produto")
df_tipos = df_cliente[["Serviço", "Tipo", "Valor"]].copy()
receita_geral = df_tipos.groupby(["Serviço", "Tipo"])["Valor"].sum().reset_index()
receita_geral = receita_geral.sort_values("Valor", ascending=False)
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
fig_receita_tipos.update_layout(height=450, margin=dict(t=80), uniformtext_minsize=10, uniformtext_mode='show')
st.plotly_chart(fig_receita_tipos, use_container_width=True)

# === Atendimentos por Funcionário
st.subheader("📊 Atendimentos por Funcionário")
atendimentos_unicos = df_cliente.drop_duplicates(subset=["Cliente", "Data", "Funcionário"])
atendimentos_por_funcionario = atendimentos_unicos["Funcionário"].value_counts().reset_index()
atendimentos_por_funcionario.columns = ["Funcionário", "Qtd Atendimentos"]
st.dataframe(atendimentos_por_funcionario, use_container_width=True)

# === Resumo de Atendimentos
st.subheader("📋 Resumo de Atendimentos")
df_cliente_dt = df.copy()
df_cliente_dt = df_cliente_dt[df_cliente_dt["Cliente"] == cliente]
resumo = df_cliente_dt.groupby("Data").agg(
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

# === Frequência do Cliente
st.subheader("📈 Frequência de Atendimento")
data_corte = pd.to_datetime("2025-05-11")
df_antes = df_cliente_dt[df_cliente_dt["Data"] < data_corte].copy()
df_depois = df_cliente_dt[df_cliente_dt["Data"] >= data_corte].drop_duplicates(subset=["Data"]).copy()
df_freq = pd.concat([df_antes, df_depois]).sort_values("Data")
datas = df_freq["Data"].tolist()

if len(datas) < 2:
    st.info("Cliente possui apenas um atendimento. Frequência não aplicável.")
else:
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media_freq = sum(diffs) / len(diffs)
    ultimo_atendimento = datas[-1]
    dias_desde_ultimo = (pd.Timestamp.today().normalize() - ultimo_atendimento).days

    if dias_desde_ultimo <= media_freq:
        status = "🟢 Em dia"
    elif dias_desde_ultimo <= media_freq * 1.5:
        status = "🟠 Pouco atrasado"
    else:
        status = "🔴 Muito atrasado"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("📅 Último Atendimento", ultimo_atendimento.strftime("%d/%m/%Y"))
    col2.metric("📊 Frequência Média", f"{media_freq:.1f} dias")
    col3.metric("⏱️ Dias Desde Último", dias_desde_ultimo)
    col4.metric("📌 Status", status)

    # === Insights Adicionais do Cliente
    st.subheader("💡 Insights Adicionais do Cliente")

    meses_ativos = df_cliente["Mês_Ano"].nunique()
    gasto_mensal_medio = df_cliente["Valor"].sum() / meses_ativos if meses_ativos > 0 else 0
    status_vip = "Sim ⭐" if gasto_mensal_medio >= 70 else "Não"

    mais_frequente = df_cliente["Funcionário"].mode()[0] if not df_cliente["Funcionário"].isna().all() else "Indefinido"

    tempo_total = df_cliente["Duração (min)"].sum() if "Duração (min)" in df_cliente.columns else None
    tempo_total_str = f"{int(tempo_total)} minutos" if pd.notna(tempo_total) else "Indisponível"

    ticket_medio = df_cliente["Valor"].mean()
    intervalo_medio = media_freq if len(datas) >= 2 else None

    col5, col6, col7 = st.columns(3)
    col5.metric("🏅 Cliente VIP", status_vip)
    col6.metric("💇 Mais atendido por", mais_frequente)
    col7.metric("🕒 Tempo Total no Salão", tempo_total_str)

    col8, col9 = st.columns(2)
    col8.metric("💸 Ticket Médio", f"R$ {ticket_medio:.2f}".replace(".", ","))
    col9.metric("📆 Intervalo Médio", f"{intervalo_medio:.1f} dias" if intervalo_medio else "Indisponível")

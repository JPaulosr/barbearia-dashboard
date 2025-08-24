import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(layout="wide")
st.title("📊 Dashboard Salão JP")

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
    # Normaliza Data
    df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
    df = df.dropna(subset=["Data"])
    # Derivadas de tempo
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Ano-Mês"] = df["Data"].dt.to_period("M").astype(str)
    return df

df_full = carregar_dados()  # base intacta para partirmos sempre do mesmo lugar

# --- Identifica coluna de pagamento/conta que indica FIADO ---
col_conta = next(
    (c for c in df_full.columns if c.strip().lower() in ["conta", "forma de pagamento", "pagamento", "status"]),
    None
)
if col_conta:
    is_fiado_full = df_full[col_conta].astype(str).str.strip().str.lower().eq("fiado")
else:
    is_fiado_full = pd.Series(False, index=df_full.index)  # se não houver coluna, ninguém é fiado

# === Sidebar: Filtros ===
st.sidebar.header("🎛️ Filtros")

# Filtro de pagamento (igual à imagem)
pagamento_opcao = st.sidebar.radio(
    "Filtro de pagamento",
    ["Apenas pagos", "Apenas fiado", "Incluir tudo"],
    index=0,
    help="Pagos = tudo que NÃO é 'Fiado'. Escolha 'Apenas fiado' para ver somente fiados; "
         "'Incluir tudo' considera pagos + fiados."
)
aplicar_hist = st.sidebar.checkbox("Aplicar no histórico (tabela)", value=False)

# Máscara para valores (receita)
if pagamento_opcao == "Apenas pagos":
    mask_valores_full = ~is_fiado_full
elif pagamento_opcao == "Apenas fiado":
    mask_valores_full = is_fiado_full
else:  # Incluir tudo
    mask_valores_full = pd.Series(True, index=df_full.index)

# Máscara para base histórica (tabelas/contagens)
mask_historico_full = mask_valores_full if aplicar_hist else pd.Series(True, index=df_full.index)

# --- Deriva bases com as máscaras escolhidas ---
df_valores_full = df_full[mask_valores_full].copy()   # usado para somatórios/gráficos de VALOR
df_hist_full    = df_full[mask_historico_full].copy() # usado para histórico/contagens/tabelas

# === Filtro por Ano e Meses múltiplos ===
anos_disponiveis = sorted(df_full["Ano"].dropna().unique(), reverse=True)
ano_escolhido = st.sidebar.selectbox("🗓️ Escolha o Ano", anos_disponiveis)

meses_pt = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

meses_disponiveis = sorted(df_full[df_full["Ano"] == ano_escolhido]["Mês"].dropna().unique())
mes_opcoes = [meses_pt[m] for m in meses_disponiveis]
meses_selecionados = st.sidebar.multiselect("📆 Selecione os Meses (opcional)", mes_opcoes, default=mes_opcoes)

if meses_selecionados:
    meses_numeros = [k for k, v in meses_pt.items() if v in meses_selecionados]
    df_hist = df_hist_full[(df_hist_full["Ano"] == ano_escolhido) & (df_hist_full["Mês"].isin(meses_numeros))].copy()
    df_valores = df_valores_full[(df_valores_full["Ano"] == ano_escolhido) & (df_valores_full["Mês"].isin(meses_numeros))].copy()
else:
    df_hist = df_hist_full[df_hist_full["Ano"] == ano_escolhido].copy()
    df_valores = df_valores_full[df_valores_full["Ano"] == ano_escolhido].copy()

# Coluna numérica de valor para as bases de VALOR
df_valores["ValorNum"] = pd.to_numeric(df_valores["Valor"], errors="coerce").fillna(0)

# === Indicadores principais ===
receita_total = df_valores["ValorNum"].sum()  # respeita o filtro de pagamento
total_atendimentos = len(df_hist)             # respeita "Aplicar no histórico (tabela)" se marcado

# Clientes únicos com a regra 11/05/2025 (na base histórica)
data_limite = pd.to_datetime("2025-05-11")
antes = df_hist[df_hist["Data"] < data_limite]
depois = df_hist[df_hist["Data"] >= data_limite].drop_duplicates(subset=["Cliente", "Data"])
clientes_unicos = pd.concat([antes, depois])["Cliente"].nunique()

ticket_medio = receita_total / total_atendimentos if total_atendimentos else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 Receita Total", f"R$ {receita_total:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col2.metric("📅 Total de Atendimentos", total_atendimentos)
col3.metric("🎯 Ticket Médio", f"R$ {ticket_medio:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))
col4.metric("🟢 Clientes Ativos", clientes_unicos)

# === Receita por Funcionário ===
st.markdown("### 📊 Receita por Funcionário")
df_func = df_valores.groupby("Funcionário")["ValorNum"].sum().reset_index().rename(columns={"ValorNum": "Valor"})
fig_func = px.bar(df_func, x="Funcionário", y="Valor", text_auto=True)
fig_func.update_traces(marker_color=["#5179ff", "#33cc66", "#ff9933"])
fig_func.update_layout(height=400, yaxis_title="Receita (R$)", showlegend=False)
st.plotly_chart(fig_func, use_container_width=True)

# === Receita por Tipo ===
st.markdown("### 🧾 Receita por Tipo")
df_tipo = df_valores.copy()
df_tipo["Tipo"] = df_tipo["Serviço"].apply(
    lambda x: "Combo" if "combo" in str(x).lower()
    else "Produto" if ("gel" in str(x).lower() or "produto" in str(x).lower())
    else "Serviço"
)
df_pizza = df_tipo.groupby("Tipo")["ValorNum"].sum().reset_index().rename(columns={"ValorNum": "Valor"})
fig_pizza = px.pie(df_pizza, values="Valor", names="Tipo", title="Distribuição de Receita")
fig_pizza.update_traces(textinfo='percent+label')
st.plotly_chart(fig_pizza, use_container_width=True)

# === Top 10 Clientes (frequência da base histórica + valor da base de valores) ===
st.markdown("### 🥇 Top 10 Clientes")
nomes_excluir = ["boliviano", "brasileiro", "menino"]

# contagem de serviços (frequência) — histórica (pode ou não aplicar fiado, conforme checkbox)
cnt = df_hist.groupby("Cliente")["Serviço"].count().rename("Qtd_Serviços")

# soma de valores — sempre respeita filtro de pagamento escolhido
val = df_valores.groupby("Cliente")["ValorNum"].sum().rename("Valor")

df_top = pd.concat([cnt, val], axis=1).reset_index().fillna(0)
df_top = df_top[~df_top["Cliente"].str.lower().isin(nomes_excluir)]
df_top = df_top.sort_values(by="Valor", ascending=False).head(10)
df_top["Valor Formatado"] = df_top["Valor"].apply(lambda x: f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", "."))

st.dataframe(df_top[["Cliente", "Qtd_Serviços", "Valor Formatado"]], use_container_width=True)

st.markdown("---")
st.caption("Criado por JPaulo ✨ | Versão principal do painel consolidado")

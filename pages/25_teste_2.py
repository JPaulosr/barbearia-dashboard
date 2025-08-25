# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
import re

st.set_page_config(layout="wide", page_title="Dashboard Salão JP", page_icon="💈")
st.title("📊 Dashboard Salão JP")

# =========================
# CONFIG / CONSTANTES
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
BASE_ABA = "Base de Dados"
DATA_CORTE_UNICIDADE = pd.to_datetime("2025-05-11")

MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}
NOMES_EXCLUIR_RANKINGS = ["boliviano", "brasileiro", "menino"]

# Padrões de identificação
REGEX_PRODUTO = re.compile(r"(produto|gel|pomad|shampoo|cera|spray|po\b|pó\b|p\u00f3\b)", re.IGNORECASE)
REGEX_CAIXINHA = re.compile(r"(caix|gorjet)", re.IGNORECASE)

# =========================
# ESTILOS (CSS leve para cards)
# =========================
st.markdown("""
<style>
.kpi-grid {display:grid; grid-template-columns: repeat(5, minmax(180px, 1fr)); gap: 12px;}
.kpi-card {background:#111418; border:1px solid #262b33; border-radius:16px; padding:14px;}
.kpi-title {font-size:0.90rem; color:#aab2c5; margin:0;}
.kpi-value {font-size:1.4rem; font-weight:700; margin-top:6px;}
.block {background:#0c0f13; border:1px solid #1e242d; border-radius:16px; padding:14px;}
.section-title {font-weight:700; font-size:1.05rem; margin-bottom:0.5rem;}
.stPlotlyChart {background:transparent;}
</style>
""", unsafe_allow_html=True)

# =========================
# GOOGLE SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

@st.cache_data(show_spinner=False)
def carregar_dados():
    planilha = conectar_sheets()
    aba = planilha.worksheet(BASE_ABA)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]

    # Normaliza Data
    df["Data"] = pd.to_datetime(df.get("Data"), errors="coerce")
    df = df.dropna(subset=["Data"])

    # Valor numérico
    df["ValorNum"] = pd.to_numeric(df.get("Valor"), errors="coerce").fillna(0)

    # Derivadas de tempo
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Ano-Mês"] = df["Data"].dt.to_period("M").astype(str)
    return df

df_full = carregar_dados()

# =========================
# DETECÇÃO DE COLUNA DE PAGAMENTO / FIADO
# =========================
col_conta = next(
    (c for c in df_full.columns if c.strip().lower() in ["conta", "forma de pagamento", "pagamento", "status"]),
    None
)
if col_conta:
    is_fiado_full = df_full[col_conta].astype(str).str.strip().str.lower().eq("fiado")
else:
    is_fiado_full = pd.Series(False, index=df_full.index)

# =========================
# SIDEBAR: FILTROS
# =========================
st.sidebar.header("🎛️ Filtros")

pagamento_opcao = st.sidebar.radio(
    "Filtro de pagamento",
    ["Apenas pagos", "Apenas fiado", "Incluir tudo"],
    index=0,
    help="Pagos = tudo que NÃO é 'Fiado'. 'Apenas fiado' mostra somente fiados; 'Incluir tudo' mostra ambos."
)

aplicar_hist = st.sidebar.checkbox("Aplicar no histórico (contagens e tabelas)", value=False)

anos_disponiveis = sorted(df_full["Ano"].dropna().unique(), reverse=True)
ano_escolhido = st.sidebar.selectbox("🗓️ Ano", anos_disponiveis)

meses_disponiveis = sorted(df_full[df_full["Ano"] == ano_escolhido]["Mês"].dropna().unique())
mes_opcoes = [MESES_PT[m] for m in meses_disponiveis]
meses_selecionados = st.sidebar.multiselect("📆 Meses (opcional)", mes_opcoes, default=mes_opcoes)

# =========================
# CONSTRUÇÃO DAS MÁSCARAS
# =========================
# Máscara de valores conforme filtro de pagamento
if pagamento_opcao == "Apenas pagos":
    mask_valores_full = ~is_fiado_full
elif pagamento_opcao == "Apenas fiado":
    mask_valores_full = is_fiado_full
else:
    mask_valores_full = pd.Series(True, index=df_full.index)

# Máscara para histórico (contagens/tabelas)
mask_historico_full = mask_valores_full if aplicar_hist else pd.Series(True, index=df_full.index)

# Filtra por ano/meses
if meses_selecionados:
    meses_numeros = [k for k, v in MESES_PT.items() if v in meses_selecionados]
    df_hist = df_full[mask_historico_full & (df_full["Ano"] == ano_escolhido) & (df_full["Mês"].isin(meses_numeros))].copy()
    df_valores = df_full[mask_valores_full & (df_full["Ano"] == ano_escolhido) & (df_full["Mês"].isin(meses_numeros))].copy()
else:
    df_hist = df_full[mask_historico_full & (df_full["Ano"] == ano_escolhido)].copy()
    df_valores = df_full[mask_valores_full & (df_full["Ano"] == ano_escolhido)].copy()

# =========================
# FUNÇÕES AUXILIARES
# =========================
def brl(x: float) -> str:
    return f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

def is_produto(nome_servico: str) -> bool:
    if not isinstance(nome_servico, str): return False
    return bool(REGEX_PRODUTO.search(nome_servico))

def is_caixinha(nome_servico: str) -> bool:
    if not isinstance(nome_servico, str): return False
    return bool(REGEX_CAIXINHA.search(nome_servico))

# Flags de tipo
df_valores["EhProduto"] = df_valores["Serviço"].astype(str).apply(is_produto)
df_valores["EhCaixinha"] = df_valores["Serviço"].astype(str).apply(is_caixinha)
df_valores["EhServico"]  = ~(df_valores["EhProduto"] | df_valores["EhCaixinha"])

# =========================
# KPI's PRINCIPAIS
# =========================
receita_total = float(df_valores["ValorNum"].sum())
total_atendimentos = len(df_hist)

# Clientes únicos com regra de unicidade a partir de 11/05/2025
antes = df_hist[df_hist["Data"] < DATA_CORTE_UNICIDADE]
depois = df_hist[df_hist["Data"] >= DATA_CORTE_UNICIDADE].drop_duplicates(subset=["Cliente", "Data"])
clientes_unicos = pd.concat([antes, depois])["Cliente"].nunique()

ticket_medio = (receita_total / total_atendimentos) if total_atendimentos else 0.0

# Caixinha no período (geral)
caixinha_periodo_total = float(df_valores.loc[df_valores["EhCaixinha"], "ValorNum"].sum())

# =========================
# CARDS SUPERIORES
# =========================
st.markdown('<div class="kpi-grid">', unsafe_allow_html=True)

st.markdown(f'''
<div class="kpi-card">
  <p class="kpi-title">💰 Receita Total</p>
  <div class="kpi-value">{brl(receita_total)}</div>
</div>''', unsafe_allow_html=True)

st.markdown(f'''
<div class="kpi-card">
  <p class="kpi-title">📅 Total de Atendimentos</p>
  <div class="kpi-value">{total_atendimentos}</div>
</div>''', unsafe_allow_html=True)

st.markdown(f'''
<div class="kpi-card">
  <p class="kpi-title">🎯 Ticket Médio</p>
  <div class="kpi-value">{brl(ticket_medio)}</div>
</div>''', unsafe_allow_html=True)

st.markdown(f'''
<div class="kpi-card">
  <p class="kpi-title">🟢 Clientes Ativos</p>
  <div class="kpi-value">{clientes_unicos}</div>
</div>''', unsafe_allow_html=True)

st.markdown(f'''
<div class="kpi-card">
  <p class="kpi-title">🎁 Caixinha (Período)</p>
  <div class="kpi-value">{brl(caixinha_periodo_total)}</div>
</div>''', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# =========================
# CAIXINHAS — POR FUNCIONÁRIO (PERÍODO) + TOTAL ANUAL
# =========================
st.markdown("")
col_a, col_b = st.columns([1.1, 1])

with col_a:
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🎁 Caixinhas por Funcionário (período filtrado)</div>', unsafe_allow_html=True)
    df_cx_func = (
        df_valores[df_valores["EhCaixinha"]]
        .groupby("Funcionário", dropna=False)["ValorNum"]
        .sum().reset_index()
        .rename(columns={"ValorNum": "Caixinha"})
        .sort_values("Caixinha", ascending=False)
    )
    if not df_cx_func.empty:
        df_cx_func["Caixinha"] = df_cx_func["Caixinha"].astype(float)
        fig_cx = px.bar(df_cx_func, x="Funcionário", y="Caixinha", text_auto=True)
        fig_cx.update_layout(height=340, yaxis_title="Valor (R$)", showlegend=False, margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig_cx, use_container_width=True)
    else:
        st.info("Nenhuma caixinha encontrada no período com os filtros atuais.")
    st.markdown('</div>', unsafe_allow_html=True)

with col_b:
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📅 Caixinha Total no Ano</div>', unsafe_allow_html=True)
    df_ano = df_full[(df_full["Ano"] == ano_escolhido)]
    # Respeita filtro de pagamento para valores?
    # Normalmente caixinha é 'paga', mas seguimos o mesmo critério escolhido para manter consistência visual:
    df_ano = df_ano[mask_valores_full.loc[df_ano.index]] if len(mask_valores_full) == len(df_full) else df_ano
    cx_ano = float(df_ano[df_ano["Serviço"].astype(str).apply(is_caixinha)]["ValorNum"].sum())
    st.metric("Total no Ano", brl(cx_ano))
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# TENDÊNCIA MENSAL (RECEITA) — APENAS DO ANO SELECIONADO
# =========================
st.markdown('<div class="block">', unsafe_allow_html=True)
st.markdown('<div class="section-title">📈 Tendência Mensal de Receita (Ano Selecionado)</div>', unsafe_allow_html=True)
df_anual_val = df_full[(df_full["Ano"] == ano_escolhido)]
df_anual_val = df_anual_val[mask_valores_full.loc[df_anual_val.index]] if len(mask_valores_full) == len(df_full) else df_anual_val

df_mensal = (
    df_anual_val.groupby("Mês")["ValorNum"]
    .sum().reset_index().sort_values("Mês")
)
if not df_mensal.empty:
    df_mensal["MêsNome"] = df_mensal["Mês"].map(MESES_PT)
    fig_mes = px.bar(df_mensal, x="MêsNome", y="ValorNum", text_auto=True)
    fig_mes.update_layout(height=360, yaxis_title="Receita (R$)", xaxis_title=None, margin=dict(l=10,r=10,t=30,b=10))
    st.plotly_chart(fig_mes, use_container_width=True)
else:
    st.info("Sem dados de receita para o ano selecionado com os filtros atuais.")
st.markdown('</div>', unsafe_allow_html=True)

# =========================
# PRODUTOS VENDIDOS (QTD) + TOP PRODUTOS (VALOR)
# =========================
st.markdown("")
col_p1, col_p2 = st.columns([1.2, 1])

with col_p1:
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🛍️ Produtos Vendidos (quantidade)</div>', unsafe_allow_html=True)
    df_prod = df_valores[df_valores["EhProduto"]].copy()
    if not df_prod.empty:
        top_qty = (
            df_prod.groupby("Serviço")["Serviço"].count()
            .rename("Qtd").reset_index()
            .sort_values("Qtd", ascending=False).head(12)
        )
        fig_prod_qtd = px.bar(top_qty, x="Serviço", y="Qtd", text_auto=True)
        fig_prod_qtd.update_layout(height=360, yaxis_title="Quantidade", xaxis_title=None, margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig_prod_qtd, use_container_width=True)
    else:
        st.info("Nenhum produto vendido no período filtrado.")
    st.markdown('</div>', unsafe_allow_html=True)

with col_p2:
    st.markdown('<div class="block">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏆 Top Produtos por Valor</div>', unsafe_allow_html=True)
    if not df_prod.empty:
        top_val = (
            df_prod.groupby("Serviço")["ValorNum"].sum()
            .reset_index().rename(columns={"ValorNum":"Valor"})
            .sort_values("Valor", ascending=False).head(10)
        )
        top_val["Valor"] = top_val["Valor"].astype(float)
        top_val["Valor"] = top_val["Valor"].apply(brl)
        st.dataframe(top_val, use_container_width=True, hide_index=True)
    else:
        st.info("Sem valores de produtos no período filtrado.")
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# TOP SERVIÇOS (exclui produtos e caixinha)
# =========================
st.markdown('<div class="block">', unsafe_allow_html=True)
st.markdown('<div class="section-title">✂️ Top Serviços por Valor</div>', unsafe_allow_html=True)
df_serv = df_valores[df_valores["EhServico"]].copy()
if not df_serv.empty:
    top_serv = (
        df_serv.groupby("Serviço")["ValorNum"].sum()
        .reset_index().rename(columns={"ValorNum":"Valor"})
        .sort_values("Valor", ascending=False).head(12)
    )
    fig_serv = px.bar(top_serv, x="Serviço", y="Valor", text_auto=True)
    fig_serv.update_layout(height=360, yaxis_title="Receita (R$)", xaxis_title=None, margin=dict(l=10,r=10,t=30,b=10))
    st.plotly_chart(fig_serv, use_container_width=True)
else:
    st.info("Sem serviços para exibir neste período.")
st.markdown('</div>', unsafe_allow_html=True)

# =========================
# TOP 10 CLIENTES (frequência + valor) — mantém sua lógica base
# =========================
st.markdown('<div class="block">', unsafe_allow_html=True)
st.markdown('<div class="section-title">🥇 Top 10 Clientes</div>', unsafe_allow_html=True)

# Frequência (histórico)
cnt = df_hist.groupby("Cliente")["Serviço"].count().rename("Qtd_Serviços")

# Soma de valores (respeita filtro pagamento)
val = df_valores.groupby("Cliente")["ValorNum"].sum().rename("Valor")

df_top = pd.concat([cnt, val], axis=1).reset_index().fillna(0)
df_top = df_top[~df_top["Cliente"].str.lower().isin(NOMES_EXCLUIR_RANKINGS)]
df_top = df_top.sort_values(by="Valor", ascending=False).head(10)
if not df_top.empty:
    df_top["Valor Formatado"] = df_top["Valor"].apply(brl)
    st.dataframe(df_top[["Cliente", "Qtd_Serviços", "Valor Formatado"]], use_container_width=True, hide_index=True)
else:
    st.info("Sem clientes para exibir com os filtros atuais.")
st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")
st.caption("Criado por JPaulo ✨ | Versão modernizada do painel")

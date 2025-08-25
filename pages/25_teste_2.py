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

# Produtos por nome do serviço
REGEX_PRODUTO = re.compile(r"(produto|gel|pomad|shampoo|cera|spray|po\b|pó\b|p\u00f3\b)", re.IGNORECASE)

# --- URNA: regra de divisão ---
URNA_SPLIT_YEAR = 2025      # a partir deste ano divide
URNA_PCT_VINICIUS = 0.50    # 50% Vinicius; restante JP

# Linhas de URNA por nome do serviço (Natal/Urna)
REGEX_URNA = re.compile(
    r"(caixinh[aã].*nat|caixinh[aã].*urna|urna.*caixinh[aã]|caixinh[aã]\s*natal|natal\s*caixinh[aã])",
    re.IGNORECASE
)

# =========================
# CSS (cards + blocos)
# =========================
st.markdown("""
<style>
.block {background:#0c0f13; border:1px solid #1e242d; border-radius:16px; padding:14px; margin-bottom:14px;}
.kpi {background:#111418; border:1px solid #262b33; border-radius:16px; padding:16px;}
.kpi .title{font-size:.9rem;color:#aab2c5;margin:0 0 6px 0;}
.kpi .value{font-size:1.4rem;font-weight:700;margin:0;}
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

    # Datas e valores
    df["Data"] = pd.to_datetime(df.get("Data"), errors="coerce")
    df = df.dropna(subset=["Data"])
    df["ValorNum"] = pd.to_numeric(df.get("Valor"), errors="coerce").fillna(0)

    # ---- Caixinha Dia/Fundo: vem nas MESMAS LINHAS dos atendimentos
    cand_cx = ["CaixinhaDia", "Caixinha_Fundo", "CaixinhaFundo", "Caixinha", "Gorjeta"]
    existentes = [c for c in cand_cx if c in df.columns]
    for c in existentes:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["CaixinhaDiaTotal"] = df[existentes].sum(axis=1) if existentes else 0

    # Derivadas de tempo
    df["Ano"] = df["Data"].dt.year
    df["Mês"] = df["Data"].dt.month
    df["Ano-Mês"] = df["Data"].dt.to_period("M").astype(str)

    # Flags
    df["EhProduto"] = df["Serviço"].astype(str).apply(lambda s: bool(REGEX_PRODUTO.search(s)))
    df["EhUrna"] = df["Serviço"].astype(str).apply(lambda s: bool(REGEX_URNA.search(s)))
    df["EhServico"] = ~(df["EhProduto"] | df["EhUrna"])  # serviço operacional (exclui produto e URNA)
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
    help="Pagos = tudo que NÃO é 'Fiado'."
)

aplicar_hist = st.sidebar.checkbox("Aplicar no histórico (contagens e tabelas)", value=False)

anos_disponiveis = sorted(df_full["Ano"].dropna().unique(), reverse=True)
ano_escolhido = st.sidebar.selectbox("🗓️ Ano", anos_disponiveis)

meses_disponiveis = sorted(df_full[df_full["Ano"] == ano_escolhido]["Mês"].dropna().unique())
mes_opcoes = [MESES_PT[m] for m in meses_disponiveis]
meses_selecionados = st.sidebar.multiselect("📆 Meses (opcional)", mes_opcoes, default=mes_opcoes)

# =========================
# MÁSCARAS / FILTROS
# =========================
# Pagamento
if pagamento_opcao == "Apenas pagos":
    mask_valores_full = ~is_fiado_full
elif pagamento_opcao == "Apenas fiado":
    mask_valores_full = is_fiado_full
else:
    mask_valores_full = pd.Series(True, index=df_full.index)

# Histórico
mask_historico_full = mask_valores_full if aplicar_hist else pd.Series(True, index=df_full.index)

# Período
if meses_selecionados:
    meses_numeros = [k for k, v in MESES_PT.items() if v in meses_selecionados]
    mask_periodo = (df_full["Ano"] == ano_escolhido) & (df_full["Mês"].isin(meses_numeros))
else:
    mask_periodo = (df_full["Ano"] == ano_escolhido)

df_hist    = df_full[mask_historico_full & mask_periodo].copy()
df_valores = df_full[mask_valores_full & mask_periodo].copy()

# =========================
# AUX
# =========================
def brl(x: float) -> str:
    return f"R$ {x:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

# =========================
# KPIs + CARDS (LADO A LADO)
# =========================
# Receita operacional: exclui URNA para não inflar
receita_total = float(df_valores.loc[~df_valores["EhUrna"], "ValorNum"].sum())
total_atendimentos = len(df_hist)

# Clientes únicos com regra de unicidade a partir de 11/05/2025
antes = df_hist[df_hist["Data"] < DATA_CORTE_UNICIDADE]
depois = df_hist[df_hist["Data"] >= DATA_CORTE_UNICIDADE].drop_duplicates(subset=["Cliente", "Data"])
clientes_unicos = pd.concat([antes, depois])["Cliente"].nunique()

ticket_medio = (receita_total / total_atendimentos) if total_atendimentos else 0.0

# 🎁 Caixinha do período = SOMENTE Caixinha do DIA (linhas dos atendimentos)
caixinha_periodo_total = float(df_valores.loc[~df_valores["EhUrna"], "CaixinhaDiaTotal"].sum())

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(f'<div class="kpi"><p class="title">💰 Receita Total</p><p class="value">{brl(receita_total)}</p></div>', unsafe_allow_html=True)
with c2:
    st.markdown(f'<div class="kpi"><p class="title">📅 Total de Atendimentos</p><p class="value">{total_atendimentos}</p></div>', unsafe_allow_html=True)
with c3:
    st.markdown(f'<div class="kpi"><p class="title">🎯 Ticket Médio</p><p class="value">{brl(ticket_medio)}</p></div>', unsafe_allow_html=True)
with c4:
    st.markdown(f'<div class="kpi"><p class="title">🟢 Clientes Ativos</p><p class="value">{clientes_unicos}</p></div>', unsafe_allow_html=True)
with c5:
    st.markdown(f'<div class="kpi"><p class="title">🎁 Caixinha (Período)</p><p class="value">{brl(caixinha_periodo_total)}</p></div>', unsafe_allow_html=True)

# =========================
# 🎁 BLOCO: Caixinha do Período (somente DIA)
# =========================
col_a, col_b = st.columns([1.1, 1])

with col_a:
    st.markdown('<div class="block"><b>🎁 Caixinha do Período — por Funcionário</b>', unsafe_allow_html=True)
    df_cx_func = (
        df_valores.loc[~df_valores["EhUrna"]]
        .groupby("Funcionário", dropna=False)["CaixinhaDiaTotal"]
        .sum().reset_index().rename(columns={"CaixinhaDiaTotal":"Caixinha"})
        .sort_values("Caixinha", ascending=False)
    )
    if not df_cx_func.empty and df_cx_func["Caixinha"].sum() > 0:
        fig_cx = px.bar(df_cx_func, x="Funcionário", y="Caixinha", text_auto=True)
        fig_cx.update_layout(height=340, yaxis_title="Valor (R$)", showlegend=False, margin=dict(l=10,r=10,t=30,b=10))
        st.plotly_chart(fig_cx, use_container_width=True)
    else:
        st.info("Nenhuma caixinha do dia encontrada no período com os filtros atuais.")
    st.markdown('</div>', unsafe_allow_html=True)

with col_b:
    st.markdown('<div class="block"><b>📅 Caixinha do Dia — Total no Ano</b>', unsafe_allow_html=True)
    df_ano = df_full[df_full["Ano"] == ano_escolhido]
    df_ano = df_ano[mask_valores_full.loc[df_ano.index]] if len(mask_valores_full) == len(df_full) else df_ano
    cx_dia_ano = float(df_ano.loc[~df_ano["EhUrna"], "CaixinhaDiaTotal"].sum())
    st.metric("Total no Ano (Dia)", brl(cx_dia_ano))
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# 🎄 BLOCO: Caixinha NATAL (URNA) — divisão por ano
# =========================
st.markdown('<div class="block"><b>🎄 Caixinha NATAL (URNA) — Ano</b>', unsafe_allow_html=True)
df_urna_ano = df_full[(df_full["Ano"] == ano_escolhido) & (df_full["EhUrna"])].copy()
df_urna_ano = df_urna_ano[mask_valores_full.loc[df_urna_ano.index]] if len(mask_valores_full) == len(df_full) else df_urna_ano
urna_total_ano = float(df_urna_ano["ValorNum"].sum())

if ano_escolhido >= URNA_SPLIT_YEAR:
    quota_vinicius = urna_total_ano * URNA_PCT_VINICIUS
    quota_jpaulo   = urna_total_ano - quota_vinicius
else:
    quota_vinicius = 0.0
    quota_jpaulo   = urna_total_ano

colu1, colu2, colu3 = st.columns(3)
colu1.metric("Total URNA no Ano", brl(urna_total_ano))
colu2.metric("Quota JPaulo",       brl(quota_jpaulo))
colu3.metric("Quota Vinicius",     brl(quota_vinicius))

# (opcional) mostrar quem lançou as linhas de URNA
if not df_urna_ano.empty:
    df_urna_lanc = (df_urna_ano.groupby("Funcionário", dropna=False)["ValorNum"]
                    .sum().reset_index().rename(columns={"ValorNum":"Valor Lançado"}))
    df_urna_lanc["Valor Lançado"] = df_urna_lanc["Valor Lançado"].astype(float)
    st.dataframe(df_urna_lanc, use_container_width=True, hide_index=True)
else:
    st.info("Nenhuma linha de URNA registrada para o ano selecionado.")
st.markdown('</div>', unsafe_allow_html=True)

# =========================
# TENDÊNCIA MENSAL (RECEITA) — APENAS DO ANO SELECIONADO
# =========================
st.markdown('<div class="block"><b>📈 Tendência Mensal de Receita (Ano Selecionado)</b>', unsafe_allow_html=True)
df_anual_val = df_full[(df_full["Ano"] == ano_escolhido)]
df_anual_val = df_anual_val[mask_valores_full.loc[df_anual_val.index]] if len(mask_valores_full) == len(df_full) else df_anual_val
# receita operacional (sem URNA)
df_mensal = (
    df_anual_val.loc[~df_anual_val["EhUrna"]]
    .groupby("Mês")["ValorNum"].sum().reset_index().sort_values("Mês")
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
# PRODUTOS (QTD e VALOR)
# =========================
col_p1, col_p2 = st.columns([1.2, 1])

with col_p1:
    st.markdown('<div class="block"><b>🛍️ Produtos Vendidos (quantidade)</b>', unsafe_allow_html=True)
    df_prod = df_valores.loc[~df_valores["EhUrna"] & df_valores["EhProduto"]].copy()
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
    st.markdown('<div class="block"><b>🏆 Top Produtos por Valor</b>', unsafe_allow_html=True)
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
# TOP SERVIÇOS (exclui produto e URNA)
# =========================
st.markdown('<div class="block"><b>✂️ Top Serviços por Valor</b>', unsafe_allow_html=True)
df_serv = df_valores.loc[~df_valores["EhUrna"] & ~df_valores["EhProduto"]].copy()
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
# TOP 10 CLIENTES (frequência + valor)
# =========================
st.markdown('<div class="block"><b>🥇 Top 10 Clientes</b>', unsafe_allow_html=True)
cnt = df_hist.groupby("Cliente")["Serviço"].count().rename("Qtd_Serviços")
val = df_valores.loc[~df_valores["EhUrna"]].groupby("Cliente")["ValorNum"].sum().rename("Valor")
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
st.caption("Criado por JPaulo ✨ | Cards lado a lado • Caixinha do Dia separada • URNA com divisão 50/50 a partir de 2025")

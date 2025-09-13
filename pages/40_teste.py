# pages/01_estoque_gel_pomada.py
# -*- coding: utf-8 -*-
import unicodedata as _ud
from datetime import datetime, date

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

st.set_page_config(page_title="Estoque — Gel & Pomada", page_icon="🧴", layout="wide")
st.title("🧴 Estoque — Gel & Pomada (simples)")

# =============================================================================
# CONFIG
# =============================================================================
# 👉 Troque pelo ID da SUA planilha (o ID é o que fica entre /d/ e /edit)
SHEET_ID = st.secrets.get("PLANILHA_SHEET_ID", "COLOQUE_O_ID_AQUI")
ABA_NOME = "Estoque_Simples"  # será criada se não existir

PRODUTOS = ["Gel", "Pomada"]   # fixos para esta página
UNIDADES = {"Gel": "un", "Pomada": "un"}  # deixe "un"; mude para "L" se quiser litros
COLS = ["Data", "Produto", "TipoMov", "Qtd", "Unidade", "Obs", "CriadoEm"]

# =============================================================================
# AUTENTICAÇÃO / SHEETS
# =============================================================================
def _normalize_private_key(key: str) -> str:
    if not isinstance(key, str):
        return key
    key = key.replace("\\n", "\n")
    # remove controles invisíveis (mantém \n \r \t)
    key = "".join(ch for ch in key if _ud.category(ch)[0] != "C" or ch in ("\n","\r","\t"))
    return key

def _open_sheet():
    sa = st.secrets["GCP_SERVICE_ACCOUNT"]
    sa = {**sa, "private_key": _normalize_private_key(sa["private_key"])}
    creds = Credentials.from_service_account_info(
        sa,
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

@st.cache_data(show_spinner=False, ttl=60)
def carregar_df():
    sh = _open_sheet()
    try:
        ws = sh.worksheet(ABA_NOME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=ABA_NOME, rows=2000, cols=10)
        df_vazio = pd.DataFrame(columns=COLS)
        set_with_dataframe(ws, df_vazio, include_index=False, include_column_header=True)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    if df.empty:
        df = pd.DataFrame(columns=COLS)
    # normalizações
    df = df.dropna(how="all")
    for c in COLS:
        if c not in df.columns:
            df[c] = None
    # tipos
    if "Qtd" in df.columns:
        df["Qtd"] = pd.to_numeric(df["Qtd"], errors="coerce").fillna(0.0)
    return df[COLS].copy()

def salvar_linha(linha: dict):
    sh = _open_sheet()
    ws = sh.worksheet(ABA_NOME)
    df = carregar_df()
    df = pd.concat([df, pd.DataFrame([linha])], ignore_index=True)
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)
    st.cache_data.clear()

def saldo_atual(df: pd.DataFrame) -> pd.DataFrame:
    # Entrada = +Qtd | Saída = -Qtd | Ajuste = Qtd (pode ser + ou -)
    df_calc = df.copy()
    def efeito(row):
        if row["TipoMov"] == "Entrada":
            return row["Qtd"]
        if row["TipoMov"] == "Saída":
            return -abs(row["Qtd"])
        # Ajuste aplica como veio (ex.: -2 para corrigir pra baixo; +3 pra cima)
        return row["Qtd"]
    if not df_calc.empty:
        df_calc["Efeito"] = df_calc.apply(efeito, axis=1)
        sld = df_calc.groupby(["Produto", "Unidade"], as_index=False)["Efeito"].sum()
        sld = sld.rename(columns={"Efeito": "Saldo"})
    else:
        sld = pd.DataFrame(columns=["Produto", "Unidade", "Saldo"])
    # garantir todos os produtos presentes
    for p in PRODUTOS:
        if not (sld["Produto"] == p).any() if not sld.empty else True:
            sld = pd.concat([sld, pd.DataFrame([{"Produto": p, "Unidade": UNIDADES[p], "Saldo": 0}])], ignore_index=True)
    sld["Saldo"] = sld["Saldo"].fillna(0).round(2)
    return sld.sort_values("Produto")

def registrar_mov(tipo: str, produto: str, qtd: float, obs: str):
    if qtd <= 0:
        st.error("Quantidade deve ser maior que zero.")
        return
    # prevenção de saldo negativo em SAÍDA
    df = carregar_df()
    sld = saldo_atual(df)
    unid = UNIDADES.get(produto, "un")
    saldo_prod = float(sld.loc[sld["Produto"] == produto, "Saldo"].iloc[0]) if not sld.empty else 0.0
    if tipo == "Saída" and qtd > saldo_prod:
        st.error(f"Saldo insuficiente de **{produto}**. Saldo atual: {saldo_prod:g} {unid}.")
        return

    linha = {
        "Data": date.today().strftime("%d/%m/%Y"),
        "Produto": produto,
        "TipoMov": tipo,       # Entrada | Saída | Ajuste
        "Qtd": float(qtd),
        "Unidade": unid,
        "Obs": obs.strip() if obs else "",
        "CriadoEm": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    salvar_linha(linha)
    st.success(f"{tipo} registrada para **{produto}**: {qtd:g} {unid}")

# =============================================================================
# UI
# =============================================================================
tab_reg, tab_saldo, tab_hist = st.tabs(["➕ Registrar", "📊 Saldo atual", "📜 Histórico"])

with tab_reg:
    st.subheader("Registrar movimento")
    c1, c2, c3 = st.columns([1,1,2])
    with c1:
        produto = st.selectbox("Produto", PRODUTOS, index=0)
    with c2:
        tipo = st.selectbox("Tipo de movimento", ["Entrada", "Saída", "Ajuste"], index=0)
    with c3:
        qtd = st.number_input("Quantidade", min_value=0.0, step=1.0, value=1.0, format="%.2f")
    obs = st.text_input("Observação (opcional)", placeholder="lote, motivo do ajuste, etc.")

    # dica de ajuste
    if tipo == "Ajuste":
        st.info("💡 Ajuste aceita positivo (aumenta estoque) ou negativo (ex.: -2 para corrigir).")

    colb1, colb2 = st.columns([1,3])
    with colb1:
        if st.button("Salvar movimento", type="primary"):
            registrar_mov(tipo, produto, qtd, obs)

with tab_saldo:
    st.subheader("Saldo por produto")
    df = carregar_df()
    sld = saldo_atual(df)
    st.dataframe(sld, hide_index=True, use_container_width=True)
    # Cards simples
    c1, c2 = st.columns(2)
    for i, p in enumerate(PRODUTOS):
        col = c1 if i % 2 == 0 else c2
        saldo_p = float(sld.loc[sld["Produto"] == p, "Saldo"].iloc[0])
        unid = UNIDADES[p]
        with col:
            st.metric(p, f"{saldo_p:g} {unid}")

with tab_hist:
    st.subheader("Histórico de movimentos")
    df = carregar_df()
    # filtros rápidos
    colf1, colf2 = st.columns([1,1])
    with colf1:
        prod_f = st.multiselect("Filtrar produto", PRODUTOS, default=PRODUTOS)
    with colf2:
        tipo_f = st.multiselect("Filtrar tipo", ["Entrada","Saída","Ajuste"], default=["Entrada","Saída","Ajuste"])

    if not df.empty:
        mask = df["Produto"].isin(prod_f) & df["TipoMov"].isin(tipo_f)
        dfv = df.loc[mask].copy()
        # ordena: mais recente em cima
        def _dtparse(s):
            try:
                return datetime.strptime(str(s), "%d/%m/%Y")
            except:
                return pd.NaT
        dfv["__ord"] = dfv["Data"].apply(_dtparse)
        dfv = dfv.sort_values(["__ord","CriadoEm"], ascending=False).drop(columns=["__ord"])
        st.dataframe(dfv, hide_index=True, use_container_width=True)
    else:
        st.info("Sem registros ainda. Lance uma entrada para começar.")

st.caption("Dica: use **Entrada** para compras/estoque inicial, **Saída** para venda/uso, e **Ajuste** para correções pontuais.")


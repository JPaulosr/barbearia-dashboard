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
st.title("🧴 Estoque — Gel, Pomada & Pomada em pó")

# =============================================================================
# CONFIG
# =============================================================================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_ESTOQUE = "Estoque_Simples"   # será criada se não existir
ABA_DESPESAS = "Despesas"         # onde lançaremos o gasto da Entrada (criada se não existir)

# Produtos controlados
PRODUTOS = ["Gel", "Pomada", "Pomada em pó"]
UNIDADES = {"Gel": "un", "Pomada": "un", "Pomada em pó": "un"}

# Colunas das movimentações de estoque
COLS_ESTOQUE = ["Data", "Produto", "TipoMov", "Qtd", "Unidade", "Obs", "CriadoEm"]

# Colunas para a aba Despesas
COLS_DESPESAS = [
    "Data", "Categoria", "Descrição", "Valor", "Conta", "Fornecedor", "NF/Ref", "CriadoEm"
]

# Categorias/Contas padrão
CATEGORIA_ESTOQUE = "Compra de estoque"
CONTAS_PADRAO = ["Carteira", "Pix", "Transferência", "Nubank CNPJ", "Nubank", "Pagseguro", "Mercado Pago", "Outro"]

# =============================================================================
# AUTENTICAÇÃO / SHEETS
# =============================================================================
def _normalize_private_key(key: str) -> str:
    if not isinstance(key, str):
        return key
    key = key.replace("\\n", "\n")
    key = "".join(ch for ch in key if _ud.category(ch)[0] != "C" or ch in ("\n","\r","\t"))
    return key

def _open_sheet():
    sa = st.secrets["GCP_SERVICE_ACCOUNT"]
    sa = {**sa, "private_key": _normalize_private_key(sa["private_key"])}
    creds = Credentials.from_service_account_info(
        sa,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

# ---------- helpers genéricos ----------
def _ensure_worksheet(sh, title: str, cols: list[str]):
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=2000, cols=max(10, len(cols)))
        set_with_dataframe(ws, pd.DataFrame(columns=cols), include_index=False, include_column_header=True)
    return ws

# =============================================================================
# ESTOQUE — carregar/salvar
# =============================================================================
@st.cache_data(show_spinner=False, ttl=60)
def carregar_df_estoque() -> pd.DataFrame:
    sh = _open_sheet()
    ws = _ensure_worksheet(sh, ABA_ESTOQUE, COLS_ESTOQUE)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    if df.empty:
        df = pd.DataFrame(columns=COLS_ESTOQUE)
    df = df.dropna(how="all")
    for c in COLS_ESTOQUE:
        if c not in df.columns:
            df[c] = None
    if "Qtd" in df.columns:
        df["Qtd"] = pd.to_numeric(df["Qtd"], errors="coerce").fillna(0.0)
    return df[COLS_ESTOQUE].copy()

def salvar_mov_estoque(linha: dict):
    sh = _open_sheet()
    ws = _ensure_worksheet(sh, ABA_ESTOQUE, COLS_ESTOQUE)
    df = carregar_df_estoque()
    df = pd.concat([df, pd.DataFrame([linha])], ignore_index=True)
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)
    st.cache_data.clear()

def saldo_atual(df: pd.DataFrame) -> pd.DataFrame:
    df_calc = df.copy()
    def efeito(row):
        if row["TipoMov"] == "Entrada":
            return row["Qtd"]
        if row["TipoMov"] == "Saída":
            return -abs(row["Qtd"])
        return row["Qtd"]  # Ajuste pode ser +/-
    if not df_calc.empty:
        df_calc["Efeito"] = df_calc.apply(efeito, axis=1)
        sld = df_calc.groupby(["Produto", "Unidade"], as_index=False)["Efeito"].sum()
        sld = sld.rename(columns={"Efeito": "Saldo"})
    else:
        sld = pd.DataFrame(columns=["Produto", "Unidade", "Saldo"])
    # garantir todos os produtos
    for p in PRODUTOS:
        if sld.empty or not (sld["Produto"] == p).any():
            sld = pd.concat([sld, pd.DataFrame([{"Produto": p, "Unidade": UNIDADES[p], "Saldo": 0}])], ignore_index=True)
    sld["Saldo"] = sld["Saldo"].fillna(0).round(2)
    return sld.sort_values("Produto")

# =============================================================================
# DESPESAS — salvar linha de compra (Entrada)
# =============================================================================
def salvar_despesa(data_str: str, descricao: str, valor_total: float, conta: str, fornecedor: str, nf: str):
    if valor_total is None or float(valor_total) <= 0:
        return
    sh = _open_sheet()
    ws = _ensure_worksheet(sh, ABA_DESPESAS, COLS_DESPESAS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    if df.empty:
        df = pd.DataFrame(columns=COLS_DESPESAS)
    for c in COLS_DESPESAS:
        if c not in df.columns:
            df[c] = ""
    nova = {
        "Data": data_str,
        "Categoria": CATEGORIA_ESTOQUE,
        "Descrição": descricao,
        "Valor": float(valor_total),
        "Conta": (conta or "").strip(),
        "Fornecedor": (fornecedor or "").strip(),
        "NF/Ref": (nf or "").strip(),
        "CriadoEm": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    df = pd.concat([df, pd.DataFrame([nova])], ignore_index=True)
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================================================================
# OPERAÇÃO
# =============================================================================
def registrar_mov(tipo: str, produto: str, qtd: float, obs: str,
                  custo_unit: float | None = None, conta: str | None = None,
                  fornecedor: str | None = None, nf: str | None = None,
                  lancar_despesa: bool = True):
    if qtd <= 0:
        st.error("Quantidade deve ser maior que zero.")
        return

    df = carregar_df_estoque()
    sld = saldo_atual(df)
    unid = UNIDADES.get(produto, "un")
    saldo_prod = float(sld.loc[sld["Produto"] == produto, "Saldo"].iloc[0]) if not sld.empty else 0.0
    if tipo == "Saída" and qtd > saldo_prod:
        st.error(f"Saldo insuficiente de **{produto}**. Saldo atual: {saldo_prod:g} {unid}.")
        return

    # 1) grava a movimentação de estoque
    linha = {
        "Data": date.today().strftime("%d/%m/%Y"),
        "Produto": produto,
        "TipoMov": tipo,
        "Qtd": float(qtd),
        "Unidade": unid,
        "Obs": obs.strip() if obs else "",
        "CriadoEm": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    salvar_mov_estoque(linha)

    # 2) se for ENTRADA, grava também em Despesas
    if tipo == "Entrada" and lancar_despesa:
        try:
            custo_unit_f = float(custo_unit or 0.0)
            total = round(custo_unit_f * float(qtd), 2)
            desc = f"Compra de {int(qtd) if qtd.is_integer() else qtd:g} {unid} de {produto}"
            if obs and obs.strip():
                desc += f" — {obs.strip()}"
            salvar_despesa(
                data_str=linha["Data"],
                descricao=desc,
                valor_total=total,
                conta=(conta or ""),
                fornecedor=(fornecedor or ""),
                nf=(nf or "")
            )
        except Exception as e:
            st.warning(f"Movimentação registrada, mas não consegui lançar a despesa ({e}).")

    st.success(f"{tipo} registrada para **{produto}**: {qtd:g} {unid}" + (" + despesa lançada." if tipo == "Entrada" and lancar_despesa else ""))

# =============================================================================
# UI
# =============================================================================
tab_reg, tab_saldo, tab_hist, tab_diag = st.tabs(
    ["➕ Registrar", "📊 Saldo atual", "📜 Histórico", "🔎 Diagnóstico"]
)

with tab_reg:
    st.subheader("Registrar movimento")
    c1, c2, c3 = st.columns([1,1,1.2])
    with c1:
        produto = st.selectbox("Produto", PRODUTOS, index=0)
    with c2:
        tipo = st.selectbox("Tipo de movimento", ["Entrada", "Saída", "Ajuste"], index=0)
    with c3:
        qtd = st.number_input("Quantidade", min_value=0.0, step=1.0, value=1.0, format="%.2f")
    obs = st.text_input("Observação (opcional)", placeholder="lote, motivo do ajuste, etc.")

    # Campos extras quando é Entrada → custo + dados de despesa
    lancar_desp = True
    custo_unit = None
    conta = None
    fornecedor = None
    nf = None

    if tipo == "Entrada":
        st.markdown("#### 💸 Dados da compra (será lançada em **Despesas**)")
        c4, c5, c6 = st.columns([1, 1, 1])
        with c4:
            custo_unit = st.number_input("Custo unitário", min_value=0.0, step=1.0, value=0.0, format="%.2f",
                                         help="Valor pago por unidade (ex.: por frasco)")
        with c5:
            conta = st.selectbox("Conta/Meio de pagamento", CONTAS_PADRAO, index=0)
        with c6:
            fornecedor = st.text_input("Fornecedor (opcional)", placeholder="ex.: Atacado XYZ")
        nf = st.text_input("NF/Ref (opcional)", placeholder="nº da nota, pedido, etc.")
        lancar_desp = st.checkbox("Lançar esta Entrada como despesa?", value=True)

        if custo_unit and qtd:
            total_prev = float(custo_unit) * float(qtd)
            st.caption(f"💡 Total previsto da despesa: **R$ {total_prev:,.2f}**".replace(",", "X").replace(".", ",").replace("X", "."))

    if tipo == "Ajuste":
        st.info("💡 Ajuste aceita positivo (aumenta estoque) ou negativo (ex.: -2).")
    if st.button("Salvar movimento", type="primary"):
        registrar_mov(tipo, produto, qtd, obs, custo_unit, conta, fornecedor, nf, lancar_desp)

with tab_saldo:
    st.subheader("Saldo por produto")
    df_e = carregar_df_estoque()
    sld = saldo_atual(df_e)
    st.dataframe(sld, hide_index=True, use_container_width=True)
    c1, c2, c3 = st.columns(3)
    for i, p in enumerate(PRODUTOS):
        col = [c1, c2, c3][i % 3]
        saldo_p = float(sld.loc[sld["Produto"] == p, "Saldo"].iloc[0])
        unid = UNIDADES[p]
        with col:
            st.metric(p, f"{saldo_p:g} {unid}")

with tab_hist:
    st.subheader("Histórico de movimentos")
    df_e = carregar_df_estoque()
    colf1, colf2 = st.columns([1,1])
    with colf1:
        prod_f = st.multiselect("Filtrar produto", PRODUTOS, default=PRODUTOS)
    with colf2:
        tipo_f = st.multiselect("Filtrar tipo", ["Entrada","Saída","Ajuste"], default=["Entrada","Saída","Ajuste"])
    if not df_e.empty:
        mask = df_e["Produto"].isin(prod_f) & df_e["TipoMov"].isin(tipo_f)
        dfv = df_e.loc[mask].copy()
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

with tab_diag:
    st.subheader("Diagnóstico de conexão")
    st.write("SHEET_ID alvo:", SHEET_ID)
    try:
        sh = _open_sheet()
        st.success(f"Conectado em: {sh.title}")
        st.write("Abas usadas:")
        st.write(f"• Estoque → {ABA_ESTOQUE}")
        st.write(f"• Despesas → {ABA_DESPESAS}")
    except Exception as e:
        st.error(f"Falha ao abrir planilha: {e}")

st.caption("Use **Entrada** para compras/estoque inicial (gera despesa), **Saída** para venda/uso, e **Ajuste** para correções.")

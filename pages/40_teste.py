# pages/01_estoque_gel_pomada.py
# -*- coding: utf-8 -*-
import unicodedata as _ud
from datetime import datetime, date

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

st.set_page_config(page_title="Estoque — Gel, Pomada & Pó", page_icon="🧴", layout="wide")
st.title("🧴 Estoque — Gel, Pomada & Pomada em pó")

# =============================================================================
# CONFIG
# =============================================================================
# Usa a MESMA planilha do seu app
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"

# Abas/nomes
ABA_ESTOQUE  = "Estoque_Simples"
ABA_DESPESAS = "Despesas"  # já existe na sua planilha

# Produtos controlados
PRODUTOS = ["Gel", "Pomada", "Pomada em pó"]
UNIDADES = {"Gel": "un", "Pomada": "un", "Pomada em pó": "un"}

# Colunas das movimentações de estoque
COLS_ESTOQUE = ["Data", "Produto", "TipoMov", "Qtd", "Unidade", "Obs", "CriadoEm"]

# Layout base esperado na aba Despesas (respeitaremos o cabeçalho existente)
COLS_DESPESAS_BASE = [
    "Data","Prestador","Descrição","Valor","Me Pag","RefID",
    "Categoria","Fornecedor","NF/Ref","CriadoEm"
]
CATEGORIA_ESTOQUE = "Compra de estoque"
PRESTADORES = ["JPaulo","Vinicius"]  # ajuste se quiser
CONTAS_PADRAO = ["Carteira","Pix","Transferência","Nubank CNPJ","Nubank","Pagseguro","Mercado Pago","Outro"]

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
    """Cria a worksheet se não existir (com cabeçalho fornecido)."""
    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=3000, cols=max(12, len(cols)))
        set_with_dataframe(ws, pd.DataFrame(columns=cols), include_index=False, include_column_header=True)
    return ws

def _headers(ws):
    try:
        return [h.strip() for h in ws.row_values(1)]
    except Exception:
        return []

def _fmt_brl(v: float) -> str:
    try: v = float(v)
    except: v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

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
        if row["TipoMov"] == "Entrada": return row["Qtd"]
        if row["TipoMov"] == "Saída":   return -abs(row["Qtd"])
        return row["Qtd"]  # Ajuste pode ser +/-
    if not df_calc.empty:
        df_calc["Efeito"] = df_calc.apply(efeito, axis=1)
        sld = df_calc.groupby(["Produto","Unidade"], as_index=False)["Efeito"].sum()
        sld = sld.rename(columns={"Efeito":"Saldo"})
    else:
        sld = pd.DataFrame(columns=["Produto","Unidade","Saldo"])
    for p in PRODUTOS:
        if sld.empty or not (sld["Produto"] == p).any():
            sld = pd.concat([sld, pd.DataFrame([{"Produto":p,"Unidade":UNIDADES[p],"Saldo":0}])], ignore_index=True)
    sld["Saldo"] = sld["Saldo"].fillna(0).round(2)
    return sld.sort_values("Produto")

# =============================================================================
# DESPESAS — salva respeitando SOMENTE colunas existentes (usa apenas “Me Pag”)
# =============================================================================
def salvar_despesa(data_str: str, prestador: str, descricao: str, valor_total: float,
                   mepag: str, fornecedor: str, nf: str):
    """Lança a compra na aba 'Despesas' usando só 'Me Pag' (não cria/usa 'Conta')."""
    if not valor_total or float(valor_total) <= 0:
        return
    sh = _open_sheet()
    # usa a worksheet existente; se não houver, cria com layout base (sem 'Conta')
    try:
        ws = sh.worksheet(ABA_DESPESAS)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=ABA_DESPESAS, rows=3000, cols=20)
        set_with_dataframe(ws, pd.DataFrame(columns=COLS_DESPESAS_BASE),
                           include_index=False, include_column_header=True)

    headers_ref = _headers(ws) or COLS_DESPESAS_BASE

    df = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")
    if df.empty:
        df = pd.DataFrame(columns=headers_ref)

    # helper: só preenche se a coluna existir (não criamos novas)
    def set_if_present(d: dict, col: str, val):
        if col in headers_ref:
            d[col] = val

    nova = {h: "" for h in headers_ref}
    set_if_present(nova, "Data", data_str)
    set_if_present(nova, "Prestador", (prestador or "").strip())
    set_if_present(nova, "Descrição", descricao)
    set_if_present(nova, "Valor", float(valor_total))
    set_if_present(nova, "Me Pag", (mepag or "").strip())     # <- só essa coluna de pagamento
    set_if_present(nova, "RefID", "")
    set_if_present(nova, "Categoria", CATEGORIA_ESTOQUE)
    set_if_present(nova, "Fornecedor", (fornecedor or "").strip())
    set_if_present(nova, "NF/Ref", (nf or "").strip())
    set_if_present(nova, "CriadoEm", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    df = pd.concat([df, pd.DataFrame([nova])], ignore_index=True)
    df = df[headers_ref]  # mantém a ordem exata da planilha existente
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================================================================
# OPERAÇÃO
# =============================================================================
def registrar_mov(tipo: str, produto: str, qtd: float, obs: str,
                  custo_unit: float | None = None, mepag: str | None = None,
                  fornecedor: str | None = None, nf: str | None = None,
                  prestador: str | None = None, lancar_despesa: bool = True):
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
        "Obs": (obs or "").strip(),
        "CriadoEm": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    salvar_mov_estoque(linha)

    # 2) se for ENTRADA, lança despesa usando só "Me Pag"
    if tipo == "Entrada" and lancar_despesa:
        try:
            custo_unit_f = float(custo_unit or 0.0)
            total = round(custo_unit_f * float(qtd), 2)
            desc = f"Compra de {int(qtd) if float(qtd).is_integer() else float(qtd):g} {unid} de {produto}"
            if obs and obs.strip():
                desc += f" — {obs.strip()}"
            salvar_despesa(
                data_str=linha["Data"],
                prestador=(prestador or "JPaulo"),
                descricao=desc,
                valor_total=total,
                mepag=(mepag or ""),
                fornecedor=(fornecedor or ""),
                nf=(nf or "")
            )
        except Exception as e:
            st.warning(f"Movimentação registrada, mas não consegui lançar a despesa ({e}).")

    msg = f"{tipo} registrada para **{produto}**: {qtd:g} {unid}"
    if tipo == "Entrada" and lancar_despesa and float(custo_unit or 0) > 0:
        msg += f" • Despesa {_fmt_brl((float(custo_unit or 0)*float(qtd)))} lançada."
    st.success(msg)

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
        tipo = st.selectbox("Tipo de movimento", ["Entrada","Saída","Ajuste"], index=0)
    with c3:
        qtd = st.number_input("Quantidade", min_value=0.0, step=1.0, value=1.0, format="%.2f")
    obs = st.text_input("Observação (opcional)", placeholder="lote, motivo do ajuste, etc.")

    # Campos de compra -> só quando ENTRADA
    lancar_desp = True
    custo_unit = None
    mepag = None
    fornecedor = None
    nf = None
    prestador = None

    if tipo == "Entrada":
        st.markdown("#### 💸 Dados da compra (será lançada em **Despesas**)")
        c4, c5, c6 = st.columns([1,1,1])
        with c4:
            custo_unit = st.number_input("Custo unitário", min_value=0.0, step=1.0, value=0.0, format="%.2f",
                                         help="Valor pago por unidade (ex.: por frasco)")
        with c5:
            mepag = st.selectbox("Meio de pagamento (preenche **Me Pag**)", CONTAS_PADRAO, index=0)
        with c6:
            prestador = st.selectbox("Prestador (quem comprou)", PRESTADORES, index=0)
        colx1, colx2 = st.columns([1,1])
        with colx1:
            fornecedor = st.text_input("Fornecedor (opcional)", placeholder="ex.: Atacado XYZ")
        with colx2:
            nf = st.text_input("NF/Ref (opcional)", placeholder="nº da nota, pedido, etc.")
        lancar_desp = st.checkbox("Lançar esta Entrada como despesa?", value=True)

        if custo_unit and qtd:
            total_prev = float(custo_unit) * float(qtd)
            st.caption(f"💡 Total previsto da despesa: **{_fmt_brl(total_prev)}**")

    if tipo == "Ajuste":
        st.info("💡 Ajuste aceita positivo (aumenta estoque) ou negativo (ex.: -2).")

    if st.button("Salvar movimento", type="primary"):
        registrar_mov(tipo, produto, qtd, obs, custo_unit, mepag, fornecedor, nf, prestador, lancar_desp)

with tab_saldo:
    st.subheader("Saldo por produto")
    df_e = carregar_df_estoque()
    sld = saldo_atual(df_e)
    st.dataframe(sld, hide_index=True, use_container_width=True)
    cols = st.columns(3)
    for i, p in enumerate(PRODUTOS):
        saldo_p = float(sld.loc[sld["Produto"] == p, "Saldo"].iloc[0])
        unid = UNIDADES[p]
        with cols[i % 3]:
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
        def _dtparse(s):
            try: return datetime.strptime(str(s), "%d/%m/%Y")
            except: return pd.NaT
        mask = df_e["Produto"].isin(prod_f) & df_e["TipoMov"].isin(tipo_f)
        dfv = df_e.loc[mask].copy()
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
        st.write(f"• Despesas → {ABA_DESPESAS} (usa só a coluna 'Me Pag')")
    except Exception as e:
        st.error(f"Falha ao abrir planilha: {e}")

st.caption("Use **Entrada** para compras/estoque (gera despesa), **Saída** para venda/uso, e **Ajuste** para correções.")

# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão (3 blocos): Não fiado | Fiados liberados | Fiado a receber
# - IDs únicos (key=)
# - Arredondamento inteligente (tolerância abaixo/acima)
# - Override de % comissão por linha (com patch para não quebrar se estiver desligado)
# - Leitura de VALOR robusta (R$, vírgula, ponto, cabeçalho variável, DF/Series/lista)
# - Filtros de texto insensíveis a acento (Funcionário, etc.)

import streamlit as st
import pandas as pd
import gspread, re, hashlib, unicodedata
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
from typing import Union

# =============================
# CONFIG
# =============================
st.set_page_config(layout="wide")
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"
TZ = "America/Sao_Paulo"

COLS_OFICIAIS = [
    "Data","Serviço","Valor","Conta","Cliente","Combo",
    "Funcionário","Fase","Tipo","Período",
    "StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento"
]
COLS_DESPESAS_FIX = ["Data","Prestador","Descrição","Valor","Me Pag:"]

PERCENTUAL_PADRAO = 50.0

VALOR_TABELA = {
    "Corte": 25.0, "Barba": 15.0, "Sobrancelha": 7.0,
    "Luzes": 45.0, "Tintura": 20.0, "Alisamento": 40.0,
    "Gel": 10.0, "Pomada": 15.0,
}

# =============================
# CONEXÃO SHEETS
# =============================
@st.cache_resource
def _conn():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    cred = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(cred).open_by_key(SHEET_ID)

def _ws(title:str):
    sh = _conn()
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=50)

def _read_df(title:str)->pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how="all").fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df

def _write_df(title:str, df:pd.DataFrame):
    ws = _ws(title); ws.clear()
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================
# HELPERS GERAIS
# =============================
def br_now(): 
    return datetime.now(pytz.timezone(TZ))

def parse_br_date(x: Union[str, datetime]):
    if isinstance(x, datetime):
        return x
    s = (str(x) if x is not None else "").strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d","%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            pass
    # serial do Sheets
    try:
        num = float(s)
        base = datetime(1899,12,30)
        return base + timedelta(days=num)
    except Exception:
        return None

def to_br_date(dt:datetime): 
    return dt.strftime("%d/%m/%Y")

def competencia_from_data_str(s:str):
    dt = parse_br_date(s);  
    return dt.strftime("%m/%Y") if dt else ""

def janela_terca_a_segunda(terca_dt:datetime):
    ini = terca_dt - timedelta(days=7)
    fim = ini + timedelta(days=6)
    ini = datetime.combine(ini.date(), datetime.min.time())
    fim = datetime.combine(fim.date(), datetime.max.time())
    return ini, fim

def make_refid(row:pd.Series)->str:
    key = "|".join([str(row.get(k,"")).strip() for k in ["Cliente","Data","Serviço","Valor","Funcionário","Combo"]])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

def garantir_colunas(df:pd.DataFrame, cols:list[str])->pd.DataFrame:
    for c in cols:
        if c not in df.columns: 
            df[c] = ""
    return df

def is_cartao(conta:str)->bool:
    c = (conta or "").strip().lower()
    return bool(re.search(r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos)", c))

def fold_text(s: str) -> str:
    """lower + remove acentos/espaços extras"""
    s = unicodedata.normalize("NFKC", str(s)).replace("\xa0"," ")
    s = unicodedata.normalize("NFKD", s).encode("ASCII","ignore").decode("ASCII")
    return s.strip().lower()

# ===== VALOR =====
VAL_COL_CANDS = ["Valor","Valor (R$)","Valor Liquido","Valor Líquido","Valor Recebido","Valor_liquido","Valor_total"]

def find_val_col(df: pd.DataFrame) -> str | None:
    # procura por chave insensível a acento e espaços
    mapper = {}
    for c in df.columns:
        k = fold_text(c).replace(" ", "").replace("_","")
        mapper[k] = c
    for raw in VAL_COL_CANDS:
        key = fold_text(raw).replace(" ", "").replace("_","")
        if key in mapper:
            return mapper[key]
    # fallback genérico: contém "valor"
    for k, c in mapper.items():
        if "valor" in k:
            return c
    return None

def _series_from_any(s, length_hint:int=0) -> pd.Series:
    if isinstance(s, pd.DataFrame):
        if s.shape[1] == 0:
            return pd.Series([None]*length_hint)
        s = s.iloc[:, 0]
    if isinstance(s, pd.Series):
        return s
    try:
        return pd.Series(s)
    except Exception:
        return pd.Series([s]*length_hint)

def _money_to_float_series(s) -> pd.Series:
    """Converte Series/DF/lista/escalar em float preservando decimais (ponto/vírgula)."""
    s = _series_from_any(s)
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    if pd.api.types.is_numeric_dtype(s):
        return s.astype(float).fillna(0.0)

    s = s.astype(str).str.strip()
    s = s.str.replace(r"[^\d,.\-+]", "", regex=True)

    def conv(txt: str) -> float:
        if not txt:
            return 0.0
        if "," in txt and "." in txt:
            # separador decimal = o símbolo mais à direita
            if txt.rfind(",") > txt.rfind("."):
                txt = txt.replace(".", "").replace(",", ".")  # 1.234,56 -> 1234.56
            else:
                txt = txt.replace(",", "")                    # 1,234.56 -> 1234.56
        elif "," in txt:
            txt = txt.replace(",", ".")                       # 25,5 -> 25.5
        # else: "25.50" permanece
        try:
            return float(txt)
        except:
            return 0.0

    return s.apply(conv).astype(float).fillna(0.0)

# =============================
# UI
# =============================
st.title("💈 Comissão — Vinícius")

base = _read_df(ABA_DADOS)
base = garantir_colunas(base, COLS_OFICIAIS).copy()  # não mexe no nome das colunas!

# ========== Inputs ==========
colA, colB, colC = st.columns([1,1,1])
with colA:
    hoje = br_now()
    delta = (1 - hoje.weekday()) % 7  # próxima terça (ou hoje se já for)
    terca_base = hoje + timedelta(days=delta)
    dtwidget = st.date_input("🗓️ Terça do pagamento", value=terca_base.date(), key="dt_terca_pagto")
    terca_pagto = datetime.combine(dtwidget, datetime.min.time())
with colB:
    perc_padrao = st.number_input("Percentual padrão (%)", value=PERCENTUAL_PADRAO, step=1.0, key="pct_padrao")
with colC:
    descricao_padrao = st.text_input("Descrição (DESPESAS)", value="Comissão Vinícius", key="desc_desp")

colD, colE = st.columns([1,1])
with colD:
    usar_tabela_quando_valor_zero = st.checkbox("Usar TABELA quando Valor 0/vazio", value=True, key="chk_tab_val0")
    usar_tabela_cartao = st.checkbox("Usar TABELA quando cartão (só se Valor=0)", value=True, key="chk_tab_cartao")
    ajustar_quebrados_para_tabela = st.checkbox("Ajustar 'quebrados' para TABELA (se perto)", value=True, key="chk_quebrados")
with colE:
    tol_baixo = st.number_input("Tolerância abaixo da TABELA (%) (ex.: 23,9 → 25)", value=25.0, min_value=0.0, max_value=100.0, step=1.0, key="tol_baixo")
    tol_cima  = st.number_input("Tolerância acima da TABELA (%) (ex.: 26,2 → 25)",  value=0.0,  min_value=0.0, max_value=100.0, step=1.0, key="tol_cima")

# Pagamento (único ou fatiado por contas)
dividir_pagamento = st.checkbox("Dividir pagamento em múltiplas contas (por dia)", value=False, key="chk_split")
if not dividir_pagamento:
    meio_pag_unico = st.selectbox("Meio de pagamento (DESPESAS)", ["Dinheiro","Pix","Cartão","Transferência","CNPJ"], index=0, key="sel_meiopag")
else:
    st.caption("As porcentagens devem somar 100%.")
    split_default = pd.DataFrame({"Me Pag:": ["Dinheiro","CNPJ"], "%": [50.0, 50.0]})
    split_df = st.data_editor(split_default, key="editor_split", num_rows="dynamic", use_container_width=True)
    soma_pct = float(pd.to_numeric(split_df.get("%", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    split_invalido = abs(soma_pct - 100.0) > 0.001

reprocessar_terca = st.checkbox("Reprocessar esta terça (regravar)", value=False, key="chk_reprocessar")

# ========= Lógica de semana =========
# filtro do funcionário insensível a acento
if "Funcionário" in base.columns:
    func_col = "Funcionário"
elif "Funcionario" in base.columns:
    func_col = "Funcionario"
else:
    st.error("Coluna 'Funcionário' não encontrada na Base de Dados.")
    func_col = None

if func_col:
    mask_func = base[func_col].astype(str).map(fold_text) == "vinicius"
    dfv = base[mask_func].copy()
else:
    dfv = base.copy()  # evita crash; mas sem filtro

dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

ini, fim = janela_terca_a_segunda(terca_pagto)
mask_semana = (dfv["_dt_serv"].notna()) & (dfv["_dt_serv"]>=ini) & (dfv["_dt_serv"]<=fim)

status = dfv["StatusFiado"].astype(str).str.strip().str.lower()
mask_nao_fiado = (status=="") | (status=="nao") | (status=="não")
semana_df = dfv[mask_semana & mask_nao_fiado].copy()

mask_fiado_all = ~mask_nao_fiado
fiado_df = dfv[mask_semana & mask_fiado_all].copy()

fiado_df["_dt_pagto"] = fiado_df["DataPagamento"].apply(parse_br_date)
fiados_liberados = fiado_df[(fiado_df["_dt_pagto"].notna()) & (fiado_df["_dt_pagto"]<=terca_pagto)].copy()
fiados_pendentes = fiado_df[(fiado_df["_dt_pagto"].isna()) | (fiado_df["_dt_pagto"]>terca_pagto)].copy()

# ========= Cache pagos =========
cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID","PagoEm","TerçaPagamento","ValorComissao","Competencia","Observacao"]
cache = garantir_colunas(cache, cache_cols)
terca_str = to_br_date(terca_pagto)
if reprocessar_terca:
    ja_pagos = set(cache[cache["TerçaPagamento"]!=terca_str]["RefID"].astype(str).tolist())
else:
    ja_pagos = set(cache["RefID"].astype(str).tolist())

# ========= Cálculos =========
def _valor_num(df: pd.DataFrame) -> pd.Series:
    col_val = find_val_col(df)
    if not col_val:
        st.warning("⚠️ Coluna de valor não encontrada. Procurei por: Valor, Valor (R$), Valor Líquido, Valor Recebido…")
        return pd.Series([0.0]*len(df), dtype=float)
    return _money_to_float_series(df.loc[:, [col_val]])

def _base_valor_row(row) -> float:
    serv = str(row.get("Serviço","")).strip()
    val  = float(row.get("Valor_num", 0.0))
    # 1) Já tem valor anotado → usa, arredondando para tabela só se “quebrado” e próximo
    if val > 0:
        if ajustar_quebrados_para_tabela and serv in VALOR_TABELA:
            tab = float(VALOR_TABELA[serv])
            if tab > 0:
                diff = val - tab
                rel = abs(diff) / tab
                if diff < 0 and rel <= (tol_baixo/100.0):   # abaixo e perto → sobe pra tabela
                    return tab
                if diff > 0 and rel <= (tol_cima/100.0):    # acima e perto → desce pra tabela
                    return tab
        return val
    # 2) Fallbacks (só quando Valor==0)
    if usar_tabela_quando_valor_zero and serv in VALOR_TABELA:
        return float(VALOR_TABELA[serv])
    if usar_tabela_cartao and is_cartao(row.get("Conta","")) and serv in VALOR_TABELA:
        return float(VALOR_TABELA[serv])
    return val

def _preparar(df_in: pd.DataFrame, titulo: str, key_prefix: str):
    if df_in is None or df_in.empty:
        st.warning(f"Sem itens em **{titulo}**.")
        return pd.DataFrame(), 0.0
    df = df_in.copy()
    df["RefID"] = df.apply(make_refid, axis=1)
    df = df[~df["RefID"].isin(ja_pagos)]
    if df.empty and ("Fiado" not in titulo):
        st.info(f"Todos os itens de **{titulo}** já foram pagos.")
        return pd.DataFrame(), 0.0

    df["Valor_num"] = _valor_num(df)
    df["Valor_base_comissao"] = df.apply(_base_valor_row, axis=1)
    df["Competência"] = df["Data"].apply(competencia_from_data_str)

    # % padrão + override opcional
    df["% Comissão"] = float(perc_padrao)
    permitir_override = st.checkbox("✏️ Permitir editar % comissão por linha", value=False, key=f"chk_override_{key_prefix}")
    if permitir_override:
        if "% Comissão (override)" not in df.columns:
            df["% Comissão (override)"] = ""
        st.caption("Preencha apenas onde quiser mudar o percentual daquela linha. Vazio = usa o padrão.")
        edit_cols = ["Data","Cliente","Serviço","Valor_base_comissao","% Comissão (override)"]
        df_edit = st.data_editor(df[edit_cols], key=f"editor_{key_prefix}", use_container_width=True, num_rows="fixed")
        # alinhamento por posição (garante mesmo tamanho)
        if len(df_edit) == len(df):
            df.loc[:, "% Comissão (override)"] = df_edit["% Comissão (override)"].values

    # ===== PATCH DO OVERRIDE (não quebra se o switch estiver desligado) =====
    if "% Comissão (override)" in df.columns:
        override_series = df["% Comissão (override)"]
    else:
        override_series = pd.Series([None] * len(df), index=df.index, dtype="float")

    pct_override = pd.to_numeric(override_series, errors="coerce")

    df["% Efetivo"] = pd.to_numeric(df["% Comissão"], errors="coerce").fillna(0.0)
    mask = pct_override.notna()
    df.loc[mask, "% Efetivo"] = pct_override.loc[mask].astype(float).clip(lower=0.0, upper=100.0)
    # =======================================================================

    df["Comissão (R$)"] = (df["Valor_base_comissao"] * df["% Efetivo"] / 100.0).round(2)

    st.subheader(titulo)
    show_cols = ["Data","Cliente","Serviço","Valor_base_comissao","% Efetivo","Comissão (R$)"]
    st.dataframe(df[show_cols], use_container_width=True)
    total = float(df["Comissão (R$)"].sum())
    st.success(f"Total em **{titulo}**: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    return df, total

# ========= Blocos =========
semana_grid, total_semana     = _preparar(semana_df,       "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_grid, total_fiados     = _preparar(fiados_liberados,"Fiados liberados (pagos até a terça)", "fiados_ok")
pendentes_grid, total_pend    = _preparar(fiados_pendentes,"Fiado a receber (pendentes)", "fiados_pendentes")

st.header(
    f"💵 Totais — Não fiado: R$ {total_semana:,.2f} | Fiados liberados: R$ {total_fiados:,.2f} | "
    f"Fiado a receber: R$ {total_pend:,.2f}"
    .replace(",", "X").replace(".", ",").replace("X",".")
)

# ========= Salvar =========
btn_disabled = dividir_pagamento and ('split_invalido' in locals() and split_invalido)
if st.button("✅ Registrar comissão desta terça", disabled=btn_disabled, key="btn_registrar"):
    if ((semana_grid is None or semana_grid.empty) and (fiados_grid is None or fiados_grid.empty)):
        st.warning("Não há itens para pagar hoje (NÃO FIADO e/ou FIADOS LIBERADOS vazios).")
    else:
        # 1) Cache
        novos_cache = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty: 
                continue
            for _, r in df_part.iterrows():
                novos_cache.append({
                    "RefID": r["RefID"],
                    "PagoEm": to_br_date(br_now()),
                    "TerçaPagamento": to_br_date(terca_pagto),
                    "ValorComissao": f'{float(r["Comissão (R$)"]):.2f}'.replace(".", ","),
                    "Competencia": r.get("Competência",""),
                    "Observacao": f'{r.get("Cliente","")} | {r.get("Serviço","")} | {r.get("Data","")}',
                })

        cache_df = _read_df(ABA_COMISSOES_CACHE)
        cache_df = garantir_colunas(cache_df, cache_cols)
        if reprocessar_terca:
            cache_df = cache_df[cache_df["TerçaPagamento"] != to_br_date(terca_pagto)]
        _write_df(ABA_COMISSOES_CACHE, pd.concat([cache_df[cache_cols], pd.DataFrame(novos_cache)], ignore_index=True))

        # 2) Despesas (1 linha por dia)
        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)

        pagaveis = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty: 
                continue
            pagaveis.append(df_part[["Data","Competência","Comissão (R$)"]].copy().rename(columns={"Comissão (R$)":"ComissaoValor"}))
        if pagaveis:
            pagos = pd.concat(pagaveis, ignore_index=True)
            pagos["_dt"] = pagos["Data"].apply(parse_br_date)
            pagos = pagos[pagos["_dt"].notna()]
            por_dia = pagos.groupby(["Data","Competência"])["ComissaoValor"].sum().reset_index()

            linhas = []
            if not dividir_pagamento:
                for _, row in por_dia.iterrows():
                    linhas.append({
                        "Data": str(row["Data"]).strip(),
                        "Prestador": "Vinicius",
                        "Descrição": f"{descricao_padrao} — Comp {str(row['Competência']).strip()} — Pago em {to_br_date(terca_pagto)}",
                        "Valor": f'R$ {float(row["ComissaoValor"]):.2f}'.replace(".", ","),
                        "Me Pag:": meio_pag_unico
                    })
            else:
                soma_pct = float(pd.to_numeric(split_df.get("%", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum() or 100.0)
                for _, row in por_dia.iterrows():
                    val_total = float(row["ComissaoValor"])
                    for _, r2 in split_df.iterrows():
                        conta = str(r2.get("Me Pag:", "")).strip()
                        pct = float(pd.to_numeric(r2.get("%",0.0), errors="coerce") or 0.0)
                        if not conta or pct<=0: 
                            continue
                        val = round(val_total * pct / soma_pct, 2)
                        linhas.append({
                            "Data": str(row["Data"]).strip(),
                            "Prestador": "Vinicius",
                            "Descrição": f"{descricao_padrao} — Comp {str(row['Competência']).strip()} — Pago em {to_br_date(terca_pagto)} — {pct:.1f}%",
                            "Valor": f'R$ {val:.2f}'.replace(".", ","),
                            "Me Pag:": conta
                        })

            _write_df(ABA_DESPESAS, pd.concat([despesas_df, pd.DataFrame(linhas)], ignore_index=True))
        st.success("🎉 Comissão registrada (NÃO FIADO + FIADOS LIBERADOS). Fiado a receber permanece no painel para controle futuro.")
        st.balloons()

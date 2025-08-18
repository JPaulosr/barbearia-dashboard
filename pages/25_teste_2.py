# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão (3 blocos): Não fiado | Fiados liberados | Fiado a receber

import streamlit as st
import pandas as pd# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão (3 blocos): Não fiado | Fiados liberados | Fiado a receber

import streamlit as st
import pandas as pd
import gspread, re, hashlib
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
from typing import Union

# =============================
# CONFIG
# =============================
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
    # normaliza cabeçalhos e remove duplicados mantendo a 1ª ocorrência
    df.columns = [str(c).strip() for c in df.columns]
    if df.columns.duplicated().any():
        # quando há duplicata, keep='first'
        keep = ~pd.Index(df.columns).duplicated(keep="first")
        df = df.loc[:, keep]
    return df

def _write_df(title:str, df:pd.DataFrame):
    ws = _ws(title); ws.clear()
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================
# HELPERS
# =============================
def br_now(): 
    return datetime.now(pytz.timezone(TZ))

def parse_br_date(x: Union[str, datetime]):
    # já é datetime?
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
    # tenta datas do Google Sheets (número serial) — opcional
    try:
        num = float(s)
        # 1899-12-30 é a base do Sheets
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
    # zera hora
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

def _series_from_any(s, length_hint:int=0) -> pd.Series:
    """Converte qualquer coisa em Series (aceita Series/DataFrame/escalar/lista)."""
    if isinstance(s, pd.DataFrame):
        # pega a 1ª coluna
        if s.shape[1] == 0:
            return pd.Series([None]*length_hint)
        s = s.iloc[:, 0]
    if isinstance(s, pd.Series):
        return s
    # lista/tupla/ndarray
    try:
        return pd.Series(s)
    except Exception:
        # escalar
        return pd.Series([s]*length_hint)

def _money_to_float_series(s) -> pd.Series:
    s = _series_from_any(s)
    # garante mesmo comprimento > 0
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    s = s.astype(str).str.strip()
    # remove símbolos e deixa só dígitos, ., , e sinais
    s = s.str.replace(r"[^\d,.\-+]", "", regex=True)
    # resolve separador brasileiro
    s = s.str.replace(".", "", regex=False) \
         .str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

# =============================
# UI
# =============================
st.set_page_config(layout="wide")
st.title("💈 Comissão — Vinícius")

base = _read_df(ABA_DADOS)
base = garantir_colunas(base, COLS_OFICIAIS).copy()

# Inputs principais
colA, colB, colC = st.columns([1,1,1])
with colA:
    hoje = br_now()
    # próxima terça (ou hoje se já for terça)
    delta = (1 - hoje.weekday()) % 7
    terca_base = hoje + timedelta(days=delta)
    terca_pagto = datetime.combine(st.date_input("🗓️ Terça do pagamento", value=terca_base.date()), datetime.min.time())
with colB:
    perc_padrao = st.number_input("Percentual padrão (%)", value=PERCENTUAL_PADRAO, step=1.0)
with colC:
    descricao_padrao = st.text_input("Descrição (DESPESAS)", value="Comissão Vinícius")

# Regras de valor
colD, colE = st.columns([1,1])
with colD:
    usar_tabela_quando_valor_zero = st.checkbox("Usar TABELA quando Valor 0/vazio", value=True)
    usar_tabela_cartao = st.checkbox("Usar TABELA quando cartão", value=True)
with colE:
    ajustar_quebrados_para_tabela = st.checkbox("Ajustar valores 'quebrados' para TABELA (se perto)", value=True)
    tolerancia_pct = st.number_input("Tolerância para TABELA (%)", value=25.0, min_value=0.0, max_value=100.0, step=5.0)
tolerancia_rel = float(tolerancia_pct)/100.0

# Pagamento (único ou fatiado por contas)
dividir_pagamento = st.checkbox("Dividir pagamento em múltiplas contas (por dia)", value=False)
if not dividir_pagamento:
    meio_pag_unico = st.selectbox("Meio de pagamento (DESPESAS)", ["Dinheiro","Pix","Cartão","Transferência","CNPJ"], index=0)
else:
    st.caption("As porcentagens devem somar 100%.")
    split_default = pd.DataFrame({"Me Pag:": ["Dinheiro","CNPJ"], "%": [50.0, 50.0]})
    split_df = st.data_editor(split_default, key="editor_split", num_rows="dynamic", use_container_width=True)
    soma_pct = float(pd.to_numeric(split_df.get("%", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    split_invalido = abs(soma_pct - 100.0) > 0.001

reprocessar_terca = st.checkbox("Reprocessar esta terça (regravar)", value=False)

# =============================
# FILTRO DA SEMANA
# =============================
dfv = base[base["Funcionário"].astype(str).str.strip().str.lower()=="vinicius"].copy()
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

ini, fim = janela_terca_a_segunda(terca_pagto)
mask_semana = (dfv["_dt_serv"].notna()) & (dfv["_dt_serv"]>=ini) & (dfv["_dt_serv"]<=fim)

# Não fiado (sem status ou 'nao')
status = dfv["StatusFiado"].astype(str).str.strip().str.lower()
mask_nao_fiado = (status=="") | (status=="nao") | (status=="não")
semana_df = dfv[mask_semana & mask_nao_fiado].copy()

# Fiado (todos)
mask_fiado_all = ~mask_nao_fiado
fiado_df = dfv[mask_semana & mask_fiado_all].copy()

# Fiados liberados (pagos até a terça)
fiado_df["_dt_pagto"] = fiado_df["DataPagamento"].apply(parse_br_date)
fiados_liberados = fiado_df[(fiado_df["_dt_pagto"].notna()) & (fiado_df["_dt_pagto"]<=terca_pagto)].copy()

# Fiado a receber (pendentes)
fiados_pendentes = fiado_df[(fiado_df["_dt_pagto"].isna()) | (fiado_df["_dt_pagto"]>terca_pagto)].copy()

# =============================
# CACHE DE PAGOS JÁ LANÇADOS
# =============================
cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID","PagoEm","TerçaPagamento","ValorComissao","Competencia","Observacao"]
cache = garantir_colunas(cache, cache_cols)
terca_str = to_br_date(terca_pagto)
if reprocessar_terca:
    ja_pagos = set(cache[cache["TerçaPagamento"]!=terca_str]["RefID"].astype(str).tolist())
else:
    ja_pagos = set(cache["RefID"].astype(str).tolist())

# =============================
# CÁLCULO COMISSÃO (funções)
# =============================
def _valor_num(df: pd.DataFrame) -> pd.Series:
    # aceita Series/DataFrame/escalar e também coluna ausente
    if "Valor" in df.columns:
        col = df.loc[:, ["Valor"]]
        return _money_to_float_series(col)
    return pd.Series([0.0]*len(df), dtype=float)

def _base_valor_row(row) -> float:
    serv = str(row.get("Serviço","")).strip()
    val  = float(row.get("Valor_num", 0.0))
    # 1) anotado > 0
    if val > 0:
        # se "quebrado" e perto da tabela, arredonda para TABELA
        if ajustar_quebrados_para_tabela and (abs(val - round(val)) > 1e-9) and serv in VALOR_TABELA:
            tab = float(VALOR_TABELA[serv])
            if tab > 0 and abs(val - tab)/tab <= tolerancia_rel:
                return tab
        return val
    # 2) Fallbacks de TABELA
    if usar_tabela_quando_valor_zero and serv in VALOR_TABELA:
        return float(VALOR_TABELA[serv])
    if usar_tabela_cartao and is_cartao(row.get("Conta","")) and serv in VALOR_TABELA:
        return float(VALOR_TABELA[serv])
    # 3) nada
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
    df["% Comissão"] = float(perc_padrao)
    df["Comissão (R$)"] = (df["Valor_base_comissao"] * df["% Comissão"] / 100.0).round(2)

    st.subheader(titulo)
    show_cols = ["Data","Cliente","Serviço","Valor_base_comissao","% Comissão","Comissão (R$)"]
    st.dataframe(df[show_cols], use_container_width=True)
    total = float(df["Comissão (R$)"].sum())
    st.success(f"Total em **{titulo}**: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    return df, total

# =============================
# BLOCOS
# =============================
semana_grid, total_semana = _preparar(semana_df, "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_grid, total_fiados = _preparar(fiados_liberados, "Fiados liberados (pagos até a terça)", "fiados_ok")
pendentes_grid, total_pend = _preparar(fiados_pendentes, "Fiado a receber (pendentes)", "fiados_pendentes")

st.header(
    f"💵 Totais — Não fiado: R$ {total_semana:,.2f} | Fiados liberados: R$ {total_fiados:,.2f} | "
    f"Fiado a receber: R$ {total_pend:,.2f}"
    .replace(",", "X").replace(".", ",").replace("X",".")
)

# =============================
# SALVAR (apenas o que é para pagar hoje)
# - Grava cache e DESPESAS para: NÃO FIADO + FIADOS LIBERADOS
# - NÃO grava fiado a receber (apenas painel)
# =============================
btn_disabled = dividir_pagamento and ('split_invalido' in locals() and split_invalido)
if st.button("✅ Registrar comissão desta terça", disabled=btn_disabled):
    if ((semana_grid is None or semana_grid.empty) and (fiados_grid is None or fiados_grid.empty)):
        st.warning("Não há itens para pagar hoje (NÃO FIADO e/ou FIADOS LIBERADOS vazios).")
    else:
        # 1) Atualizar cache
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

        # 2) Lançar em DESPESAS (1 linha por dia), só para semana + fiados liberados
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

import gspread, re, hashlib
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz

# =============================
# CONFIG
# =============================
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
    try: return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(title=title, rows=2000, cols=50)

def _read_df(title:str)->pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how="all").fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _write_df(title:str, df:pd.DataFrame):
    ws = _ws(title); ws.clear()
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================
# HELPERS
# =============================
def br_now(): return datetime.now(pytz.timezone(TZ))
def parse_br_date(s:str):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y","%d-%m-%Y","%Y-%m-%d"):
        try: return datetime.strptime(s, fmt)
        except: pass
    return None
def to_br_date(dt:datetime): return dt.strftime("%d/%m/%Y")
def competencia_from_data_str(s:str):
    dt = parse_br_date(s);  return dt.strftime("%m/%Y") if dt else ""
def janela_terca_a_segunda(terca:datetime):
    ini = terca - timedelta(days=7); fim = ini + timedelta(days=6); return ini, fim
def make_refid(row:pd.Series)->str:
    key = "|".join([str(row.get(k,"")).strip() for k in ["Cliente","Data","Serviço","Valor","Funcionário","Combo"]])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
def garantir_colunas(df:pd.DataFrame, cols:list[str])->pd.DataFrame:
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df
def is_cartao(conta:str)->bool:
    c = (conta or "").strip().lower()
    return bool(re.search(r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos)", c))

def _money_to_float_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.str.replace(r"[^\d,.\-+]", "", regex=True)
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

# =============================
# UI
# =============================
st.set_page_config(layout="wide")
st.title("💈 Comissão — Vinícius")

base = _read_df(ABA_DADOS)
base = garantir_colunas(base, COLS_OFICIAIS).copy()

# Inputs principais
colA, colB, colC = st.columns([1,1,1])
with colA:
    hoje = br_now()
    sugestao_terca = hoje if hoje.weekday()==1 else hoje + timedelta(days=(1 - hoje.weekday()) % 7 or 7)
    terca_pagto = datetime.combine(st.date_input("🗓️ Terça do pagamento", value=sugestao_terca.date()), datetime.min.time())
with colB:
    perc_padrao = st.number_input("Percentual padrão (%)", value=PERCENTUAL_PADRAO, step=1.0)
with colC:
    descricao_padrao = st.text_input("Descrição (DESPESAS)", value="Comissão Vinícius")

# Regras de valor
colD, colE = st.columns([1,1])
with colD:
    usar_tabela_quando_valor_zero = st.checkbox("Usar TABELA quando Valor 0/vazio", value=True)
    usar_tabela_cartao = st.checkbox("Usar TABELA quando cartão", value=True)
with colE:
    ajustar_quebrados_para_tabela = st.checkbox("Ajustar valores 'quebrados' para TABELA (se perto)", value=True)
    tolerancia_pct = st.number_input("Tolerância para TABELA (%)", value=25.0, min_value=0.0, max_value=100.0, step=5.0)
tolerancia_rel = float(tolerancia_pct)/100.0

# Pagamento (único ou fatiado por contas)
dividir_pagamento = st.checkbox("Dividir pagamento em múltiplas contas (por dia)", value=False)
if not dividir_pagamento:
    meio_pag_unico = st.selectbox("Meio de pagamento (DESPESAS)", ["Dinheiro","Pix","Cartão","Transferência","CNPJ"], index=0)
else:
    st.caption("As porcentagens devem somar 100%.")
    split_default = pd.DataFrame({"Me Pag:": ["Dinheiro","CNPJ"], "%": [50.0, 50.0]})
    split_df = st.data_editor(split_default, key="editor_split", num_rows="dynamic", use_container_width=True)
    soma_pct = float(pd.to_numeric(split_df.get("%", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    split_invalido = abs(soma_pct - 100.0) > 0.001

reprocessar_terca = st.checkbox("Reprocessar esta terça (regravar)", value=False)

# =============================
# FILTRO DA SEMANA
# =============================
dfv = base[base["Funcionário"].astype(str).str.strip()=="Vinicius"].copy()
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

ini, fim = janela_terca_a_segunda(terca_pagto)
mask_semana = (dfv["_dt_serv"].notna()) & (dfv["_dt_serv"]>=ini) & (dfv["_dt_serv"]<=fim)

# Não fiado (sem status ou 'nao')
mask_nao_fiado = (dfv["StatusFiado"].astype(str).str.strip()=="") | (dfv["StatusFiado"].astype(str).str.strip().str.lower()=="nao")
semana_df = dfv[mask_semana & mask_nao_fiado].copy()

# Fiado (todos)
mask_fiado_all = ~mask_nao_fiado
fiado_df = dfv[mask_semana & mask_fiado_all].copy()

# Fiados liberados (pagos até a terça)
fiado_df["_dt_pagto"] = fiado_df["DataPagamento"].apply(parse_br_date)
fiados_liberados = fiado_df[(fiado_df["_dt_pagto"].notna()) & (fiado_df["_dt_pagto"]<=terca_pagto)].copy()

# Fiado a receber (pendentes)
fiados_pendentes = fiado_df[(fiado_df["_dt_pagto"].isna()) | (fiado_df["_dt_pagto"]>terca_pagto)].copy()

# =============================
# CACHE DE PAGOS JÁ LANÇADOS
# =============================
cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID","PagoEm","TerçaPagamento","ValorComissao","Competencia","Observacao"]
cache = garantir_colunas(cache, cache_cols)
terca_str = to_br_date(terca_pagto)
ja_pagos = set(cache["RefID"].astype(str).tolist()) if not reprocessar_terca else set(cache[cache["TerçaPagamento"]!=terca_str]["RefID"].astype(str).tolist())

# =============================
# CÁLCULO COMISSÃO (funções)
# =============================
def _valor_num(df: pd.DataFrame) -> pd.Series:
    col_val = "Valor"
    return _money_to_float_series(df[col_val]) if col_val in df.columns else pd.Series([0.0]*len(df))

def _base_valor_row(row) -> float:
    serv = str(row.get("Serviço","")).strip()
    val  = float(row.get("Valor_num", 0.0))
    # 1) Se anotado > 0, prioriza anotado…
    if val > 0:
        # …mas se for "quebrado" e perto da tabela, encaixa na TABELA (se habilitado)
        if ajustar_quebrados_para_tabela and (abs(val - int(val)) > 1e-9) and serv in VALOR_TABELA:
            tab = float(VALOR_TABELA[serv])
            if tab > 0 and abs(val - tab)/tab <= tolerancia_rel:
                return tab
        return val
    # 2) Fallbacks de TABELA
    if usar_tabela_quando_valor_zero and serv in VALOR_TABELA:
        return float(VALOR_TABELA[serv])
    if usar_tabela_cartao and is_cartao(row.get("Conta","")):
        return float(VALOR_TABELA.get(serv, val))
    # 3) Sem nada
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
    df["% Comissão"] = float(perc_padrao)
    df["Comissão (R$)"] = (df["Valor_base_comissao"] * df["% Comissão"] / 100.0).round(2)

    st.subheader(titulo)
    show_cols = ["Data","Cliente","Serviço","Valor_base_comissao","% Comissão","Comissão (R$)"]
    st.dataframe(df[show_cols], use_container_width=True)
    total = float(df["Comissão (R$)"].sum())
    st.success(f"Total em **{titulo}**: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    return df, total

# =============================
# BLOCOS
# =============================
semana_grid, total_semana = _preparar(semana_df, "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_grid, total_fiados = _preparar(fiados_liberados, "Fiados liberados (pagos até a terça)", "fiados_ok")
pendentes_grid, total_pend = _preparar(fiados_pendentes, "Fiado a receber (pendentes)", "fiados_pendentes")

st.header(
    f"💵 Totais — Não fiado: R$ {total_semana:,.2f} | Fiados liberados: R$ {total_fiados:,.2f} | "
    f"Fiado a receber: R$ {total_pend:,.2f}"
    .replace(",", "X").replace(".", ",").replace("X",".")
)

# =============================
# SALVAR (apenas o que é para pagar hoje)
# - Grava cache e DESPESAS para: NÃO FIADO + FIADOS LIBERADOS
# - NÃO grava fiado a receber (apenas painel)
# =============================
btn_disabled = dividir_pagamento and ('split_invalido' in locals() and split_invalido)
if st.button("✅ Registrar comissão desta terça", disabled=btn_disabled):
    if ((semana_grid is None or semana_grid.empty) and (fiados_grid is None or fiados_grid.empty)):
        st.warning("Não há itens para pagar hoje (NÃO FIADO e/ou FIADOS LIBERADOS vazios).")
    else:
        # 1) Atualizar cache
        novos_cache = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty: continue
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

        # 2) Lançar em DESPESAS (1 linha por dia), só para semana + fiados liberados
        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)

        pagaveis = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty: continue
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
                        if not conta or pct<=0: continue
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

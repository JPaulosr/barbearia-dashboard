# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Pagamento de comissão (linhas por DIA do atendimento)
# Regras:
# - Paga toda terça o período de terça→segunda anterior.
# - Fiado só entra quando DataPagamento <= terça do pagamento.
# - Em Despesas grava UMA LINHA POR DIA DO ATENDIMENTO (Data = data do serviço).
# - Evita duplicidades via sheet "comissoes_cache" com RefID por atendimento.
# - Se pago no cartão, comissão calculada sobre TABELA (ignora desconto do cartão).
# - Permite dividir pagamento por várias contas (percentuais que somam 100%).

import streamlit as st
import pandas as pd
import gspread
import hashlib
import re
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz

# =============================
# CONFIG BÁSICA
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"

TZ = "America/Sao_Paulo"

COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período",
    "StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"
]
COLS_DESPESAS_FIX = ["Data", "Prestador", "Descrição", "Valor", "Me Pag:"]

PERCENTUAL_PADRAO = 50.0

VALOR_TABELA = {
    "Corte": 25.00,
    "Barba": 15.00,
    "Sobrancelha": 7.00,
    "Luzes": 45.00,
    "Tintura": 20.00,
    "Alisamento": 40.00,
    "Gel": 10.00,
    "Pomada": 15.00,
}

# =============================
# CONEXÃO SHEETS
# =============================
@st.cache_resource
def _conn():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    cred = Credentials.from_service_account_info(info, scopes=escopo)
    cli = gspread.authorize(cred)
    return cli.open_by_key(SHEET_ID)

def _ws(title: str):
    sh = _conn()
    try:
        return sh.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=2000, cols=50)
        return ws

def _dedup_cols(cols):
    seen = {}
    out = []
    for c in cols:
        k = ("" if pd.isna(c) else str(c)).strip() or f"col_{len(out)}"
        if k in seen:
            seen[k] += 1
            out.append(f"{k}.{seen[k]}")
        else:
            seen[k] = 0
            out.append(k)
    return out

def _read_df(title: str) -> pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how="all").fillna("")
    df.columns = _dedup_cols(df.columns)
    obj_cols = df.select_dtypes(include=["object"]).columns
    for c in obj_cols:
        df[c] = df[c].astype(str)
    return df

def _write_df(title: str, df: pd.DataFrame):
    ws = _ws(title)
    ws.clear()
    set_with_dataframe(ws, df, include_index=False, include_column_header=True)

# =============================
# HELPERS
# =============================
def br_now():
    return datetime.now(pytz.timezone(TZ))

def parse_br_date(s: str):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except:
            pass
    return None

def to_br_date(dt: datetime):
    return dt.strftime("%d/%m/%Y")

def competencia_from_data_str(data_servico_str: str) -> str:
    dt = parse_br_date(data_servico_str)
    if not dt: return ""
    return dt.strftime("%m/%Y")

def janela_terca_a_segunda(terca_pagto: datetime):
    inicio = terca_pagto - timedelta(days=7)
    fim = inicio + timedelta(days=6)
    return inicio, fim

def make_refid(row: pd.Series) -> str:
    key = "|".join([
        str(row.get("Cliente", "")).strip(),
        str(row.get("Data", "")).strip(),
        str(row.get("Serviço", "")).strip(),
        str(row.get("Valor", "")).strip(),
        str(row.get("Funcionário", "")).strip(),
        str(row.get("Combo", "")).strip(),
    ])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

def garantir_colunas(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns: df[c] = ""
    return df

def is_cartao(conta: str) -> bool:
    c = (conta or "").strip().lower()
    return bool(re.search(r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos)", c))

def _get_col(df: pd.DataFrame, name: str):
    if name in df.columns: return name
    lower = {c.lower(): c for c in df.columns}
    return lower.get(name.lower())

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
st.title("💈 Pagamento de Comissão — Vinicius (1 linha por DIA do atendimento)")

base = _read_df(ABA_DADOS)
base = garantir_colunas(base, COLS_OFICIAIS).copy()

# Inputs
colA, colB, colC = st.columns([1,1,1])
with colA:
    hoje = br_now()
    if hoje.weekday() == 1: sugestao_terca = hoje
    else:
        delta = (1 - hoje.weekday()) % 7
        if delta == 0: delta = 7
        sugestao_terca = hoje + timedelta(days=delta)
    terca_pagto = st.date_input("🗓️ Terça do pagamento", value=sugestao_terca.date())
    terca_pagto = datetime.combine(terca_pagto, datetime.min.time())

with colB:
    perc_padrao = st.number_input("Percentual padrão da comissão (%)", value=PERCENTUAL_PADRAO, step=1.0)

with colC:
    incluir_produtos = st.checkbox("Incluir PRODUTOS?", value=False)

descricao_padrao = st.text_input("Descrição (para DESPESAS)", value="Comissão Vinícius")

usar_tabela_cartao = st.checkbox("Usar preço de TABELA para cartão", value=True)

# Dividir pagamento?
dividir_pagamento = st.checkbox("Dividir pagamento em múltiplas contas", value=False)
if not dividir_pagamento:
    meio_pag_unico = st.selectbox("Meio de pagamento", ["Dinheiro", "Pix", "Cartão", "Transferência", "CNPJ"], index=0)
else:
    st.caption("Informe contas e percentuais (somar 100%).")
    split_default = pd.DataFrame({"Me Pag:": ["Dinheiro", "CNPJ"], "%": [50.0, 50.0]})
    split_df = st.data_editor(split_default, key="editor_split", num_rows="dynamic")
    soma_pct = float(pd.to_numeric(split_df.get("%", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    split_invalido = abs(soma_pct - 100.0) > 0.001

reprocessar_terca = st.checkbox("Reprocessar esta terça (regravar)", value=False)

# =============================
# FILTRAR BASE
# =============================
dfv = base[base["Funcionário"].astype(str).str.strip() == "Vinicius"].copy()
if not incluir_produtos:
    dfv = dfv[dfv["Tipo"].astype(str).str.lower() == "serviço"]
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}**")

mask_semana = (
    (dfv["_dt_serv"].notna()) &
    (dfv["_dt_serv"] >= ini) & (dfv["_dt_serv"] <= fim) &
    ((dfv["StatusFiado"].astype(str).str.strip() == "") |
     (dfv["StatusFiado"].astype(str).str.lower() == "nao"))
)
semana_df = dfv[mask_semana].copy()

df_fiados = dfv[(dfv["StatusFiado"].astype(str).str.strip() != "") |
                (dfv["IDLancFiado"].astype(str).str.strip() != "")]
df_fiados["_dt_pagto"] = df_fiados["DataPagamento"].apply(parse_br_date)
fiados_liberados = df_fiados[(df_fiados["_dt_pagto"].notna()) & (df_fiados["_dt_pagto"] <= terca_pagto)].copy()

cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID", "PagoEm", "TerçaPagamento", "ValorComissao", "Competencia", "Observacao"]
cache = garantir_colunas(cache, cache_cols)

terca_str = to_br_date(terca_pagto)
ja_pagos = set(cache["RefID"].astype(str).tolist())
if reprocessar_terca:
    ja_pagos = set(cache[cache["TerçaPagamento"] != terca_str]["RefID"].astype(str).tolist())

# =============================
# GRADE EDITÁVEL
# =============================
def preparar_grid(df_in, titulo: str, key_prefix: str):
    if df_in is None or df_in.empty:
        st.warning(f"Sem itens em {titulo}.")
        return pd.DataFrame(), 0.0
    df = df_in.copy()
    df["RefID"] = df.apply(make_refid, axis=1)
    df = df[~df["RefID"].isin(ja_pagos)]
    if df.empty:
        st.info(f"Todos itens de {titulo} já pagos.")
        return pd.DataFrame(), 0.0

    col_val = _get_col(df, "Valor")
    if col_val is None: df["Valor_num"] = 0.0
    else: df["Valor_num"] = _money_to_float_series(df[col_val])

    df["Competência"] = df["Data"].apply(competencia_from_data_str)

    if usar_tabela_cartao:
        def _base(row):
            if is_cartao(row.get("Conta", "")):
                serv = str(row.get("Serviço", "")).strip()
                return float(VALOR_TABELA.get(serv, row["Valor_num"]))
            return float(row["Valor_num"])
        df["Valor_base_comissao"] = df.apply(_base, axis=1)
    else:
        df["Valor_base_comissao"] = df["Valor_num"]

    ed = df[["Data", "Cliente", "Serviço", "Valor_base_comissao", "Competência", "RefID"]].rename(
        columns={"Valor_base_comissao": "Valor (para comissão)"})
    ed["% Comissão"] = float(perc_padrao)

    edited = st.data_editor(ed, key=f"editor_{key_prefix}", num_rows="fixed")

    v = pd.to_numeric(edited["Valor (para comissão)"], errors="coerce").fillna(0.0)
    p = pd.to_numeric(edited["% Comissão"], errors="coerce").fillna(float(perc_padrao))
    comissao_series = (v * p / 100.0).round(2)

    total = float(comissao_series.sum())

    merged = df.merge(edited[["RefID", "% Comissão"]], on="RefID", how="left")
    merged["ComissaoValor"] = comissao_series

    st.success(f"Total em {titulo}: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    return merged, total

semana_grid, total_semana = preparar_grid(semana_df, "Semana — NÃO FIADO", "semana")
fiados_grid, total_fiados = preparar_grid(fiados_liberados, "Fiados liberados", "fiados")

total_geral = total_semana + total_fiados
st.header(f"💵 Total desta terça: R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

# =============================
# CONFIRMAR E GRAVAR
# =============================
btn_disabled = dividir_pagamento and split_invalido
if st.button("✅ Registrar comissão", disabled=btn_disabled):
    novos_cache = []
    for df_part in [semana_grid, fiados_grid]:
        if df_part is None or df_part.empty: continue
        for _, r in df_part.iterrows():
            novos_cache.append({
                "RefID": r["RefID"],
                "PagoEm": to_br_date(br_now()),
                "TerçaPagamento": to_br_date(terca_pagto),
                "ValorComissao": f'{r["ComissaoValor"]:.2f}'.replace(".", ","),
                "Competencia": r.get("Competência", ""),
                "Observacao": f'{r.get("Cliente","")} | {r.get("Serviço","")} | {r.get("Data","")}',
            })

    cache_df = _read_df(ABA_COMISSOES_CACHE)
    cache_df = garantir_colunas(cache_df, cache_cols)
    if reprocessar_terca:
        cache_df = cache_df[cache_df["TerçaPagamento"] != terca_str]
    cache_upd = pd.concat([cache_df[cache_cols], pd.DataFrame(novos_cache)], ignore_index=True)
    _write_df(ABA_COMISSOES_CACHE, cache_upd)

    despesas_df = _read_df(ABA_DESPESAS)
    despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)

    pagaveis = []
    for df_part in [semana_grid, fiados_grid]:
        if df_part is None or df_part.empty: continue
        pagaveis.append(df_part[["Data", "Competência", "ComissaoValor"]].copy())
    pagos = pd.concat(pagaveis, ignore_index=True)
    pagos["_dt"] = pagos["Data"].apply(parse_br_date)
    pagos = pagos[pagos["_dt"].notna()]

    por_dia = pagos.groupby(["Data", "Competência"])["ComissaoValor"].sum().reset_index()

    linhas = []
    for _, row in por_dia.iterrows():
        data_serv = str(row["Data"]).strip()
        comp = str(row["Competência"]).strip()
        val_total = float(row["ComissaoValor"])
        if not dividir_pagamento:
            linhas.append({
                "Data": data_serv, "Prestador": "Vinicius",
                "Descrição": f"{descricao_padrao} — Comp {comp} — Pago em {terca_str}",
                "Valor": f'R$ {val_total:.2f}'.replace(".", ","),
                "Me Pag:": meio_pag_unico
            })
        else:
            soma_pct = float(pd.to_numeric(split_df["%"], errors="coerce").fillna(0.0).sum())
            for _, r2 in split_df.iterrows():
                conta = str(r2.get("Me Pag:", "")).strip()
                pct = float(r2.get("%", 0.0))
                if conta and pct > 0:
                    val = round(val_total * pct / soma_pct, 2)
                    linhas.append({
                        "Data": data_serv, "Prestador": "Vinicius",
                        "Descrição": f"{descricao_padrao} — Comp {comp} — Pago em {terca_str} — {pct:.1f}%",
                        "Valor": f'R$ {val:.2f}'.replace(".", ","),
                        "Me Pag:": conta
                    })

    despesas_final = pd.concat([despesas_df, pd.DataFrame(linhas)], ignore_index=True)
    _write_df(ABA_DESPESAS, despesas_final)

    st.success(f"🎉 Comissão registrada! {len(linhas)} linhas em {ABA_DESPESAS} e {len(novos_cache)} itens no cache.")
    st.balloons()

# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Pagamento de comissão (linhas por DIA do atendimento)

import streamlit as st
import pandas as pd
import gspread
import hashlib, re
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

PERCENTUAL_PADRAO = 50.0  # % padrão

VALOR_TABELA = {  # ajuste se quiser
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

def _dedup_cols(cols):
    seen, out = {}, []
    for c in cols:
        k = ("" if pd.isna(c) else str(c)).strip() or f"col_{len(out)}"
        if k in seen: seen[k]+=1; out.append(f"{k}.{seen[k]}")
        else: seen[k]=0; out.append(k)
    return out

def _read_df(title:str)->pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws, evaluate_formulas=True).dropna(how="all").fillna("")
    df.columns = _dedup_cols(df.columns)
    for c in df.select_dtypes(include=["object"]).columns:
        df[c] = df[c].astype(str)
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
def _get_col(df:pd.DataFrame, name:str):
    if name in df.columns: return name
    lower = {c.lower():c for c in df.columns}; return lower.get(name.lower())

# --- moeda BR: "R$ 1.234,56" -> 1234.56 ---
def _money_to_float_series(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip()
    s = s.str.replace(r"[^\d,.\-+]", "", regex=True)  # remove R$, espaços etc
    s = s.str.replace(".", "", regex=False)          # milhar
    s = s.str.replace(",", ".", regex=False)         # decimal
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
    sugestao_terca = hoje if hoje.weekday()==1 else hoje + timedelta(days=(1 - hoje.weekday()) % 7 or 7)
    terca_pagto = datetime.combine(st.date_input("🗓️ Terça do pagamento", value=sugestao_terca.date()), datetime.min.time())
with colB:
    perc_padrao = st.number_input("Percentual padrão da comissão (%)", value=PERCENTUAL_PADRAO, step=1.0)
with colC:
    incluir_produtos = st.checkbox("Incluir PRODUTOS?", value=False)

descricao_padrao = st.text_input("Descrição (para DESPESAS)", value="Comissão Vinícius")

usar_tabela_cartao = st.checkbox("Usar TABELA quando for cartão", value=True)
usar_tabela_quando_valor_zero = st.checkbox("Usar TABELA quando Valor vier 0/vazio", value=True)

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
# FILTRAR BASE
# =============================
dfv = base[base["Funcionário"].astype(str).str.strip()=="Vinicius"].copy()
if not incluir_produtos:
    dfv = dfv[dfv["Tipo"].astype(str).str.strip().str.lower()=="serviço"]
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}** (terça→segunda)")

mask_semana = (
    dfv["_dt_serv"].notna() & (dfv["_dt_serv"]>=ini) & (dfv["_dt_serv"]<=fim) &
    ((dfv["StatusFiado"].astype(str).str.strip()=="") | (dfv["StatusFiado"].astype(str).str.strip().str.lower()=="nao"))
)
semana_df = dfv[mask_semana].copy()

df_fiados = dfv[(dfv["StatusFiado"].astype(str).str.strip()!="") | (dfv["IDLancFiado"].astype(str).str.strip()!="")].copy()
df_fiados["_dt_pagto"] = df_fiados["DataPagamento"].apply(parse_br_date)
fiados_liberados = df_fiados[(df_fiados["_dt_pagto"].notna()) & (df_fiados["_dt_pagto"]<=terca_pagto)].copy()

cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID","PagoEm","TerçaPagamento","ValorComissao","Competencia","Observacao"]
cache = garantir_colunas(cache, cache_cols)
terca_str = to_br_date(terca_pagto)
ja_pagos = set(cache["RefID"].astype(str).tolist()) if not reprocessar_terca else set(cache[cache["TerçaPagamento"]!=terca_str]["RefID"].astype(str).tolist())

# =============================
# GRADE + CÁLCULO  (BLOCO PRINCIPAL)
# =============================
def preparar_grid(df_in, titulo: str, key_prefix: str):
    # 0) DataFrame válido
    if df_in is None or (isinstance(df_in, pd.DataFrame) and df_in.empty):
        st.warning(f"Sem itens em **{titulo}**."); return pd.DataFrame(), 0.0
    df = df_in.copy() if isinstance(df_in, pd.DataFrame) else pd.DataFrame(df_in)

    # 1) RefID + remove já pagos
    df["RefID"] = df.apply(make_refid, axis=1)
    df = df[~df["RefID"].isin(ja_pagos)]
    if df.empty:
        st.info(f"Todos os itens de **{titulo}** já foram pagos."); return pd.DataFrame(), 0.0

    # 2) Valor -> numérico (moeda BR)
    col_val = _get_col(df, "Valor") or _get_col(df, "valor_total") or _get_col(df, "preco")
    if col_val is None:
        st.warning(f"⚠️ {titulo}: coluna de valor não encontrada; valores considerados como R$ 0,00.")
        df["Valor_num"] = 0.0
    else:
        # converte sempre com o parser BR (funciona para número ou string)
        try:
            df["Valor_num"] = _money_to_float_series(df[col_val])
        except Exception:
            df["Valor_num"] = pd.to_numeric(df[col_val], errors="coerce").fillna(0.0)

    # 3) Competência
    df["Competência"] = df["Data"].apply(competencia_from_data_str)

    # 4) Base para comissão
    def _base_valor(row):
        serv = str(row.get("Serviço","")).strip()
        val  = float(row.get("Valor_num", 0.0))

        # (a) se valor 0/vazio e opção marcada → tabela
        if usar_tabela_quando_valor_zero and val <= 0.0 and serv in VALOR_TABELA:
            return float(VALOR_TABELA[serv])
        # (b) se cartão e opção marcada → tabela priorizada
        if usar_tabela_cartao and is_cartao(row.get("Conta","")):
            return float(VALOR_TABELA.get(serv, val))
        # (c) normal
        return val
    df["Valor_base_comissao"] = df.apply(_base_valor, axis=1)

    # 5) Editor (você só muda a % se quiser)
    for c in ["Data","Cliente","Serviço"]:
        if c not in df.columns: df[c] = ""
    ed = df[["Data","Cliente","Serviço","Valor_base_comissao","Competência","RefID"]].rename(
        columns={"Valor_base_comissao":"Valor (para comissão)"}
    )
    ed["% Comissão"] = float(perc_padrao)
    edited = st.data_editor(ed, key=f"editor_{key_prefix}", num_rows="fixed", use_container_width=True)

    # 6) Calcula SEMPRE aqui
    v = pd.to_numeric(edited["Valor (para comissão)"], errors="coerce").fillna(0.0)
    p = pd.to_numeric(edited["% Comissão"], errors="coerce").fillna(float(perc_padrao))
    comissao_series = (v * p / 100.0).round(2)
    total = float(comissao_series.sum())

    merged = df.merge(edited[["RefID","% Comissão"]], on="RefID", how="left")
    merged["ComissaoValor"] = comissao_series

    zeros_original = int((df["Valor_num"]<=0.0).sum())
    if zeros_original > 0 and usar_tabela_quando_valor_zero:
        st.info(f"{zeros_original} atendimento(s) tinham Valor 0/vazio e usaram o preço de TABELA.")

    st.subheader(titulo)
    st.success(f"Total em **{titulo}**: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
    st.dataframe(edited.assign(**{"Comissão (R$)": comissao_series}), use_container_width=True)
    return merged, total

# ----- chama para NÃO FIADO e FIADO liberado
semana_grid, total_semana = preparar_grid(semana_df, "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_grid, total_fiados = preparar_grid(fiados_liberados, "Fiados liberados (pagos até a terça)", "fiados")

total_geral = total_semana + total_fiados
st.header(f"💵 Total desta terça: R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))

# =============================
# SALVAR — CACHE + DESPESAS
# =============================
btn_disabled = dividir_pagamento and ('split_invalido' in locals() and split_invalido)
if st.button("✅ Registrar comissão (por DIA do atendimento)", disabled=btn_disabled):
    if (semana_grid is None or semana_grid.empty) and (fiados_grid is None or fiados_grid.empty):
        st.warning("Não há itens para pagar.")
    else:
        # cache
        novos_cache = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty: continue
            for _, r in df_part.iterrows():
                novos_cache.append({
                    "RefID": r["RefID"],
                    "PagoEm": to_br_date(br_now()),
                    "TerçaPagamento": to_br_date(terca_pagto),
                    "ValorComissao": f'{float(r["ComissaoValor"]):.2f}'.replace(".", ","),
                    "Competencia": r.get("Competência",""),
                    "Observacao": f'{r.get("Cliente","")} | {r.get("Serviço","")} | {r.get("Data","")}',
                })

        cache_df = _read_df(ABA_COMISSOES_CACHE)
        cache_df = garantir_colunas(cache_df, cache_cols)
        if reprocessar_terca:
            cache_df = cache_df[cache_df["TerçaPagamento"] != to_br_date(terca_pagto)]
        _write_df(ABA_COMISSOES_CACHE, pd.concat([cache_df[cache_cols], pd.DataFrame(novos_cache)], ignore_index=True))

        # despesas
        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)

        pagaveis = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty: continue
            pagaveis.append(df_part[["Data","Competência","ComissaoValor"]].copy())
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
        st.success(f"🎉 Comissão registrada! {len(linhas)} linhas em **{ABA_DESPESAS}** e {len(novos_cache)} itens no **{ABA_COMISSOES_CACHE}**.")
        st.balloons()

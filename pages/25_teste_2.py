# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Pagamento de comissão (linhas por DIA do atendimento)
# Regras:
# - Paga toda terça o período de terça→segunda anterior.
# - Fiado só entra quando DataPagamento <= terça do pagamento.
# - Em Despesas grava UMA LINHA POR DIA DO ATENDIMENTO (Data = data do serviço).
# - Evita duplicidades via sheet "comissoes_cache" com RefID por atendimento.
# - (Opcional) Se pago no cartão, comissão calculada sobre TABELA (ignora desconto do cartão).
# - (Novo) Permite dividir cada valor diário em múltiplas contas (percentuais que somam 100%).

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

# Colunas esperadas na Base de Dados
COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período",
    # Fiado
    "StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"
]

# Colunas da aba Despesas
COLS_DESPESAS_FIX = ["Data", "Prestador", "Descrição", "Valor", "Me Pag:"]

# Percentual padrão da comissão
PERCENTUAL_PADRAO = 50.0

# Tabela de preços para comissão (ajuste se necessário)
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
    df = get_as_dataframe(ws, evaluate_formulas=True)
    df = df.dropna(how="all").fillna("")
    df.columns = _dedup_cols(df.columns)
    # Apenas colunas object para string
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
        except Exception:
            pass
    return None

def to_br_date(dt: datetime):
    return dt.strftime("%d/%m/%Y")

def competencia_from_data_str(data_servico_str: str) -> str:
    dt = parse_br_date(data_servico_str)
    if not dt:
        return ""
    return dt.strftime("%m/%Y")

def janela_terca_a_segunda(terca_pagto: datetime):
    # terça de pagamento paga a semana ANTERIOR (terça→segunda)
    inicio = terca_pagto - timedelta(days=7)  # terça anterior
    fim = inicio + timedelta(days=6)          # segunda
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
        if c not in df.columns:
            df[c] = ""
    return df

def is_cartao(conta: str) -> bool:
    c = (conta or "").strip().lower()
    padrao = r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos)"
    return bool(re.search(padrao, c))

def _get_col(df: pd.DataFrame, name: str):
    if name in df.columns:
        return name
    lower = {c.lower(): c for c in df.columns}
    return lower.get(name.lower())

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

# Carrega base
base = _read_df(ABA_DADOS)
base = garantir_colunas(base, COLS_OFICIAIS).copy()

# Inputs
colA, colB, colC = st.columns([1,1,1])
with colA:
    hoje = br_now()
    if hoje.weekday() == 1:  # terça
        sugestao_terca = hoje
    else:
        delta = (1 - hoje.weekday()) % 7
        if delta == 0:
            delta = 7
        sugestao_terca = (hoje + timedelta(days=delta))
    terca_pagto = st.date_input("🗓️ Terça do pagamento", value=sugestao_terca.date())
    terca_pagto = datetime.combine(terca_pagto, datetime.min.time())

with colB:
    perc_padrao = st.number_input("Percentual padrão da comissão (%)", value=PERCENTUAL_PADRAO, step=1.0)

with colC:
    incluir_produtos = st.checkbox("Incluir PRODUTOS?", value=False)

descricao_padrao = st.text_input("Descrição (para DESPESAS)", value="Comissão Vinícius")

usar_tabela_cartao = st.checkbox(
    "Usar preço de TABELA para comissão quando pago no cartão",
    value=True,
    help="Ignora o valor líquido (com taxa) e comissiona pelo preço de tabela do serviço."
)

# ✅ Novo: dividir pagamento em múltiplas contas?
dividir_pagamento = st.checkbox(
    "Dividir pagamento em múltiplas contas (por dia, em percentuais)",
    value=False,
    help="Se marcado, cada total DIÁRIO será repartido conforme os percentuais abaixo (a soma deve ser 100%)."
)

if not dividir_pagamento:
    meio_pag_unico = st.selectbox("Meio de pagamento (para DESPESAS)", ["Dinheiro", "Pix", "Cartão", "Transferência", "CNPJ"], index=0)
else:
    st.caption("Informe as contas e os percentuais (por dia). Ex.: 50% Dinheiro + 50% CNPJ.")
    split_default = pd.DataFrame({"Me Pag:": ["Dinheiro", "CNPJ"], "%": [50.0, 50.0]})
    split_df = st.data_editor(
        split_default,
        key="editor_split",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Me Pag:": st.column_config.TextColumn(help="Nome da conta que aparecerá na coluna 'Me Pag:'"),
            "%": st.column_config.NumberColumn(format="%.1f %%", min_value=0.0, max_value=100.0, step=0.5)
        }
    )
    soma_pct = float(pd.to_numeric(split_df.get("%", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum())
    if abs(soma_pct - 100.0) > 0.001:
        st.warning(f"Os percentuais somam **{soma_pct:.1f}%**. Ajuste para somar 100%.")
    # trava o botão de salvar se percentuais inválidos
    split_invalido = abs(soma_pct - 100.0) > 0.001 or split_df.empty or split_df["Me Pag:"].isna().any() or (split_df["Me Pag:"].astype(str).str.strip() == "").any()

# ✅ Reprocessar esta terça (limpa/ignora cache desta terça)
reprocessar_terca = st.checkbox(
    "Reprocessar esta terça (regravar): ignorar/limpar cache desta terça antes de salvar",
    value=False,
    help="Marque se você apagou as linhas em Despesas e quer gravar novamente esta terça."
)

# Conjunto Vinicius
dfv = base[base["Funcionário"].astype(str).str.strip() == "Vinicius"].copy()
if not incluir_produtos:
    dfv = dfv[dfv["Tipo"].astype(str).str.strip().str.lower() == "serviço"]
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

# Janela terça→segunda (anterior à terça de pagamento)
ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}** (terça→segunda)")

# 1) Itens da SEMANA NÃO FIADO
mask_semana = (
    (dfv["_dt_serv"].notna()) &
    (dfv["_dt_serv"] >= ini) &
    (dfv["_dt_serv"] <= fim) &
    ((dfv["StatusFiado"].astype(str).str.strip() == "") |
     (dfv["StatusFiado"].astype(str).str.strip().str.lower() == "nao"))
)
semana_df = dfv[mask_semana].copy()

# 2) Fiados liberados até a terça (independe da data do serviço)
df_fiados = dfv[
    (dfv["StatusFiado"].astype(str).str.strip() != "") |
    (dfv["IDLancFiado"].astype(str).str.strip() != "")
].copy()
df_fiados["_dt_pagto"] = df_fiados["DataPagamento"].apply(parse_br_date)
fiados_liberados = df_fiados[(df_fiados["_dt_pagto"].notna()) & (df_fiados["_dt_pagto"] <= terca_pagto)].copy()

# Cache de comissões já pagas (por RefID)
cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID", "PagoEm", "TerçaPagamento", "ValorComissao", "Competencia", "Observacao"]
cache = garantir_colunas(cache, cache_cols)

terca_str = to_br_date(terca_pagto)
if reprocessar_terca:
    ja_pagos = set(cache[cache["TerçaPagamento"] != terca_str]["RefID"].astype(str).tolist())
else:
    ja_pagos = set(cache["RefID"].astype(str).tolist())

# =============================
# GRADE EDITÁVEL (ROBUSTA)
# =============================
def preparar_grid(df_in, titulo: str, key_prefix: str):
    if df_in is None:
        st.warning(f"Sem itens em **{titulo}**.")
        return pd.DataFrame(), 0.0
    if not isinstance(df_in, pd.DataFrame):
        try:
            df = pd.DataFrame(df_in)
        except Exception:
            st.warning(f"Dados inesperados em **{titulo}** (não foi possível converter).")
            return pd.DataFrame(), 0.0
    else:
        df = df_in.copy()

    if df.empty:
        st.warning(f"Sem itens em **{titulo}**.")
        return pd.DataFrame(), 0.0

    df["RefID"] = df.apply(make_refid, axis=1)
    df = df[~df["RefID"].isin(ja_pagos)]
    if df.empty:
        st.info(f"Todos os itens de **{titulo}** já foram pagos.")
        return pd.DataFrame(), 0.0

    col_val = _get_col(df, "Valor") or _get_col(df, "valor_total") or _get_col(df, "preco")
    if col_val is None:
        st.warning(f"⚠️ {titulo}: coluna de valor não encontrada; valores considerados como R$ 0,00.")
        df["Valor_num"] = 0.0
    else:
        if pd.api.types.is_numeric_dtype(df[col_val]):
            df["Valor_num"] = pd.to_numeric(df[col_val], errors="coerce").fillna(0.0)
        else:
            df["Valor_num"] = _money_to_float_series(df[col_val])

    df["Competência"] = df["Data"].apply(competencia_from_data_str)

    if usar_tabela_cartao:
        def _base_valor(row):
            if is_cartao(row.get("Conta", "")):
                serv = str(row.get("Serviço", "")).strip()
                return float(VALOR_TABELA.get(serv, row.get("Valor_num", 0.0)))
            return float(row.get("Valor_num", 0.0))
        df["Valor_base_comissao"] = df.apply(_base_valor, axis=1)
    else:
        df["Valor_base_comissao"] = df["Valor_num"].astype(float)

    st.subheader(titulo)
    st.caption("Edite a % de comissão por linha, se precisar.")

    for c in ["Data", "Cliente", "Serviço"]:
        if c not in df.columns:
            df[c] = ""
    ed = df[["Data", "Cliente", "Serviço", "Valor_base_comissao", "Competência", "RefID"]].rename(
        columns={"Valor_base_comissao": "Valor (para comissão)"}
    )
    ed["% Comissão"] = float(perc_padrao)
    ed["Comissão (R$)"] = (ed["Valor (para comissão)"] * ed["% Comissão"] / 100.0).round(2)
    ed = ed.reset_index(drop=True)

    edited = st.data_editor(
        ed,
        key=f"editor_{key_prefix}",
        num_rows="fixed",
        column_config={
            "Valor (para comissão)": st.column_config.NumberColumn(format="R$ %.2f"),
            "% Comissão": st.column_config.NumberColumn(format="%.1f %%", min_value=0.0, max_value=100.0, step=0.5),
            "Comissão (R$)": st.column_config.NumberColumn(format="R$ %.2f"),
        }
    )

    total = float(pd.to_numeric(edited["Comissão (R$)"], errors="coerce").fillna(0.0).sum())
    merged = df.merge(edited[["RefID", "% Comissão", "Comissão (R$)"]], on="RefID", how="left")
    merged["ComissaoValor"] = pd.to_numeric(merged["Comissão (R$)"], errors="coerce").fillna(0.0)

    st.success(f"Total de comissão em **{titulo}**: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
    return merged, total

semana_grid, total_semana = preparar_grid(semana_df, "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_grid, total_fiados = preparar_grid(fiados_liberados, "Fiados liberados (pagos até a terça)", "fiados")

total_geral = total_semana + total_fiados
st.header(f"💵 Total desta terça (consolidado): R$ {total_geral:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))

# =============================
# CONFIRMAR E GRAVAR
# =============================
btn_disabled = False
if dividir_pagamento:
    btn_disabled = 'split_invalido' in locals() and split_invalido

if st.button("✅ Registrar comissão (por DIA do atendimento) e marcar itens como pagos", disabled=btn_disabled):
    if (semana_grid is None or semana_grid.empty) and (fiados_grid is None or fiados_grid.empty):
        st.warning("Não há itens para pagar.")
    else:
        # 1) Atualiza cache item a item (para não pagar duas vezes)
        novos_cache = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty:
                continue
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
        cache_cols = ["RefID", "PagoEm", "TerçaPagamento", "ValorComissao", "Competencia", "Observacao"]
        cache_df = garantir_colunas(cache_df, cache_cols)

        if reprocessar_terca:
            cache_df = cache_df[cache_df["TerçaPagamento"] != to_br_date(terca_pagto)].copy()

        cache_upd = pd.concat([cache_df[cache_cols], pd.DataFrame(novos_cache)], ignore_index=True)
        _write_df(ABA_COMISSOES_CACHE, cache_upd)

        # 2) Lança em DESPESAS: UMA LINHA POR DIA DO ATENDIMENTO
        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)
        for c in COLS_DESPESAS_FIX:
            if c not in despesas_df.columns:
                despesas_df[c] = ""

        # Junta itens pagáveis com Data do serviço, Competência e valor da comissão
        pagaveis = []
        for df_part in [semana_grid, fiados_grid]:
            if df_part is None or df_part.empty:
                continue
            pagaveis.append(df_part[["Data", "Competência", "ComissaoValor"]].copy())

        if pagaveis:
            pagos = pd.concat(pagaveis, ignore_index=True)

            def _norm_dt(s):
                s = (s or "").strip()
                for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
                    try:
                        return datetime.strptime(s, fmt)
                    except Exception:
                        pass
                return None

            pagos["_dt"] = pagos["Data"].apply(_norm_dt)
            pagos = pagos[pagos["_dt"].notna()].copy()

            por_dia = pagos.groupby(["Data", "Competência"], dropna=False)["ComissaoValor"].sum().reset_index()

            linhas = []
            terca_str_local = to_br_date(terca_pagto)

            for _, row in por_dia.iterrows():
                data_serv = str(row["Data"]).strip()            # dd/mm/aaaa do atendimento
                comp      = str(row["Competência"]).strip()     # mm/aaaa
                val_total = float(row["ComissaoValor"])

                if not dividir_pagamento:
                    linhas.append({
                        "Data": data_serv,
                        "Prestador": "Vinicius",
                        "Descrição": f"{descricao_padrao} — Comp {comp} — Pago em {terca_str_local}",
                        "Valor": f'R$ {val_total:.2f}'.replace(".", ","),
                        "Me Pag:": meio_pag_unico
                    })
                else:
                    # reparte conforme percentuais
                    parts = []
                    for _, r2 in split_df.iterrows():
                        conta = str(r2.get("Me Pag:", "")).strip()
                        pct = float(pd.to_numeric(r2.get("%", 0.0), errors="coerce") or 0.0)
                        if conta and pct > 0:
                            parts.append((conta, pct))
                    # normaliza (por segurança) para somar 100
                    soma_pct = sum(p for _, p in parts) or 1.0
                    parts = [(c, p * 100.0 / soma_pct) for (c, p) in parts]

                    for conta, pct in parts:
                        val = round(val_total * pct / 100.0, 2)
                        if val <= 0:
                            continue
                        linhas.append({
                            "Data": data_serv,
                            "Prestador": "Vinicius",
                            "Descrição": f"{descricao_padrao} — Comp {comp} — Pago em {terca_str_local} — {pct:.1f}%",
                            "Valor": f'R$ {val:.2f}'.replace(".", ","),
                            "Me Pag:": conta
                        })

            despesas_final = pd.concat([despesas_df, pd.DataFrame(linhas)], ignore_index=True)
            colunas_finais = [c for c in COLS_DESPESAS_FIX if c in despesas_final.columns] + \
                             [c for c in despesas_final.columns if c not in COLS_DESPESAS_FIX]
            despesas_final = despesas_final[colunas_finais]
            _write_df(ABA_DESPESAS, despesas_final)

            st.success(
                f"🎉 Comissão registrada! {len(linhas)} linha(s) adicionada(s) em **{ABA_DESPESAS}** "
                f"(uma por DIA do atendimento, divididas por conta) e {len(novos_cache)} itens marcados no **{ABA_COMISSOES_CACHE}**."
            )
            st.balloons()
        else:
            st.warning("Não há valores a lançar em Despesas.")

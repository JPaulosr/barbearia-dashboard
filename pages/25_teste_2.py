# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Pagamento de comissão (linhas por DIA do atendimento)
# - Paga toda terça o período de terça→segunda anterior.
# - Fiado só entra quando DataPagamento <= terça do pagamento.
# - Em Despesas grava UMA LINHA POR DIA DO ATENDIMENTO (Data = data do serviço).
# - Evita duplicidades via sheet "comissoes_cache" com RefID por atendimento.
# - Arredondamento opcional para preço cheio por serviço (tabela) com tolerância.
# - Blocos: NÃO fiado, Fiados liberados, Fiados pendentes (futuro).
# - Telegram: Resumo Resumido (curto) e Detalhado, preview e ping.

import streamlit as st
import pandas as pd
import gspread
import hashlib
import re
import requests
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import pytz
from typing import List

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
# TELEGRAM (secrets ou FALLBACKS)
# =============================
TELEGRAM_TOKEN_FALLBACK = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
CHAT_ID_JP_FALLBACK     = "493747253"
CHAT_ID_VINI_FALLBACK   = "-1002953102982"  # ID real que você mostrou nos updates

TELEGRAM_TOKEN            = st.secrets.get("TELEGRAM_TOKEN", TELEGRAM_TOKEN_FALLBACK)
TELEGRAM_CHAT_ID_VINICIUS = st.secrets.get("TELEGRAM_CHAT_ID_VINICIUS", CHAT_ID_VINI_FALLBACK)
TELEGRAM_CHAT_ID_JPAULO   = st.secrets.get("TELEGRAM_CHAT_ID_JPAULO", CHAT_ID_JP_FALLBACK)

def _tg_send_text(token: str, chat_id: str, text: str, parse_mode: str = "HTML"):
    if not token or not chat_id:
        return (False, None, "Missing token or chat_id")
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url,
            json={
                "chat_id": chat_id,  # pode ser -100... ou @username
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        ok = resp.status_code == 200
        return (ok, resp.status_code, resp.text)
    except Exception as e:
        return (False, None, str(e))

def tg_send_long(token: str, chat_id: str, text: str, parse_mode: str = "HTML", chunk: int = 3800):
    detalhes, ok_all = [], True
    for i in range(0, len(text), chunk):
        part = text[i:i+chunk]
        ok, status, body = _tg_send_text(token, chat_id, part, parse_mode=parse_mode)
        detalhes.append((ok, status, body))
        ok_all = ok_all and ok
    return ok_all, detalhes

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
        return sh.add_worksheet(title=title, rows=2000, cols=50)

def _read_df(title: str) -> pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all").replace({pd.NA: ""})

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
    return dt.strftime("%m/%Y") if dt else ""

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

def garantir_colunas(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for c in cols:
        if c not in df.columns:
            df[c] = ""
    return df

def s_lower(s):
    return s.astype(str).str.strip().str.lower()

def is_cartao(conta: str) -> bool:
    c = (conta or "").strip().lower()
    return bool(re.search(r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos)", c))

def snap_para_preco_cheio(servico: str, valor: float, tol: float, habilitado: bool) -> float:
    if not habilitado:
        return valor
    cheio = VALOR_TABELA.get((servico or "").strip())
    if isinstance(cheio, (int, float)) and abs(valor - float(cheio)) <= tol:
        return float(cheio)
    return valor

def format_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# =============================
# UI — entradas
# =============================
st.set_page_config(layout="wide")
st.title("💈 Pagamento de Comissão — Vinicius (1 linha por DIA do atendimento)")

base = _read_df(ABA_DADOS)
base = garantir_colunas(base, COLS_OFICIAIS).copy()

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

meio_pag = st.selectbox("Meio de pagamento (para DESPESAS)", ["Dinheiro", "Pix", "Cartão", "Transferência"], index=0)
descricao_padrao = st.text_input("Descrição (para DESPESAS)", value="Comissão Vinícius")

usar_tabela_cartao = st.checkbox(
    "Usar preço de TABELA para comissão quando pago no cartão",
    value=True,
    help="Ignora o valor líquido (com taxa) e comissiona pelo preço de tabela do serviço."
)
col_r1, col_r2 = st.columns([2,1])
with col_r1:
    arred_cheio = st.checkbox(
        "Arredondar para preço cheio de TABELA (tolerância abaixo)",
        value=True,
        help="Ex.: 23,00 / 24,75 / 25,10 → 25,00 (se dentro da tolerância)."
    )
with col_r2:
    tol_reais = st.number_input("Tolerância (R$)", value=2.00, step=0.50, min_value=0.0)

reprocessar_terca = st.checkbox(
    "Reprocessar esta terça (regravar): ignorar/limpar cache desta terça antes de salvar",
    value=False
)

enviar_copia_jp = st.checkbox("Enviar cópia do resumo para o JP (privado)", value=False)

# =============================
# Filtragem e janelas
# =============================
dfv = base[s_lower(base["Funcionário"]) == "vinicius"].copy()
if not incluir_produtos:
    dfv = dfv[s_lower(dfv["Tipo"]) == "serviço"]
dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)

ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}** (terça→segunda)")

mask_semana = (
    (dfv["_dt_serv"].notna()) &
    (dfv["_dt_serv"] >= ini) &
    (dfv["_dt_serv"] <= fim) &
    ((s_lower(dfv["StatusFiado"]) == "") | (s_lower(dfv["StatusFiado"]) == "nao"))
)
semana_df = dfv[mask_semana].copy()

df_fiados = dfv[(s_lower(dfv["StatusFiado"]) != "") | (s_lower(dfv["IDLancFiado"]) != "")]
df_fiados["_dt_pagto"] = df_fiados["DataPagamento"].apply(parse_br_date)
fiados_liberados = df_fiados[(df_fiados["_dt_pagto"].notna()) & (df_fiados["_dt_pagto"] <= terca_pagto)].copy()
fiados_pendentes = df_fiados[(df_fiados["_dt_pagto"].isna()) | (df_fiados["_dt_pagto"] > terca_pagto)].copy()

cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID", "PagoEm", "TerçaPagamento", "ValorComissao", "Competencia", "Observacao"]
cache = garantir_colunas(cache, cache_cols)

terca_str = to_br_date(terca_pagto)
if reprocessar_terca:
    ja_pagos = set(cache[cache["TerçaPagamento"] != terca_str]["RefID"].astype(str).tolist())
else:
    ja_pagos = set(cache["RefID"].astype(str).tolist())

def montar_valor_base(df):
    if df.empty:
        df["Valor_num"] = []
        df["Competência"] = []
        df["Valor_base_comissao"] = []
        return df
    df["Valor_num"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
    df["Competência"] = df["Data"].apply(competencia_from_data_str)

    def _base_valor(row):
        serv = str(row.get("Serviço", "")).strip()
        conta = str(row.get("Conta", "")).strip()
        bruto = float(row.get("Valor_num", 0.0))
        if usar_tabela_cartao and is_cartao(conta):
            return float(VALOR_TABELA.get(serv, bruto))
        return snap_para_preco_cheio(serv, bruto, tol_reais, arred_cheio)

    df["Valor_base_comissao"] = df.apply(_base_valor, axis=1)
    return df

# ------- GRADE EDITÁVEL
def preparar_grid(df: pd.DataFrame, titulo: str, key_prefix: str):
    if df.empty:
        st.warning(f"Sem itens em **{titulo}**.")
        return pd.DataFrame(), 0.0
    df = df.copy()
    df["RefID"] = df.apply(make_refid, axis=1)
    df = df[~df["RefID"].isin(ja_pagos)]
    if df.empty:
        st.info(f"Todos os itens de **{titulo}** já foram pagos.")
        return pd.DataFrame(), 0.0

    df = montar_valor_base(df)

    st.subheader(titulo)
    st.caption("Edite a % de comissão por linha, se precisar.")

    ed_cols = ["Data", "Cliente", "Serviço", "Valor_base_comissao", "Competência", "RefID"]
    ed = df[ed_cols].rename(columns={"Valor_base_comissao": "Valor (para comissão)"})
    ed["% Comissão"] = perc_padrao
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

    total = float(edited["Comissão (R$)"].sum())
    merged = df.merge(edited[["RefID", "% Comissão", "Comissão (R$)"]], on="RefID", how="left")
    merged["ComissaoValor"] = pd.to_numeric(merged["Comissão (R$)"], errors="coerce").fillna(0.0)

    st.success(f"Total de comissão em **{titulo}**: {format_brl(total)}")
    return merged, total

semana_grid, total_semana = preparar_grid(semana_df, "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_liberados_grid, total_fiados = preparar_grid(fiados_liberados, "Fiados liberados (pagos até a terça)", "fiados_liberados")

# ------- FIADOS PENDENTES (somente leitura)
st.subheader("📌 Fiados a receber (histórico — ainda NÃO pagos)")
if fiados_pendentes.empty:
    st.info("Nenhum fiado pendente no momento.")
    total_fiados_pend = 0.0
else:
    fiados_pendentes = montar_valor_base(fiados_pendentes)
    vis = fiados_pendentes[["Data", "Cliente", "Serviço", "Valor", "Valor_base_comissao"]].rename(
        columns={"Valor_base_comissao": "Valor (para comissão)"}
    ).copy()
    vis["% Comissão"] = perc_padrao
    vis["Comissão (R$)"] = (pd.to_numeric(vis["Valor (para comissão)"], errors="coerce").fillna(0.0) * vis["% Comissão"] / 100.0).round(2)
    total_fiados_pend = float(vis["Comissão (R$)"].sum())
    st.dataframe(vis.sort_values(by=["Data", "Cliente"]).reset_index(drop=True), use_container_width=True)
    st.warning(f"Comissão futura (quando pagarem): **{format_brl(total_fiados_pend)}**")

# ------- MÉTRICAS
col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1: st.metric("Nesta terça — NÃO fiado", format_brl(total_semana))
with col_m2: st.metric("Nesta terça — fiados liberados", format_brl(total_fiados))
with col_m3: st.metric("Total desta terça", format_brl(total_semana + total_fiados))
with col_m4: st.metric("Fiados pendentes (futuro)", format_brl(total_fiados_pend))

# =============================
# MENSAGENS TELEGRAM (detalhado + resumido)
# =============================
def _fmt_linhas_para_card(df: pd.DataFrame, pct_col: str = "% Comissão") -> List[str]:
    linhas = []
    if df is None or df.empty:
        return linhas
    show = df.copy()
    if "Comissão (R$)" not in show.columns and "ComissaoValor" in show.columns:
        show["Comissão (R$)"] = show["ComissaoValor"]
    if "Valor (para comissão)" not in show.columns and "Valor_base_comissao" in show.columns:
        show["Valor (para comissão)"] = show["Valor_base_comissao"]
    cols_ok = {"Data","Cliente","Serviço","Valor (para comissão)","% Comissão","Comissão (R$)"}
    if not cols_ok.issubset(set(show.columns)):
        return linhas
    for _, r in show.iterrows():
        data = str(r["Data"]).strip()
        cli  = str(r["Cliente"]).strip()
        srv  = str(r["Serviço"]).strip()
        valb = float(pd.to_numeric(r["Valor (para comissão)"], errors="coerce") or 0.0)
        pc   = float(pd.to_numeric(r[pct_col], errors="coerce") or 0.0)
        com  = float(pd.to_numeric(r["Comissão (R$)"], errors="coerce") or 0.0)
        linhas.append(f"• <b>{data}</b> — {cli} — {srv} | Base: {format_brl(valb)} | %: {pc:.1f}% | Comissão: <b>{format_brl(com)}</b>")
    return linhas

def _build_resumo_msg(ini: datetime, fim: datetime,
                      semana_edit: pd.DataFrame, total_sem: float,
                      fiados_edit: pd.DataFrame, total_fia: float,
                      pend_df: pd.DataFrame, total_pend: float) -> str:
    head = (
        f"<b>💈 Comissão — Vinícius</b>\n"
        f"Janela: <b>{to_br_date(ini)} → {to_br_date(fim)}</b>\n"
        f"Gerado em: {to_br_date(br_now())}\n\n"
    )
    bloco_sem = "<u>✅ Não fiado (terça→segunda)</u>\n"
    linhas_sem = _fmt_linhas_para_card(semana_edit)
    bloco_sem += ("\n".join(linhas_sem) if linhas_sem else "— Sem itens\n")
    bloco_sem += f"\n<b>Total não fiado:</b> {format_brl(total_sem)}\n\n"

    bloco_fia = "<u>💸 Fiados liberados (pagos até a terça)</u>\n"
    linhas_fia = _fmt_linhas_para_card(fiados_edit)
    bloco_fia += ("\n".join(linhas_fia) if linhas_fia else "— Sem itens\n")
    bloco_fia += f"\n<b>Total fiados liberados:</b> {format_brl(total_fia)}\n\n"

    bloco_pend = "<u>🕒 Fiados pendentes (a receber)</u>\n"
    if pend_df is not None and not pend_df.empty:
        vis = pend_df[["Data","Cliente","Serviço","Valor_base_comissao"]].copy()
        for _, r in vis.sort_values(by=["Data","Cliente"]).iterrows():
            bloco_pend += f"• <b>{str(r['Data']).strip()}</b> — {str(r['Cliente']).strip()} — {str(r['Serviço']).strip()} | Base: {format_brl(float(r['Valor_base_comissao']))}\n"
    else:
        bloco_pend += "— Nenhum fiado pendente\n"
    bloco_pend += f"\n<b>Comissão futura estimada:</b> {format_brl(total_pend)}\n\n"

    total_hoje = total_sem + total_fia
    rodape = f"🧾 <b>Total a receber nesta terça:</b> {format_brl(total_hoje)}"
    return head + bloco_sem + bloco_fia + bloco_pend + rodape

# ---- RESUMIDO (curto)
def _contagem_servicos(df: pd.DataFrame) -> str:
    if df is None or df.empty or "Serviço" not in df.columns:
        return "—"
    cont = df["Serviço"].astype(str).str.strip().value_counts()
    return ", ".join([f"{s}×{int(q)}" for s, q in cont.items()]) if not cont.empty else "—"

def _somar_base_para_comissao(df: pd.DataFrame) -> float:
    if df is None or df.empty:
        return 0.0
    if "Valor (para comissão)" in df.columns:
        base = pd.to_numeric(df["Valor (para comissão)"], errors="coerce").fillna(0)
    elif "Valor_base_comissao" in df.columns:
        base = pd.to_numeric(df["Valor_base_comissao"], errors="coerce").fillna(0)
    else:
        return 0.0
    return float(base.sum())

def _clientes_unicos(*dfs: pd.DataFrame) -> int:
    vals = []
    for d in dfs:
        if d is not None and not d.empty and "Cliente" in d.columns:
            vals.extend(d["Cliente"].astype(str).str.strip().tolist())
    return len(pd.Series(vals).dropna().unique())

def _build_resumo_msg_resumido(ini: datetime, fim: datetime,
                               semana_edit: pd.DataFrame, total_sem: float,
                               fiados_edit: pd.DataFrame, total_fia: float,
                               pend_df: pd.DataFrame, total_pend: float) -> str:
    a = semana_edit if semana_edit is not None else pd.DataFrame()
    b = fiados_edit if fiados_edit is not None else pd.DataFrame()
    juntos = pd.concat([a, b], ignore_index=True) if (not a.empty or not b.empty) else a

    clientes   = _clientes_unicos(semana_edit, fiados_edit)
    servicos   = _contagem_servicos(juntos)
    base_total = _somar_base_para_comissao(semana_edit) + _somar_base_para_comissao(fiados_edit)
    com_total  = float(total_sem + total_fia)

    linhas = [
        f"<b>💈 Resumo — Vinícius</b>  ({to_br_date(ini)} → {to_br_date(fim)})",
        f"👥 Clientes: <b>{clientes}</b>",
        f"✂️ Serviços: {servicos}",
        f"💵 Base p/ comissão: <b>{format_brl(base_total)}</b>",
        f"🧾 Comissão de hoje: <b>{format_brl(com_total)}</b>",
    ]
    if total_pend > 0:
        linhas.append(f"🕒 Comissão futura (fiados pendentes): <b>{format_brl(total_pend)}</b>")
    return "\n".join(linhas)

# =============================
# TELEGRAM — preview e botões
# =============================
st.divider()
formato_resumo = st.radio("Formato do resumo", ["Resumido", "Detalhado"], index=0, horizontal=True)

# Garante base calculada para pendentes
pend_ok = fiados_pendentes if 'Valor_base_comissao' in fiados_pendentes.columns else montar_valor_base(fiados_pendentes)

# Pré-visualização
if formato_resumo == "Resumido":
    msg_preview = _build_resumo_msg_resumido(
        ini, fim, semana_grid, total_semana, fiados_liberados_grid, total_fiados, pend_ok, total_fiados_pend
    )
else:
    msg_preview = _build_resumo_msg(
        ini, fim, semana_grid, total_semana, fiados_liberados_grid, total_fiados, pend_ok, total_fiados_pend
    )

st.caption("Pré‑visualização do texto que será enviado:")
st.code(msg_preview, language="html")

col_tg1, col_tg2, col_tg3 = st.columns([1,1,1])

with col_tg1:
    if st.button("📢 Enviar RESUMO (curto)"):
        msg = _build_resumo_msg_resumido(
            ini, fim, semana_grid, total_semana, fiados_liberados_grid, total_fiados, pend_ok, total_fiados_pend
        )
        ok_v, det_v = tg_send_long(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID_VINICIUS, msg, parse_mode="HTML")
        if enviar_copia_jp:
            tg_send_long(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID_JPAULO, msg, parse_mode="HTML")
        st.success("Resumo (curto) enviado ✅") if ok_v else st.error(det_v)

with col_tg2:
    if st.button("📢 Enviar (formato escolhido)"):
        msg = msg_preview
        ok_v, det_v = tg_send_long(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID_VINICIUS, msg, parse_mode="HTML")
        if enviar_copia_jp:
            tg_send_long(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID_JPAULO, msg, parse_mode="HTML")
        st.success("Resumo enviado ✅") if ok_v else st.error(det_v)

with col_tg3:
    if st.button("🔔 Ping Telegram"):
        ok, status, body = _tg_send_text(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID_VINICIUS, "Ping de teste ✅")
        st.success("Ping OK") if ok else st.error({"status": status, "resp": body})

# =============================
# CONFIRMAR E GRAVAR
# =============================
if st.button("✅ Registrar comissão (por DIA do atendimento) e marcar itens como pagos"):
    if (semana_grid is None or semana_grid.empty) and (fiados_liberados_grid is None or fiados_liberados_grid.empty):
        st.warning("Não há itens para pagar.")
    else:
        novos_cache = []
        for df_part in [semana_grid, fiados_liberados_grid]:
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
        cache_df = garantir_colunas(cache_df, cache_cols)

        if reprocessar_terca:
            cache_df = cache_df[cache_df["TerçaPagamento"] != to_br_date(terca_pagto)].copy()

        cache_upd = pd.concat([cache_df[cache_cols], pd.DataFrame(novos_cache)], ignore_index=True)
        _write_df(ABA_COMISSOES_CACHE, cache_upd)

        despesas_df = _read_df(ABA_DESPESAS)
        despesas_df = garantir_colunas(despesas_df, COLS_DESPESAS_FIX)
        for c in COLS_DESPESAS_FIX:
            if c not in despesas_df.columns:
                despesas_df[c] = ""

        pagaveis = []
        for df_part in [semana_grid, fiados_liberados_grid]:
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
            for _, row in por_dia.iterrows():
                data_serv = str(row["Data"]).strip()
                comp      = str(row["Competência"]).strip()
                val       = float(row["ComissaoValor"])
                linhas.append({
                    "Data": data_serv,
                    "Prestador": "Vinicius",
                    "Descrição": f"{descricao_padrao} — Comp {comp} — Pago em {to_br_date(terca_pagto)}",
                    "Valor": f'R$ {val:.2f}'.replace(".", ","),
                    "Me Pag:": meio_pag
                })

            despesas_final = pd.concat([despesas_df, pd.DataFrame(linhas)], ignore_index=True)
            colunas_finais = [c for c in COLS_DESPESAS_FIX if c in despesas_final.columns] + \
                             [c for c in despesas_final.columns if c not in COLS_DESPESAS_FIX]
            despesas_final = despesas_final[colunas_finais]
            _write_df(ABA_DESPESAS, despesas_final)

            st.success(
                f"🎉 Comissão registrada! {len(linhas)} linha(s) adicionada(s) em **{ABA_DESPESAS}** "
                f"(uma por DIA do atendimento) e {len(novos_cache)} itens marcados no **{ABA_COMISSOES_CACHE}**."
            )
            st.balloons()
        else:
            st.warning("Não há valores a lançar em Despesas.")

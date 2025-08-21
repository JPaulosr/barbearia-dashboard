# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Pagamento de comissão (linhas por DIA do atendimento)
# - Paga toda terça o período de terça→segunda anterior.
# - Fiado só entra quando DataPagamento <= terça do pagamento.
# - Em Despesas grava UMA LINHA POR DIA DO ATENDIMENTO (Data = data do serviço).
# - Evita duplicidades via sheet "comissoes_cache" com RefID por atendimento.
# - Preço de TABELA para cartão (opcional) e arredondamento com tolerância.
# - Caixinha NÃO entra na comissão; pode ser paga junto (opção).
# - Envia resumo no Telegram no formato do exemplo (clientes, serviços, totais).

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

# =============================
# CONFIG BÁSICA
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_COMISSOES_CACHE = "comissoes_cache"
ABA_DESPESAS = "Despesas"

TZ = "America/Sao_Paulo"

# Telegram fallbacks (serão substituídos por st.secrets, se existirem)
TG_TOKEN_FALLBACK = "SEU_TOKEN_AQUI"
TG_CHAT_JPAULO_FALLBACK = "SEU_CHATID_PESSOAL"
TG_CHAT_VINICIUS_FALLBACK = "SEU_CHATID_VINICIUS_OU_CANAL"

# Colunas existentes na planilha (inclui extras + caixinhas)
COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período",
    # Fiado
    "StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento",
    # Extras cartão / meta-dados
    "ValorBrutoRecebido", "ValorLiquidoRecebido",
    "TaxaCartaoValor", "TaxaCartaoPct",
    "FormaPagDetalhe", "PagamentoID",
    # Caixinhas
    "CaixinhaDia", "CaixinhaFundo",
]

# Colunas da aba Despesas
COLS_DESPESAS_FIX = ["Data", "Prestador", "Descrição", "Valor", "Me Pag:"]

# Percentual padrão da comissão
PERCENTUAL_PADRAO = 50.0

# Tabela de preços (valores cheios por serviço)
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

def _read_df(title: str) -> pd.DataFrame:
    ws = _ws(title)
    df = get_as_dataframe(ws).fillna("")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.dropna(how="all").replace({pd.NA: ""})
    for c in COLS_OFICIAIS:
        if c not in df.columns:
            df[c] = ""
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

def s_lower(s: pd.Series):
    return s.astype(str).str.strip().str.lower()

def is_cartao(conta: str) -> bool:
    c = (conta or "").strip().lower()
    padrao = r"(cart|cart[ãa]o|cr[eé]dito|d[eé]bito|maquin|pos|pagseguro|mercado\s*pago|sumup|cielo|stone|getnet|nubank)"
    return bool(re.search(padrao, c))

def _to_float_brl(v) -> float:
    """Converte 'R$ 10,00'/'10,00'/'10.00' para 10.0. Vazio/erro -> 0.0"""
    s = str(v).strip()
    if not s:
        return 0.0
    s = s.replace("R$", "").replace(" ", "")
    s = re.sub(r"\.(?=\d{3}(\D|$))", "", s)  # milhar
    s = s.replace(",", ".")
    try:
        return float(s)
    except:
        return 0.0

def snap_para_preco_cheio(servico: str, valor: float, tol: float, habilitado: bool) -> float:
    if not habilitado:
        return valor
    cheio = VALOR_TABELA.get((servico or "").strip())
    if isinstance(cheio, (int, float)) and abs(valor - float(cheio)) <= tol:
        return float(cheio)
    return valor

def format_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ---- Telegram helpers ----
def _get_telegram_creds():
    token = TG_TOKEN_FALLBACK
    chat_jp = TG_CHAT_JPAULO_FALLBACK
    chat_vn = TG_CHAT_VINICIUS_FALLBACK
    try:
        tg = st.secrets.get("TELEGRAM", {})
        token = tg.get("TOKEN", token)
        chat_jp = tg.get("CHAT_ID_JPAULO", chat_jp)
        chat_vn = tg.get("CHAT_ID_VINICIUS", chat_vn)
    except Exception:
        pass
    return token, chat_jp, chat_vn

def tg_send_text(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "disable_web_page_preview": True}, timeout=15)
        if not (r.status_code == 200 and r.json().get("ok", False)):
            st.warning(f"Telegram falhou para {chat_id}: {r.text[:200]}")
    except Exception as e:
        st.warning(f"Erro Telegram para {chat_id}: {e}")

def contar_clientes_e_servicos(df_list):
    """Recebe [semana_df, fiados_liberados] e devolve (num_clientes, dict_servicos)."""
    if not any(d is not None and not d.empty for d in df_list):
        return 0, {}
    df_all = pd.concat([d for d in df_list if d is not None and not d.empty], ignore_index=True)
    num_clientes = df_all["Cliente"].astype(str).str.strip().str.lower().nunique() if "Cliente" in df_all.columns else 0
    serv_counts = (df_all["Serviço"].astype(str).str.strip().value_counts().to_dict()) if "Serviço" in df_all.columns else {}
    return num_clientes, serv_counts

def build_text_resumo(period_ini, period_fim, total_comissao_hoje, total_futuros, pagar_caixinha, total_cx, df_semana, df_fiados):
    clientes, servs = contar_clientes_e_servicos([df_semana, df_fiados])
    serv_lin = ", ".join([f"{k}×{v}" for k, v in servs.items()]) if servs else "—"
    linhas = []
    linhas.append(f"💈 Resumo — Vinícius  ({to_br_date(period_ini)} → {to_br_date(period_fim)})")
    linhas.append(f"👥 Clientes: {clientes}")
    linhas.append(f"✂️ Serviços: {serv_lin}")
    linhas.append(f"🧾 Comissão de hoje: {format_brl(total_comissao_hoje)}")
    if pagar_caixinha and total_cx > 0:
        linhas.append(f"🎁 Caixinha de hoje: {format_brl(total_cx)}")
        linhas.append(f"💵 Total GERAL pago hoje: {format_brl(total_comissao_hoje + total_cx)}")
    linhas.append(f"🕒 Comissão futura (fiados pendentes): {format_brl(total_futuros)}")
    return "\n".join(linhas)

# =============================
# UI
# =============================
st.set_page_config(layout="wide")
st.title("💈 Pagamento de Comissão — Vinicius (1 linha por DIA do atendimento)")

# Carrega base
base = _read_df(ABA_DADOS).copy()

# Inputs (linha 1)
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

# Inputs (linha 2)
meio_pag = st.selectbox("Meio de pagamento (para DESPESAS — comissão)", ["Dinheiro", "Pix", "Cartão", "Transferência"], index=0)
descricao_padrao = st.text_input("Descrição (para DESPESAS — comissão)", value="Comissão Vinícius")

# Inputs (linha 3) — regras de cálculo
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

# ⚙️ Opções da CAIXINHA & Telegram
st.markdown("### 🎁 Caixinha & 📲 Telegram")
pagar_caixinha = st.checkbox("Pagar caixinha nesta terça (lançar em Despesas por DIA)", value=True)
meio_pag_cx = st.selectbox(
    "Meio de pagamento (para DESPESAS — caixinha)",
    ["Dinheiro", "Pix", "Cartão", "Transferência"],
    index=["Dinheiro", "Pix", "Cartão", "Transferência"].index(meio_pag) if meio_pag in ["Dinheiro","Pix","Cartão","Transferência"] else 0
)
descricao_cx = st.text_input("Descrição (para DESPESAS — caixinha)", value="Caixinha Vinícius")

enviar_tg = st.checkbox("Enviar resumo no Telegram ao registrar", value=True)
dest_vini = st.checkbox("Enviar para canal do Vinícius", value=True)
dest_jp = st.checkbox("Enviar cópia para JPaulo (privado)", value=True)

# ✅ Reprocessar esta terça (limpa/ignora cache desta terça)
reprocessar_terca = st.checkbox(
    "Reprocessar esta terça (regravar): ignorar/limpar cache desta terça antes de salvar",
    value=False,
    help="Marque se você apagou as linhas em Despesas e quer gravar novamente esta terça."
)

# ============ Pré-filtros ============
dfv = base[s_lower(base["Funcionário"]) == "vinicius"].copy()
if not incluir_produtos:
    dfv = dfv[s_lower(dfv["Tipo"]) == "serviço"]

# EXCLUIR linhas de 'caixinha' da comissão
mask_caixinha_lanc = (
    (s_lower(dfv["Conta"]) == "caixinha") |
    (s_lower(dfv["Tipo"]) == "caixinha") |
    (s_lower(dfv["Serviço"]) == "caixinha")
)
dfv = dfv[~mask_caixinha_lanc].copy()

dfv["_dt_serv"] = dfv["Data"].apply(parse_br_date)
dfv["_dt_pagto"] = dfv["DataPagamento"].apply(parse_br_date)

# Janela terça→segunda (anterior à terça de pagamento)
ini, fim = janela_terca_a_segunda(terca_pagto)
st.info(f"Janela desta folha: **{to_br_date(ini)} a {to_br_date(fim)}** (terça→segunda)")

# -------- CAIXINHA (exibição + base para pagar) --------
base["_dt_serv"] = base["Data"].apply(parse_br_date)
mask_vini = s_lower(base["Funcionário"]) == "vinicius"
mask_janela = base["_dt_serv"].notna() & (base["_dt_serv"] >= ini) & (base["_dt_serv"] <= fim)
base_jan_vini = base[mask_vini & mask_janela].copy()

base_jan_vini["CaixinhaDia_num"] = base_jan_vini["CaixinhaDia"].apply(_to_float_brl)
base_jan_vini["CaixinhaFundo_num"] = base_jan_vini["CaixinhaFundo"].apply(_to_float_brl)

mask_caixinha_rows_all = (
    (s_lower(base_jan_vini["Conta"]) == "caixinha") |
    (s_lower(base_jan_vini["Tipo"]) == "caixinha") |
    (s_lower(base_jan_vini["Serviço"]) == "caixinha")
)
base_jan_vini["CaixinhaRow_num"] = 0.0
if mask_caixinha_rows_all.any():
    base_jan_vini.loc[mask_caixinha_rows_all, "CaixinhaRow_num"] = base_jan_vini.loc[mask_caixinha_rows_all, "Valor"].apply(_to_float_brl)

total_cx_dia_cols = float(base_jan_vini["CaixinhaDia_num"].sum())
total_cx_fundo_cols = float(base_jan_vini["CaixinhaFundo_num"].sum())
total_cx_rows = float(base_jan_vini["CaixinhaRow_num"].sum())
total_caixinha = total_cx_dia_cols + total_cx_fundo_cols + total_cx_rows

cx1, cx2, cx3 = st.columns(3)
with cx1:
    st.metric("🎁 Caixinha do Dia (janela)", format_brl(total_cx_dia_cols))
with cx2:
    st.metric("🎁 Caixinha do Fundo (janela)", format_brl(total_cx_fundo_cols))
with cx3:
    st.metric("🎁 Caixinha total (janela)", format_brl(total_caixinha))

mostrar_det = st.checkbox("Mostrar detalhes da caixinha na janela (tabela)", value=False)
if mostrar_det:
    det_cols = ["Data", "Cliente", "Serviço", "Conta", "Tipo", "CaixinhaDia", "CaixinhaFundo", "Valor"]
    has_cols = (base_jan_vini["CaixinhaDia_num"] > 0) | (base_jan_vini["CaixinhaFundo_num"] > 0)
    det_df = base_jan_vini.loc[has_cols | mask_caixinha_rows_all, det_cols].copy()
    st.dataframe(det_df.reset_index(drop=True), use_container_width=True)

# -------- CONTADORES/DEBUG --------
total_linhas_vini = len(dfv)
na_janela = dfv[(dfv["_dt_serv"].notna()) & (dfv["_dt_serv"] >= ini) & (dfv["_dt_serv"] <= fim)]
nao_fiado = na_janela[(s_lower(na_janela["StatusFiado"]) == "") | (s_lower(na_janela["StatusFiado"]) == "nao")]
fiado_all = dfv[(s_lower(dfv["StatusFiado"]) != "") | (s_lower(dfv["IDLancFiado"]) != "")]
fiados_ok = fiado_all[(fiado_all["_dt_pagto"].notna()) & (fiado_all["_dt_pagto"] <= terca_pagto)]
fiados_pend_all = fiado_all[(fiado_all["_dt_pagto"].isna()) | (fiado_all["_dt_pagto"] > terca_pagto)]

st.caption(
    f"Linhas do Vinicius na base (já sem 'caixinha' para comissão): {total_linhas_vini} "
    f"| Na janela (não fiado): {len(nao_fiado)} "
    f"| Fiados liberados até a terça: {len(fiados_ok)} "
    f"| Fiados pendentes: {len(fiados_pend_all)}"
)

# 1) Itens da SEMANA NÃO FIADO
mask_semana = (
    (dfv["_dt_serv"].notna()) &
    (dfv["_dt_serv"] >= ini) &
    (dfv["_dt_serv"] <= fim) &
    ((s_lower(dfv["StatusFiado"]) == "") | (s_lower(dfv["StatusFiado"]) == "nao"))
)
semana_df = dfv[mask_semana].copy()

# 2) Fiados liberados até a terça (independe da data do serviço)
fiados_liberados = fiado_all[(fiado_all["_dt_pagto"].notna()) & (fiado_all["_dt_pagto"] <= terca_pagto)].copy()

# 3) Fiados pendentes (histórico, ainda não pagos)
fiados_pendentes = fiado_all[(fiado_all["_dt_pagto"].isna()) | (fiado_all["_dt_pagto"] > terca_pagto)].copy()

# Cache de comissões já pagas (por RefID)
cache = _read_df(ABA_COMISSOES_CACHE)
cache_cols = ["RefID", "PagoEm", "TerçaPagamento", "ValorComissao", "Competencia", "Observacao"]
cache = garantir_colunas(cache, cache_cols)

terca_str = to_br_date(terca_pagto)
if reprocessar_terca:
    ja_pagos = set(cache[cache["TerçaPagamento"] != terca_str]["RefID"].astype(str).tolist())
else:
    ja_pagos = set(cache["RefID"].astype(str).tolist())

# Função base de cálculo da comissão
def montar_valor_base(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df.assign(Valor_num=[], Competência=[], Valor_base_comissao=[])
    df = df.copy()
    df["Valor_num"] = pd.to_numeric(df["Valor"].apply(_to_float_brl), errors="coerce").fillna(0.0)
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

# ------- GRADE EDITÁVEL -------
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
    ed["% Comissão"] = float(perc_padrao)
    ed["Comissão (R$)"] = (pd.to_numeric(ed["Valor (para comissão)"], errors="coerce").fillna(0.0) *
                           pd.to_numeric(ed["% Comissão"], errors="coerce").fillna(0.0) / 100.0).round(2)
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

    st.success(f"Total de comissão em **{titulo}**: {format_brl(total)}")
    return merged, total

semana_grid, total_semana = preparar_grid(semana_df, "Semana (terça→segunda) — NÃO FIADO", "semana")
fiados_liberados_grid, total_fiados = preparar_grid(fiados_liberados, "Fiados liberados (pagos até a terça)", "fiados_liberados")

# ------- FIADOS A RECEBER (somente leitura) -------
st.subheader("📌 Fiados a receber (histórico — ainda NÃO pagos)")
if fiados_pendentes.empty:
    st.info("Nenhum fiado pendente no momento.")
    total_fiados_pend = 0.0
else:
    vis = montar_valor_base(fiados_pendentes)[["Data", "Cliente", "Serviço", "Valor", "Valor_base_comissao"]].rename(
        columns={"Valor": "Valor original", "Valor_base_comissao": "Valor (para comissão)"}
    ).copy()
    vis["% Comissão"] = float(perc_padrao)
    vis["Comissão (R$)"] = (
        pd.to_numeric(vis["Valor (para comissão)"], errors="coerce").fillna(0.0) *
        pd.to_numeric(vis["% Comissão"], errors="coerce").fillna(0.0) / 100.0
    ).round(2)
    total_fiados_pend = float(vis["Comissão (R$)"].sum())

    st.dataframe(
        vis.sort_values(by=["Data", "Cliente"]).reset_index(drop=True),
        use_container_width=True
    )
    st.warning(f"Comissão futura (quando pagarem): **{format_brl(total_fiados_pend)}**")

# ------- RESUMO DE MÉTRICAS (com fiados e total geral) -------
total_comissao_hoje = float(total_semana + total_fiados)
total_geral_hoje = float(total_comissao_hoje + (total_caixinha if pagar_caixinha else 0.0))

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
with col_m1:
    st.metric("Nesta terça — NÃO fiado", format_brl(total_semana))
with col_m2:
    st.metric("Nesta terça — fiados liberados (a pagar)", format_brl(total_fiados))
with col_m3:
    st.metric("Total desta terça (comissão)", format_brl(total_comissao_hoje))
with col_m4:
    st.metric("Caixinha (se marcado)", format_brl(total_caixinha))

st.subheader("💵 Total GERAL a pagar nesta terça")
st.success(f"**{format_brl(total_geral_hoje)}**  "
           f"{'(inclui caixinha)' if pagar_caixinha and total_caixinha>0 else '(sem caixinha)'}")

# =============================
# CONFIRMAR E GRAVAR
# =============================
if st.button("✅ Registrar comissão (por DIA do atendimento) e marcar itens como pagos"):
    if (semana_grid is None or semana_grid.empty) and (fiados_liberados_grid is None or fiados_liberados_grid.empty) and not (pagar_caixinha and total_caixinha > 0):
        st.warning("Não há itens para pagar.")
    else:
        # 1) Atualiza cache (comissão)
        novos_cache = []
        for df_part in [semana_grid, fiados_liberados_grid]:
            if df_part is None or df_part.empty:
                continue
            for _, r in df_part.iterrows():
                novos_cache.append({
                    "RefID": r["RefID"],
                    "PagoEm": to_br_date(br_now()),
                    "TerçaPagamento": to_br_date(terca_pagto),
                    "ValorComissao": f'{float(r["ComissaoValor"]):.2f}'.replace(".", ","),
                    "Competencia": r.get("Competência", ""),
                    "Observacao": f'{r.get("Cliente","")} | {r.get("Serviço","")} | {r.get("Data","")}',
                })

        cache_df = _read_df(ABA_COMISSOES_CACHE)
        cache_df = garantir_colunas(cache_df, cache_cols)

        if reprocessar_terca:
            cache_df = cache_df[cache_df["TerçaPagamento"] != to_br_date(terca_pagto)].copy()

        cache_upd = pd.concat([cache_df[cache_cols], pd.DataFrame(novos_cache)], ignore_index=True)
        _write_df(ABA_COMISSOES_CACHE, cache_upd)

        # 2) Lança em DESPESAS: UMA LINHA POR DIA DO ATENDIMENTO (comissão)
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

        linhas = []
        linhas_comissao = 0
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
            linhas_comissao = len(por_dia)

        # 3) Caixinha por dia (se marcado)
        linhas_caixinha = 0
        if pagar_caixinha and total_caixinha > 0:
            base_cx = base_jan_vini.copy()
            base_cx["ValorCxTotal"] = base_cx["CaixinhaDia_num"] + base_cx["CaixinhaFundo_num"] + base_cx["CaixinhaRow_num"]
            cx_por_dia = base_cx.groupby("Data", dropna=False)["ValorCxTotal"].sum().reset_index()
            for _, row in cx_por_dia.iterrows():
                data_serv = str(row["Data"]).strip()
                val_cx    = float(row["ValorCxTotal"])
                if val_cx <= 0:
                    continue
                linhas.append({
                    "Data": data_serv,
                    "Prestador": "Vinicius",
                    "Descrição": f"{descricao_cx} — Pago em {to_br_date(terca_pagto)}",
                    "Valor": f'R$ {val_cx:.2f}'.replace(".", ","),
                    "Me Pag:": meio_pag_cx
                })
            linhas_caixinha = (cx_por_dia["ValorCxTotal"] > 0).sum()

        # Grava DESPESAS
        if linhas:
            despesas_final = pd.concat([despesas_df, pd.DataFrame(linhas)], ignore_index=True)
            colunas_finais = [c for c in COLS_DESPESAS_FIX if c in despesas_final.columns] + \
                             [c for c in despesas_final.columns if c not in COLS_DESPESAS_FIX]
            despesas_final = despesas_final[colunas_finais]
            _write_df(ABA_DESPESAS, despesas_final)

            # ======= Enviar Telegram (opcional) =======
            if enviar_tg:
                token, chat_jp, chat_vn = _get_telegram_creds()
                texto = build_text_resumo(
                    period_ini=ini, period_fim=fim,
                    total_comissao_hoje=float(total_comissao_hoje),
                    total_futuros=float(total_fiados_pend),
                    pagar_caixinha=bool(pagar_caixinha),
                    total_cx=float(total_caixinha if pagar_caixinha else 0.0),
                    df_semana=semana_df, df_fiados=fiados_liberados
                )
                if dest_vini:
                    tg_send_text(token, chat_vn, texto)
                if dest_jp:
                    tg_send_text(token, chat_jp, texto)

            st.success(
                f"🎉 Pagamento registrado!\n"
                f"- Comissão: {linhas_comissao} linha(s) em **{ABA_DESPESAS}**\n"
                f"- Caixinha: {linhas_caixinha} linha(s) em **{ABA_DESPESAS}**\n"
                f"Itens marcados no **{ABA_COMISSOES_CACHE}**: {len(novos_cache)}"
            )
            st.balloons()
        else:
            st.warning("Não há valores a lançar em Despesas.")

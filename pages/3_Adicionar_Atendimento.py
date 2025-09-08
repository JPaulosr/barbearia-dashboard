# -*- coding: utf-8 -*-
# 11_Adicionar_Atendimento.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from gspread.utils import rowcol_to_a1
from datetime import datetime, date
import pytz
import unicodedata
import requests

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
STATUS_ABA = "clientes_status"
FOTO_COL_CANDIDATES = ["link_foto", "foto", "imagem", "url_foto", "foto_link", "link", "image"]

TZ = "America/Sao_Paulo"
DATA_FMT = "%d/%m/%Y"

COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período"
]
COLS_FIADO = ["StatusFiado", "IDLancFiado", "VencimentoFiado", "DataPagamento"]
COLS_PAG_EXTRAS = [
    "ValorBrutoRecebido", "ValorLiquidoRecebido",
    "TaxaCartaoValor", "TaxaCartaoPct",
    "FormaPagDetalhe", "PagamentoID"
]
COLS_CAIXINHAS = ["CaixinhaDia"]

# Comissão padrão do Vinicius
PCT_COMISSAO_VINI_DEFAULT = 0.50  # 50%

# Valores padrão para campos obrigatórios
FASE_PADRAO = "Dono + funcionário"
TIPO_PADRAO = "Serviço"

# =========================
# UTILS
# =========================
def today_local() -> date:
    return datetime.now(pytz.timezone(TZ)).date()

def gerar_id_fiado() -> str:
    return f"L-{datetime.now(pytz.timezone(TZ)).strftime('%Y%m%d%H%M%S%f')[:-3]}"

def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def _norm_key(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s).strip()).casefold()

def _cap_first(s: str) -> str:
    return (str(s).strip().lower().capitalize()) if s is not None else ""

def contains_cartao(s: str) -> bool:
    MAQ = {
        "cart", "cartao", "cartão", "credito", "crédito",
        "debito", "débito", "maquina", "maquininha", "maquineta", "pos",
        "pagseguro", "mercadopago", "mercado pago", "sumup", "stone", "cielo",
        "rede", "getnet", "safra", "visa", "master", "maestro", "elo",
        "hiper", "amex", "nubank", "nubank cnpj"
    }
    x = unicodedata.normalize("NFKD", (s or "")).encode("ascii", "ignore").decode("ascii")
    x = x.lower().replace(" ", "")
    return any(k in x for k in MAQ)

def is_nao_cartao(conta: str) -> bool:
    s = unicodedata.normalize("NFKD", (conta or "")).encode("ascii","ignore").decode("ascii").lower()
    tokens = {"pix", "dinheiro", "carteira", "cash", "especie", "espécie", "transfer", "transferencia", "transferência", "ted", "doc"}
    return any(t in s for t in tokens)

def default_card_flag(conta: str) -> bool:
    s = unicodedata.normalize("NFKD", (conta or "")).encode("ascii","ignore").decode("ascii").lower().replace(" ", "")
    if "nubankcnpj" in s:
        return False
    if is_nao_cartao(conta):
        return False
    return contains_cartao(conta)

def gerar_pag_id(prefixo="A"):
    return f"{prefixo}-{datetime.now(pytz.timezone(TZ)).strftime('%Y%m%d%H%M%S%f')[:-3]}"

def _fmt_brl(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# =========================
# SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def ler_cabecalho(aba):
    try:
        headers = aba.row_values(1)
        return [h.strip() for h in headers] if headers else []
    except Exception:
        return []

def _cmap(ws):
    headers = ler_cabecalho(ws)
    cmap = {}
    for i, h in enumerate(headers):
        k = _norm_key(h)
        if k and k not in cmap:
            cmap[k] = i + 1
    return cmap

def format_extras_numeric(ws):
    cmap = _cmap(ws)
    def fmt(name, ntype, pattern):
        c = cmap.get(_norm_key(name))
        if not c: return
        a1_from = rowcol_to_a1(2, c)
        a1_to = rowcol_to_a1(50000, c)
        try:
            ws.format(f"{a1_from}:{a1_to}", {"numberFormat": {"type": ntype, "pattern": pattern}})
        except Exception:
            pass
    fmt("ValorBrutoRecebido", "NUMBER", "0.00")
    fmt("ValorLiquidoRecebido", "NUMBER", "0.00")
    fmt("TaxaCartaoValor", "NUMBER", "0.00")
    fmt("TaxaCartaoPct", "PERCENT", "0.00%")

def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]
    for c in [*COLS_OFICIAIS, *COLS_FIADO, *COLS_PAG_EXTRAS, *COLS_CAIXINHAS]:
        if c not in df.columns:
            df[c] = ""
    norm = {"manha": "Manhã", "Manha": "Manhã", "manha ": "Manhã", "tarde": "Tarde", "noite": "Noite"}
    df["Período"] = df["Período"].astype(str).str.strip().replace(norm)
    df.loc[~df["Período"].isin(["Manhã", "Tarde", "Noite"]), "Período"] = ""
    df["Combo"] = df["Combo"].fillna("")
    return df, aba

def salvar_base(df_final: pd.DataFrame):
    aba = conectar_sheets().worksheet(ABA_DADOS)
    headers_existentes = ler_cabecalho(aba) or [*COLS_OFICIAIS, *COLS_FIADO, *COLS_PAG_EXTRAS, *COLS_CAIXINHAS]
    colunas_alvo = list(dict.fromkeys([*headers_existentes, *COLS_OFICIAIS, *COLS_FIADO, *COLS_PAG_EXTRAS, *COLS_CAIXINHAS]))
    for c in colunas_alvo:
        if c not in df_final.columns:
            df_final[c] = ""
    df_final = df_final[colunas_alvo]
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)
    try:
        format_extras_numeric(aba)
    except Exception:
        pass

# =========================
# FOTOS (status sheet)
# =========================
@st.cache_data(show_spinner=False)
def carregar_fotos_mapa():
    try:
        sh = conectar_sheets()
        if STATUS_ABA not in [w.title for w in sh.worksheets()]:
            return {}
        ws = sh.worksheet(STATUS_ABA)
        df = get_as_dataframe(ws).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        df = df.loc[:, ~pd.Index(df.columns).duplicated(keep="first")]
        cols_lower = {c.lower(): c for c in df.columns}
        foto_col = next((cols_lower[c] for c in FOTO_COL_CANDIDATES if c in cols_lower), None)
        cli_col = next((cols_lower[c] for c in ["cliente", "nome", "nome_cliente"] if c in cols_lower), None)
        if not (foto_col and cli_col): return {}
        tmp = df[[cli_col, foto_col]].copy()
        tmp.columns = ["Cliente", "Foto"]
        tmp["k"] = tmp["Cliente"].astype(str).map(_norm)
        return {r["k"]: str(r["Foto"]).strip() for _, r in tmp.iterrows() if str(r["Foto"]).strip()}
    except Exception:
        return {}
FOTOS = carregar_fotos_mapa()

def get_foto_url(nome: str) -> str | None:
    if not nome:
        return None
    url = FOTOS.get(_norm(nome))
    return url if (url and url.strip()) else None

# =========================
# TELEGRAM
# =========================
TELEGRAM_TOKEN_CONST = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
TELEGRAM_CHAT_ID_JPAULO_CONST = "493747253"
TELEGRAM_CHAT_ID_VINICIUS_CONST = "-1002953102982"

def _get_secret(name: str, default: str | None = None) -> str | None:
    try:
        val = st.secrets.get(name)
        val = (val or "").strip()
        if val:
            return val
    except Exception:
        pass
    return (default or "").strip() or None

def _get_token() -> str | None:
    return _get_secret("TELEGRAM_TOKEN", TELEGRAM_TOKEN_CONST)

def _get_chat_id_jp() -> str | None:
    return _get_secret("TELEGRAM_CHAT_ID_JPAULO", TELEGRAM_CHAT_ID_JPAULO_CONST)

def _get_chat_id_vini() -> str | None:
    return _get_secret("TELEGRAM_CHAT_ID_VINICIUS", TELEGRAM_CHAT_ID_VINICIUS_CONST)

def _check_tg_ready(token: str | None, chat_id: str | None) -> bool:
    return bool((token or "").strip() and (chat_id or "").strip())

def _chat_id_por_func(funcionario: str) -> str | None:
    if funcionario == "Vinicius":
        return _get_chat_id_vini()
    return _get_chat_id_jp()

def tg_send(text: str, chat_id: str | None = None) -> bool:
    token = _get_token()
    chat = chat_id or _get_chat_id_jp()
    if not _check_tg_ready(token, chat):
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        r = requests.post(url, json=payload, timeout=30)
        js = r.json()
        return bool(r.ok and js.get("ok"))
    except Exception:
        return False

def tg_send_photo(photo_url: str, caption: str, chat_id: str | None = None) -> bool:
    token = _get_token()
    chat = chat_id or _get_chat_id_jp()
    if not _check_tg_ready(token, chat):
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = {"chat_id": chat, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=payload, timeout=30)
        js = r.json()
        if r.ok and js.get("ok"):
            return True
        return tg_send(caption, chat_id=chat)
    except Exception:
        return tg_send(caption, chat_id=chat)

# =========================
# RESUMOS DIÁRIOS (ATUALIZADOS)
# =========================
def _parse_pct_vini() -> float:
    try:
        raw = st.secrets.get("PCT_COMISSAO_VINI", PCT_COMISSAO_VINI_DEFAULT)
        if raw is None:
            return PCT_COMISSAO_VINI_DEFAULT
        if isinstance(raw, (int, float)):
            v = float(raw);  return v/100.0 if v > 1.0 else v
        s = str(raw).strip().replace(",", ".").replace("%", "")
        v = float(s);      return v/100.0 if v > 1.0 else v
    except Exception:
        return PCT_COMISSAO_VINI_DEFAULT

def _valor_bruto_row(row) -> float:
    try:
        vb = float(row.get("ValorBrutoRecebido", 0) or 0)
        if vb and vb > 0:
            return vb
    except Exception:
        pass
    try:
        return float(row.get("Valor", 0) or 0)
    except Exception:
        return 0.0

def _is_servico(s):
    t = _norm_key(s)
    return t in {"servico", "serviço", ""}  # mantém vazios como serviço registrado

def _servicos_1x_por_atendimento(d_srv: pd.DataFrame) -> pd.DataFrame:
    """Usa chave Cliente+Data para contar cada serviço apenas 1x por atendimento."""
    base = d_srv.copy()
    base["_dia"] = pd.to_datetime(base["Data"], format=DATA_FMT, errors="coerce").dt.date
    base["_chave_att"] = base["Cliente"].astype(str).str.strip() + " | " + base["_dia"].astype(str)
    base["_serv_norm"] = base["Serviço"].astype(str).str.strip()
    base = base.drop_duplicates(subset=["_chave_att", "_serv_norm"])
    return base

def _make_daily_summary_caption(df_all: pd.DataFrame, data_str: str, funcionario: str) -> str:
    # Resumo por funcionário — sempre retorna texto.
    def _fmt_names(ns, maxn=8):
        ns = [n for n in ns if str(n).strip()]
        if not ns:
            return ""
        cut = ns[:maxn]
        s = ", ".join(cut)
        return s + ("…" if len(ns) > maxn else "")

    dia_ref = pd.to_datetime(data_str, format=DATA_FMT, errors="coerce")
    if pd.isna(dia_ref):
        return f"📊 <b>Resumo do Dia — {funcionario}</b>\n🗓️ {data_str}\n—\n⚠️ Data inválida."
    dia_ref = dia_ref.date()

    d = df_all.copy()
    d["_dt"] = pd.to_datetime(d["Data"], format=DATA_FMT, errors="coerce")
    d = d[~d["_dt"].isna() & (d["_dt"].dt.date == dia_ref)].copy()

    func_norm = _norm_key(funcionario)
    d["__func_norm"] = d["Funcionário"].astype(str).map(_norm_key)
    d = d[d["__func_norm"] == func_norm].copy()

    cab = [f"📊 <b>Resumo do Dia — {funcionario}</b>", f"🗓️ {data_str}", "—"]

    if d.empty:
        cab += [
            "👀 Sem atendimentos registrados para este funcionário na data.",
            "💵 Bruto: R$ 0,00 • 🪙 Líquido: R$ 0,00",
            "💳 Taxa cartão: R$ 0,00",
            "💖 Caixinha: —",
            "🕒 Períodos: —",
            f"👨‍🔧 Funcionário: {funcionario}: 0x",
            "🏆 Top 3: —",
        ]
        return "\n".join(cab)

    d["__tipo_norm"] = d["Tipo"].astype(str).map(_norm_key)
    d_srv = d[d["__tipo_norm"].apply(_is_servico)].copy()

    # Serviços contados 1x por atendimento
    base_srv = _servicos_1x_por_atendimento(d_srv)
    srv_counts = (
        base_srv["_serv_norm"]
        .replace("", pd.NA).dropna()
        .value_counts().rename_axis("Serviço").reset_index(name="Qtd")
    )
    srv_str = "—" if srv_counts.empty else ", ".join(f"{r['Serviço']} ×{int(r['Qtd'])}" for _, r in srv_counts.iterrows())

    # pagos x fiado
    conta_cli = d_srv[["Cliente", "Conta"]].copy()
    conta_cli["Conta"] = conta_cli["Conta"].astype(str).str.strip().str.lower()
    clientes_fiado = set(conta_cli.loc[conta_cli["Conta"] == "fiado", "Cliente"].unique())
    clientes_pago_raw = set(conta_cli.loc[conta_cli["Conta"] != "fiado", "Cliente"].unique())
    clientes_pago = clientes_pago_raw - clientes_fiado
    qtd_fiado = len(clientes_fiado)
    qtd_pago = len(clientes_pago)

    bruto_total = float(d_srv.apply(_valor_bruto_row, axis=1).sum())
    liquido_total = float(pd.to_numeric(d_srv.get("Valor", 0), errors="coerce").fillna(0).sum())
    taxa_cartao_total = float(pd.to_numeric(d_srv.get("TaxaCartaoValor", 0), errors="coerce").fillna(0).sum())

    v_cx = float(pd.to_numeric(d.get("CaixinhaDia", 0), errors="coerce").fillna(0).sum())
    doadores = d.loc[pd.to_numeric(d.get("CaixinhaDia", 0), errors="coerce").fillna(0) > 0, "Cliente"].unique().tolist()
    cx_list = _fmt_names(doadores, 8)
    cx_line = f"{_fmt_brl(v_cx)}" + (f" • {cx_list}" if cx_list else "")

    clientes_unicos = d_srv["Cliente"].astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist()
    qtd_clientes = len(clientes_unicos)

    d_srv["__periodo"] = d_srv["Período"].astype(str).str.strip()
    per_parts = []
    for p in ["Manhã", "Tarde", "Noite"]:
        dp = d_srv[d_srv["__periodo"] == p]
        if not dp.empty:
            per_parts.append(f"{p}: {len(dp)}")
    per_str = " • ".join(per_parts) if per_parts else "—"

    funcs_str = f"{funcionario}: {len(d_srv)}x"

    d_srv["__bruto_i"] = d_srv.apply(_valor_bruto_row, axis=1)
    top3 = d_srv.groupby("Cliente")["__bruto_i"].sum().sort_values(ascending=False).head(3)
    top3_str = ", ".join(f"{cli}: {_fmt_brl(v)}" for cli, v in top3.items()) or "—"

    linhas = cab + [
        f"🧾 Serviços: {srv_str}",
        f"👥 Clientes atendidos: <b>{qtd_clientes}</b>",
        f"💸 Pagos: <b>{qtd_pago}</b> • 🧾 Fiado: <b>{qtd_fiado}</b>",
    ]

    # Fiados do dia
    fiados_df = d_srv[d_srv["Conta"].astype(str).str.strip().str.lower() == "fiado"].copy()
    fiados_df["__bruto_i"] = fiados_df.apply(_valor_bruto_row, axis=1)
    fiados_group = fiados_df.groupby("Cliente")["__bruto_i"].sum().sort_values(ascending=False)
    if not fiados_group.empty:
        linhas.append("")
        linhas.append("🧾 <b>Fiados do dia</b>")
        for cli, v in fiados_group.items():
            linhas.append(f"• {cli}: {_fmt_brl(v)}")

    linhas += [
        "",
        f"💵 Bruto: {_fmt_brl(bruto_total)} • 🪙 Líquido: {_fmt_brl(liquido_total)}",
        f"💳 Taxa cartão: {_fmt_brl(taxa_cartao_total)}",
        (f"💖 Caixinha: {cx_line}" if v_cx > 0 else "💖 Caixinha: —"),
        f"🕒 Períodos: {per_str}",
        f"👨‍🔧 Funcionário: {funcs_str}",
        f"🏆 Top 3: {top3_str}",
    ]
    if funcionario == "Vinicius":
        pct = _parse_pct_vini()
        linhas.append(f"🤝 Comissão: {pct*100:.0f}% • 💰 {_fmt_brl(bruto_total*pct)}")
    return "\n".join(linhas)

def _make_daily_summary_caption_geral(df_all: pd.DataFrame, data_str: str) -> str:
    # Resumo GERAL — sempre retorna texto.
    def _fmt_names(ns, maxn=12):
        ns = [n for n in ns if str(n).strip()]
        if not ns:
            return ""
        cut = ns[:maxn]
        s = ", ".join(cut)
        return s + ("…" if len(ns) > maxn else "")

    dia_ref = pd.to_datetime(data_str, format=DATA_FMT, errors="coerce")
    if pd.isna(dia_ref):
        return f"📊 <b>Resumo GERAL</b>\n🗓️ {data_str}\n—\n⚠️ Data inválida."
    dia_ref = dia_ref.date()

    d = df_all.copy()
    d["_dt"] = pd.to_datetime(d["Data"], format=DATA_FMT, errors="coerce")
    d = d[~d["_dt"].isna() & (d["_dt"].dt.date == dia_ref)].copy()

    linhas = ["📊 <b>Resumo GERAL</b>", f"🗓️ {data_str}", "—"]

    if d.empty:
        linhas += [
            "👀 Sem atendimentos registrados nesta data.",
            "💵 Bruto: R$ 0,00 • 🪙 Líquido: R$ 0,00",
            "💳 Taxa cartão: R$ 0,00",
            "💖 Caixinha: —",
            "🕒 Períodos: —",
            "👨‍🔧 Funcionários: —",
        ]
        return "\n".join(linhas)

    d["__tipo_norm"] = d["Tipo"].astype(str).map(_norm_key)
    d_srv = d[d["__tipo_norm"].apply(_is_servico)].copy()

    # Serviços contados 1x por atendimento
    base_srv = _servicos_1x_por_atendimento(d_srv)
    srv_counts = (
        base_srv["_serv_norm"]
        .replace("", pd.NA).dropna()
        .value_counts().rename_axis("Serviço").reset_index(name="Qtd")
    )
    srv_str = "—" if srv_counts.empty else ", ".join(f"{r['Serviço']} ×{int(r['Qtd'])}" for _, r in srv_counts.iterrows())

    conta_cli = d_srv[["Cliente", "Conta"]].copy()
    conta_cli["Conta"] = conta_cli["Conta"].astype(str).str.strip().str.lower()
    clientes_fiado = set(conta_cli.loc[conta_cli["Conta"] == "fiado", "Cliente"].unique())
    clientes_pago_raw = set(conta_cli.loc[conta_cli["Conta"] != "fiado", "Cliente"].unique())
    clientes_pago = clientes_pago_raw - clientes_fiado
    qtd_fiado = len(clientes_fiado)
    qtd_pago = len(clientes_pago)

    clientes_unicos = d_srv["Cliente"].astype(str).str.strip().replace("", pd.NA).dropna().unique().tolist()
    qtd_clientes = len(clientes_unicos)

    bruto_total = float(d_srv.apply(_valor_bruto_row, axis=1).sum())
    liquido_total = float(pd.to_numeric(d_srv.get("Valor", 0), errors="coerce").fillna(0).sum())
    taxa_cartao_total = float(pd.to_numeric(d_srv.get("TaxaCartaoValor", 0), errors="coerce").fillna(0).sum())

    v_cx = float(pd.to_numeric(d.get("CaixinhaDia", 0), errors="coerce").fillna(0).sum())
    doadores = d.loc[pd.to_numeric(d.get("CaixinhaDia", 0), errors="coerce").fillna(0) > 0, "Cliente"].unique().tolist()
    cx_line = f"{_fmt_brl(v_cx)} • {_fmt_names(doadores)}" if v_cx > 0 else "—"

    d_srv["__periodo"] = d_srv["Período"].astype(str).str.strip()
    per_parts = []
    for p in ["Manhã", "Tarde", "Noite"]:
        dp = d_srv[d_srv["__periodo"] == p]
        if not dp.empty:
            per_parts.append(f"{p}: {len(dp)}")
    per_str = " • ".join(per_parts) if per_parts else "—"

    por_func = d_srv.groupby("Funcionário")["Valor"].count().to_dict()
    funcs_str = " • ".join(f"{f}: {q}x" for f, q in por_func.items()) or "—"

    linhas += [
        f"🧾 Serviços: {srv_str}",
        f"👥 Clientes atendidos: <b>{qtd_clientes}</b>",
        f"💸 Pagos: <b>{qtd_pago}</b> • 🧾 Fiado: <b>{qtd_fiado}</b>",
    ]

    fiados_df = d_srv[d_srv["Conta"].astype(str).str.strip().str.lower() == "fiado"].copy()
    fiados_df["__bruto_i"] = fiados_df.apply(_valor_bruto_row, axis=1)
    fiados_group = fiados_df.groupby("Cliente")["__bruto_i"].sum().sort_values(ascending=False)
    if not fiados_group.empty:
        linhas.append("")
        linhas.append("🧾 <b>Fiados do dia</b>")
        for cli, v in fiados_group.items():
            linhas.append(f"• {cli}: {_fmt_brl(v)}")

    linhas += [
        "",
        f"💵 Bruto: {_fmt_brl(bruto_total)} • 🪙 Líquido: {_fmt_brl(liquido_total)}",
        f"💳 Taxa cartão: {_fmt_brl(taxa_cartao_total)}",
        (f"💖 Caixinha: {cx_line}" if v_cx > 0 else "💖 Caixinha: —"),
        f"🕒 Períodos: {per_str}",
        f"👨‍🔧 Funcionários: {funcs_str}",
    ]
    return "\n".join(linhas)

def enviar_resumo_diario(df_all: pd.DataFrame, data_str: str, funcionario: str) -> bool:
    try:
        caption = _make_daily_summary_caption(df_all, data_str, funcionario)
        if not caption:
            return False
        if funcionario == "Vinicius":
            ok_v = tg_send(caption, chat_id=_get_chat_id_vini())
            ok_j = tg_send(caption, chat_id=_get_chat_id_jp())
            return bool(ok_v or ok_j)
        return tg_send(caption, chat_id=_chat_id_por_func(funcionario))
    except Exception:
        return False

def enviar_resumo_geral(df_all: pd.DataFrame, data_str: str) -> bool:
    try:
        caption = _make_daily_summary_caption_geral(df_all, data_str)
        if not caption:
            return False
        return tg_send(caption, chat_id=_get_chat_id_jp())
    except Exception:
        return False

# =========================
# CARD – bloco principal + seções extras (cartão, caixinha, fiado)
# =========================
def _resumo_do_dia(df_all: pd.DataFrame, cliente: str, data_str: str):
    d = df_all[
        (df_all["Cliente"].astype(str).str.strip() == cliente) &
        (df_all["Data"].astype(str).str.strip() == data_str)
    ].copy()

    d["Valor"] = pd.to_numeric(d["Valor"], errors="coerce").fillna(0.0)
    servicos = [str(s).strip() for s in d["Serviço"].fillna("").tolist() if str(s).strip()]
    valor_total = float(d["Valor"].sum()) if not d.empty else 0.0
    is_combo = len(servicos) > 1 or (d["Combo"].fillna("").str.strip() != "").any()

    if servicos:
        label = " + ".join(servicos) + (" (Combo)" if is_combo else " (Simples)")
    else:
        label = "-"

    periodo_vals = [p for p in d["Período"].astype(str).str.strip().tolist() if p]
    periodo_label = max(set(periodo_vals), key=periodo_vals.count) if periodo_vals else "-"

    return label, valor_total, is_combo, servicos, periodo_label

def _ano_from_date_str(data_str: str) -> int | None:
    dt = pd.to_datetime(data_str, format=DATA_FMT, errors="coerce")
    return None if pd.isna(dt) else int(dt.year)

def _year_sections_for_jpaulo(df_all: pd.DataFrame, cliente: str, ano: int) -> tuple[str, str]:
    d = df_all.copy()
    d = d[d["Cliente"].astype(str).str.strip() == cliente].copy()
    d["_dt"] = pd.to_datetime(d["Data"], format=DATA_FMT, errors="coerce")
    d = d.dropna(subset=["_dt"])
    d["ano"] = d["_dt"].dt.year
    d = d[d["ano"] == ano].copy()

    if d.empty:
        return (f"📚 <b>Histórico por ano</b>\n{ano}: R$ 0,00",
                f"🧾 <b>{ano}: por serviço</b>\n—")

    d["Valor"] = pd.to_numeric(d.get("Valor", 0), errors="coerce").fillna(0.0)
    if "CaixinhaDia" not in d.columns:
        d["CaixinhaDia"] = 0.0
    d["CaixinhaDia"] = pd.to_numeric(d["CaixinhaDia"], errors="coerce").fillna(0.0)

    total_servicos = float(d["Valor"].sum())
    total_caixinha = float(d["CaixinhaDia"].sum())
    total_com_caixinha = total_servicos + total_caixinha

    sec_hist = (
        "📚 <b>Histórico por ano</b>\n"
        f"{ano}: <b>{_fmt_brl(total_com_caixinha)}</b>\n"
        f"• Serviços: {_fmt_brl(total_servicos)}\n"
        f"• Caixinha: {_fmt_brl(total_caixinha)}"
    )

    grp = (
        d.dropna(subset=["Serviço"])
         .assign(Serviço=lambda x: x["Serviço"].astype(str).str.strip())
         .groupby("Serviço", as_index=False)
         .agg(qtd=("Serviço", "count"), total=("Valor", "sum"))
         .sort_values(["total", "qtd"], ascending=[False, False])
    )

    linhas_serv = []
    for _, r in grp.iterrows():
        linhas_serv.append(
            f"• <b>{r['Serviço']}</b>: {int(r['qtd'])}× • <b>{_fmt_brl(float(r['total']))}</b>"
        )

    total_geral = float(grp["total"].sum() if not grp.empty else 0.0) + total_caixinha
    bloco_servicos = "\n".join(linhas_serv) if linhas_serv else "—"
    sec_serv = (
        f"🧾 <b>{ano}: por serviço</b>\n"
        f"{bloco_servicos}"
        + ("\n\n" if linhas_serv else "\n")
        + f"<i>Total ({ano}):</i> <b>{_fmt_brl(total_geral)}</b>"
    )

    # Frequência por funcionário
    visitas_por_dia = (
        d.assign(dia=d["_dt"].dt.date, func=d["Funcionário"].astype(str).str.strip())
         .groupby("dia")["func"]
         .agg(lambda s: s.value_counts(dropna=False).idxmax())
    )
    if not visitas_por_dia.empty:
        contagem = visitas_por_dia.value_counts()
        ordem = ["JPaulo", "Vinicius"]
        linhas_func = [f"{f}: <b>{int(contagem.get(f, 0))}</b> visita(s)" for f in ordem]
        sec_serv += "\n\n👥 <b>Frequência por funcionário</b>\n" + "\n".join(linhas_func)

    return sec_hist, sec_serv

def _secao_pag_cartao(df_all: pd.DataFrame, cliente: str, data_str: str) -> str:
    df = df_all[
        (df_all["Cliente"].astype(str).str.strip() == cliente) &
        (df_all["Data"].astype(str).str.strip() == data_str)
    ].copy()
    if df.empty:
        return ""

    df["_idx"] = df.index
    com_pid = df[df["PagamentoID"].astype(str).str.strip() != ""].copy()
    if com_pid.empty:
        return ""

    latest_row = com_pid.loc[com_pid["_idx"].idxmax()]
    pid = str(latest_row["PagamentoID"]).strip()
    bloco = df[df["PagamentoID"].astype(str).str.strip() == pid].copy()

    bruto  = pd.to_numeric(bloco.get("ValorBrutoRecebido", 0), errors="coerce").fillna(0).sum()
    liqui  = pd.to_numeric(bloco.get("ValorLiquidoRecebido", 0), errors="coerce").fillna(0).sum()
    taxa_v = pd.to_numeric(bloco.get("TaxaCartaoValor", 0), errors="coerce").fillna(0).sum()
    if liqui <= 0:
        liqui = pd.to_numeric(bloco.get("Valor", 0), errors="coerce").fillna(0).sum()
    taxa_pct = (taxa_v / bruto * 100.0) if bruto > 0 else 0.0

    det = ""
    if "FormaPagDetalhe" in bloco.columns:
        s = bloco["FormaPagDetalhe"].astype(str).str.strip()
        s = s[s != ""]
        if not s.empty:
            det = s.iloc[0]
    conta = ""
    if "Conta" in bloco.columns:
        s2 = bloco["Conta"].astype(str).str.strip()
        s2 = s2[s2 != ""]
        if not s2.empty:
            conta = s2.iloc[0]

    linhas = [
        "------------------------------",
        "💳 <b>Pagamento no cartão</b>",
        f"Forma: <b>{conta or '-'}</b>{(' · ' + det) if det else ''}",
        f"Bruto: <b>{_fmt_brl(bruto)}</b> · Líquido: <b>{_fmt_brl(liqui)}</b>",
        f"Taxa total: <b>{_fmt_brl(taxa_v)} ({taxa_pct:.2f}%)</b>",
    ]
    return "\n".join(linhas)

def _secao_caixinha(df_all: pd.DataFrame, cliente: str, data_str: str) -> str:
    d = df_all[
        (df_all["Cliente"].astype(str).str.strip() == cliente) &
        (df_all["Data"].astype(str).str.strip() == data_str)
    ].copy()
    if d.empty or "CaixinhaDia" not in d.columns:
        return ""

    v_dia = pd.to_numeric(d.get("CaixinhaDia", 0), errors="coerce").fillna(0).sum()
    if v_dia <= 0:
        return ""

    linhas = [
        "------------------------------",
        "💝 <b>Caixinha</b>",
        f"Dia: <b>{_fmt_brl(v_dia)}</b>",
    ]
    return "\n".join(linhas)

def _secao_fiado(df_all: pd.DataFrame, cliente: str, data_str: str) -> str:
    d = df_all[
        (df_all["Cliente"].astype(str).str.strip() == cliente) &
        (df_all["Data"].astype(str).str.strip() == data_str) &
        (df_all["Conta"].astype(str).str.strip().str.lower() == "fiado")
    ].copy()
    if d.empty:
        return ""
    d["_idx"] = d.index
    d = d.sort_values("_idx")
    idf = str(d["IDLancFiado"].dropna().astype(str).str.strip().iloc[-1]) if "IDLancFiado" in d.columns and not d["IDLancFiado"].isna().all() else ""
    status = str(d["StatusFiado"].dropna().astype(str).str.strip().iloc[-1]) if "StatusFiado" in d.columns and not d["StatusFiado"].isna().all() else "Em aberto"
    venc = str(d["VencimentoFiado"].dropna().astype(str).str.strip().iloc[-1]) if "VencimentoFiado" in d.columns and not d["VencimentoFiado"].isna().all() else "-"
    linhas = [
        "------------------------------",
        "🧾 <b>Fiado</b>",
        f"Status: <b>{status or 'Em aberto'}</b>",
        f"Vencimento: <b>{venc or '-'}</b>" + (f"\nID: <code>{idf}</code>" if idf else "")
    ]
    return "\n".join(linhas)

def make_card_caption_classico(
    df_all, cliente, data_str, funcionario, servico_label, valor_total, periodo_label,
    append_sections: list[str] | None = None
):
    d_hist = df_all[df_all["Cliente"].astype(str).str.strip() == cliente].copy()
    d_hist["_dt"] = pd.to_datetime(d_hist["Data"], format=DATA_FMT, errors="coerce")
    d_hist = d_hist.dropna(subset=["_dt"]).sort_values("_dt")

    unique_days = sorted(set(d_hist["_dt"].dt.date.tolist()))
    total_atend = len(unique_days)

    dt_atual = pd.to_datetime(data_str, format=DATA_FMT, errors="coerce")
    dia_atual = None if pd.isna(dt_atual) else dt_atual.date()

    prev_days = [d for d in unique_days if (dia_atual is None or d < dia_atual)]
    prev_date = prev_days[-1] if prev_days else None

    if prev_date is not None:
        ultimo_reg = d_hist[d_hist["_dt"].dt.date == prev_date].iloc[-1]
        ultimo_func = str(ultimo_reg.get("Funcionário", "-"))
    else:
        ultimo_func = "-"

    if prev_date is not None and dia_atual is not None:
        dias_dif = (dia_atual - prev_date).days
        dias_str = f"{dias_dif} dias"
    else:
        dias_dif = None
        dias_str = "-"

    if len(unique_days) >= 2:
        ts = [pd.to_datetime(x) for x in unique_days]
        diffs = [(ts[i] - ts[i-1]).days for i in range(1, len(ts))]
        media = sum(diffs) / len(diffs) if diffs else None
    else:
        media = None
    media_str = "-" if media is None else f"{media:.1f} dias".replace(".", ",")

    # Status do cliente (comparação com a média)
    if dias_dif is not None and media is not None:
        if dias_dif <= media * 1.2:
            status_cli = "✅ Em dia"
        elif dias_dif <= media * 1.5:
            status_cli = "⚠️ Pouco atrasado"
        else:
            status_cli = "❌ Muito atrasado"
    else:
        status_cli = "—"

    valor_str = _fmt_brl(valor_total)

    linhas = []
    linhas.append("📌 <b>Atendimento registrado</b>")
    linhas.append(f"👤 Cliente: <b>{cliente}</b>")
    linhas.append(f"🗓️ Data: <b>{data_str}</b>")
    linhas.append(f"🕒 Período: <b>{periodo_label}</b>")
    linhas.append(f"✂️ Serviço: <b>{servico_label}</b>")
    linhas.append(f"💰 Valor: <b>{valor_str}</b>")
    linhas.append(f"👨‍🔧 Atendido por: <b>{funcionario}</b>")
    linhas.append("")
    linhas.append("📊 <b>Resumo</b>")
    linhas.append(f"🔁 Média: <b>{media_str}</b>")
    linhas.append(f"⏳ Distância da última: <b>{dias_str}</b>")
    linhas.append(f"📈 Total de atendimentos: <b>{total_atend}</b>")
    linhas.append(f"👨‍🔧 Último atendente: <b>{ultimo_func}</b>")
    linhas.append(f"📌 Status: <b>{status_cli}</b>")

    if append_sections:
        extra = "\n\n".join([s for s in append_sections if s and s.strip()])
        if extra:
            linhas.append("\n" + extra)

    return "\n".join(linhas)

def enviar_card(df_all, cliente, funcionario, data_str, servico=None, valor=None, combo=None) -> bool:
    if servico is None or valor is None:
        servico_label, valor_total, _, _, periodo_label = _resumo_do_dia(df_all, cliente, data_str)
    else:
        is_combo = bool(combo and str(combo).strip())
        eh_combo = is_combo or ("+" in str(servico))
        servico_label = f"{servico} (Combo)" if eh_combo else f"{servico} (Simples)"
        valor_total = float(valor)
        _, _, _, _, periodo_label = _resumo_do_dia(df_all, cliente, data_str)

    sec_cartao = _secao_pag_cartao(df_all, cliente, data_str)
    sec_caixa  = _secao_caixinha(df_all, cliente, data_str)
    sec_fiado  = _secao_fiado(df_all, cliente, data_str)

    extras_base = []
    if sec_cartao: extras_base.append(sec_cartao)
    if sec_caixa:  extras_base.append(sec_caixa)
    if sec_fiado:  extras_base.append(sec_fiado)

    ano = _ano_from_date_str(data_str)
    extras_jp = extras_base.copy()
    if ano is not None:
        sec_hist, sec_serv = _year_sections_for_jpaulo(df_all, cliente, ano)
        extras_jp.extend([sec_hist, sec_serv])

    foto = FOTOS.get(_norm(cliente))

    caption_base = make_card_caption_classico(
        df_all, cliente, data_str, funcionario, servico_label, valor_total, periodo_label,
        append_sections=extras_base
    )
    caption_jp = make_card_caption_classico(
        df_all, cliente, data_str, funcionario, servico_label, valor_total, periodo_label,
        append_sections=extras_jp
    )

    if funcionario == "JPaulo":
        chat_jp = _get_chat_id_jp()
        return tg_send_photo(foto, caption_jp, chat_id=chat_jp) if foto else tg_send(caption_jp, chat_id=chat_jp)

    if funcionario == "Vinicius":
        chat_v = _get_chat_id_vini()
        sent_v = tg_send_photo(foto, caption_base, chat_id=chat_v) if foto else tg_send(caption_base, chat_id=chat_v)
        chat_jp = _get_chat_id_jp()
        sent_jp = tg_send_photo(foto, caption_jp, chat_id=chat_jp) if foto else tg_send(caption_jp, chat_id=chat_jp)
        return bool(sent_v or sent_jp)

    destino = _chat_id_por_func(funcionario)
    return tg_send_photo(foto, caption_base, chat_id=destino) if foto else tg_send(caption_base, chat_id=destino)

# =========================
# VALORES DE SERVIÇO
# =========================
VALORES = {
    "Corte": 25.0, "Pezinho": 7.0, "Barba": 15.0, "Sobrancelha": 7.0,
    "Luzes": 45.0, "Tintura": 20.0, "Alisamento": 40.0, "Gel": 10.0, "Pomada": 15.0,
}
def obter_valor_servico(servico):
    for k, v in VALORES.items():
        if k.lower() == servico.lower():
            return v
    return 0.0

def _preencher_fiado_vazio(linha: dict):
    for c in [*COLS_FIADO, *COLS_PAG_EXTRAS, *COLS_CAIXINHAS]:
        linha.setdefault(c, "")
    return linha

def ja_existe_atendimento(cliente, data, servico, combo=""):
    df, _ = carregar_base()
    df["Combo"] = df["Combo"].fillna("")
    servico_norm = _cap_first(servico)
    df_serv_norm = df["Serviço"].astype(str).map(_cap_first)
    f = (
        (df["Cliente"].astype(str).str.strip() == cliente) &
        (df["Data"].astype(str).str.strip() == data) &
        (df_serv_norm == servico_norm) &
        (df["Combo"].astype(str).str.strip() == str(combo).strip())
    )
    return not df[f].empty

def sugestoes_do_cliente(df_all, cli, conta_default, periodo_default, funcionario_default):
    d = df_all[df_all["Cliente"].astype(str).str.strip() == cli].copy()
    if d.empty: return conta_default, periodo_default, funcionario_default
    d["_dt"] = pd.to_datetime(d["Data"], format=DATA_FMT, errors="coerce")
    d = d.dropna(subset=["_dt"]).sort_values("_dt")
    if d.empty: return conta_default, periodo_default, funcionario_default
    ultima = d.iloc[-1]
    conta = (ultima.get("Conta") or "").strip() or conta_default
    periodo = (ultima.get("Período") or "").strip() or periodo_default
    func = (ultima.get("Funcionário") or "").strip() or funcionario_default
    if periodo not in ["Manhã", "Tarde", "Noite"]: periodo = periodo_default
    if func not in ["JPaulo", "Vinicius"]: func = funcionario_default
    return conta, periodo, func

# =========================
# UI – Cabeçalho
# =========================
st.set_page_config(layout="wide")
st.title("📅 Adicionar Atendimento")

# =========================
# DADOS BASE PARA SUGESTÕES
# =========================
df_existente, _ = carregar_base()
df_existente["_dt"] = pd.to_datetime(df_existente["Data"], format=DATA_FMT, errors="coerce")
df_2025 = df_existente[df_existente["_dt"].dt.year == 2025]

clientes_existentes = sorted(df_2025["Cliente"].dropna().unique())
df_2025 = df_2025[df_2025["Serviço"].notna()].copy()

servicos_existentes = sorted(df_2025["Serviço"].str.strip().unique())
servicos_ui = list(dict.fromkeys(["Corte", *servicos_existentes]))

contas_existentes = sorted([c for c in df_2025["Conta"].dropna().astype(str).str.strip().unique() if c])
combos_existentes = sorted([c for c in df_2025["Combo"].dropna().astype(str).str.strip().unique() if c])

# =========================
# REENVIAR RESUMOS (Data dentro da seção, layout antigo)
# =========================
st.divider()
st.subheader("📣 Reenviar resumos do dia")
data = st.date_input("Data", value=today_local()).strftime(DATA_FMT)

col_a, col_b, col_c = st.columns(3)
with col_a:
    if st.button("📤 Reenviar resumo GERAL (todos)", use_container_width=True):
        try:
            df_all, _ = carregar_base()
            ok = enviar_resumo_geral(df_all, data)
            st.success("Resumo GERAL reenviado." if ok else "Não consegui enviar o resumo GERAL.")
        except Exception as e:
            st.error(f"Erro ao reenviar resumo geral: {e}")

with col_b:
    if st.button("👨‍🔧 Reenviar resumo do JPaulo", use_container_width=True):
        try:
            df_all, _ = carregar_base()
            ok = enviar_resumo_diario(df_all, data, "JPaulo")
            st.success("Resumo do JPaulo reenviado." if ok else "Não consegui enviar o resumo do JPaulo.")
        except Exception as e:
            st.error(f"Erro ao reenviar (JPaulo): {e}")

with col_c:
    if st.button("💈 Reenviar resumo do Vinicius", use_container_width=True):
        try:
            df_all, _ = carregar_base()
            ok = enviar_resumo_diario(df_all, data, "Vinicius")
            st.success("Resumo do Vinicius reenviado." if ok else "Não consegui enviar o resumo do Vinicius.")
        except Exception as e:
            st.error(f"Erro ao reenviar (Vinicius): {e}")

# =========================
# FORM – Modo
# =========================
modo_lote = st.toggle("📦 Cadastro em Lote (vários clientes de uma vez)", value=False)

# =========================
# MODO UM POR VEZ
# =========================
if not modo_lote:
    cA, cB = st.columns([2, 1])
    with cA:
        cliente = st.selectbox("Nome do Cliente", clientes_existentes)
        novo_nome = st.text_input("Ou digite um novo nome de cliente")
        cliente = novo_nome if novo_nome else cliente
    with cB:
        foto_url = get_foto_url(cliente)
        if foto_url:
            st.image(foto_url, caption=(cliente or "Cliente"), width=250)

    conta_fallback = (contas_existentes[0] if contas_existentes else "Carteira")
    periodo_fallback = "Manhã"
    func_fallback = "JPaulo"

    sug_conta, sug_periodo, sug_func = sugestoes_do_cliente(
        df_existente, cliente, conta_fallback, periodo_fallback, func_fallback
    )

    conta = st.selectbox(
        "Forma de Pagamento",
        list(dict.fromkeys([sug_conta] + contas_existentes +
                           ["Carteira", "Pix", "Transferência", "Nubank CNPJ", "Nubank", "Pagseguro", "Mercado Pago"]))
    )

    # ====== FIADO (um por vez) ======
    colf1, colf2 = st.columns([1,1])
    with colf1:
        marcar_fiado = st.checkbox(
            "🔖 Marcar como FIADO?",
            value=False,
            help="Se marcado, será lançado como fiado (Conta='Fiado') e o cartão fica desativado."
        )
    with colf2:
        venc_fiado_um = st.date_input(
            "Vencimento (fiado)",
            value=today_local()
        )

    force_off = is_nao_cartao(conta)
    cartao_bloqueado = force_off or marcar_fiado
    usar_cartao = st.checkbox(
        "Tratar como cartão (com taxa)?",
        value=(False if cartao_bloqueado else default_card_flag(conta)),
        key="flag_card_um",
        disabled=cartao_bloqueado,
        help=("Desabilitado para PIX/Dinheiro/Transferência ou se for FIADO." if cartao_bloqueado else None)
    )

    funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"], index=(0 if sug_func == "JPaulo" else 1))
    periodo_opcao = st.selectbox("Período do Atendimento", ["Manhã", "Tarde", "Noite"],
                                 index=["Manhã", "Tarde", "Noite"].index(sug_periodo))

    ultimo = df_existente[df_existente["Cliente"] == cliente]
    ultimo = ultimo.sort_values("Data", ascending=False).iloc[0] if not ultimo.empty else None
    combo = ""
    if ultimo is not None:
        ult_combo = ultimo.get("Combo", "")
        combo = st.selectbox("Combo (último primeiro)", [""] + list(dict.fromkeys([ult_combo] + combos_existentes)))

    # ---- reseta travas de estado quando muda o "contexto"
    ctx_key = f"{cliente}|{data}|{combo or '-'}"
    if st.session_state.get("last_ctx_key") != ctx_key:
        st.session_state["last_ctx_key"] = ctx_key
        st.session_state["combo_salvo"] = False
        st.session_state["simples_salvo"] = False

    # -------- COMBO (um por vez) --------
    if combo:
        st.subheader("💰 Edite os valores do combo antes de salvar:")
        valores_customizados = {}
        for s in combo.split("+"):
            s2 = s.strip()
            valores_customizados[s2] = st.number_input(
                f"{s2} (padrão: R$ {obter_valor_servico(s2)})",
                value=obter_valor_servico(s2), step=1.0, key=f"valor_{s2}"
            )

        # 💝 Caixinha (opcional)
        with st.expander("💝 Caixinha (opcional)", expanded=False):
            caixinha_dia = st.number_input("Caixinha do dia", value=0.0, step=1.0, format="%.2f")

        liquido_total = None
        bandeira = ""
        tipo_cartao = "Crédito"
        parcelas = 1
        dist_modo = "Proporcional (padrão)"
        alvo_servico = None

        usar_cartao_efetivo = usar_cartao and not is_nao_cartao(conta) and not marcar_fiado
        if usar_cartao_efetivo:
            with st.expander("💳 Pagamento no cartão (informe o LÍQUIDO recebido)", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    total_bruto_combo = float(sum(valores_customizados.values()))
                    liquido_total = st.number_input("Valor recebido (líquido)", value=total_bruto_combo, step=1.0, format="%.2f")
                    bandeira = st.selectbox("Bandeira", ["", "Visa", "Mastercard", "Maestro", "Elo", "Hipercard", "Amex", "Outros"], index=0)
                with c2:
                    tipo_cartao = st.selectbox("Tipo", ["Débito", "Crédito"], index=1)
                    parcelas = st.number_input("Parcelas (se crédito)", min_value=1, max_value=12, value=1, step=1)

                dist_modo = st.radio("Distribuição do desconto/taxa",
                                     ["Proporcional (padrão)", "Concentrar em um serviço"],
                                     horizontal=False)
                if dist_modo == "Concentrar em um serviço":
                    alvo_servico = st.selectbox("Aplicar TODO o desconto/taxa em", list(valores_customizados.keys()))

                taxa_val = max(0.0, total_bruto_combo - float(liquido_total or 0.0))
                taxa_pct = (taxa_val / total_bruto_combo * 100.0) if total_bruto_combo > 0 else 0.0
                st.caption(f"Taxa estimada: {_fmt_brl(taxa_val)} ({taxa_pct:.2f}%)")

        if st.button("🧹 Limpar formulário", key="btn_limpar"):
            for k in ["combo_salvo", "simples_salvo", "last_ctx_key"]:
                st.session_state[k] = False if k != "last_ctx_key" else None
            st.rerun()

        if st.button("✅ Confirmar e Salvar Combo", key="btn_salvar_combo"):
            try:
                duplicado = any(ja_existe_atendimento(cliente, data, _cap_first(s), combo) for s in combo.split("+"))
                if duplicado:
                    st.warning("⚠️ Combo já registrado para este cliente e data.")
                else:
                    df_all, _ = carregar_base()
                    novas = []
                    total_bruto = float(sum(valores_customizados.values()))
                    usar_cartao_efetivo2 = usar_cartao and not is_nao_cartao(conta) and not marcar_fiado
                    id_pag = gerar_pag_id("A") if usar_cartao_efetivo2 else ""

                    soma_outros = None
                    if usar_cartao_efetivo2 and dist_modo == "Concentrar em um serviço" and alvo_servico:
                        soma_outros = sum(v for k, v in valores_customizados.items() if k != alvo_servico)

                    primeiro_raw = combo.split("+")[0].strip() if "+" in combo else combo.strip()

                    # Se FIADO: um único ID para o combo todo
                    id_fiado_combo = gerar_id_fiado() if marcar_fiado else ""

                    for s in combo.split("+"):
                        s2_raw = s.strip()
                        s2_norm = _cap_first(s2_raw)
                        bruto_i = float(valores_customizados.get(s2_raw, obter_valor_servico(s2_norm)))

                        if marcar_fiado:
                            li = {
                                "Data": data, "Serviço": s2_norm, "Valor": float(bruto_i),
                                "Conta": "Fiado", "Cliente": cliente, "Combo": combo,
                                "Funcionário": funcionario, "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_opcao,
                                "StatusFiado": "Em aberto",
                                "IDLancFiado": id_fiado_combo,
                                "VencimentoFiado": (venc_fiado_um.strftime(DATA_FMT) if isinstance(venc_fiado_um, date) else str(venc_fiado_um)),
                                "DataPagamento": ""
                            }
                            linha = _preencher_fiado_vazio(li)
                        elif usar_cartao_efetivo2 and total_bruto > 0:
                            if dist_modo == "Concentrar em um serviço" and alvo_servico:
                                if s2_raw == alvo_servico:
                                    liq_i = float(liquido_total or 0.0) - float(soma_outros or 0.0)
                                    liq_i = round(max(0.0, liq_i), 2)
                                else:
                                    liq_i = round(bruto_i, 2)
                            else:
                                liq_i = round(float(liquido_total or 0.0) * (bruto_i / total_bruto), 2)

                            taxa_i = round(bruto_i - liq_i, 2)
                            taxa_pct_i = (taxa_i / bruto_i * 100.0) if bruto_i > 0 else 0.0
                            linha = _preencher_fiado_vazio({
                                "Data": data, "Serviço": s2_norm,
                                "Valor": liq_i,
                                "Conta": conta, "Cliente": cliente, "Combo": combo,
                                "Funcionário": funcionario, "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_opcao,
                                "ValorBrutoRecebido": bruto_i,
                                "ValorLiquidoRecebido": liq_i,
                                "TaxaCartaoValor": taxa_i,
                                "TaxaCartaoPct": round(taxa_pct_i, 4),
                                "FormaPagDetalhe": f"{bandeira or '-'} | {tipo_cartao} | {int(parcelas)}x",
                                "PagamentoID": id_pag,
                            })
                        else:
                            linha = _preencher_fiado_vazio({
                                "Data": data, "Serviço": s2_norm,
                                "Valor": float(bruto_i),
                                "Conta": conta, "Cliente": cliente, "Combo": combo,
                                "Funcionário": funcionario, "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_opcao,
                            })

                        if s2_raw == primeiro_raw and float(caixinha_dia or 0) > 0:
                            linha["CaixinhaDia"] = float(caixinha_dia or 0)

                        novas.append(linha)

                    # Ajuste de arredondamento (cartão)
                    if usar_cartao_efetivo2 and novas and not marcar_fiado:
                        soma_liq = sum(float(n.get("Valor", 0) or 0) for n in novas)
                        delta = round(float(liquido_total or 0.0) - soma_liq, 2)
                        if abs(delta) >= 0.01:
                            idx_ajuste = len(novas) - 1
                            if dist_modo == "Concentrar em um serviço" and alvo_servico:
                                for i, n in enumerate(novas):
                                    if _norm_key(n.get("Serviço","")) == _norm_key(_cap_first(alvo_servico)):
                                        idx_ajuste = i; break
                            novas[idx_ajuste]["Valor"] = float(novas[idx_ajuste]["Valor"]) + delta
                            bsel = float(novas[idx_ajuste].get("ValorBrutoRecebido", 0) or 0)
                            lsel = float(novas[idx_ajuste]["Valor"])
                            tsel = round(bsel - lsel, 2)
                            psel = (tsel / bsel * 100.0) if bsel > 0 else 0.0
                            novas[idx_ajuste]["ValorLiquidoRecebido"] = lsel
                            novas[idx_ajuste]["TaxaCartaoValor"] = tsel
                            novas[idx_ajuste]["TaxaCartaoPct"] = round(psel, 4)

                    df_final = pd.concat([df_all, pd.DataFrame(novas)], ignore_index=True)
                    salvar_base(df_final)
                    st.session_state.combo_salvo = True
                    ok_tg = enviar_card(
                        df_final, cliente, funcionario, data,
                        servico=combo.replace("+", " + "),
                        valor=sum(float(n["Valor"]) for n in novas),
                        combo=combo
                    )
                    st.success(
                        f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}."
                        + (" 📲 Notificação enviada." if ok_tg else " ⚠️ Não consegui notificar no Telegram.")
                    )
                    # dispara resumos recalculados
                    try:
                        for _f in ["JPaulo", "Vinicius"]:
                            enviar_resumo_diario(df_final, data, _f)
                        enviar_resumo_geral(df_final, data)
                    except Exception:
                        pass
            except Exception as e:
                st.error(f"❌ Erro ao salvar combo: {e}")

    # -------- SIMPLES (um por vez) --------
    else:
        st.subheader("✂️ Selecione o serviço e valor:")

        servico = st.selectbox(
            "Serviço",
            servicos_ui,
            index=servicos_ui.index("Corte"),
            key="servico_um_v2"
        )

        valor = st.number_input("Valor", value=obter_valor_servico(servico), step=1.0)

        with st.expander("💝 Caixinha (opcional)", expanded=False):
            caixinha_dia = st.number_input("Caixinha do dia", value=0.0, step=1.0, format="%.2f")

        usar_cartao_efetivo = usar_cartao and not is_nao_cartao(conta) and not marcar_fiado
        if usar_cartao_efetivo:
            def bloco_cartao_ui(total_bruto_padrao: float):
                with st.expander("💳 Pagamento no cartão (informe o LÍQUIDO recebido)", expanded=True):
                    c1, c2 = st.columns(2)
                    with c1:
                        liquido = st.number_input("Valor recebido (líquido)", value=float(total_bruto_padrao), step=1.0, format="%.2f")
                        bandeira = st.selectbox("Bandeira", ["", "Visa", "Mastercard", "Maestro", "Elo", "Hipercard", "Amex", "Outros"], index=0)
                    with c2:
                        tipo_cartao = st.selectbox("Tipo", ["Débito", "Crédito"], index=1)
                        parcelas = st.number_input("Parcelas (se crédito)", min_value=1, max_value=12, value=1, step=1)
                    taxa_val = max(0.0, float(total_bruto_padrao) - float(liquido or 0.0))
                    taxa_pct = (taxa_val / float(total_bruto_padrao) * 100.0) if total_bruto_padrao > 0 else 0.0
                    st.caption(f"Taxa estimada: {_fmt_brl(taxa_val)} ({taxa_pct:.2f}%)")
                    return float(liquido or 0.0), str(bandeira), str(tipo_cartao), int(parcelas), float(taxa_val), float(taxa_pct)
            liquido_total, bandeira, tipo_cartao, parcelas, _, _ = bloco_cartao_ui(valor)
        else:
            liquido_total, bandeira, tipo_cartao, parcelas = None, "", "Crédito", 1

        if st.button("📁 Salvar Atendimento", key="btn_salvar_simples"):
            try:
                servico_norm = _cap_first(servico)
                if ja_existe_atendimento(cliente, data, servico_norm):
                    st.warning("⚠️ Atendimento já registrado para este cliente, data e serviço.")
                else:
                    df_all, _ = carregar_base()

                    if marcar_fiado:
                        id_fiado = gerar_id_fiado()
                        nova = _preencher_fiado_vazio({
                            "Data": data, "Serviço": servico_norm, "Valor": float(valor), "Conta": "Fiado",
                            "Cliente": cliente, "Combo": "", "Funcionário": funcionario,
                            "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_opcao,
                            "StatusFiado": "Em aberto",
                            "IDLancFiado": id_fiado,
                            "VencimentoFiado": (venc_fiado_um.strftime(DATA_FMT) if isinstance(venc_fiado_um, date) else str(venc_fiado_um)),
                            "DataPagamento": ""
                        })
                    elif usar_cartao_efetivo:
                        id_pag = gerar_pag_id("A")
                        bruto = float(valor)
                        liq = float(liquido_total or 0.0)
                        taxa_v = round(max(0.0, bruto - liq), 2)
                        taxa_pct = round((taxa_v / bruto * 100.0), 4) if bruto > 0 else 0.0
                        nova = _preencher_fiado_vazio({
                            "Data": data, "Serviço": servico_norm, "Valor": liq, "Conta": conta,
                            "Cliente": cliente, "Combo": "", "Funcionário": funcionario,
                            "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_opcao,
                            "ValorBrutoRecebido": bruto,
                            "ValorLiquidoRecebido": liq,
                            "TaxaCartaoValor": taxa_v,
                            "TaxaCartaoPct": taxa_pct,
                            "FormaPagDetalhe": f"{bandeira or '-'} | {tipo_cartao} | {int(parcelas)}x",
                            "PagamentoID": id_pag
                        })
                    else:
                        nova = _preencher_fiado_vazio({
                            "Data": data, "Serviço": servico_norm, "Valor": float(valor), "Conta": conta,
                            "Cliente": cliente, "Combo": "", "Funcionário": funcionario,
                            "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_opcao,
                        })

                    if float(caixinha_dia or 0) > 0:
                        nova["CaixinhaDia"] = float(caixinha_dia or 0)

                    df_final = pd.concat([df_all, pd.DataFrame([nova])], ignore_index=True)
                    salvar_base(df_final)

                    ok_tg = enviar_card(
                        df_final, cliente, funcionario, data,
                        servico=servico_norm, valor=float(nova.get("Valor", 0.0)), combo=""
                    )

                    st.success(
                        f"✅ Atendimento salvo com sucesso para {cliente} no dia {data}."
                        + (" 📲 Notificação enviada." if ok_tg else " ⚠️ Não consegui notificar no Telegram.")
                    )

                    # dispara resumos recalculados
                    try:
                        for _f in ["JPaulo", "Vinicius"]:
                            enviar_resumo_diario(df_final, data, _f)
                        enviar_resumo_geral(df_final, data)
                    except Exception:
                        pass

            except Exception as e:
                st.error(f"❌ Erro ao salvar atendimento: {e}")

# =========================
# MODO LOTE — LAYOUT CLÁSSICO (multiselect + cartões)
# =========================
else:
    st.info("Defina atendimento individual por cliente (misture combos e simples). Também escolha forma de pagamento, período e funcionário para cada um.")

    clientes_multi = st.multiselect("Clientes existentes", clientes_existentes)
    novos_nomes_raw = st.text_area("Ou cole novos nomes (um por linha)", value="")
    novos_nomes = [n.strip() for n in novos_nomes_raw.splitlines() if n.strip()]
    lista_final = list(dict.fromkeys(clientes_multi + novos_nomes))
    st.write(f"Total selecionados: **{len(lista_final)}**")

    enviar_cards = st.checkbox("Enviar card no Telegram após salvar", value=True)

    for cli in lista_final:
        with st.container(border=True):
            foto_url = get_foto_url(cli)
            if foto_url:
                st.image(foto_url, caption=cli, width=200)

            st.subheader(f"⚙️ Atendimento para {cli}")
            sug_conta, sug_periodo, sug_func = sugestoes_do_cliente(
                df_existente, cli, (contas_existentes[0] if contas_existentes else "Carteira"), "Manhã", "JPaulo"
            )

            tipo_at = st.radio(f"Tipo de atendimento para {cli}", ["Simples", "Combo"], horizontal=True, key=f"tipo_{cli}")

            st.selectbox(
                f"Forma de Pagamento de {cli}",
                list(dict.fromkeys([sug_conta] + contas_existentes +
                                   ["Carteira", "Pix", "Transferência", "Nubank CNPJ", "Nubank", "Pagseguro", "Mercado Pago"])),
                key=f"conta_{cli}"
            )

            conta_cli_tmp = st.session_state.get(f"conta_{cli}", "")
            force_off_cli = is_nao_cartao(conta_cli_tmp)

            # --- FIADO (por cliente) ---
            colfl1, colfl2 = st.columns([1,1])
            with colfl1:
                st.checkbox(
                    f"{cli} - 🔖 Fiado?",
                    value=False,
                    key=f"flag_fiado_{cli}",
                    help="Se marcado, lançamento desse cliente será fiado e o cartão desativado."
                )
            with colfl2:
                st.date_input(
                    f"{cli} - Vencimento (fiado)",
                    value=today_local(),
                    key=f"venc_fiado_{cli}"
                )
            fiado_cli = bool(st.session_state.get(f"flag_fiado_{cli}", False))

            cartao_bloqueado_cli = force_off_cli or fiado_cli
            st.checkbox(
                f"{cli} - Tratar como cartão (com taxa)?",
                value=(False if cartao_bloqueado_cli else default_card_flag(conta_cli_tmp)),
                key=f"flag_card_{cli}",
                disabled=cartao_bloqueado_cli,
                help=("Desabilitado para PIX/Dinheiro/Transferência ou se for FIADO." if cartao_bloqueado_cli else None),
            )

            with st.expander(f"💝 Caixinha de {cli} (opcional)", expanded=False):
                st.number_input(f"{cli} - Caixinha do dia", value=0.0, step=1.0, format="%.2f", key=f"cx_dia_{cli}")

            use_card_cli = (not force_off_cli) and (not fiado_cli) and bool(st.session_state.get(f"flag_card_{cli}", False))

            st.selectbox(f"Período do Atendimento de {cli}", ["Manhã", "Tarde", "Noite"],
                         index=["Manhã", "Tarde", "Noite"].index(sug_periodo), key=f"periodo_{cli}")
            st.selectbox(f"Funcionário de {cli}", ["JPaulo", "Vinicius"],
                         index=(0 if sug_func == "JPaulo" else 1), key=f"func_{cli}")

            if tipo_at == "Combo":
                st.selectbox(f"Combo para {cli} (formato corte+barba)", [""] + combos_existentes, key=f"combo_{cli}")
                combo_cli = st.session_state.get(f"combo_{cli}", "")
                if combo_cli:
                    total_padrao = 0.0
                    itens = []
                    for s in combo_cli.split("+"):
                        s2 = s.strip()
                        val = st.number_input(f"{cli} - {s2} (padrão: R$ {obter_valor_servico(s2)})",
                                              value=obter_valor_servico(s2), step=1.0, key=f"valor_{cli}_{s2}")
                        itens.append((s2, val))
                        total_padrao += float(val)

                    if use_card_cli and not is_nao_cartao(st.session_state.get(f"conta_{cli}", "")):
                        with st.expander(f"💳 {cli} - Pagamento no cartão", expanded=True):
                            c1, c2 = st.columns(2)
                            with c1:
                                st.number_input(f"{cli} - Valor recebido (líquido)", value=float(total_padrao), step=1.0, key=f"liq_{cli}")
                                st.selectbox(f"{cli} - Bandeira", ["", "Visa", "Mastercard", "Maestro", "Elo", "Hipercard", "Amex", "Outros"], index=0, key=f"bandeira_{cli}")
                            with c2:
                                st.selectbox(f"{cli} - Tipo", ["Débito", "Crédito"], index=1, key=f"tipo_cartao_{cli}")
                                st.number_input(f"{cli} - Parcelas", min_value=1, max_value=12, value=1, step=1, key=f"parc_{cli}")

                            st.radio(f"{cli} - Distribuição do desconto/taxa",
                                     ["Proporcional (padrão)", "Concentrar em um serviço"],
                                     horizontal=False, key=f"dist_{cli}")
                            if st.session_state.get(f"dist_{cli}", "Proporcional (padrão)") == "Concentrar em um serviço":
                                st.selectbox(f"{cli} - Aplicar TODO o desconto/taxa em",
                                             [nm for (nm, _) in itens], key=f"alvo_{cli}")

            else:
                st.selectbox(
                    f"Serviço simples para {cli}",
                    servicos_ui,
                    index=servicos_ui.index("Corte"),
                    key=f"servico_{cli}_v2"
                )

                serv_cli = st.session_state.get(f"servico_{cli}_v2", None)
                st.number_input(
                    f"{cli} - Valor do serviço",
                    value=(obter_valor_servico(serv_cli) if serv_cli else 0.0),
                    step=1.0,
                    key=f"valor_{cli}_simples"
                )
                if use_card_cli and not is_nao_cartao(st.session_state.get(f"conta_{cli}", "")):
                    with st.expander(f"💳 {cli} - Pagamento no cartão", expanded=True):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.number_input(f"{cli} - Valor recebido (líquido)", value=float(st.session_state.get(f"valor_{cli}_simples", 0.0)), step=1.0, key=f"liq_{cli}")
                            st.selectbox(f"{cli} - Bandeira", ["", "Visa", "Mastercard", "Maestro", "Elo", "Hipercard", "Amex", "Outros"], index=0, key=f"bandeira_{cli}")
                        with c2:
                            st.selectbox(f"{cli} - Tipo", ["Débito", "Crédito"], index=1, key=f"tipo_cartao_{cli}")
                            st.number_input(f"{cli} - Parcelas", min_value=1, max_value=12, value=1, step=1, key=f"parc_{cli}")

    if st.button("💾 Salvar TODOS atendimentos"):
        if not lista_final:
            st.warning("Selecione ou informe ao menos um cliente.")
        else:
            df_all, _ = carregar_base()
            novas, clientes_salvos = [], set()
            funcionario_por_cliente = {}

            for cli in lista_final:
                tipo_at = st.session_state.get(f"tipo_{cli}", "Simples")
                conta_cli = st.session_state.get(f"conta_{cli}", (contas_existentes[0] if contas_existentes else "Carteira"))
                fiado_cli = bool(st.session_state.get(f"flag_fiado_{cli}", False))
                use_card_cli = bool(st.session_state.get(f"flag_card_{cli}", False)) and not is_nao_cartao(conta_cli) and not fiado_cli
                periodo_cli = st.session_state.get(f"periodo_{cli}", "Manhã")
                func_cli = st.session_state.get(f"func_{cli}", "JPaulo")
                cx_dia = float(st.session_state.get(f"cx_dia_{cli}", 0.0) or 0.0)

                if tipo_at == "Combo":
                    combo_cli = st.session_state.get(f"combo_{cli}", "")
                    if not combo_cli:
                        st.warning(f"⚠️ {cli}: combo não definido. Pulando.")
                        continue
                    if any(ja_existe_atendimento(cli, data, _cap_first(s), combo_cli) for s in str(combo_cli).split("+")):
                        st.warning(f"⚠️ {cli}: já existia COMBO em {data}. Pulando.")
                        continue

                    itens = []
                    total_bruto = 0.0
                    for s in str(combo_cli).split("+"):
                        s2_raw = s.strip()
                        s2_norm = _cap_first(s2_raw)
                        val = float(st.session_state.get(f"valor_{cli}_{s2_raw}", obter_valor_servico(s2_norm)))
                        itens.append((s2_raw, s2_norm, val))
                        total_bruto += val

                    id_pag = gerar_pag_id("A") if use_card_cli else ""
                    liq_total_cli = float(st.session_state.get(f"liq_{cli}", total_bruto)) if use_card_cli else total_bruto

                    dist_modo = st.session_state.get(f"dist_{cli}", "Proporcional (padrão)")
                    alvo = st.session_state.get(f"alvo_{cli}", None)
                    soma_outros = None
                    if use_card_cli and dist_modo == "Concentrar em um serviço" and alvo:
                        soma_outros = sum(val for (r, _, val) in itens if r != alvo)

                    primeiro_raw = str(combo_cli).split("+")[0].strip() if "+" in str(combo_cli) else str(combo_cli).strip()

                    # ID fiado para o combo inteiro (se fiado)
                    id_fiado_cli = gerar_id_fiado() if fiado_cli else ""

                    for (s_raw, s_norm, bruto_i) in itens:
                        if fiado_cli:
                            registro = _preencher_fiado_vazio({
                                "Data": data, "Serviço": s_norm, "Valor": float(bruto_i), "Conta": "Fiado",
                                "Cliente": cli, "Combo": combo_cli, "Funcionário": func_cli,
                                "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_cli,
                                "StatusFiado": "Em aberto",
                                "IDLancFiado": id_fiado_cli,
                                "VencimentoFiado": (st.session_state.get(f"venc_fiado_{cli}", today_local()).strftime(DATA_FMT)
                                                    if isinstance(st.session_state.get(f"venc_fiado_{cli}", today_local()), date)
                                                    else str(st.session_state.get(f"venc_fiado_{cli}", today_local()))),
                                "DataPagamento": ""
                            })
                            valor_para_base = float(bruto_i)
                        elif use_card_cli and total_bruto > 0:
                            if dist_modo == "Concentrar em um serviço" and alvo:
                                if s_raw == alvo:
                                    liq_i = liq_total_cli - float(soma_outros or 0.0)
                                    liq_i = round(max(0.0, liq_i), 2)
                                else:
                                    liq_i = round(bruto_i, 2)
                            else:
                                liq_i = round(liq_total_cli * (bruto_i / total_bruto), 2)

                            taxa_i = round(bruto_i - liq_i, 2)
                            taxa_pct_i = (taxa_i / bruto_i * 100.0) if bruto_i > 0 else 0.0
                            registro = _preencher_fiado_vazio({
                                "Data": data, "Serviço": s_norm, "Valor": liq_i, "Conta": conta_cli,
                                "Cliente": cli, "Combo": combo_cli, "Funcionário": func_cli,
                                "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_cli,
                                "ValorBrutoRecebido": bruto_i, "ValorLiquidoRecebido": liq_i,
                                "TaxaCartaoValor": taxa_i, "TaxaCartaoPct": round(taxa_pct_i, 4),
                                "FormaPagDetalhe": f"{st.session_state.get(f'bandeira_{cli}','-')} | {st.session_state.get(f'tipo_cartao_{cli}','Crédito')} | {int(st.session_state.get(f'parc_{cli}',1))}x",
                                "PagamentoID": id_pag
                            })
                            valor_para_base = liq_i
                        else:
                            registro = _preencher_fiado_vazio({
                                "Data": data, "Serviço": s_norm, "Valor": float(bruto_i), "Conta": conta_cli,
                                "Cliente": cli, "Combo": combo_cli, "Funcionário": func_cli,
                                "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_cli,
                            })
                            valor_para_base = float(bruto_i)

                        if s_raw == primeiro_raw and float(cx_dia or 0) > 0:
                            registro["CaixinhaDia"] = float(cx_dia or 0)

                        novas.append(registro)

                    # Ajuste arredondamento (cartão)
                    if use_card_cli and not fiado_cli:
                        indices_cli = [i for i, n in enumerate(novas) if n["Cliente"] == cli and n["Combo"] == combo_cli]
                        soma_liq = sum(float(novas[i]["Valor"]) for i in indices_cli)
                        delta = round(liq_total_cli - soma_liq, 2)
                        if abs(delta) >= 0.01 and indices_cli:
                            idx_ajuste = indices_cli[-1]
                            if dist_modo == "Concentrar em um serviço" and alvo:
                                for i in indices_cli:
                                    if _norm_key(novas[i]["Serviço"]) == _norm_key(_cap_first(alvo)):
                                        idx_ajuste = i; break
                            novas[idx_ajuste]["Valor"] = float(novas[idx_ajuste]["Valor"]) + delta
                            bsel = float(novas[idx_ajuste].get("ValorBrutoRecebido", 0) or 0)
                            lsel = float(novas[idx_ajuste]["Valor"])
                            tsel = round(bsel - lsel, 2)
                            psel = (tsel / bsel * 100.0) if bsel > 0 else 0.0
                            novas[idx_ajuste]["ValorLiquidoRecebido"] = lsel
                            novas[idx_ajuste]["TaxaCartaoValor"] = tsel
                            novas[idx_ajuste]["TaxaCartaoPct"] = round(psel, 4)

                    clientes_salvos.add(cli)
                    funcionario_por_cliente[cli] = func_cli

                else:
                    serv_cli = st.session_state.get(f"servico_{cli}_v2", None)
                    serv_norm = _cap_first(serv_cli) if serv_cli else ""
                    if not serv_norm:
                        st.warning(f"⚠️ {cli}: serviço simples não definido. Pulando."); continue
                    if ja_existe_atendimento(cli, data, serv_norm):
                        st.warning(f"⚠️ {cli}: já existia atendimento simples ({serv_norm}) em {data}. Pulando."); continue
                    bruto = float(st.session_state.get(f"valor_{cli}_simples", obter_valor_servico(serv_norm)))

                    if fiado_cli:
                        registro = _preencher_fiado_vazio({
                            "Data": data, "Serviço": serv_norm, "Valor": bruto, "Conta": "Fiado",
                            "Cliente": cli, "Combo": "", "Funcionário": func_cli,
                            "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_cli,
                            "StatusFiado": "Em aberto",
                            "IDLancFiado": gerar_id_fiado(),
                            "VencimentoFiado": (st.session_state.get(f"venc_fiado_{cli}", today_local()).strftime(DATA_FMT)
                                                if isinstance(st.session_state.get(f"venc_fiado_{cli}", today_local()), date)
                                                else str(st.session_state.get(f"venc_fiado_{cli}", today_local()))),
                            "DataPagamento": ""
                        })
                    elif use_card_cli:
                        liq = float(st.session_state.get(f"liq_{cli}", bruto))
                        taxa_v = round(max(0.0, bruto - liq), 2)
                        taxa_pct = round((taxa_v / bruto * 100.0), 4) if bruto > 0 else 0.0
                        registro = _preencher_fiado_vazio({
                            "Data": data, "Serviço": serv_norm, "Valor": liq, "Conta": conta_cli,
                            "Cliente": cli, "Combo": "", "Funcionário": func_cli,
                            "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_cli,
                            "ValorBrutoRecebido": bruto, "ValorLiquidoRecebido": liq,
                            "TaxaCartaoValor": taxa_v, "TaxaCartaoPct": taxa_pct,
                            "FormaPagDetalhe": f"{st.session_state.get(f'bandeira_{cli}','-')} | {st.session_state.get(f'tipo_cartao_{cli}','Crédito')} | {int(st.session_state.get(f'parc_{cli}',1))}x",
                            "PagamentoID": gerar_pag_id("A"),
                        })
                    else:
                        registro = _preencher_fiado_vazio({
                            "Data": data, "Serviço": serv_norm, "Valor": bruto, "Conta": conta_cli,
                            "Cliente": cli, "Combo": "", "Funcionário": func_cli,
                            "Fase": FASE_PADRAO, "Tipo": TIPO_PADRAO, "Período": periodo_cli,
                        })

                    if float(cx_dia or 0) > 0:
                        registro["CaixinhaDia"] = float(cx_dia or 0)

                    novas.append(registro)

                    clientes_salvos.add(cli)
                    funcionario_por_cliente[cli] = func_cli

            if not novas:
                st.warning("Nenhuma linha válida para inserir.")
            else:
                df_final = pd.concat([df_all, pd.DataFrame(novas)], ignore_index=True)
                try:
                    salvar_base(df_final)
                    st.success(f"✅ {len(novas)} linhas inseridas para {len(clientes_salvos)} cliente(s).")
                    if enviar_cards:
                        for cli in sorted(clientes_salvos):
                            enviar_card(df_final, cli, funcionario_por_cliente.get(cli, "JPaulo"), data)

                    # resumos recalculados (apenas funcionários envolvidos + geral)
                    try:
                        funcs_env = sorted(set(funcionario_por_cliente.values()))
                        for func in funcs_env:
                            enviar_resumo_diario(df_final, data, func)
                        enviar_resumo_geral(df_final, data)
                    except Exception:
                        pass

                except Exception as e:
                    st.error(f"❌ Erro ao salvar em lote: {e}")

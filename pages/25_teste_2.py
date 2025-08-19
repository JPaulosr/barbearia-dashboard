# -*- coding: utf-8 -*-
# 12_Fiado.py — Fiado + Telegram (foto + card), por funcionário + cópia p/ JP
# - NUNCA limpa a base ao lançar fiado: usa append_rows
# - Quitar por COMPETÊNCIA com atualização mínima (sem clear da planilha)
# - Notificações com FOTO (se existir) e card HTML
# - Roteamento: Vinícius → canal; JPaulo → privado
# - Cópia privada p/ JP ao quitar: comissões (somente elegíveis) + próxima terça p/ pagar
# - Cards incluem “🧰 Serviço(s)” (combo se houver; senão serviços) — sem ID
# - Cópia p/ JP inclui “Histórico por ano” e “Ano corrente: por serviço (qtd × total)”
# - 💳 Bloco de taxa do cartão (líquido → taxa R$ e %), log em Obs e na aba Cartao_Taxas

import streamlit as st
import pandas as pd
import gspread
import requests
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from gspread.utils import rowcol_to_a1
from datetime import date, datetime, timedelta
from io import BytesIO
import pytz
import unicodedata

# =========================
# TELEGRAM
# =========================
TELEGRAM_TOKEN_CONST = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
TELEGRAM_CHAT_ID_JPAULO_CONST = "493747253"
TELEGRAM_CHAT_ID_VINICIUS_CONST = "-1002953102982"  # canal do Vinícius

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
    if str(funcionario).strip() == "Vinicius":
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
        data = {"chat_id": chat, "photo": photo_url, "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=data, timeout=30)
        js = r.json()
        if r.ok and js.get("ok"):
            return True
        return tg_send(caption, chat_id=chat)
    except Exception:
        return tg_send(caption, chat_id=chat)

# =========================
# FOTOS (clientes_status)
# =========================
STATUS_ABA = "clientes_status"
FOTO_COL_CANDIDATES = ["link_foto", "foto", "imagem", "url_foto", "foto_link", "link", "image"]

def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

@st.cache_data(show_spinner=False)
def carregar_fotos_mapa():
    """NÃO recebe função; cria conexão internamente para evitar UnhashableParamError."""
    try:
        sh = conectar_sheets()
        if STATUS_ABA not in [w.title for w in sh.worksheets()]:
            return {}
        ws = sh.worksheet(STATUS_ABA)
        df = get_as_dataframe(ws).fillna("")
        df.columns = [str(c).strip() for c in df.columns]
        cols_lower = {c.lower(): c for c in df.columns}
        foto_col = next((cols_lower[c] for c in FOTO_COL_CANDIDATES if c in cols_lower), None)
        cli_col  = next((cols_lower[c] for c in ["cliente","nome","nome_cliente"] if c in cols_lower), None)
        if not (foto_col and cli_col):
            return {}
        tmp = df[[cli_col, foto_col]].copy()
        tmp.columns = ["Cliente", "Foto"]
        tmp["k"] = tmp["Cliente"].astype(str).map(_norm)
        return {r["k"]: str(r["Foto"]).strip()
                for _, r in tmp.iterrows() if str(r["Foto"]).strip()}
    except Exception:
        return {}

# =========================
# UTILS
# =========================
def proxima_terca(d: date) -> date:
    """Retorna a próxima TERÇA-FEIRA a partir de d (se for terça, retorna d)."""
    wd = d.weekday()  # Monday=0, Tuesday=1, ..., Sunday=6
    delta = (1 - wd) % 7
    return d + timedelta(days=delta)

def _fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def _fmt_pct(p: float) -> str:
    try:
        return f"{p:.2f}%"
    except Exception:
        return "-"

def _norm_key(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s).strip()).casefold()

def col_map(ws):
    """Mapeia nome de coluna -> número (1-based) a partir do cabeçalho da worksheet."""
    headers = ws.row_values(1)
    return {h.strip(): i+1 for i, h in enumerate(headers)}

def append_rows_generic(ws, dicts, default_headers=None):
    """Append robusto por cabeçalho (trim+casefold). Útil para planilhas diversas."""
    headers = ws.row_values(1)
    if not headers:
        headers = default_headers or sorted({k for d in dicts for k in d.keys()})
        ws.append_row(headers)
    hdr_norm = [_norm_key(h) for h in headers]
    rows = []
    for d in dicts:
        d_norm = {_norm_key(k): v for k, v in d.items()}
        rows.append([d_norm.get(hn, "") for hn in hdr_norm])
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")

def update_fiados_pagamento(ws, df_base: pd.DataFrame, mask, forma_pag: str, data_pag_str: str):
    """Atualiza somente colunas necessárias nas linhas do DF que correspondem ao mask."""
    cmap = col_map(ws)
    c_conta    = cmap.get("Conta")
    c_status   = cmap.get("StatusFiado")
    c_venc     = cmap.get("VencimentoFiado")
    c_data_pag = cmap.get("DataPagamento")
    assert all([c_conta, c_status, c_venc, c_data_pag]), "Cabeçalho ausente nas colunas de Fiado."
    data_updates = []
    for idx in df_base.index[mask]:
        row_no = int(idx) + 2  # 1 linha de cabeçalho
        data_updates.append({"range": rowcol_to_a1(row_no, c_conta),    "values": [[forma_pag]]})
        data_updates.append({"range": rowcol_to_a1(row_no, c_status),   "values": [["Pago"]]})
        data_updates.append({"range": rowcol_to_a1(row_no, c_venc),     "values": [[""]]})
        data_updates.append({"range": rowcol_to_a1(row_no, c_data_pag), "values": [[data_pag_str]]})
    if data_updates:
        ws.batch_update(data_updates, value_input_option="USER_ENTERED")

def contains_cartao(s: str) -> bool:
    s = (s or "").strip().lower()
    return "cart" in s  # pega "Cartão", "Cartao", etc.

# Texto: serviços sem ID (por ID selecionado)
def servicos_compactos_por_ids(df_rows: pd.DataFrame) -> str:
    """
    Retorna apenas os serviços por ID, sem prefixar com o ID.
    - Se o ID tiver Combo, usa o Combo.
    - Senão, junta os serviços distintos do ID com '+'.
    - Se houver vários IDs, junta cada bloco com ' | '.
    """
    if df_rows.empty:
        return "-"
    partes = []
    for _, grp in df_rows.groupby("IDLancFiado"):
        combo_vals = grp["Combo"].dropna().astype(str).str.strip()
        combo_vals = combo_vals[combo_vals != ""]
        if not combo_vals.empty:
            partes.append(combo_vals.iloc[0])
        else:
            servs = sorted(set(grp["Serviço"].dropna().astype(str).str.strip().tolist()))
            partes.append("+".join(servs) if servs else "-")
    partes = [p for p in partes if p]
    vistos, out = [], []
    for p in partes:
        if p and p not in vistos:
            vistos.append(p)
            out.append(p)
    return " | ".join(out) if out else "-"

# --- Histórico por ano e breakdown ---
def historico_cliente_por_ano(df_base: pd.DataFrame, cliente: str) -> dict[int, float]:
    if df_base is None or df_base.empty or not cliente:
        return {}
    df = df_base.copy()
    df["__dt"] = pd.to_datetime(df["Data"], format="%d/%m/%Y", errors="coerce")
    df["__valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
    df = df[(df["Cliente"].astype(str).str.strip() == str(cliente).strip()) & df["__dt"].notna()]
    if df.empty:
        return {}
    grp = df.groupby(df["__dt"].dt.year)["__valor"].sum().to_dict()
    return {int(ano): float(round(v, 2)) for ano, v in grp.items()}

def ano_da_data_str(dstr: str, fmt: str = "%d/%m/%Y") -> int | None:
    try:
        return datetime.strptime(dstr, fmt).year
    except Exception:
        return None

def breakdown_por_servico_no_ano(df_base: pd.DataFrame, cliente: str, ano: int,
                                 max_itens: int = 8):
    if df_base is None or df_base.empty or not cliente or not ano:
        return pd.DataFrame(columns=["Serviço","Qtd","Total"]), 0, 0.0, 0, 0.0
    df = df_base.copy()
    df["__dt"] = pd.to_datetime(df["Data"], format="%d/%m/%Y", errors="coerce")
    df["__valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
    df = df[(df["Cliente"].astype(str).str.strip() == str(cliente).strip()) & (df["__dt"].dt.year == ano)]
    if df.empty:
        return pd.DataFrame(columns=["Serviço","Qtd","Total"]), 0, 0.0, 0, 0.0
    agg = (df.groupby("Serviço", dropna=True)
             .agg(Qtd=("Serviço","count"), Total=("__valor","sum"))
             .reset_index())
    agg = agg.sort_values("Total", ascending=False)
    total_qtd = int(agg["Qtd"].sum())
    total_val = float(agg["Total"].sum())
    top = agg.head(max_itens).copy()
    outros = agg.iloc[max_itens:] if len(agg) > max_itens else pd.DataFrame(columns=agg.columns)
    outros_qtd = int(outros["Qtd"].sum()) if not outros.empty else 0
    outros_val = float(outros["Total"].sum()) if not outros.empty else 0.0
    top["Qtd"] = top["Qtd"].astype(int)
    top["Total"] = top["Total"].astype(float).round(2)
    return top, total_qtd, total_val, outros_qtd, outros_val

# =========================
# APP / SHEETS
# =========================
st.set_page_config(page_title="Fiado | Salão JP", page_icon="💳", layout="wide",
                   initial_sidebar_state="expanded")
st.title("💳 Controle de Fiado (combo por linhas + edição de valores)")

SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_LANC = "Fiado_Lancamentos"
ABA_PAGT = "Fiado_Pagamentos"
ABA_TAXAS = "Cartao_Taxas"  # NOVO: log (opcional) das taxas por pagamento

TZ = pytz.timezone("America/Sao_Paulo")
DATA_FMT = "%d/%m/%Y"

BASE_COLS_MIN = ["Data","Serviço","Valor","Conta","Cliente","Combo","Funcionário","Fase","Tipo","Período"]
EXTRA_COLS    = ["StatusFiado","IDLancFiado","VencimentoFiado","DataPagamento"]
BASE_COLS_ALL = BASE_COLS_MIN + EXTRA_COLS

VALORES_PADRAO = {
    "Corte": 25.0, "Pezinho": 7.0, "Barba": 15.0, "Sobrancelha": 7.0,
    "Luzes": 45.0, "Pintura": 35.0, "Alisamento": 40.0, "Gel": 10.0, "Pomada": 15.0
}

# Comissão (somente p/ elegíveis)
COMISSAO_FUNCIONARIOS = {"vinicius"}   # case-insensitive
COMISSAO_PERC_PADRAO = 0.50

# Cabeçalho padrão da aba Cartao_Taxas
TAXAS_COLS = [
    "IDPagamento","Cliente","DataPag","Bandeira","Tipo","Parcelas",
    "Bruto","Liquido","TaxaValor","TaxaPct","IDLancs"
]

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def garantir_aba(ss, nome, cols):
    """Garante a aba com cabeçalho (NÃO limpa se já existir)."""
    try:
        ws = ss.worksheet(nome)
    except gspread.WorksheetNotFound:
        ws = ss.add_worksheet(title=nome, rows=200, cols=max(10, len(cols)))
        ws.append_row(cols)
        return ws
    existing = ws.row_values(1)
    if not existing:
        ws.append_row(cols)
    return ws

def read_base_raw(ss):
    """Lê a 'Base de Dados' SEM dropna, preservando todas as linhas/colunas."""
    ws = garantir_aba(ss, ABA_BASE, BASE_COLS_ALL)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    for c in BASE_COLS_ALL:
        if c not in df.columns:
            df[c] = ""
    df = df[[*BASE_COLS_ALL, *[c for c in df.columns if c not in BASE_COLS_ALL]]]
    return df, ws

# Append robusto na BASE (aceita cabeçalhos com variação)
def append_rows_base(ws, novas_dicts):
    headers = ws.row_values(1)
    if not headers:
        headers = BASE_COLS_ALL
        ws.append_row(headers)
    hdr_norm = [_norm_key(h) for h in headers]
    rows = []
    for d in novas_dicts:
        d_norm = {_norm_key(k): v for k, v in d.items()}
        rows.append([d_norm.get(hn, "") for hn in hdr_norm])
    if rows:
        ws.append_rows(rows, value_input_option="USER_ENTERED")

@st.cache_data
def carregar_listas():
    ss = conectar_sheets()
    ws_base = garantir_aba(ss, ABA_BASE, BASE_COLS_ALL)
    df_list = get_as_dataframe(ws_base, evaluate_formulas=True, header=0).fillna("")
    df_list.columns = [str(c).strip() for c in df_list.columns]
    clientes = sorted([c for c in df_list.get("Cliente", "").astype(str).str.strip().unique() if c])
    combos  = sorted([c for c in df_list.get("Combo", "").astype(str).str.strip().unique() if c])
    servs   = sorted([s for s in df_list.get("Serviço","").astype(str).str.strip().unique() if s])
    contas_raw = [c for c in df_list.get("Conta","").astype(str).str.strip().unique() if c]
    contas = sorted([c for c in contas_raw if c.lower() != "fiado"])
    return clientes, combos, servs, contas

def append_row(nome_aba, vals):
    ss = conectar_sheets()
    ss.worksheet(nome_aba).append_row(vals, value_input_option="USER_ENTERED")

def gerar_id(prefixo):
    return f"{prefixo}-{datetime.now(TZ).strftime('%Y%m%d%H%M%S%f')[:-3]}"

def parse_combo(combo_str):
    if not combo_str:
        return []
    partes = [p.strip() for p in str(combo_str).split("+") if p.strip()]
    ajustadas = []
    for p in partes:
        hit = next((k for k in VALORES_PADRAO.keys() if k.lower() == p.lower()), p)
        ajustadas.append(hit)
    return ajustadas

def ultima_forma_pagto_cliente(df_base, cliente):
    if df_base.empty or not cliente:
        return None
    df = df_base[(df_base["Cliente"] == cliente) & (df_base["Conta"].str.lower() != "fiado")].copy()
    if df.empty:
        return None
    try:
        df["__d"] = pd.to_datetime(df["Data"], format=DATA_FMT, errors="coerce")
        df = df.sort_values("__d", ascending=False)
    except Exception:
        pass
    return str(df.iloc[0]["Conta"]) if not df.empty else None

# ===== Caches
clientes, combos_exist, servs_exist, contas_exist = carregar_listas()
FOTOS = carregar_fotos_mapa()

st.sidebar.header("Ações")
acao = st.sidebar.radio("Escolha:", ["➕ Lançar fiado","💰 Registrar pagamento","📋 Em aberto & exportação"])

# ---------- 1) Lançar fiado ----------
if acao == "➕ Lançar fiado":
    st.subheader("➕ Lançar fiado — cria UMA linha por serviço na Base (Conta='Fiado', StatusFiado='Em aberto')")

    c1, c2 = st.columns(2)
    with c1:
        cliente = st.selectbox("Cliente", options=[""] + clientes, index=0)
        if not cliente:
            cliente = st.text_input("Ou digite o nome do cliente", "")
        combo_str = st.selectbox("Combo (use 'corte+barba')", [""] + combos_exist)
        servico_unico = st.selectbox("Ou selecione um serviço (se não usar combo)", [""] + servs_exist)
        funcionario = st.selectbox("Funcionário", ["JPaulo", "Vinicius"], index=0)
    with c2:
        data_atend = st.date_input("Data do atendimento", value=date.today())
        venc = st.date_input("Vencimento (opcional)", value=date.today())
        fase = st.text_input("Fase", value="Dono + funcionário")
        tipo = st.selectbox("Tipo", ["Serviço", "Produto"], index=0)
        periodo = st.selectbox("Período (opcional)", ["", "Manhã", "Tarde", "Noite"], index=0)

    servicos = parse_combo(combo_str) if combo_str else ([servico_unico] if servico_unico else [])
    valores_custom = {}
    if servicos:
        st.markdown("#### 💰 Edite os valores antes de salvar")
        for s in servicos:
            padrao = VALORES_PADRAO.get(s, 0.0)
            valores_custom[s] = st.number_input(
                f"{s} (padrão: R$ {padrao:.2f})", value=float(padrao), step=1.0, format="%.2f", key=f"valor_{s}"
            )

    if st.button("Salvar fiado", use_container_width=True):
        if not cliente:
            st.error("Informe o cliente.")
        elif not servicos:
            st.error("Informe combo ou um serviço.")
        else:
            idl = gerar_id("L")
            data_str = data_atend.strftime(DATA_FMT)
            venc_str = venc.strftime(DATA_FMT) if venc else ""

            novas = []
            for s in servicos:
                valor_item = float(valores_custom.get(s, VALORES_PADRAO.get(s, 0.0)))
                novas.append({
                    "Data": data_str, "Serviço": s, "Valor": valor_item, "Conta": "Fiado",
                    "Cliente": cliente, "Combo": combo_str if combo_str else "", "Funcionário": funcionario,
                    "Fase": fase, "Tipo": tipo, "Período": periodo,
                    "StatusFiado": "Em aberto", "IDLancFiado": idl, "VencimentoFiado": venc_str,
                    "DataPagamento": ""
                })

            ss = conectar_sheets()
            ws_base = garantir_aba(ss, ABA_BASE, BASE_COLS_ALL)
            append_rows_base(ws_base, novas)

            total = float(pd.to_numeric(pd.DataFrame(novas)["Valor"], errors="coerce").fillna(0).sum())
            append_row(ABA_LANC, [idl, data_str, cliente, combo_str, "+".join(servicos),
                                  total, venc_str, funcionario, fase, tipo, periodo])

            st.success(f"Fiado criado para **{cliente}** — ID: {idl}. Geradas {len(novas)} linhas na Base.")
            st.cache_data.clear()

            # Notificação: novo fiado
            try:
                total_fmt = _fmt_brl(total)
                servicos_txt = combo_str.strip() if (combo_str and combo_str.strip()) else ("+".join(servicos) if servicos else "-")
                msg_html = (
                    "🧾 <b>Novo fiado criado</b>\n"
                    f"👤 Cliente: <b>{cliente}</b>\n"
                    f"🧰 Serviço(s): <b>{servicos_txt}</b>\n"
                    f"💵 Total: <b>{total_fmt}</b>\n"
                    f"📅 Atendimento: {data_str}\n"
                    f"⏳ Vencimento: {venc_str or '-'}\n"
                    f"🆔 ID: <code>{idl}</code>"
                )
                chat_dest = _chat_id_por_func(funcionario)
                foto = FOTOS.get(_norm(cliente))
                if foto:
                    tg_send_photo(foto, msg_html, chat_id=chat_dest)
                else:
                    tg_send(msg_html, chat_id=chat_dest)
            except Exception:
                pass

# ---------- 2) Registrar pagamento (COMPETÊNCIA) ----------
elif acao == "💰 Registrar pagamento":
    st.subheader("💰 Registrar pagamento — escolha o cliente e depois o(s) fiado(s) em aberto")

    ss = conectar_sheets()
    df_base_full, ws_base = read_base_raw(ss)

    df_abertos = df_base_full[df_base_full.get("StatusFiado", "") == "Em aberto"].copy()
    clientes_abertos = sorted(df_abertos["Cliente"].dropna().astype(str).str.strip().unique().tolist())

    colc1, colc2 = st.columns([1, 1])
    with colc1:
        cliente_sel = st.selectbox("Cliente com fiado em aberto", options=[""] + clientes_abertos, index=0)

    ultima = ultima_forma_pagto_cliente(df_base_full, cliente_sel) if cliente_sel else None
    lista_contas = contas_exist or ["Pix", "Dinheiro", "Cartão", "Transferência", "Outro"]
    default_idx = lista_contas.index(ultima) if (ultima in lista_contas) else 0
    with colc2:
        forma_pag = st.selectbox("Forma de pagamento (quitação)", options=lista_contas, index=default_idx)

    # IDs do cliente com rótulo amigável
    ids_opcoes = []
    if cliente_sel:
        grupo_cli = df_abertos[df_abertos["Cliente"].astype(str).str.strip() == str(cliente_sel).strip()].copy()
        grupo_cli["Data"] = pd.to_datetime(grupo_cli["Data"], format=DATA_FMT, errors="coerce").dt.strftime(DATA_FMT)
        grupo_cli["Valor"] = pd.to_numeric(grupo_cli["Valor"], errors="coerce").fillna(0)

        def atraso_max(idval):
            v = grupo_cli.loc[grupo_cli["IDLancFiado"] == idval, "VencimentoFiado"].dropna().astype(str)
            try:
                vdt = pd.to_datetime(v.iloc[0], format=DATA_FMT, errors="coerce").date() if not v.empty else None
            except Exception:
                vdt = None
            if vdt:
                d = (date.today() - vdt).days
                return d if d > 0 else 0
            return 0

        resumo_ids = (
            grupo_cli.groupby("IDLancFiado", as_index=False)
            .agg(Data=("Data", "min"), ValorTotal=("Valor", "sum"), Qtde=("Serviço", "count"), Combo=("Combo", "first"))
        )
        for _, r in resumo_ids.iterrows():
            atraso = atraso_max(r["IDLancFiado"])
            badge = "Em dia" if atraso <= 0 else f"{int(atraso)}d atraso"
            rotulo = f"{r['IDLancFiado']} • {r['Data']} • {int(r['Qtde'])} serv. • R$ {r['ValorTotal']:.2f} • {badge}"
            if pd.notna(r["Combo"]) and str(r["Combo"]).strip():
                rotulo += f" • {r['Combo']}"
            ids_opcoes.append((r["IDLancFiado"], rotulo))

    ids_valores = [i[0] for i in ids_opcoes]
    labels = {i: l for i, l in ids_opcoes}

    select_all = st.checkbox("Selecionar todos os fiados deste cliente", value=False, disabled=not bool(ids_valores))
    id_selecionados = st.multiselect(
        "Selecione 1 ou mais fiados do cliente",
        options=ids_valores,
        default=(ids_valores if select_all else []),
        format_func=lambda x: labels.get(x, x),
    )

    cold1, cold2 = st.columns([1, 1])
    with cold1:
        data_pag = st.date_input("Data do pagamento", value=date.today())
    with cold2:
        obs = st.text_input("Observação (opcional)", "")

    total_sel = 0.0
    funcs_envio = []  # funcionários envolvidos nos IDs (para roteamento Telegram)

    # 💳 estado do bloco de cartão
    valor_liquido_cartao = None
    bandeira_cartao = ""
    tipo_cartao = "Crédito"
    parcelas_cartao = 1
    taxa_valor_est = 0.0
    taxa_pct_est = 0.0

    if id_selecionados:
        subset = df_abertos[df_abertos["IDLancFiado"].isin(id_selecionados)].copy()
        subset["Valor"] = pd.to_numeric(subset["Valor"], errors="coerce").fillna(0)
        total_sel = float(subset["Valor"].sum())

        st.info(
            f"Cliente: **{cliente_sel}** • IDs: {', '.join(id_selecionados)} • "
            f"Total bruto selecionado: **{_fmt_brl(total_sel)}**"
        )

        # 💳 Detalhes do cartão (opcional)
        if contains_cartao(forma_pag):
            with st.expander("💳 Detalhes do cartão (opcional)", expanded=True):
                cdc1, cdc2 = st.columns([1,1])
                with cdc1:
                    valor_liquido_cartao = st.number_input(
                        "Valor recebido (líquido da maquininha)",
                        value=float(total_sel),
                        step=1.0, format="%.2f"
                    )
                    bandeira_cartao = st.selectbox(
                        "Bandeira", ["", "Visa", "Mastercard", "Elo", "Hipercard", "Amex", "Outros"], index=0
                    )
                with cdc2:
                    tipo_cartao = st.selectbox("Tipo", ["Débito", "Crédito"], index=1)
                    parcelas_cartao = st.number_input("Parcelas (se crédito)", min_value=1, max_value=12, value=1, step=1)

                taxa_valor_est = max(0.0, float(total_sel) - float(valor_liquido_cartao or 0.0))
                taxa_pct_est = (taxa_valor_est / float(total_sel) * 100.0) if total_sel > 0 else 0.0

                st.metric("Taxa estimada", _fmt_brl(taxa_valor_est), _fmt_pct(taxa_pct_est))

        resumo_srv = (
            subset.groupby("Serviço", as_index=False)
            .agg(Qtd=("Serviço", "count"), Total=("Valor", "sum"))
            .sort_values(["Qtd", "Total"], ascending=[False, False])
        )
        resumo_srv["Total"] = resumo_srv["Total"].map(_fmt_brl)
        st.caption("Resumo por serviço selecionado:")
        st.dataframe(resumo_srv, use_container_width=True, hide_index=True)

        funcs_envio = (
            subset["Funcionário"].dropna().astype(str).str.strip().str.lower().unique().tolist()
        )

    disabled_btn = not (cliente_sel and id_selecionados and forma_pag)
    if st.button("Registrar pagamento", use_container_width=True, disabled=disabled_btn):
        # Recarrega BASE crua e worksheet
        dfb, ws_base2 = read_base_raw(ss)

        # máscara para os IDs selecionados
        mask = dfb.get("IDLancFiado", "").isin(id_selecionados)
        if not mask.any():
            st.error("Nenhuma linha encontrada para os IDs selecionados.")
        else:
            subset_all = dfb[mask].copy()
            subset_all["Valor"] = pd.to_numeric(subset_all["Valor"], errors="coerce").fillna(0)
            total_pago = float(subset_all["Valor"].sum())

            # Atualiza apenas colunas necessárias
            data_pag_str = data_pag.strftime(DATA_FMT)

            # ---------- 💳 Cartão: prepara info de taxa / log opcional ----------
            cartao_info_txt = ""
            obs_extra = ""
            id_pag = f"P-{datetime.now(TZ).strftime('%Y%m%d%H%M%S%f')[:-3]}"

            if contains_cartao(forma_pag) and (valor_liquido_cartao is not None):
                liquido = float(valor_liquido_cartao or 0.0)
                taxa_valor = max(0.0, total_pago - liquido)
                taxa_pct = (taxa_valor / total_pago * 100.0) if total_pago > 0 else 0.0

                cartao_info_txt = (
                    f"💳 Cartão — Bandeira: {bandeira_cartao or '-'} | "
                    f"Tipo: {tipo_cartao} | Parcelas: {int(parcelas_cartao)}\n"
                    f"Bruto: {_fmt_brl(total_pago)} | Líquido: {_fmt_brl(liquido)} | "
                    f"Taxa: {_fmt_brl(taxa_valor)} ({_fmt_pct(taxa_pct)})"
                )
                obs_extra = (
                    f"[Cartão] Bruto={_fmt_brl(total_pago)}; Líquido={_fmt_brl(liquido)}; "
                    f"Taxa={_fmt_brl(taxa_valor)} ({_fmt_pct(taxa_pct)}); "
                    f"Bandeira={bandeira_cartao or '-'}; Tipo={tipo_cartao}; Parcelas={int(parcelas_cartao)}"
                )

                # Loga linha na aba Cartao_Taxas
                try:
                    ws_taxas = garantir_aba(ss, ABA_TAXAS, TAXAS_COLS)
                    append_rows_generic(ws_taxas, [{
                        "IDPagamento": id_pag,
                        "Cliente": cliente_sel,
                        "DataPag": data_pag_str,
                        "Bandeira": bandeira_cartao,
                        "Tipo": tipo_cartao,
                        "Parcelas": int(parcelas_cartao),
                        "Bruto": total_pago,
                        "Liquido": liquido,
                        "TaxaValor": round(taxa_valor, 2),
                        "TaxaPct": round(taxa_pct, 4),
                        "IDLancs": ";".join(id_selecionados),
                    }], default_headers=TAXAS_COLS)
                except Exception:
                    pass  # não bloqueia a quitação

            # Faz a atualização de competência na BASE
            update_fiados_pagamento(ws_base2, dfb, mask, forma_pag, data_pag_str)

            # Salva na aba Fiado_Pagamentos com observação (inclui cartão se houver)
            obs_final = (obs or "").strip()
            if obs_extra:
                obs_final = f"{obs_final + '; ' if obs_final else ''}{obs_extra}"

            append_row(
                ABA_PAGT,
                [
                    id_pag,
                    ";".join(id_selecionados),
                    data_pag_str,
                    cliente_sel,
                    forma_pag,
                    total_pago,
                    obs_final,
                ],
            )

            st.success(
                f"Pagamento registrado para **{cliente_sel}** (competência). "
                f"IDs quitados: {', '.join(id_selecionados)}. "
                f"Total: {_fmt_brl(total_pago)}"
            )
            st.cache_data.clear()

            # ---------- Notificação: pagamento registrado ----------
            try:
                servicos_txt = servicos_compactos_por_ids(subset_all)
                tot_fmt = _fmt_brl(total_pago)
                ids_txt = ", ".join(id_selecionados)

                msg_html = (
                    "✅ <b>Fiado quitado (competência)</b>\n"
                    f"👤 Cliente: <b>{cliente_sel}</b>\n"
                    f"🧰 Serviço(s): <b>{servicos_txt}</b>\n"
                    f"💳 Forma: <b>{forma_pag}</b>\n"
                    f"💵 Total pago (bruto): <b>{tot_fmt}</b>\n"
                    f"📅 Data pagto: {data_pag_str}\n"
                    f"🗂️ IDs: <code>{ids_txt}</code>\n"
                    f"📝 Obs: {obs or '-'}"
                )
                if cartao_info_txt:
                    msg_html += "\n" + cartao_info_txt

                destinos = set()
                for f in funcs_envio:
                    destinos.add(_chat_id_por_func(f.title()))
                if not destinos:
                    destinos = {_get_chat_id_jp()}
                foto = FOTOS.get(_norm(cliente_sel))
                for chat in destinos:
                    if foto:
                        tg_send_photo(foto, msg_html, chat_id=chat)
                    else:
                        tg_send(msg_html, chat_id=chat)
            except Exception:
                pass

            # ---------- Cópia privada para JP: comissão (somente elegíveis) + cartão + histórico ----------
            try:
                sub = subset_all.copy()
                sub["Valor"] = pd.to_numeric(sub["Valor"], errors="coerce").fillna(0.0)

                # Comissão só para funcionários elegíveis (ex.: Vinicius)
                grup = sub.groupby("Funcionário", dropna=True)["Valor"].sum().reset_index()
                itens_comissao = []
                total_comissao = 0.0
                for _, r in grup.iterrows():
                    func_raw = str(r["Funcionário"]).strip()
                    func_key = unicodedata.normalize("NFKC", func_raw).casefold()
                    if func_key not in COMISSAO_FUNCIONARIOS:
                        continue
                    base = float(r["Valor"])
                    comiss = round(base * COMISSAO_PERC_PADRAO, 2)
                    total_comissao += comiss
                    itens_comissao.append(f"• {func_raw}: <b>{_fmt_brl(comiss)}</b>")

                sec_comissao = ""
                if itens_comissao:
                    dt_pgto = proxima_terca(data_pag)
                    lista = "\n".join(itens_comissao)
                    sec_comissao = (
                        "\n------------------------------\n"
                        f"💸 <b>Comissões sugeridas ({int(COMISSAO_PERC_PADRAO*100)}%)</b>\n"
                        f"{lista}\n"
                        f"📌 Pagar comissão na próxima terça: <b>{dt_pgto.strftime(DATA_FMT)}</b>"
                    )

                # Histórico por ano do cliente
                ss_priv = conectar_sheets()
                df_priv, _ = read_base_raw(ss_priv)
                hist = historico_cliente_por_ano(df_priv, cliente_sel)
                if hist:
                    anos_ord = sorted(hist.keys(), reverse=True)
                    linhas_hist = "\n".join(f"• {ano}: <b>{_fmt_brl(hist[ano])}</b>" for ano in anos_ord)
                    bloco_hist = "\n------------------------------\n📚 <b>Histórico por ano</b>\n" + linhas_hist
                else:
                    bloco_hist = "\n------------------------------\n📚 <b>Histórico por ano</b>\n• (sem registros)"

                # Breakdown do ano do pagamento
                ano_corrente = data_pag.year
                df_priv2, _ = read_base_raw(ss_priv)
                brk, tq, tv, oq, ov = breakdown_por_servico_no_ano(df_priv2, cliente_sel, ano_corrente, max_itens=8)
                if not brk.empty:
                    linhas_srv = "\n".join(
                        f"• {r['Serviço']}: {int(r['Qtd'])}× · <b>{_fmt_brl(float(r['Total']))}</b>"
                        for _, r in brk.iterrows()
                    )
                    if oq > 0:
                        linhas_srv += f"\n• Outros: {oq}× · <b>{_fmt_brl(ov)}</b>"
                    bloco_srv = (
                        f"\n------------------------------\n🔎 <b>{ano_corrente}: por serviço</b>\n{linhas_srv}\n"
                        f"Total ({ano_corrente}): <b>{_fmt_brl(tv)}</b>"
                    )
                else:
                    bloco_srv = f"\n------------------------------\n🔎 <b>{ano_corrente}: por serviço</b>\n• (sem registros)"

                servicos_txt = servicos_compactos_por_ids(subset_all)
                tot_fmt = _fmt_brl(float(sub["Valor"].sum()))
                ids_txt = ", ".join(id_selecionados)

                msg_jp = (
                    "🧾 <b>Cópia para controle</b>\n"
                    f"👤 Cliente: <b>{cliente_sel}</b>\n"
                    f"🧰 Serviço(s): <b>{servicos_txt}</b>\n"
                    f"🗂️ IDs: <code>{ids_txt}</code>\n"
                    f"📅 Pagamento em: <b>{data_pag_str}</b>\n"
                    f"💳 Forma: <b>{forma_pag}</b>\n"
                    f"💵 Total recebido (bruto): <b>{tot_fmt}</b>"
                )
                if cartao_info_txt:
                    msg_jp += "\n" + cartao_info_txt
                msg_jp += sec_comissao + bloco_hist + bloco_srv

                foto = FOTOS.get(_norm(cliente_sel))
                if foto:
                    tg_send_photo(foto, msg_jp, chat_id=_get_chat_id_jp())
                else:
                    tg_send(msg_jp, chat_id=_get_chat_id_jp())
            except Exception:
                pass

# ---------- 3) Em aberto & exportação ----------
else:
    st.subheader("📋 Fiados em aberto (agrupados por ID)")
    ss = conectar_sheets()
    df_base_full, _ = read_base_raw(ss)

    if df_base_full.empty:
        st.info("Sem dados.")
    else:
        em_aberto = df_base_full[df_base_full.get("StatusFiado","") == "Em aberto"].copy()
        if em_aberto.empty:
            st.success("Nenhum fiado em aberto 🎉")
        else:
            colf1, colf2 = st.columns([2,1])
            with colf1:
                filtro_cliente = st.text_input("Filtrar por cliente (opcional)", "")
                if filtro_cliente.strip():
                    em_aberto = em_aberto[
                        em_aberto["Cliente"].astype(str).str.contains(filtro_cliente.strip(), case=False, na=False)
                    ]
            with colf2:
                funcionarios_abertos = sorted(
                    em_aberto["Funcionário"].dropna().astype(str).unique().tolist()
                )
                filtro_func = st.selectbox("Filtrar por funcionário (opcional)", [""] + funcionarios_abertos)
                if filtro_func:
                    em_aberto = em_aberto[em_aberto["Funcionário"] == filtro_func]

            hoje = date.today()
            def parse_dt(x):
                try:
                    return datetime.strptime(str(x), DATA_FMT).date()
                except Exception:
                    return None
            em_aberto["__venc"] = em_aberto["VencimentoFiado"].apply(parse_dt)
            em_aberto["DiasAtraso"] = em_aberto["__venc"].apply(
                lambda d: (hoje - d).days if (d is not None and hoje > d) else 0
            )
            em_aberto["Situação"] = em_aberto["DiasAtraso"].apply(lambda n: "Em dia" if n<=0 else f"{int(n)}d atraso")

            em_aberto["Valor"] = pd.to_numeric(em_aberto["Valor"], errors="coerce").fillna(0)
            resumo = (
                em_aberto.groupby(["IDLancFiado","Cliente"], as_index=False)
                .agg(ValorTotal=("Valor","sum"), QtdeServicos=("Serviço","count"),
                     Combo=("Combo","first"), MaxAtraso=("DiasAtraso","max"))
            )
            resumo["Situação"] = resumo["MaxAtraso"].apply(lambda n: "Em dia" if n<=0 else f"{int(n)}d atraso")

            st.dataframe(
                resumo.sort_values(["MaxAtraso","ValorTotal"], ascending=[False, False])[[
                    "IDLancFiado","Cliente","ValorTotal","QtdeServicos","Combo","Situação"
                ]],
                use_container_width=True, hide_index=True
            )

            total = float(resumo["ValorTotal"].sum())
            st.metric("Total em aberto", _fmt_brl(total))

            try:
                from openpyxl import Workbook  # noqa
                buf = BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as w:
                    em_aberto.sort_values(["Cliente","IDLancFiado","Data"]).to_excel(
                        w, index=False, sheet_name="Fiado_Em_Aberto"
                    )
                st.download_button("⬇️ Exportar (Excel)", data=buf.getvalue(), file_name="fiado_em_aberto.xlsx")
            except Exception:
                csv_bytes = em_aberto.sort_values(["Cliente","IDLancFiado","Data"]).to_csv(
                    index=False
                ).encode("utf-8-sig")
                st.download_button("⬇️ Exportar (CSV)", data=csv_bytes, file_name="fiado_em_aberto.csv")

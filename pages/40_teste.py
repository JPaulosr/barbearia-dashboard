# -*- coding: utf-8 -*-
# 15_Atendimentos_Masculino_Por_Dia.py
# KPIs do período, por funcionário, conferência (gravar/excluir no Sheets)
# e EXPORTAR PARA MOBILLS (tudo ou só NÃO conferidos) + pós-exportação marcar conferidos.

import streamlit as st
import pandas as pd
import gspread
import io, textwrap, re
import plotly.express as px
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from gspread.utils import rowcol_to_a1
from datetime import datetime, date, timedelta
import pytz
import numpy as np
from calendar import monthrange

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"  # Masculino
TZ = "America/Sao_Paulo"
DATA_FMT = "%d/%m/%Y"
FUNC_JPAULO = "JPaulo"
FUNC_VINICIUS = "Vinicius"
DATA_CORRETA = datetime(2025, 5, 11).date()

# =========================
# UTILS
# =========================
def _tz_now():
    return datetime.now(pytz.timezone(TZ))

def _fmt_data(d):
    if pd.isna(d): return ""
    if isinstance(d, (pd.Timestamp, datetime)): return d.strftime(DATA_FMT)
    if isinstance(d, date): return d.strftime(DATA_FMT)
    d2 = pd.to_datetime(str(d), dayfirst=True, errors="coerce")
    return "" if pd.isna(d2) else d2.strftime(DATA_FMT)

def _norm_col(name: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(name).strip().lower())

def _to_bool(x):
    if isinstance(x, (bool, np.bool_)): return bool(x)
    if isinstance(x, (int, float)) and not pd.isna(x): return float(x) != 0.0
    s = str(x).strip().lower()
    return s in ("1", "true", "verdadeiro", "sim", "ok", "y", "yes")

@st.cache_resource(show_spinner=False)
def _conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)

# ---------- helpers Sheets ----------
def _headers_and_indices(ws):
    headers = ws.row_values(1)
    norms = [_norm_col(h) for h in headers]
    idxs = [i for i, n in enumerate(norms) if n == "conferido"]  # 0-based
    chosen = idxs[-1] if idxs else None  # SEMPRE a última
    return headers, norms, idxs, chosen

def _ensure_conferido_column(ws):
    headers, norms, idxs, chosen = _headers_and_indices(ws)
    if chosen is not None:
        return chosen + 1  # 1-based
    col = len(headers) + 1
    ws.update_cell(1, col, "Conferido")
    return col

def _update_conferido(ws, updates):
    if not updates: return
    col_conf = _ensure_conferido_column(ws)
    for u in updates:
        row = int(u["row"])
        val = "TRUE" if u["value"] else "FALSE"
        ws.update_cell(row, col_conf, val)

def _delete_rows(ws, rows):
    for r in sorted(set(rows), reverse=True):
        try:
            ws.delete_rows(int(r))
        except Exception as e:
            st.warning(f"Falha ao excluir linha {r}: {e}")

def _fetch_conferido_map(ws):
    col_conf = _ensure_conferido_column(ws)
    a1 = rowcol_to_a1(1, col_conf)
    col_letters = "".join(ch for ch in a1 if ch.isalpha())
    rng = f"{col_letters}2:{col_letters}"
    vals = ws.get(rng, value_render_option="UNFORMATTED_VALUE")
    m = {}
    rownum = 2
    for row in vals:
        v = row[0] if row else ""
        if isinstance(v, (bool, np.bool_)):
            b = bool(v)
        elif isinstance(v, (int, float)) and not pd.isna(v):
            b = float(v) != 0.0
        else:
            s = str(v).strip().lower()
            b = s in ("1", "true", "verdadeiro", "sim", "ok", "y", "yes")
        m[rownum] = b
        rownum += 1
    return m

# ---------- leitura base ----------
@st.cache_data(ttl=60, show_spinner=False)
def carregar_base():
    gc = _conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)

    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df = df.dropna(how="all")
    if df is None or df.empty:
        return pd.DataFrame()

    df["SheetRow"] = df.index + 2
    df.columns = [str(c).strip() for c in df.columns]

    base_cols = ["Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
                 "Funcionário", "Fase", "Hora Chegada", "Hora Início",
                 "Hora Saída", "Hora Saída do Salão", "Tipo"]
    for c in base_cols:
        if c not in df.columns:
            df[c] = None

    for col in ["Cliente", "Serviço", "Funcionário", "Conta", "Combo", "Tipo", "Fase"]:
        if col not in df.columns: df[col] = ""
        df[col] = df[col].astype(str).fillna("").str.strip()

    def parse_data(x):
        if pd.isna(x): return None
        if isinstance(x, (datetime, pd.Timestamp)): return x.date()
        s = str(x).strip()
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
        return None
    df["Data_norm"] = df["Data"].apply(parse_data)

    def parse_valor(v):
        if pd.isna(v): return 0.0
        s = str(v).strip().replace("R$", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0
    df["Valor_num"] = df["Valor"].apply(parse_valor)

    conferido_map = _fetch_conferido_map(ws)
    df["Conferido"] = df["SheetRow"].map(lambda r: bool(conferido_map.get(int(r), False))).astype(bool)

    headers = ws.row_values(1)
    conf_sources = [h for h in headers if _norm_col(h) == "conferido"]
    df.attrs["__conferido_sources__"] = conf_sources or []

    return df

# ---------- caixinha helper ----------
def _first_caixinha_val(row):
    prefer = ["CaixinhaDiaTotal", "Caixinha", "Gorjeta", "CaixinhaDia"]
    for c in prefer:
        if c in row and pd.notna(row[c]) and str(row[c]).strip() != "":
            v = str(row[c]).replace(",", ".").replace("R$", "").strip()
            try:
                return float(v)
            except:
                continue
    return 0.0

# =========================
# (restante do código segue igual até a seção de exportação)
# =========================
# ... [mantém tudo como já estava no seu arquivo até chegar em "📤 Exportar para Mobills"] ...

# ========================================================
# 📤 EXPORTAR PARA MOBILLS
# ========================================================
st.markdown("---")
st.subheader("📤 Exportar para Mobills")

export_only_unchecked = st.checkbox(
    "Exportar **apenas os NÃO conferidos**",
    value=True,
    help="Desmarque para exportar TODOS os registros do período."
)

df_export_base = df_periodo.copy()
df_export_base["Conferido"] = df_export_base["Conferido"].apply(_to_bool).astype(bool)
if export_only_unchecked:
    df_export_base = df_export_base[~df_export_base["Conferido"].fillna(False)]

st.caption(
    f"Selecionados para exportação: **{len(df_export_base)}** de **{len(df_periodo)}** registros."
)

# ===== Resumo por Cliente =====
st.markdown("### Resumo por Cliente (período selecionado)")
grp_dia = (
    df_periodo
    .groupby("Cliente", as_index=False)
    .agg(Qtd_Serviços=("Serviço", "count"),
         Valor_Total=("Valor_num", "sum"))
    .sort_values(["Valor_Total", "Qtd_Serviços"], ascending=[False, False])
)
grp_dia["Valor_Total"] = grp_dia["Valor_Total"].apply(lambda v: f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
st.dataframe(
    grp_dia.rename(columns={"Qtd_Serviços": "Qtd. Serviços", "Valor_Total": "Valor Total"}),
    use_container_width=True,
    hide_index=True
)

# --- Checkbox para incluir caixinha do JPaulo
incluir_caixinha_jp = st.checkbox(
    "➕ Incluir **Caixinha (JPaulo)** na exportação",
    value=True,
    help="Adiciona uma linha 'Caixinha' por atendimento do JPaulo que tenha valor de caixinha (>0)."
)

conta_fallback = st.text_input("Conta padrão (quando vazio na base)", value="Nubank CNPJ")

def _fmt_data_ddmmyyyy(d):
    return d.strftime("%d/%m/%Y") if pd.notna(d) else ""

def _descricao(row):
    func = str(row.get("Funcionário", "")).strip().casefold()
    if func == FUNC_VINICIUS.casefold():
        return "Vinicius"
    return (str(row.get("Serviço", "")).strip() or "Serviço")

def _categoria(row):
    serv = (str(row.get("Serviço", "")).strip() or "Serviço")
    func = str(row.get("Funcionário", "")).strip().casefold()
    if func == FUNC_VINICIUS.casefold():
        return f"Lucro Vinicius > {serv}"
    return f"Lucro salão > {serv}"

if df_export_base.empty:
    st.info("Nada a exportar (com o filtro atual).")
else:
    df_mob = df_export_base.copy()
    df_mob["Data"] = df_mob["Data_norm"].apply(_fmt_data_ddmmyyyy)
    df_mob["Descrição"] = df_mob.apply(_descricao, axis=1)
    df_mob["Valor"] = pd.to_numeric(df_mob["Valor_num"], errors="coerce").fillna(0.0)

    df_mob["Conta"] = df_mob["Conta"].fillna("").astype(str).str.strip()
    df_mob.loc[df_mob["Conta"] == "", "Conta"] = conta_fallback

    df_mob["Categoria"] = df_mob.apply(_categoria, axis=1)
    df_mob["serviço"] = df_mob["Serviço"].astype(str).fillna("").str.strip()
    df_mob["cliente"] = df_mob["Cliente"].astype(str).fillna("").str.strip()
    df_mob["Combo"]   = df_mob.get("Combo", "").astype(str).fillna("").str.strip()

    cols_final = ["Data", "Descrição", "Valor", "Conta", "Categoria", "serviço", "cliente", "Combo"]
    df_mobills = df_mob[cols_final].copy()

    # ---- Caixinha do JPaulo como linhas extras ----
    if incluir_caixinha_jp:
        tmp = df_export_base.copy()
        tmp["Caixinha_num"] = tmp.apply(_first_caixinha_val, axis=1)
        mask_jp = tmp["Funcionário"].astype(str).str.casefold() == FUNC_JPAULO.casefold()
        mask_tip = tmp["Caixinha_num"] > 0
        df_tips = tmp[mask_jp & mask_tip].copy()
        if not df_tips.empty:
            df_tips["Data"] = df_tips["Data_norm"].apply(_fmt_data_ddmmyyyy)
            df_tips["Descrição"] = "Caixinha"
            df_tips["Valor"] = pd.to_numeric(df_tips["Caixinha_num"], errors="coerce").fillna(0.0)
            df_tips["Conta"] = df_tips["Conta"].fillna("").astype(str).str.strip()
            df_tips.loc[df_tips["Conta"] == "", "Conta"] = conta_fallback
            df_tips["Categoria"] = "Caixinha"
            df_tips["serviço"] = df_tips["Serviço"].astype(str).fillna("").str.strip()
            df_tips["cliente"] = df_tips["Cliente"].astype(str).fillna("").str.strip()
            df_tips["Combo"]   = df_tips.get("Combo", "").astype(str).fillna("").str.strip()
            df_tips = df_tips[cols_final].copy()
            df_mobills = pd.concat([df_mobills, df_tips], ignore_index=True)
            st.success(f"Incluídas {len(df_tips)} linha(s) de **Caixinha (JPaulo)** na exportação.")

    st.markdown("**Prévia (Mobills)**")
    st.dataframe(df_mobills, use_container_width=True, hide_index=True)

    # CSV (Mobills usa ';')
    csv_bytes = df_mobills.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "⬇️ Baixar CSV (Mobills)",
        data=csv_bytes,
        file_name=f"Mobills_{file_stamp}.csv",
        mime="text/csv",
        type="primary"
    )

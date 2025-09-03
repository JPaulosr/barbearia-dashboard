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
# Regra de unicidade Cliente+Dia a partir desta data (não altera receita)
DATA_CORRETA = datetime(2025, 5, 11).date()

# ============== GUARDS para páginas de teste (evita NameError) ==============
df_periodo = pd.DataFrame()
label_periodo = "Sem dados"
file_stamp = datetime.now().strftime("%d-%m-%Y")

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

    # strings padronizadas
    for col in ["Cliente", "Serviço", "Funcionário", "Conta", "Combo", "Tipo", "Fase"]:
        if col not in df.columns: df[col] = ""
        df[col] = df[col].astype(str).fillna("").str.strip()

    # datas
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

    # valores
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

    # Conferido (sempre a última coluna 'Conferido' presente)
    conferido_map = _fetch_conferido_map(ws)
    df["Conferido"] = df["SheetRow"].map(lambda r: bool(conferido_map.get(int(r), False))).astype(bool)

    headers = ws.row_values(1)
    conf_sources = [h for h in headers if _norm_col(h) == "conferido"]
    df.attrs["__conferido_sources__"] = conf_sources or []

    return df

# ---------- agregações ----------
def filtrar_por_dias(df, dias_set):
    if df.empty or not dias_set:
        return df.iloc[0:0]
    return df[df["Data_norm"].isin(dias_set)].copy()

def contar_clientes_periodo(df_periodo):
    """
    Regra:
    - dia < DATA_CORRETA: conta linhas
    - dia >= DATA_CORRETA: grupos únicos (Cliente, Data_norm)
    """
    if df_periodo.empty:
        return 0
    total = 0
    for dia, ddf in df_periodo.groupby("Data_norm"):
        if pd.isna(dia):
            continue
        if dia < DATA_CORRETA:
            total += len(ddf)
        else:
            total += ddf.groupby(["Cliente", "Data_norm"]).ngroups
    return total

def kpis(df_periodo):
    if df_periodo.empty: return 0, 0, 0.0, 0.0
    clientes = contar_clientes_periodo(df_periodo)
    servicos = len(df_periodo)
    receita = float(df_periodo["Valor_num"].sum())
    ticket = (receita / clientes) if clientes > 0 else 0.0
    return clientes, servicos, receita, ticket

def format_moeda(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def preparar_tabela_exibicao(df):
    cols_ordem = [
        "Data", "Cliente", "Serviço", "Valor", "Conta", "Funcionário",
        "Combo", "Tipo", "Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão"
    ]
    for c in cols_ordem:
        if c not in df.columns:
            df[c] = ""
    out = df.copy()
    out["Data"] = out["Data_norm"].apply(_fmt_data)
    out["Valor"] = out["Valor_num"].apply(format_moeda)
    return out[cols_ordem]

# ---------- Excel helpers ----------
def _choose_excel_engine():
    import importlib.util
    for eng in ("xlsxwriter", "openpyxl"):
        if importlib.util.find_spec(eng) is not None:
            return eng
    return None

def _to_xlsx_bytes(dfs_by_sheet: dict):
    engine = _choose_excel_engine()
    if not engine:
        return None
    with io.BytesIO() as buf:
        with pd.ExcelWriter(buf, engine=engine) as writer:
            for sheet, df in dfs_by_sheet.items():
                df.to_excel(writer, sheet_name=sheet, index=False)
        return buf.getvalue()

# ============= HELPER HTML (render seguro) =============
def html(s: str):
    st.markdown(textwrap.dedent(s), unsafe_allow_html=True)

def card(label, val):
    return f'<div class="card"><div class="label">{label}</div><div class="value">{val}</div></div>'

# ---------- Caixinha helper ----------
def _first_caixinha_val(row):
    """
    Pega o 1º valor disponível nas colunas conhecidas de caixinha.
    Ordem de preferência: CaixinhaDiaTotal, Caixinha, Gorjeta, CaixinhaDia, CaixinhaFundo
    """
    prefer = ["CaixinhaDiaTotal", "Caixinha", "Gorjeta", "CaixinhaDia", "CaixinhaFundo"]
    for c in prefer:
        if c in row and pd.notna(row[c]) and str(row[c]).strip() != "":
            s = str(row[c]).replace("R$", "").replace(" ", "")
            if "," in s and "." in s:
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", ".")
            try:
                return float(s)
            except:
                pass
    return 0.0

# ============= Seletor de período =============
def _semana_completa(d: date):
    dow = d.weekday()  # 0=Seg
    ini = d - timedelta(days=dow)
    fim = ini + timedelta(days=6)
    return ini, fim

def _dias_do_mes(ano: int, mes: int):
    last = monthrange(ano, mes)[1]
    ini = date(ano, mes, 1)
    fim = date(ano, mes, last)
    return ini, fim

def _label_periodo(dias):
    dias = sorted(list(dias))
    if not dias:
        return "Sem dados", "NA"
    if len(dias) == 1:
        return dias[0].strftime("%d/%m/%Y"), dias[0].strftime("%d-%m-%Y")
    return f"{dias[0].strftime('%d/%m/%Y')} a {dias[-1].strftime('%d/%m/%Y')}", \
           f"{dias[0].strftime('%d-%m-%Y')}_a_{dias[-1].strftime('%d-%m-%Y')}"

# =========================
# UI
# =========================
st.set_page_config(page_title="Atendimentos por Período (Masculino)", page_icon="📅", layout="wide")
st.title("📅 Atendimentos — Masculino (Dia / Semana / Mês / Intervalo)")
st.caption("KPIs do período, comparativo por funcionário, conferência e exportação para Mobills.")

if st.sidebar.button("🔄 Recarregar dados agora"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("Carregando base..."):
    df_base = carregar_base()

# ---------- Seletor de PERÍODO ----------
st.markdown("### 🗓️ Seleção de Período")
modo = st.selectbox(
    "Modo de período",
    ["Dia único", "Vários dias (multiseleção)", "Semana", "Mês", "Intervalo personalizado"],
    index=0
)

hoje = _tz_now().date()
todos_dias_disponiveis = sorted([d for d in df_base["Data_norm"].dropna().unique()])

dias_selecionados = set()

if modo == "Dia único":
    d = st.date_input("Dia", value=hoje, format="DD/MM/YYYY")
    dias_selecionados = {d}

elif modo == "Vários dias (multiseleção)":
    if not todos_dias_disponiveis:
        st.info("Base sem datas válidas.")
        st.stop()
    mult = st.multiselect(
        "Escolha um ou mais dias",
        options=todos_dias_disponiveis,
        default=[todos_dias_disponiveis[-1]],
        format_func=lambda x: x.strftime("%d/%m/%Y")
    )
    dias_selecionados = set(mult)

elif modo == "Semana":
    d_ref = st.date_input("Escolha uma data de referência", value=hoje, format="DD/MM/YYYY")
    ini, fim = _semana_completa(d_ref)
    st.caption(f"Semana: {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')} (Seg→Dom)")
    dias_selecionados = {ini + timedelta(days=i) for i in range((fim - ini).days + 1)}

elif modo == "Mês":
    col_a, col_m = st.columns(2)
    with col_a:
        ano = st.number_input("Ano", min_value=2023, max_value=2100, value=hoje.year, step=1)
    with col_m:
        mes = st.number_input("Mês", min_value=1, max_value=12, value=hoje.month, step=1)
    ini, fim = _dias_do_mes(int(ano), int(mes))
    st.caption(f"Mês: {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")
    dias_selecionados = {ini + timedelta(days=i) for i in range((fim - ini).days + 1)}

elif modo == "Intervalo personalizado":
    rng = st.date_input("Intervalo", value=(hoje, hoje), format="DD/MM/YYYY")
    if isinstance(rng, (list, tuple)) and len(rng) == 2:
        ini, fim = rng
    else:
        ini, fim = hoje, hoje
    if ini > fim:
        ini, fim = fim, ini
    st.caption(f"Intervalo: {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}")
    dias_selecionados = {ini + timedelta(days=i) for i in range((fim - ini).days + 1)}

# Filtra base pelo período
df_periodo = filtrar_por_dias(df_base, dias_selecionados)
label_periodo, file_stamp = _label_periodo(dias_selecionados)

if df_periodo.empty:
    st.info("Nenhum atendimento encontrado para a seleção.")
    st.stop()

# Debug rápido
st.sidebar.caption("Colunas 'Conferido' no cabeçalho: " + ", ".join(df_base.attrs.get("__conferido_sources__", ["<nenhuma>"])))
st.sidebar.caption(f"Conferidos no período: {int(df_periodo['Conferido'].fillna(False).sum())}")

# ====== KPIs (período) ======
html("""
<style>
.metrics-wrap{display:flex;flex-wrap:wrap;gap:12px;margin:8px 0}
.metrics-wrap .card{
  background:rgba(255,255,255,0.04);
  border:1px solid rgba(255,255,255,0.08);
  border-radius:12px;
  padding:12px 14px;
  min-width:160px;
  flex:1 1 200px;
}
.metrics-wrap .card .label{font-size:0.9rem;opacity:.85;margin-bottom:6px}
.metrics-wrap .card .value{font-weight:700;font-size:clamp(18px,3.8vw,28px);line-height:1.15}
.section-h{font-weight:700;margin:12px 0 6px}
</style>
""")

df_v_top = df_periodo[df_periodo["Funcionário"].astype(str).str.casefold() == FUNC_VINICIUS.casefold()]
_, _, rec_v_top, _ = kpis(df_v_top)

cli, srv, rec, tkt = kpis(df_periodo)          # rec = soma de Valor_num
rec_total_kpi = rec + cx_total_jp               # agora entra a caixinha do JP

# Se quiser que o ticket NÃO some caixinha, troque 'tkt' no card e mantenha este cálculo só para o card de receita.
# Aqui vou manter o ticket original (sem caixinha) e somar caixinha apenas no card "Receita do período".
receita_salao = (rec - (rec_v_top * 0.5)) + cx_total_jp  # opcional: também soma caixinha do JP no salão

st.markdown(f"#### Período selecionado: **{label_periodo}**")
html(
    '<div class="metrics-wrap">'
    + card("👥 Clientes únicos (regra por dia)", f"{cli}")
    + card("✂️ Serviços realizados", f"{srv}")
    + card("🧾 Ticket médio", format_moeda(tkt))
    + card("💰 Receita do período", format_moeda(rec))
    + card("🏢 Receita do salão (–50% Vinicius)", format_moeda(receita_salao))
    + "</div>"
)
st.markdown("---")

# ===== Por Funcionário =====
st.subheader("📊 Por Funcionário (período selecionado)")
df_j = df_periodo[df_periodo["Funcionário"].str.casefold() == FUNC_JPAULO.casefold()]
df_v = df_periodo[df_periodo["Funcionário"].str.casefold() == FUNC_VINICIUS.casefold()]
cli_j, srv_j, rec_j, tkt_j = kpis(df_j)
cli_v, srv_v, rec_v, tkt_v = kpis(df_v)

col_j, col_v = st.columns(2)
with col_j:
    html(f'<div class="section-h">{FUNC_JPAULO}</div>')
    html('<div class="metrics-wrap">' +
         card("Clientes (regra por dia)", f"{cli_j}") +
         card("Serviços", f"{srv_j}") +
         card("🧾 Ticket médio", format_moeda(tkt_j)) +
         card("Receita", format_moeda(rec_j)) +
         '</div>')
with col_v:
    html(f'<div class="section-h">{FUNC_VINICIUS}</div>')
    html('<div class="metrics-wrap">' +
         card("Clientes (regra por dia)", f"{cli_v}") +
         card("Serviços", f"{srv_v}") +
         card("🧾 Ticket médio", format_moeda(tkt_v)) +
         card("Receita", format_moeda(rec_v)) +
         card("💵 Comissão (50%)", format_moeda(rec_v * 0.5)) +
         '</div>')

# ===== Gráfico =====
df_comp = pd.DataFrame([
    {"Funcionário": FUNC_JPAULO, "Clientes": cli_j, "Serviços": srv_j},
    {"Funcionário": FUNC_VINICIUS, "Clientes": cli_v, "Serviços": srv_v},
])
fig = px.bar(
    df_comp.melt(id_vars="Funcionário", var_name="Métrica", value_name="Quantidade"),
    x="Funcionário", y="Quantidade", color="Métrica", barmode="group",
    title=f"Comparativo de atendimentos — {label_periodo}"
)
st.plotly_chart(fig, use_container_width=True)

# ========================================================
# 🔎 MODO DE CONFERÊNCIA
# ========================================================
st.markdown("---")
st.subheader("🧾 Conferência do período (marcar conferido e excluir)")

# base do período
df_conf = df_periodo.copy()
df_conf["Conferido"] = df_conf["Conferido"].apply(_to_bool).astype(bool)

# --- indicadores de caixinha ---
# valor numérico (lê CaixinhaDiaTotal / Caixinha / Gorjeta / CaixinhaDia / CaixinhaFundo)
df_conf["Caixinha_num"] = df_conf.apply(_first_caixinha_val, axis=1)

# se quiser considerar só JPaulo nas flags, troque a linha abaixo pela comentada
tem_cx_mask = df_conf["Caixinha_num"] > 0
# tem_cx_mask = (df_conf["Caixinha_num"] > 0) & (df_conf["Funcionário"].astype(str).str.casefold() == FUNC_JPAULO.casefold())

df_conf["TemCaixinha"] = tem_cx_mask
df_conf["Caixinha (R$)"] = df_conf["Caixinha_num"].apply(
    lambda v: "" if v <= 0 else f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
)
df_conf["💝"] = df_conf["TemCaixinha"].map(lambda b: "💝" if b else "")

# --- view para edição ---
df_conf_view = df_conf[[
    "SheetRow", "Cliente", "Serviço", "Funcionário", "Valor", "Conta",
    "💝", "Caixinha (R$)", "Conferido"
]].copy()
df_conf_view["Excluir"] = False

# --- filtro opcional: mostrar só quem tem caixinha ---
mostrar_so_com_caixinha = st.checkbox("Mostrar **apenas** linhas com caixinha", value=False)
if mostrar_so_com_caixinha:
    df_conf_view = df_conf_view[df_conf_view["💝"] == "💝"].copy()

st.caption("Edite **Conferido** e/ou marque **Excluir**. Depois clique em **Aplicar mudanças**.")
edited = st.data_editor(
    df_conf_view,
    use_container_width=True,
    hide_index=True,
    column_config={
        "SheetRow": st.column_config.NumberColumn("SheetRow", help="Nº real no Sheets", disabled=True, width="small"),
        "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
        "Serviço": st.column_config.TextColumn("Serviço", disabled=True),
        "Funcionário": st.column_config.TextColumn("Funcionário", disabled=True, width="small"),
        "Valor": st.column_config.TextColumn("Valor", disabled=True, width="small"),
        "Conta": st.column_config.TextColumn("Conta", disabled=True, width="small"),
        "💝": st.column_config.TextColumn("💝", disabled=True, help="Indicador visual de caixinha"),
        "Caixinha (R$)": st.column_config.TextColumn("Caixinha (R$)", disabled=True, help="Valor detectado de caixinha/gorjeta"),
        "Conferido": st.column_config.CheckboxColumn("Conferido"),
        "Excluir": st.column_config.CheckboxColumn("Excluir"),
    },
    key="editor_conferencia"
)

if st.button("✅ Aplicar mudanças (gravar no Sheets)", type="primary"):
    try:
        gc = _conectar_sheets()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ABA_DADOS)

        # Atualiza 'Conferido'
        orig_by_row = df_conf.set_index("SheetRow")["Conferido"].apply(_to_bool).to_dict()
        updates = []
        for _, r in edited.iterrows():
            rownum = int(r["SheetRow"])
            new_val = bool(_to_bool(r["Conferido"]))
            old_val = bool(_to_bool(orig_by_row.get(rownum, False)))
            if new_val != old_val:
                updates.append({"row": rownum, "value": new_val})
        _update_conferido(ws, updates)

        # Exclui marcados
        rows_to_delete = [int(r["SheetRow"]) for _, r in edited.iterrows() if bool(_to_bool(r["Excluir"]))]
        _delete_rows(ws, rows_to_delete)

        st.success("Alterações aplicadas com sucesso!")
        st.cache_data.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Falha ao aplicar mudanças: {e}")

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

# ===== Resumo por Cliente (do período, informativo) =====
st.markdown("### Resumo por Cliente (período selecionado)")
grp_dia = (
    df_periodo
    .groupby("Cliente", as_index=False)
    .agg(Qtd_Serviços=("Serviço", "count"),
         Valor_Total=("Valor_num", "sum"))
    .sort_values(["Valor_Total", "Qtd_Serviços"], ascending=[False, False])
)
grp_dia["Valor_Total"] = grp_dia["Valor_Total"].apply(format_moeda)
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

    # ✅ XLSX (Excel) – aba 'Mobills'
    xlsx_bytes = _to_xlsx_bytes({"Mobills": df_mobills})
    if xlsx_bytes:
        st.download_button(
            "⬇️ Baixar XLSX (Mobills)",
            data=xlsx_bytes,
            file_name=f"Mobills_{file_stamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("Para gerar Excel, instale 'xlsxwriter' ou 'openpyxl' no ambiente.")

    # Pós-exportação: marcar como conferidos
    st.markdown("#### Pós-exportação")
    if st.button("✅ Marcar exportados como Conferidos no Sheets"):
        try:
            gc = _conectar_sheets()
            sh = gc.open_by_key(SHEET_ID)
            ws = sh.worksheet(ABA_DADOS)
            updates = [{"row": int(r), "value": True} for r in df_export_base["SheetRow"].tolist()]
            _update_conferido(ws, updates)
            st.success(f"Marcados {len(updates)} registros como Conferidos.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Falha ao marcar como conferidos: {e}")

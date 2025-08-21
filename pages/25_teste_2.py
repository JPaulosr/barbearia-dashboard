# -*- coding: utf-8 -*-
# 15_Atendimentos_Masculino_Por_Dia.py
# Página: escolher um dia e ver TODOS os atendimentos (masculino),
# KPIs gerais, por funcionário, gráfico comparativo e histórico (com Top 5).
# Agora com MODO DE CONFERÊNCIA: marcar conferido e excluir registros no Sheets.

import streamlit as st
import pandas as pd
import gspread
import io
import plotly.express as px
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1
from datetime import datetime, date
import pytz

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"  # Masculino
TZ = "America/Sao_Paulo"
DATA_FMT = "%d/%m/%Y"

FUNC_JPAULO = "JPaulo"
FUNC_VINICIUS = "Vinicius"

# Marco para regra de contagem
DATA_CORRETA = datetime(2025, 5, 11).date()

COLS_ESPERADAS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Hora Chegada", "Hora Início",
    "Hora Saída", "Hora Saída do Salão", "Tipo"
]
COL_CONFERIDO = "Conferido"

# =========================
# UTILS
# =========================
def _tz_now():
    return datetime.now(pytz.timezone(TZ))

def _fmt_data(d):
    if pd.isna(d): return ""
    if isinstance(d, (pd.Timestamp, datetime)): return d.strftime(DATA_FMT)
    if isinstance(d, date): return d.strftime(DATA_FMT)
    try:
        d2 = pd.to_datetime(str(d), dayfirst=True, errors="coerce")
        return "" if pd.isna(d2) else d2.strftime(DATA_FMT)
    except Exception:
        return str(d)

@st.cache_resource(show_spinner=False)
def _conectar_sheets():
    creds_info = st.secrets["GCP_SERVICE_ACCOUNT"]
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)
    return gc, sh, ws

def _limpar_linhas_vazias(rows):
    return [r for r in rows if any((str(c).strip() != "") for c in r)]

@st.cache_data(ttl=300, show_spinner=False)
def carregar_base():
    _, _, ws = _conectar_sheets()
    vals = ws.get_all_values()
    if not vals:
        return pd.DataFrame()

    header = [str(c).strip() for c in vals[0]]
    body = _limpar_linhas_vazias(vals[1:])
    if not body:
        return pd.DataFrame(columns=header)

    n = len(header)
    norm = []
    for r in body:
        if len(r) < n: r = r + [""] * (n - len(r))
        elif len(r) > n: r = r[:n]
        norm.append(r)

    df = pd.DataFrame(norm, columns=header)
    df["_row"] = list(range(2, 2 + len(df)))  # header é linha 1

    for c in COLS_ESPERADAS + [COL_CONFERIDO]:
        if c not in df.columns:
            df[c] = ""

    def parse_data(x):
        if pd.isna(x) or str(x).strip() == "": return None
        if isinstance(x, (datetime, pd.Timestamp)): return x.date()
        s = str(x).strip()
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"]:
            try: return datetime.strptime(s, fmt).date()
            except: pass
        return None
    df["Data_norm"] = df["Data"].apply(parse_data)

    def parse_valor(v):
        if pd.isna(v): return 0.0
        s = str(v).strip().replace("R$", "").replace(" ", "")
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try: return float(s)
        except: return 0.0
    df["Valor_num"] = df["Valor"].apply(parse_valor)

    for col in ["Cliente","Serviço","Funcionário","Conta","Combo","Tipo","Fase",COL_CONFERIDO]:
        df[col] = df[col].astype(str).fillna("").str.strip()

    return df

def filtrar_por_dia(df, dia):
    if df.empty or dia is None: return df.iloc[0:0]
    return df[df["Data_norm"] == dia].copy()

def contar_atendimentos_dia(df):
    if df.empty: return 0
    d0 = df["Data_norm"].dropna()
    if d0.empty: return 0
    dia = d0.iloc[0]
    if dia < DATA_CORRETA: return len(df)
    return df.groupby(["Cliente","Data_norm"]).ngroups

def kpis(df):
    if df.empty: return 0,0,0.0,0.0
    clientes = contar_atendimentos_dia(df)
    servicos = len(df)
    receita = float(df["Valor_num"].sum())
    ticket = receita/clientes if clientes>0 else 0.0
    return clientes, servicos, receita, ticket

def format_moeda(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

def preparar_tabela_exibicao(df):
    cols_ordem = [
        "Data", "Cliente", "Serviço", "Valor", "Conta", "Funcionário",
        "Combo", "Tipo", "Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão"
    ]
    for c in cols_ordem:
        if c not in df.columns: df[c] = ""
    df_out = df.copy().reset_index(drop=True)
    try: df_out = df_out.sort_values(by=["Hora Início","Cliente"])
    except: pass
    df_out["Data"]  = df_out["Data_norm"].apply(_fmt_data)
    df_out["Valor"] = df_out["Valor_num"].apply(format_moeda)
    return df_out[cols_ordem]

def gerar_excel(df_lin, df_cli):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        df_lin.to_excel(writer, sheet_name="Linhas", index=False)
        df_cli.to_excel(writer, sheet_name="ResumoClientes", index=False)
    buffer.seek(0)
    return buffer.getvalue()

# ---------- Helpers Sheets ----------
def _get_ws_and_headers():
    _, _, ws = _conectar_sheets()
    vals = ws.row_values(1)
    headers = [h.strip() for h in vals] if vals else []
    return ws, headers

def _ensure_conferido_col() -> int:
    ws, headers = _get_ws_and_headers()
    if COL_CONFERIDO in headers:
        return headers.index(COL_CONFERIDO) + 1
    col_idx = len(headers) + 1
    if col_idx > ws.col_count:
        ws.add_cols(col_idx - ws.col_count)
    a1 = rowcol_to_a1(1, col_idx)
    ws.update(a1, [[COL_CONFERIDO]])
    return col_idx

def _chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def marcar_conferido(rows: list[int], texto: str):
    if not rows: return 0
    ws, _ = _get_ws_and_headers()
    col_idx = _ensure_conferido_col()
    total = 0
    for bloco in _chunked(sorted(rows), 100):
        reqs = [{"range": rowcol_to_a1(r, col_idx), "values": [[texto]]} for r in bloco]
        ws.batch_update(reqs, value_input_option="USER_ENTERED")
        total += len(bloco)
    return total

def excluir_linhas(rows: list[int]):
    """
    Exclui linhas via batch_update (deleteDimension) com proteção de erros.
    """
    if not rows:
        return 0
    try:
        ws, _ = _get_ws_and_headers()
        rows_sorted = sorted({int(r) for r in rows if int(r) >= 2})
        if not rows_sorted:
            return 0
        ranges = []
        start = end = None
        for r in rows_sorted:
            if start is None:
                start = end = r
            elif r == end + 1:
                end = r
            else:
                ranges.append((start, end))
                start = end = r
        if start is not None:
            ranges.append((start, end))
        requests = []
        for s, e in reversed(ranges):
            if s > ws.row_count: continue
            end_index = min(e, ws.row_count)
            requests.append({
                "deleteDimension": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": s - 1,
                        "endIndex": end_index
                    }
                }
            })
        if requests:
            ws.spreadsheet.batch_update({"requests": requests})
        return len(rows_sorted)
    except Exception as err:
        st.error(f"Falha ao excluir linhas: {err}")
        return 0

# =========================
# UI
# =========================
st.set_page_config(page_title="Atendimentos por Dia (Masculino)", page_icon="📅", layout="wide")
st.title("📅 Atendimentos por Dia — Masculino")
st.caption("KPIs do dia, comparativo por funcionário e histórico. Inclui modo de conferência (marca e exclui direto no Sheets).")

with st.spinner("Carregando base masculina..."):
    df_base = carregar_base()

# Seletor de dia
hoje = _tz_now().date()
dia_selecionado = st.date_input("Dia", value=hoje, format="DD/MM/YYYY")
df_dia = filtrar_por_dia(df_base, dia_selecionado)

if df_dia.empty:
    st.info("Nenhum atendimento encontrado para o dia selecionado.")
    st.stop()

# KPIs
cli, srv, rec, tkt = kpis(df_dia)
k1,k2,k3,k4 = st.columns(4)
k1.metric("👥 Clientes", f"{cli}")
k2.metric("✂️ Serviços", f"{srv}")
k3.metric("💰 Receita", format_moeda(rec))
k4.metric("🧾 Ticket médio", format_moeda(tkt))

st.markdown("---")

# Por funcionário
st.subheader("📊 Por Funcionário")
df_j = df_dia[df_dia["Funcionário"].str.casefold()==FUNC_JPAULO.casefold()]
df_v = df_dia[df_dia["Funcionário"].str.casefold()==FUNC_VINICIUS.casefold()]
cli_j,srv_j,rec_j,tkt_j = kpis(df_j)
cli_v,srv_v,rec_v,tkt_v = kpis(df_v)

c1,c2=st.columns(2)
with c1:
    st.markdown(f"**{FUNC_JPAULO}**")
    a,b,c,d = st.columns(4)
    a.metric("Clientes", f"{cli_j}")
    b.metric("Serviços", f"{srv_j}")
    c.metric("Receita", format_moeda(rec_j))
    d.metric("Ticket", format_moeda(tkt_j))
with c2:
    st.markdown(f"**{FUNC_VINICIUS}**")
    a,b,c,d = st.columns(4)
    a.metric("Clientes", f"{cli_v}")
    b.metric("Serviços", f"{srv_v}")
    c.metric("Receita", format_moeda(rec_v))
    d.metric("Ticket", format_moeda(tkt_v))

# Gráfico comparativo
df_comp = pd.DataFrame([
    {"Funcionário": FUNC_JPAULO, "Clientes": cli_j, "Serviços": srv_j},
    {"Funcionário": FUNC_VINICIUS, "Clientes": cli_v, "Serviços": srv_v},
])
fig = px.bar(
    df_comp.melt(id_vars="Funcionário", var_name="Métrica", value_name="Quantidade"),
    x="Funcionário", y="Quantidade", color="Métrica", barmode="group",
    title=f"Comparativo de atendimentos — {dia_selecionado.strftime('%d/%m/%Y')}"
)
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# =========================
# ✅ MODO DE CONFERÊNCIA
# =========================
st.subheader("✅ Conferência de Cortes do Dia")
only_cuts = st.checkbox("Mostrar somente serviços de **Corte**", value=True)
df_rev = df_dia[df_dia["Serviço"].str.contains(r"\bcorte\b",case=False,na=False)].copy() if only_cuts else df_dia.copy()
df_rev = df_rev.reset_index(drop=True)

dup_keys = None
if not df_rev.empty:
    corte_mask = df_rev["Serviço"].str.contains(r"\bcorte\b", case=False, na=False)
    dups = (df_rev[corte_mask]
            .groupby(["Cliente","Data_norm"], dropna=False)["Serviço"]
            .size().reset_index(name="qtd"))
    dup_keys = set(tuple(x) for x in dups[dups["qtd"]>1][["Cliente","Data_norm"]].to_records(index=False))
df_rev["Duplicado?"] = df_rev.apply(lambda r: (r["Cliente"], r["Data_norm"]) in (dup_keys or set()), axis=1)

df_rev["Valor_fmt"] = df_rev["Valor_num"].apply(format_moeda)
cols_mostrar = ["Cliente","Serviço","Funcionário","Valor_fmt","Conta","Duplicado?"]
df_rev_show = df_rev[cols_mostrar].rename(columns={"Valor_fmt":"Valor"})
df_rev_show["Selecionar"] = False

edited = st.data_editor(
    df_rev_show,
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "Selecionar": st.column_config.CheckboxColumn(help="Marque para conferir/excluir"),
        "Duplicado?": st.column_config.CheckboxColumn(disabled=True),
    },
    key="rev_editor"
)

sel_index = edited.index[edited["Selecionar"]==True].tolist()
rows_selecionadas = df_rev.iloc[sel_index]["_row"].astype(int).tolist() if sel_index else []

col_a, col_b, col_c = st.columns([1,1,2])
with col_a:
    marcar_ok = st.button("✅ Marcar conferido", type="primary", use_container_width=True)
with col_b:
    excluir_ok = st.button("🗑️ Excluir selecionados", use_container_width=True)
with col_c:
    st.caption("Dica: filtre por 'Somente Corte' e marque/exclua em lote.")

if marcar_ok:
    if not rows_selecionadas:
        st.warning("Selecione pelo menos um registro.")
    else:
        stamp = _tz_now().strftime("%d/%m/%Y %H:%M:%S")
        qt = marcar_conferido(rows_selecionadas, stamp)
        st.success(f"{qt} linha(s) marcadas como conferidas em {stamp}.")
        st.cache_data.clear(); st.rerun()

if excluir_ok:
    if not rows_selecionadas:
        st.warning("Selecione pelo menos um registro.")
    else:
        with st.expander("⚠️ Confirmar exclusão?"):
            st.write(sorted(rows_selecionadas))
            if st.button("Confirmar exclusão agora", type="primary"):
                qt = excluir_linhas(rows_selecionadas)
                st.success(f"{qt} linha(s) excluídas.")
                st.cache_data.clear(); st.rerun()

# Histórico (igual ao anterior) ...

# Exportações (igual ao anterior) ...

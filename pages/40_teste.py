# -*- coding: utf-8 -*-
# 15_Atendimentos_Masculino_Por_Dia.py
# Página: escolher um dia e ver TODOS os atendimentos (masculino),
# KPIs gerais, por funcionário, gráfico comparativo e histórico (com Top 5).
# + MODO DE CONFERÊNCIA: marcar conferido e excluir registros no Sheets.

import streamlit as st
import pandas as pd
import gspread
import io
import plotly.express as px
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime, date
import pytz, textwrap

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"  # Masculino
TZ = "America/Sao_Paulo"
DATA_FMT = "%d/%m/%Y"

FUNC_JPAULO = "JPaulo"
FUNC_VINICIUS = "Vinicius"

# Regra de corte: a partir desta data os clientes passaram a ser anotados corretamente
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

@st.cache_resource(show_spinner=False)
def _conectar_sheets():
    """Escopo de ESCRITA para marcar conferido e excluir linhas."""
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    creds = Credentials.from_service_account_info(
        info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)

@st.cache_data(ttl=300, show_spinner=False)
def carregar_base():
    """Lê a 'Base de Dados' e preserva o índice para mapear a linha real do Sheets."""
    gc = _conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)

    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df = df.dropna(how="all")
    if df is None or df.empty:
        return pd.DataFrame()

    # Mapeia linha física do Sheets (header=1 → primeira linha de dados é 2)
    df["SheetRow"] = df.index + 2

    # Normaliza nomes e garante colunas
    df.columns = [str(c).strip() for c in df.columns]
    cols = ["Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
            "Funcionário", "Fase", "Hora Chegada", "Hora Início",
            "Hora Saída", "Hora Saída do Salão", "Tipo", "Conferido"]
    for c in cols:
        if c not in df.columns:
            df[c] = None

    # Parse de datas
    def parse_data(x):
        if pd.isna(x): return None
        if isinstance(x, (datetime, pd.Timestamp)): return x.date()
        s = str(x).strip()
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"]:
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
        return None
    df["Data_norm"] = df["Data"].apply(parse_data)

    # Parse de valores
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

    # Limpeza de strings
    for col in ["Cliente", "Serviço", "Funcionário", "Conta", "Combo", "Tipo", "Fase"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].astype(str).fillna("").str.strip()

    # Conferido → bool
    def to_bool(x):
        if isinstance(x, bool): return x
        s = str(x).strip().lower()
        return s in ("1", "true", "sim", "ok", "y", "yes")
    df["Conferido"] = df["Conferido"].apply(to_bool)

    return df

def filtrar_por_dia(df, dia):
    if df.empty or dia is None: return df.iloc[0:0]
    return df[df["Data_norm"] == dia].copy()

def contar_atendimentos_dia(df):
    if df.empty: return 0
    d0 = df["Data_norm"].dropna()
    if d0.empty: return 0
    dia = d0.iloc[0]
    if dia < DATA_CORRETA:
        return len(df)
    return df.groupby(["Cliente", "Data_norm"]).ngroups

def kpis(df):
    if df.empty: return 0, 0, 0.0, 0.0
    clientes = contar_atendimentos_dia(df)
    servicos = len(df)
    receita = float(df["Valor_num"].sum())
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

def gerar_excel(df_lin, df_cli):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as w:
        df_lin.to_excel(w, sheet_name="Linhas", index=False)
        df_cli.to_excel(w, sheet_name="ResumoClientes", index=False)
    return buf.getvalue()

# ===== helpers Sheets =====
def _ensure_conferido_column(ws):
    """Garante coluna 'Conferido' e retorna o índice (1-based)."""
    headers = ws.row_values(1)
    if not headers:
        raise RuntimeError("Cabeçalho vazio no Sheets.")
    if "Conferido" in headers:
        return headers.index("Conferido") + 1
    col = len(headers) + 1
    ws.update_cell(1, col, "Conferido")
    return col

def _update_conferido(ws, updates):
    """Atualiza 1 a 1 para evitar payload inválido."""
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

# ============= HELPER HTML (render seguro) =============
def html(s: str):
    st.markdown(textwrap.dedent(s), unsafe_allow_html=True)

def card(label, val):
    return f'<div class="card"><div class="label">{label}</div><div class="value">{val}</div></div>'

# =========================
# UI
# =========================
st.set_page_config(page_title="Atendimentos por Dia (Masculino)", page_icon="📅", layout="wide")
st.title("📅 Atendimentos por Dia — Masculino")
st.caption("KPIs do dia, comparativo por funcionário e histórico dos dias com mais atendimentos (regra de 11/05/2025 aplicada).")

with st.spinner("Carregando base masculina..."):
    df_base = carregar_base()

# Seletor de dia
hoje = _tz_now().date()
dia_selecionado = st.date_input("Dia", value=hoje, format="DD/MM/YYYY")
df_dia = filtrar_por_dia(df_base, dia_selecionado)
if df_dia.empty:
    st.info("Nenhum atendimento encontrado para o dia selecionado.")
    st.stop()

# ========== CSS CARDS ==========
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
.metrics-wrap .card .value{font-weight:700;font-size:clamp(18px,3.8vw,28px);line-height:1.15;word-break:break-word}
.section-h{font-weight:700;margin:12px 0 6px}
.badge{display:inline-block;padding:6px 10px;border-radius:999px;font-size:.85rem;
       background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.15)}
</style>
""")

# =========================
# KPIs (RESPONSIVOS) — Ticket Médio + Receita do Salão
# =========================
df_v_top = df_dia[df_dia["Funcionário"].astype(str).str.casefold() == FUNC_VINICIUS.casefold()]
_, _, rec_v_top, _ = kpis(df_v_top)  # receita do Vinicius no dia

cli, srv, rec, tkt = kpis(df_dia)
receita_salao = rec - (rec_v_top * 0.5)  # total - 50% do Vinicius

html(
    '<div class="metrics-wrap">'
    + card("👥 Clientes atendidos", f"{cli}")
    + card("✂️ Serviços realizados", f"{srv}")
    + card("🧾 Ticket médio", format_moeda(tkt))
    + card("💰 Receita do dia", format_moeda(rec))
    + card("🏢 Receita do salão (–50% Vinicius)", format_moeda(receita_salao))
    + "</div>"
)

html(f'<span class="badge">Fórmula da Receita do salão: Receita total ({format_moeda(rec)}) – 50% da receita do Vinicius ({format_moeda(rec_v_top*0.5)}).</span>')
st.markdown("---")

# =========================
# Por Funcionário (RESPONSIVO)
# =========================
st.subheader("📊 Por Funcionário (dia selecionado)")

df_j = df_dia[df_dia["Funcionário"].str.casefold() == FUNC_JPAULO.casefold()]
df_v = df_dia[df_dia["Funcionário"].str.casefold() == FUNC_VINICIUS.casefold()]

cli_j, srv_j, rec_j, _ = kpis(df_j)
cli_v, srv_v, rec_v, _ = kpis(df_v)

col_j, col_v = st.columns(2)
with col_j:
    html(f'<div class="section-h">{FUNC_JPAULO}</div>')
    html('<div class="metrics-wrap">' +
         card("Clientes", f"{cli_j}") +
         card("Serviços", f"{srv_j}") +
         card("Receita", format_moeda(rec_j)) +
         '</div>')
with col_v:
    html(f'<div class="section-h">{FUNC_VINICIUS}</div>')
    html('<div class="metrics-wrap">' +
         card("Clientes", f"{cli_v}") +
         card("Serviços", f"{srv_v}") +
         card("Receita", format_moeda(rec_v)) +
         '</div>')

# =========================
# Gráfico comparativo (Clientes x Serviços)
# =========================
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

# ========================================================
# 🔎 MODO DE CONFERÊNCIA (logo após o comparativo)
# ========================================================
st.markdown("---")
st.subheader("🧾 Conferência do dia (marcar conferido e excluir)")

df_conf = df_dia.copy()
if "Conferido" not in df_conf.columns:
    df_conf["Conferido"] = False

df_conf_view = df_conf[[
    "SheetRow", "Cliente", "Serviço", "Funcionário", "Valor", "Conta", "Conferido"
]].copy()
df_conf_view["Excluir"] = False

st.caption("Edite **Conferido** e/ou marque **Excluir**. Depois clique em **Aplicar mudanças**.")
edited = st.data_editor(
    df_conf_view,
    use_container_width=True,
    hide_index=True,
    column_config={
        "SheetRow": st.column_config.NumberColumn("SheetRow", help="Nº real no Sheets", disabled=True),
        "Cliente": st.column_config.TextColumn("Cliente", disabled=True),
        "Serviço": st.column_config.TextColumn("Serviço", disabled=True),
        "Funcionário": st.column_config.TextColumn("Funcionário", disabled=True),
        "Valor": st.column_config.TextColumn("Valor", disabled=True),
        "Conta": st.column_config.TextColumn("Conta", disabled=True),
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

        # Atualiza 'Conferido' 1 a 1 (payload simples e estável)
        orig_by_row = df_conf.set_index("SheetRow")["Conferido"].to_dict()
        updates = []
        for _, r in edited.iterrows():
            rownum = int(r["SheetRow"])
            new_val = bool(r["Conferido"])
            old_val = bool(orig_by_row.get(rownum, False))
            if new_val != old_val:
                updates.append({"row": rownum, "value": new_val})
        _update_conferido(ws, updates)

        # Exclui linhas marcadas
        rows_to_delete = [int(r["SheetRow"]) for _, r in edited.iterrows() if bool(r["Excluir"])]
        _delete_rows(ws, rows_to_delete)

        st.success("Alterações aplicadas com sucesso!")
        st.experimental_rerun()

    except Exception as e:
        st.error(f"Falha ao aplicar mudanças: {e}")

# -------------------------
# Histórico — Dias com mais atendimentos
# -------------------------
st.markdown("---")
st.subheader("📈 Histórico — Dias com mais atendimentos")

only_after_cut = st.checkbox(
    f"Mostrar apenas a partir de {DATA_CORRETA.strftime('%d/%m/%Y')}",
    value=True
)

def contar_atendimentos_bloco(bloco):
    if bloco.empty: return 0, 0
    d0 = bloco["Data_norm"].dropna()
    if d0.empty: return 0, len(bloco)
    dia = d0.iloc[0]
    if dia < DATA_CORRETA:
        clientes = len(bloco)
    else:
        clientes = bloco.groupby(["Cliente", "Data_norm"]).ngroups
    return clientes, len(bloco)

lista = []
for dval, bloco in df_base.groupby("Data_norm"):
    if pd.isna(dval): continue
    if only_after_cut and dval < DATA_CORRETA: continue
    cli_h, srv_h = contar_atendimentos_bloco(bloco)
    lista.append({"Data": dval, "Clientes únicos": cli_h, "Serviços": srv_h})

df_hist = pd.DataFrame(lista).sort_values("Data")
if not df_hist.empty:
    df_hist["Data"] = pd.to_datetime(df_hist["Data"], errors="coerce")

if not df_hist.empty:
    top_idx = df_hist["Clientes únicos"].idxmax()
    top_dia = df_hist.loc[top_idx]
    st.success(
        f"📅 Recorde: **{_fmt_data(top_dia['Data'])}** — "
        f"**{int(top_dia['Clientes únicos'])} clientes** e **{int(top_dia['Serviços'])} serviços**."
    )

    df_top5 = df_hist.sort_values(
        ["Clientes únicos", "Serviços", "Data"],
        ascending=[False, False, False]
    ).head(5).copy()
    df_top5["Data_fmt"] = df_top5["Data"].apply(_fmt_data)

    ct1, ct2 = st.columns([1, 1])
    with ct1:
        st.markdown("**🏆 Top 5 dias (por clientes)**")
        st.dataframe(
            df_top5[["Data_fmt", "Clientes únicos", "Serviços"]]
                .rename(columns={"Data_fmt": "Data"}),
            use_container_width=True, hide_index=True
        )
    with ct2:
        fig_top = px.bar(
            df_top5, x="Data_fmt", y="Clientes únicos", text="Clientes únicos",
            title="Top 5 — Clientes por dia"
        )
        st.plotly_chart(fig_top, use_container_width=True)

    st.markdown("**Histórico completo**")
    df_hist_show = df_hist.copy()
    df_hist_show["Data_fmt"] = df_hist_show["Data"].apply(_fmt_data)
    st.dataframe(
        df_hist_show[["Data_fmt", "Clientes únicos", "Serviços"]]
            .rename(columns={"Data_fmt": "Data"}),
        use_container_width=True, hide_index=True
    )

    fig2 = px.line(
        df_hist, x="Data", y="Clientes únicos", markers=True,
        title="Clientes únicos por dia (histórico)"
    )
    st.plotly_chart(fig2, use_container_width=True)

# -------------------------
# Tabela do dia + exportações
# -------------------------
st.markdown("---")
df_exibe = preparar_tabela_exibicao(df_dia)
st.subheader("Registros do dia (linhas)")
st.dataframe(df_exibe, use_container_width=True, hide_index=True)

st.subheader("Resumo por Cliente (no dia)")
grp = (
    df_dia
    .groupby("Cliente", as_index=False)
    .agg(Quantidade_Serviços=("Serviço", "count"),
         Valor_Total=("Valor_num", "sum"))
    .sort_values(["Valor_Total", "Quantidade_Serviços"], ascending=[False, False])
)
grp["Valor_Total"] = grp["Valor_Total"].apply(format_moeda)

st.dataframe(
    grp.rename(columns={"Quantidade_Serviços": "Qtd. Serviços", "Valor_Total": "Valor Total"}),
    use_container_width=True, hide_index=True
)

st.markdown("### Exportar")
df_lin_export = df_exibe.copy()
df_cli_export = grp.rename(columns={"Quantidade_Serviços": "Qtd. Serviços", "Valor_Total": "Valor Total"}).copy()

st.download_button(
    "⬇️ Baixar Linhas (CSV)",
    data=df_lin_export.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}_linhas.csv",
    mime="text/csv"
)
st.download_button(
    "⬇️ Baixar Resumo por Cliente (CSV)",
    data=df_cli_export.to_csv(index=False).encode("utf-8-sig"),
    file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}_resumo_clientes.csv",
    mime="text/csv"
)

try:
    xlsx_bytes = gerar_excel(df_lin_export, df_cli_export)
    st.download_button(
        "⬇️ Baixar Excel (Linhas + Resumo)",
        data=xlsx_bytes,
        file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
except Exception as e:
    st.warning(f"Não foi possível gerar o Excel agora. Detalhe: {e}")

st.caption(
    "• Contagem de clientes aplica a regra: antes de 11/05/2025 cada linha=1 atendimento; "
    "a partir de 11/05/2025: 1 atendimento por Cliente + Data. "
    "• 'Por Funcionário' usa o campo **Funcionário** da base. "
    "• No modo de conferência, a coluna **Conferido** é criada automaticamente se não existir."
)

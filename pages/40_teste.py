# -*- coding: utf-8 -*-
# 15_Atendimentos_Masculino_Por_Dia.py
# Página: escolher um dia e ver TODOS os atendimentos (masculino),
# KPIs gerais, por funcionário, gráfico comparativo e histórico (com Top 5).
# + MODO DE CONFERÊNCIA: marcar conferido e excluir registros no Sheets.
# + EXPORTAR: só NÃO conferidos (opcional), inclusive no layout Mobills.

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

# ---------- Excel helpers ----------
def _choose_excel_engine():
    """Retorna 'xlsxwriter' se existir, senão 'openpyxl', senão None."""
    import importlib.util
    for eng in ("xlsxwriter", "openpyxl"):
        if importlib.util.find_spec(eng) is not None:
            return eng
    return None

def _to_xlsx_bytes(dfs_by_sheet: dict):
    """Recebe {'NomeAba': df, ...} e devolve bytes do XLSX com a melhor engine disponível."""
    engine = _choose_excel_engine()
    if not engine:
        return None
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine=engine) as writer:
        for sheet, df in dfs_by_sheet.items():
            df.to_excel(writer, sheet_name=sheet, index=False)
    return buf.getvalue()

def gerar_excel(df_lin, df_cli):
    return _to_xlsx_bytes({"Linhas": df_lin, "ResumoClientes": df_cli})

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

cli_j, srv_j, rec_j, tkt_j = kpis(df_j)
cli_v, srv_v, rec_v, tkt_v = kpis(df_v)

col_j, col_v = st.columns(2)
with col_j:
    html(f'<div class="section-h">{FUNC_JPAULO}</div>')
    html('<div class="metrics-wrap">' +
         card("Clientes", f"{cli_j}") +
         card("Serviços", f"{srv_j}") +
         card("🧾 Ticket médio", format_moeda(tkt_j)) +
         card("Receita", format_moeda(rec_j)) +
         '</div>')
with col_v:
    html(f'<div class="section-h">{FUNC_VINICIUS}</div>')
    html('<div class="metrics-wrap">' +
         card("Clientes", f"{cli_v}") +
         card("Serviços", f"{srv_v}") +
         card("🧾 Ticket médio", format_moeda(tkt_v)) +
         card("Receita", format_moeda(rec_v)) +
         card("💵 Comissão (50%)", format_moeda(rec_v * 0.5)) +
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
# FILTRO DE EXPORTAÇÃO: só NÃO conferidos (opcional)
# -------------------------
st.markdown("---")
st.subheader("⚙️ Filtro para exportação")

export_only_unchecked = st.checkbox(
    "Exportar apenas os registros NÃO conferidos",
    value=True,
    help="Quando marcado, os botões de download considerarão somente linhas com Conferido = False."
)

# Base de exportação (dia selecionado), já filtrando pelo checkbox
df_export_base = df_dia.copy()
if "Conferido" not in df_export_base.columns:
    df_export_base["Conferido"] = False
if export_only_unchecked:
    df_export_base = df_export_base[~df_export_base["Conferido"].fillna(False)]

st.caption(f"Selecionados para exportação: **{len(df_export_base)}** de **{len(df_dia)}** registros.")

# -------------------------
# Tabela do dia + exportações (respeita o filtro NÃO conferidos)
# -------------------------
st.markdown("---")
st.subheader("Registros selecionados para exportação")

if df_export_base.empty:
    st.info("Nada a exportar com o filtro atual (todos conferidos). Desmarque o filtro acima para ver todos.")
else:
    df_exibe = preparar_tabela_exibicao(df_export_base)
    st.dataframe(df_exibe, use_container_width=True, hide_index=True)

    st.subheader("Resumo por Cliente (seleção atual)")
    grp = (
        df_export_base
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

    st.markdown("### Exportar (CSV/XLSX)")
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
        if xlsx_bytes:
            st.download_button(
                "⬇️ Baixar Excel (Linhas + Resumo)",
                data=xlsx_bytes,
                file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        else:
            st.warning("Nenhuma engine Excel instalada (xlsxwriter/openpyxl). Use os CSVs ou instale uma engine.")
    except Exception as e:
        st.warning(f"Não foi possível gerar o Excel agora. Detalhe: {e}")

    # Botão para marcar exportados como Conferidos
    st.markdown("#### Pós-exportação")
    if st.button("✅ Marcar exportados como Conferidos no Sheets"):
        try:
            gc = _conectar_sheets()
            sh = gc.open_by_key(SHEET_ID)
            ws = sh.worksheet(ABA_DADOS)
            updates = [{"row": int(r), "value": True} for r in df_export_base["SheetRow"].tolist()]
            _update_conferido(ws, updates)
            st.success(f"Marcados {len(updates)} registros como Conferidos.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Falha ao marcar como conferidos: {e}")

# ===========================================
# 📤 Exportar Mobills (layout solicitado) + CSV/XLSX
# ===========================================
st.markdown("---")
st.subheader("📤 Exportar Mobills")

# Opções rápidas (pode alterar)
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

if not df_export_base.empty:
    df_mob = df_export_base.copy()  # usa a seleção (pode ser só NÃO conferidos)

    # Campos base
    df_mob["Data"] = df_mob["Data_norm"].apply(_fmt_data_ddmmyyyy)
    df_mob["Descrição"] = df_mob.apply(_descricao, axis=1)
    df_mob["Valor"] = pd.to_numeric(df_mob["Valor_num"], errors="coerce").fillna(0.0)

    # Conta (fallback quando vier vazia)
    df_mob["Conta"] = df_mob["Conta"].fillna("").astype(str).str.strip()
    df_mob.loc[df_mob["Conta"] == "", "Conta"] = conta_fallback

    # Categoria conforme funcionário
    df_mob["Categoria"] = df_mob.apply(_categoria, axis=1)

    # Colunas extras solicitadas
    df_mob["serviço"] = df_mob["Serviço"].astype(str).fillna("").str.strip()
    df_mob["cliente"] = df_mob["Cliente"].astype(str).fillna("").str.strip()
    df_mob["Combo"]   = df_mob.get("Combo", "").astype(str).fillna("").str.strip()

    # Ordem final igual ao exemplo
    cols_final = ["Data", "Descrição", "Valor", "Conta", "Categoria", "serviço", "cliente", "Combo"]
    df_mobills = df_mob[cols_final].copy()

    st.markdown("**Prévia (Mobills)**")
    st.dataframe(df_mobills, use_container_width=True, hide_index=True)

    # CSV (separador ';')
    csv_bytes = df_mobills.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
    st.download_button(
        "⬇️ Baixar CSV (Mobills)",
        data=csv_bytes,
        file_name=f"Mobills_{dia_selecionado.strftime('%d-%m-%Y')}.csv",
        mime="text/csv",
        type="primary"
    )

    # XLSX (aba 'Mobills') com fallback de engine
    xlsx_mob = _to_xlsx_bytes({"Mobills": df_mobills})
    if xlsx_mob:
        st.download_button(
            "⬇️ Baixar XLSX (Mobills)",
            data=xlsx_mob,
            file_name=f"Mobills_{dia_selecionado.strftime('%d-%m-%Y')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.info("Sem engine Excel instalada (xlsxwriter/openpyxl). Use o CSV ou instale uma engine para liberar o XLSX.")
else:
    st.info("Sem dados para exportar (com o filtro atual).")

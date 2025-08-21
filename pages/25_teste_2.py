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
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from gspread.utils import rowcol_to_a1
from datetime import datetime, date
import pytz
import re

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

    # Garante colunas esperadas + Conferido
    for c in COLS_ESPERADAS + [COL_CONFERIDO]:
        if c not in df.columns:
            df[c] = ""

    # Datas
    def parse_data(x):
        if pd.isna(x) or str(x).strip() == "": return None
        if isinstance(x, (datetime, pd.Timestamp)): return x.date()
        s = str(x).strip()
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"]:
            try: return datetime.strptime(s, fmt).date()
            except: pass
        return None
    df["Data_norm"] = df["Data"].apply(parse_data)

    # Valores
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

    # Strings
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

# ---------- Helpers Sheets: Conferido ----------
def _get_ws_and_headers():
    _, _, ws = _conectar_sheets()
    vals = ws.row_values(1)
    headers = [h.strip() for h in vals] if vals else []
    return ws, headers

def _ensure_conferido_col() -> int:
    """
    Garante a coluna 'Conferido' e retorna o índice (1-based).
    - Expande colunas se necessário (ws.add_cols).
    - Escreve cabeçalho via A1 (ws.update).
    """
    ws, headers = _get_ws_and_headers()
    if COL_CONFERIDO in headers:
        return headers.index(COL_CONFERIDO) + 1

    col_idx = len(headers) + 1
    # se precisar, adiciona colunas novas
    if col_idx > ws.col_count:
        ws.add_cols(col_idx - ws.col_count)

    a1 = rowcol_to_a1(1, col_idx)
    ws.update(a1, [[COL_CONFERIDO]])
    return col_idx

def _chunked(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def marcar_conferido(rows: list[int], texto: str):
    """
    Marca as linhas na coluna 'Conferido' usando batch_update (mais estável).
    Divide em blocos para evitar limites de payload.
    """
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
    if not rows: return 0
    ws, _ = _get_ws_and_headers()
    for r in sorted(rows, reverse=True):
        ws.delete_rows(r)
    return len(rows)

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
df_rev = df_rev.reset_index(drop=True)  # alinhar com data_editor

# Duplicidades (corte repetido no mesmo dia por cliente)
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

# -------------------------
# Histórico — Dias com mais atendimentos
# -------------------------
st.subheader("📈 Histórico — Dias com mais atendimentos")
only_after_cut = st.checkbox(f"Mostrar apenas a partir de {DATA_CORRETA.strftime('%d/%m/%Y')}", value=True)

def contar_atendimentos_bloco(bloco: pd.DataFrame):
    if bloco.empty: return 0,0
    d0 = bloco["Data_norm"].dropna()
    if d0.empty: return 0, len(bloco)
    dia = d0.iloc[0]
    if dia < DATA_CORRETA: clientes = len(bloco)
    else: clientes = bloco.groupby(["Cliente","Data_norm"]).ngroups
    return clientes, len(bloco)

lista=[]
for d, bloco in df_base.groupby("Data_norm"):
    if pd.isna(d): continue
    if only_after_cut and d < DATA_CORRETA: continue
    cli_h, srv_h = contar_atendimentos_bloco(bloco)
    lista.append({"Data": d, "Clientes únicos": cli_h, "Serviços": srv_h})

df_hist = pd.DataFrame(lista).sort_values("Data")
if not df_hist.empty:
    df_hist["Data"] = pd.to_datetime(df_hist["Data"], errors="coerce")
    top_idx = df_hist["Clientes únicos"].idxmax()
    top_dia = df_hist.loc[top_idx]
    st.success(f"📅 Recorde: **{_fmt_data(top_dia['Data'])}** — **{int(top_dia['Clientes únicos'])} clientes** e **{int(top_dia['Serviços'])} serviços**.")

    df_top5 = df_hist.sort_values(["Clientes únicos","Serviços","Data"], ascending=[False,False,False]).head(5).copy()
    df_top5["Data_fmt"] = df_top5["Data"].apply(_fmt_data)

    c1, c2 = st.columns([1,1])
    with c1:
        st.markdown("**🏆 Top 5 dias (por clientes)**")
        st.dataframe(df_top5[["Data_fmt","Clientes únicos","Serviços"]].rename(columns={"Data_fmt":"Data"}), use_container_width=True, hide_index=True)
    with c2:
        st.plotly_chart(px.bar(df_top5, x="Data_fmt", y="Clientes únicos", text="Clientes únicos", title="Top 5 — Clientes por dia"), use_container_width=True)

    st.markdown("**Histórico completo**")
    df_hist_show = df_hist.copy()
    df_hist_show["Data_fmt"] = df_hist_show["Data"].apply(_fmt_data)
    st.dataframe(df_hist_show[["Data_fmt","Clientes únicos","Serviços"]].rename(columns={"Data_fmt":"Data"}), use_container_width=True, hide_index=True)
    st.plotly_chart(px.line(df_hist, x="Data", y="Clientes únicos", markers=True, title="Clientes únicos por dia (histórico)"), use_container_width=True)

# -------------------------
# Tabela do dia + exportações
# -------------------------
st.markdown("---")
df_exibe = preparar_tabela_exibicao(df_dia)
st.subheader("Registros do dia (linhas)")
st.dataframe(df_exibe, use_container_width=True, hide_index=True)

st.subheader("Resumo por Cliente (no dia)")
grp = (df_dia.groupby("Cliente", as_index=False)
       .agg(Quantidade_Serviços=("Serviço","count"), Valor_Total=("Valor_num","sum"))
       .sort_values(["Valor_Total","Quantidade_Serviços"], ascending=[False,False]))
grp["Valor_Total"] = grp["Valor_Total"].apply(format_moeda)
st.dataframe(grp.rename(columns={"Quantidade_Serviços":"Qtd. Serviços","Valor_Total":"Valor Total"}), use_container_width=True, hide_index=True)

st.markdown("### Exportar")
df_lin_export = df_exibe.copy()
df_cli_export = grp.rename(columns={"Quantidade_Serviços":"Qtd. Serviços","Valor_Total":"Valor Total"}).copy()

csv_lin = df_lin_export.to_csv(index=False).encode("utf-8-sig")
st.download_button("⬇️ Baixar Linhas (CSV)", data=csv_lin, file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}_linhas.csv", mime="text/csv")

csv_cli = df_cli_export.to_csv(index=False).encode("utf-8-sig")
st.download_button("⬇️ Baixar Resumo por Cliente (CSV)", data=csv_cli, file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}_resumo_clientes.csv", mime="text/csv")

try:
    xlsx_bytes = gerar_excel(df_lin_export, df_cli_export)
    st.download_button("⬇️ Baixar Excel (Linhas + Resumo)", data=xlsx_bytes, file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
except Exception as e:
    st.warning(f"Não foi possível gerar o Excel agora. Detalhe: {e}")

st.caption("• Regra: antes de 11/05/2025 cada linha=1 atendimento; depois: 1 atendimento por Cliente+Data. • Modo de conferência grava na coluna 'Conferido' e permite excluir sem abrir o Sheets.")

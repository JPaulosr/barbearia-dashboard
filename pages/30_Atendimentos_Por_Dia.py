# -*- coding: utf-8 -*-
# 15_Atendimentos_Masculino_Por_Dia.py
# Página: escolher um dia e ver TODOS os atendimentos (masculino),
# KPIs gerais, por funcionário, gráfico comparativo e histórico (com Top 5).

import streamlit as st
import pandas as pd
import gspread
import io
import plotly.express as px
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime, date
import pytz

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"  # Masculino
TZ = "America/Sao_Paulo"
DATA_FMT = "%d/%m/%Y"

# Funcionários oficiais
FUNC_JPAULO = "JPaulo"
FUNC_VINICIUS = "Vinicius"

# Regra de corte: a partir desta data os clientes passaram a ser anotados corretamente
DATA_CORRETA = datetime(2025, 5, 11).date()

# =========================
# UTILS
# =========================
def _tz_now():
    return datetime.now(pytz.timezone(TZ))

@st.cache_resource(show_spinner=False)
def _conectar_sheets():
    """Conecta no Google Sheets usando st.secrets['GCP_SERVICE_ACCOUNT']."""
    creds_info = st.secrets["GCP_SERVICE_ACCOUNT"]
    creds = Credentials.from_service_account_info(
        creds_info,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    return gspread.authorize(creds)

@st.cache_data(ttl=300, show_spinner=False)
def carregar_base():
    """Lê a 'Base de Dados' (masculino) direto do Google Sheets."""
    gc = _conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df = df.dropna(how="all")
    if df.empty:
        return df

    # Normaliza nomes de colunas
    df.columns = [str(c).strip() for c in df.columns]

    # Garante colunas esperadas
    cols = ["Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
            "Funcionário", "Fase", "Hora Chegada", "Hora Início",
            "Hora Saída", "Hora Saída do Salão", "Tipo"]
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

    # Normaliza strings
    for col in ["Cliente", "Serviço", "Funcionário", "Conta", "Combo", "Tipo", "Fase"]:
        df[col] = df[col].astype(str).fillna("").str.strip()

    return df

def filtrar_por_dia(df: pd.DataFrame, dia: date) -> pd.DataFrame:
    if df.empty or dia is None:
        return df.iloc[0:0]
    return df[df["Data_norm"] == dia].copy()

def contar_atendimentos_dia(df: pd.DataFrame) -> int:
    """Aplica a regra de 11/05/2025 para contar atendimentos do bloco (um único dia)."""
    if df.empty:
        return 0
    # supõe que df contém um único dia
    dia = df["Data_norm"].dropna().iloc[0]
    if dia < DATA_CORRETA:
        # Antes do marco: cada linha = 1 atendimento
        return len(df)
    else:
        # Depois do marco: 1 atendimento por Cliente + Data
        return df.groupby(["Cliente", "Data_norm"]).ngroups

def kpis(df: pd.DataFrame):
    if df.empty:
        return 0, 0, 0.0, 0.0
    clientes = contar_atendimentos_dia(df)
    servicos = len(df)
    receita = float(df["Valor_num"].sum())
    ticket = (receita / clientes) if clientes > 0 else 0.0
    return clientes, servicos, receita, ticket

def kpis_por_funcionario(df_dia: pd.DataFrame, nome_func: str):
    df_f = df_dia[df_dia["Funcionário"].str.casefold() == nome_func.casefold()].copy()
    if df_f.empty:
        return 0, 0, 0.0, 0.0
    clientes = contar_atendimentos_dia(df_f)
    servicos = len(df_f)
    receita = float(df_f["Valor_num"].sum())
    ticket = (receita / clientes) if clientes > 0 else 0.0
    return clientes, servicos, receita, ticket

def format_moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def preparar_tabela_exibicao(df: pd.DataFrame) -> pd.DataFrame:
    cols_ordem = [
        "Data", "Cliente", "Serviço", "Valor", "Conta", "Funcionário",
        "Combo", "Tipo", "Hora Chegada", "Hora Início", "Hora Saída", "Hora Saída do Salão"
    ]
    for c in cols_ordem:
        if c not in df.columns:
            df[c] = ""

    df_out = df.copy()

    # Ordena por hora de início (quando houver) e cliente
    ord_cols = []
    if "Hora Início" in df_out.columns:
        ord_cols.append("Hora Início")
    ord_cols.append("Cliente")
    try:
        df_out = df_out.sort_values(by=ord_cols, ascending=[True] * len(ord_cols))
    except Exception:
        pass

    def fmt_data(d):
        if pd.isna(d): return ""
        if isinstance(d, (datetime, pd.Timestamp)): return d.strftime(DATA_FMT)
        if isinstance(d, date): return d.strftime(DATA_FMT)
        return str(d)

    df_out["Data"] = df_out["Data_norm"].apply(fmt_data)
    df_out["Valor"] = df_out["Valor_num"].apply(format_moeda)
    return df_out[cols_ordem]

def gerar_excel(df_lin: pd.DataFrame, df_cli: pd.DataFrame) -> bytes:
    """Gera um .xlsx com duas abas: Linhas e ResumoClientes."""
    with pd.ExcelWriter(io.BytesIO(), engine="xlsxwriter") as writer:
        df_lin.to_excel(writer, sheet_name="Linhas", index=False)
        df_cli.to_excel(writer, sheet_name="ResumoClientes", index=False)
        writer.save()
        data = writer.book.filename.getvalue()
    return data

# =========================
# UI
# =========================
st.set_page_config(page_title="Atendimentos por Dia (Masculino)", page_icon="📅", layout="wide")
st.title("📅 Atendimentos por Dia — Masculino")
st.caption("KPIs do dia, comparativo por funcionário e histórico dos dias com mais atendimentos (regra de 11/05/2025 aplicada).")

with st.spinner("Carregando base masculina..."):
    df_base = carregar_base()

# -------------------------
# Seletor de dia
# -------------------------
hoje = _tz_now().date()
dia_selecionado = st.date_input("Dia", value=hoje, format="DD/MM/YYYY")
df_dia = filtrar_por_dia(df_base, dia_selecionado)

if df_dia.empty:
    st.info("Nenhum atendimento encontrado para o dia selecionado.")
    st.stop()

# -------------------------
# KPIs do dia
# -------------------------
cli, srv, rec, tkt = kpis(df_dia)
k1, k2, k3, k4 = st.columns(4)
k1.metric("👥 Clientes atendidos", f"{cli}")
k2.metric("✂️ Serviços realizados", f"{srv}")
k3.metric("💰 Receita do dia", format_moeda(rec))
k4.metric("🧾 Ticket médio", format_moeda(tkt))

st.markdown("---")

# -------------------------
# Por Funcionário (dia)
# -------------------------
st.subheader("📊 Por Funcionário (dia selecionado)")

df_j = df_dia[df_dia["Funcionário"].str.casefold() == FUNC_JPAULO.casefold()]
df_v = df_dia[df_dia["Funcionário"].str.casefold() == FUNC_VINICIUS.casefold()]

cli_j, srv_j, rec_j, tkt_j = kpis(df_j)
cli_v, srv_v, rec_v, tkt_v = kpis(df_v)

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**{FUNC_JPAULO}**")
    jj1, jj2, jj3, jj4 = st.columns(4)
    jj1.metric("Clientes", f"{cli_j}")
    jj2.metric("Serviços", f"{srv_j}")
    jj3.metric("Receita", format_moeda(rec_j))
    jj4.metric("Ticket", format_moeda(tkt_j))
with c2:
    st.markdown(f"**{FUNC_VINICIUS}**")
    vv1, vv2, vv3, vv4 = st.columns(4)
    vv1.metric("Clientes", f"{cli_v}")
    vv2.metric("Serviços", f"{srv_v}")
    vv3.metric("Receita", format_moeda(rec_v))
    vv4.metric("Ticket", format_moeda(tkt_v))

# Gráfico comparativo (Clientes x Serviços)
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

# -------------------------
# Histórico — Dias com mais atendimentos
# -------------------------
st.subheader("📈 Histórico — Dias com mais atendimentos")

# Opção para ocultar dias anteriores a DATA_CORRETA (evita poluição visual)
only_after_cut = st.checkbox(
    f"Mostrar apenas a partir de {DATA_CORRETA.strftime('%d/%m/%Y')}",
    value=True
)

# Função para contar clientes e serviços por dia com a regra de corte
def contar_atendimentos_bloco(bloco: pd.DataFrame):
    if bloco.empty:
        return 0, 0
    dia = bloco["Data_norm"].dropna().iloc[0]
    if pd.isna(dia):
        return 0, len(bloco)
    if dia < DATA_CORRETA:
        clientes = len(bloco)               # antes do marco
    else:
        clientes = bloco.groupby(["Cliente", "Data_norm"]).ngroups  # depois do marco
    servicos = len(bloco)
    return clientes, servicos

# Monta histórico
lista = []
for dia, bloco in df_base.groupby("Data_norm"):
    if pd.isna(dia):
        continue
    if only_after_cut and dia < DATA_CORRETA:
        continue
    cli_h, srv_h = contar_atendimentos_bloco(bloco)
    lista.append({"Data": dia, "Clientes únicos": cli_h, "Serviços": srv_h})

df_hist = pd.DataFrame(lista).sort_values("Data")

# Destaque do recorde e Top 5
if not df_hist.empty:
    # Recorde (mais clientes)
    top_idx = df_hist["Clientes únicos"].idxmax()
    top_dia = df_hist.loc[top_idx]
    st.success(
        f"📅 Recorde: **{top_dia['Data'].strftime('%d/%m/%Y')}** — "
        f"**{int(top_dia['Clientes únicos'])} clientes** e **{int(top_dia['Serviços'])} serviços**."
    )

    # Top 5 por clientes (desempate por serviços e data recency)
    df_top5 = df_hist.sort_values(
        ["Clientes únicos", "Serviços", "Data"],
        ascending=[False, False, False]
    ).head(5)

    col_t1, col_t2 = st.columns([1,1])
    with col_t1:
        st.markdown("**🏆 Top 5 dias (por clientes)**")
        st.dataframe(
            df_top5.assign(Data=df_top5["Data"].dt.strftime("%d/%m/%Y")),
            use_container_width=True, hide_index=True
        )

    with col_t2:
        fig_top = px.bar(
            df_top5.assign(Data=df_top5["Data"].dt.strftime("%d/%m/%Y")),
            x="Data", y="Clientes únicos", text="Clientes únicos",
            title="Top 5 — Clientes por dia"
        )
        st.plotly_chart(fig_top, use_container_width=True)

    # Tabela completa + gráfico de linha
    st.markdown("**Histórico completo**")
    st.dataframe(
        df_hist.assign(Data=df_hist["Data"].dt.strftime("%d/%m/%Y")),
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

csv_lin = df_lin_export.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ Baixar Linhas (CSV)",
    data=csv_lin,
    file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}_linhas.csv",
    mime="text/csv"
)

csv_cli = df_cli_export.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ Baixar Resumo por Cliente (CSV)",
    data=csv_cli,
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
    "• 'Por Funcionário' usa o campo **Funcionário** da base."
)

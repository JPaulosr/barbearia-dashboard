# -*- coding: utf-8 -*-
# 15_Atendimentos_Masculino_Por_Dia.py
# Página: escolher um dia e ver TODOS os atendimentos (masculino),
# KPIs gerais, por funcionário, gráfico comparativo e histórico de picos.

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

FUNC_JPAULO = "JPaulo"
FUNC_VINICIUS = "Vinicius"

# =========================
# UTILS
# =========================
def _tz_now():
    return datetime.now(pytz.timezone(TZ))

@st.cache_resource(show_spinner=False)
def _conectar_sheets():
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
    gc = _conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    df = df.dropna(how="all")
    if df.empty:
        return df

    df.columns = [str(c).strip() for c in df.columns]
    for col in ["Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
                "Funcionário", "Fase", "Hora Chegada", "Hora Início",
                "Hora Saída", "Hora Saída do Salão", "Tipo"]:
        if col not in df.columns:
            df[col] = None

    def parse_data(x):
        if pd.isna(x): return None
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
        if "," in s and "." in s: s = s.replace(".", "").replace(",", ".")
        else: s = s.replace(",", ".")
        try: return float(s)
        except: return 0.0

    df["Valor_num"] = df["Valor"].apply(parse_valor)
    for col in ["Cliente", "Serviço", "Funcionário", "Conta", "Combo", "Tipo", "Fase"]:
        df[col] = df[col].astype(str).fillna("").str.strip()
    return df

def filtrar_por_dia(df, dia: date):
    if df.empty or dia is None: return df.iloc[0:0]
    return df[df["Data_norm"] == dia].copy()

def kpis(df):
    cli = df["Cliente"].nunique() if not df.empty else 0
    srv = len(df)
    rec = float(df["Valor_num"].sum()) if not df.empty else 0.0
    tkt = (rec/cli) if cli > 0 else 0.0
    return cli, srv, rec, tkt

def format_moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# =========================
# UI
# =========================
st.set_page_config(page_title="Atendimentos por Dia (Masculino)", page_icon="📅", layout="wide")

st.title("📅 Atendimentos por Dia — Masculino")
st.caption("KPIs do dia, comparativo por funcionário e histórico dos dias com mais atendimentos.")

with st.spinner("Carregando base masculina..."):
    df_base = carregar_base()

# =========================
# SELETOR DE DIA
# =========================
hoje = _tz_now().date()
dia_selecionado = st.date_input("Dia", value=hoje, format="DD/MM/YYYY")

df_dia = filtrar_por_dia(df_base, dia_selecionado)

if df_dia.empty:
    st.info("Nenhum atendimento encontrado para o dia selecionado.")
    st.stop()

# =========================
# KPIs GERAIS
# =========================
cli, srv, rec, tkt = kpis(df_dia)
k1, k2, k3, k4 = st.columns(4)
k1.metric("👥 Clientes atendidos", f"{cli}")
k2.metric("✂️ Serviços realizados", f"{srv}")
k3.metric("💰 Receita do dia", format_moeda(rec))
k4.metric("🧾 Ticket médio", format_moeda(tkt))

st.markdown("---")

# =========================
# POR FUNCIONÁRIO
# =========================
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

# Gráfico comparativo
df_comp = pd.DataFrame([
    {"Funcionário": FUNC_JPAULO, "Clientes": cli_j, "Serviços": srv_j},
    {"Funcionário": FUNC_VINICIUS, "Clientes": cli_v, "Serviços": srv_v},
])
fig = px.bar(df_comp.melt(id_vars="Funcionário", var_name="Métrica", value_name="Quantidade"),
             x="Funcionário", y="Quantidade", color="Métrica", barmode="group",
             title=f"Comparativo de atendimentos em {dia_selecionado.strftime('%d/%m/%Y')}")
st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# =========================
# HISTÓRICO — QUAL O DIA COM MAIS ATENDIMENTOS
# =========================
st.subheader("📈 Histórico — Dias com mais atendimentos")

# Contagem total de clientes únicos por dia
df_hist = (
    df_base.groupby("Data_norm", as_index=False)
    .agg(
        Clientes=("Cliente", "nunique"),
        Servicos=("Serviço", "count")
    )
    .dropna()
    .sort_values("Data_norm")
)

# Dia com maior nº de clientes
if not df_hist.empty:
    top_dia = df_hist.loc[df_hist["Clientes"].idxmax()]
    st.success(
        f"📅 O dia com **maior número de clientes atendidos** foi **{top_dia['Data_norm'].strftime('%d/%m/%Y')}** "
        f"com **{int(top_dia['Clientes'])} clientes** e **{int(top_dia['Servicos'])} serviços.**"
    )

    # Tabela e gráfico
    st.dataframe(df_hist.rename(columns={
        "Data_norm": "Data", "Clientes": "Clientes únicos", "Servicos": "Serviços"
    }), use_container_width=True, hide_index=True)

    fig2 = px.line(df_hist, x="Data_norm", y="Clientes", markers=True,
                   title="Clientes únicos por dia")
    st.plotly_chart(fig2, use_container_width=True)

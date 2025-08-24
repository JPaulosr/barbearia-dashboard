# -*- coding: utf-8 -*-
# 12_Dashboard_Funcionario.py — Dashboard por Funcionário
# FIADO corrigido: "Pago" só vale com DataPagamento <= dt_fim do filtro (ou status textual pago).

import streamlit as st
import pandas as pd
import numpy as np
import io, re
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime, date, timedelta
import pytz
import plotly.express as px

# =============================
# CONFIG
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
ABA_DESPESAS = "Despesas"
TZ = "America/Sao_Paulo"

DEFAULT_PCT_MAP = {"Vinicius": 0.50}

# Colunas na Base
COL_DATA      = "Data"
COL_SERVICO   = "Serviço"
COL_VALOR     = "Valor"
COL_CLIENTE   = "Cliente"
COL_FUNC      = "Funcionário"
COL_TIPO      = "Tipo"
COL_STATUSF   = "StatusFiado"
COL_DT_PAG    = "DataPagamento"
COL_PCT       = "% Comissão"
COL_REFID     = "RefID"

# Colunas alternativas que podem indicar FIADO
FIADO_HINT_COLS = [
    COL_TIPO, "Conta", "Forma de pagamento", "Forma de Pagamento",
    "Pagamento", "Status", "Meio de Pagamento", "Categoria"
]

# Despesas
DESP_COL_DATA   = "Data"
DESP_COL_VALOR  = "Valor"
DESP_TXT_CANDS  = ["Categoria", "Descrição", "Descricao", "Tipo", "Conta", "Histórico"]

# =============================
# CONEXÃO
# =============================
@st.cache_resource(show_spinner=False)
def conectar_sheets():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["GCP_SERVICE_ACCOUNT"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(show_spinner=False, ttl=300)
def carregar_base():
    gc = conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")

    # Data
    if COL_DATA in df.columns:
        def _parse(x):
            if pd.isna(x): return None
            if isinstance(x,(datetime,date)): return pd.to_datetime(x)
            s=str(x).strip()
            for fmt in ("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y"):
                try: return pd.to_datetime(s, format=fmt, dayfirst=True)
                except: pass
            return pd.to_datetime(s, dayfirst=True, errors="coerce")
        df[COL_DATA] = df[COL_DATA].apply(_parse)

    # Valor
    if COL_VALOR in df.columns:
        df[COL_VALOR] = pd.to_numeric(df[COL_VALOR], errors="coerce").fillna(0.0)

    # % Comissão
    if COL_PCT in df.columns:
        def _pct(v):
            if pd.isna(v): return None
            s=str(v).strip().replace(",",".")
            if s.endswith("%"):
                try: return float(s[:-1])/100.0
                except: return None
            try:
                f=float(s); return f/100.0 if f>1 else f
            except: return None
        df[COL_PCT] = df[COL_PCT].apply(_pct)

    return df

@st.cache_data(show_spinner=False, ttl=300)
def carregar_despesas():
    try:
        gc = conectar_sheets()
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(ABA_DESPESAS)
        d = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")
    except Exception:
        return pd.DataFrame()

    if DESP_COL_DATA in d.columns:
        def _pd(x):
            if pd.isna(x): return None
            if isinstance(x,(datetime,date)): return pd.to_datetime(x)
            s=str(x).strip()
            for fmt in ("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y"):
                try: return pd.to_datetime(s, format=fmt, dayfirst=True)
                except: pass
            return pd.to_datetime(s, dayfirst=True, errors="coerce")
        d[DESP_COL_DATA] = d[DESP_COL_DATA].apply(_pd)
    if DESP_COL_VALOR in d.columns:
        d[DESP_COL_VALOR] = pd.to_numeric(d[DESP_COL_VALOR], errors="coerce").fillna(0.0)

    txt_cols = [c for c in DESP_TXT_CANDS if c in d.columns]
    d["_texto"] = d[txt_cols].astype(str).agg(" ".join, axis=1).str.lower() if txt_cols else ""
    return d

# =============================
# DETECÇÃO DE FIADO
# =============================
def _parse_date_any(x):
    if pd.isna(x): return None
    if isinstance(x,(datetime,date)): return pd.to_datetime(x)
    s=str(x).strip()
    for fmt in ("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y"):
        try: return pd.to_datetime(s, format=fmt, dayfirst=True)
        except: pass
    return pd.to_datetime(s, dayfirst=True, errors="coerce")

def detectar_fiado_e_pago(df: pd.DataFrame, dt_ref: date):
    """dt_ref = data final do filtro (para validar DataPagamento <= dt_ref)."""
    if df.empty:
        return pd.Series(dtype=bool), pd.Series(dtype=bool), {"fiado_cols": [], "status_cols": []}

    # FIADO: procura 'fiado' em várias colunas
    fiado_cols_presentes = [c for c in FIADO_HINT_COLS if c in df.columns]
    if fiado_cols_presentes:
        textos = df[fiado_cols_presentes].astype(str).agg(" ".join, axis=1).str.lower()
        eh_fiado = textos.str.contains(r"\bfiado\b", na=False)
    else:
        eh_fiado = df.get(COL_TIPO, pd.Series([""]*len(df))).astype(str).str.lower().eq("fiado")

    # PAGO: status textual OU DataPagamento válida <= dt_ref
    status_cols = []
    pago_mask = pd.Series(False, index=df.index)

    if COL_STATUSF in df.columns:
        status_cols.append(COL_STATUSF)
        pago_mask |= df[COL_STATUSF].astype(str).str.strip().str.lower().isin(
            ["pago","paga","quitado","quitada","liberado","liberada"]
        )
    for alt in ["Status","Situação","Situacao"]:
        if alt in df.columns:
            status_cols.append(alt)
            pago_mask |= df[alt].astype(str).str.strip().str.lower().isin(
                ["pago","paga","quitado","quitada","liberado","liberada"]
            )

    if COL_DT_PAG in df.columns:
        status_cols.append(COL_DT_PAG)
        dp = df[COL_DT_PAG].apply(_parse_date_any)
        pago_mask |= (pd.to_datetime(dp, errors="coerce").dt.date <= dt_ref)

    debug = {"fiado_cols": fiado_cols_presentes, "status_cols": status_cols}
    return eh_fiado, pago_mask, debug

# =============================
# LÓGICA
# =============================
def preparar_df_funcionario(df_raw: pd.DataFrame, funcionario: str,
                            incluir_fiado_nao_pago: bool, dt_ref: date):
    if df_raw.empty:
        vazio = df_raw.head(0)
        return vazio, dict(total=0, fiados_total=0, fiados_pagos=0, fiados_nao_pagos=0, considerados=0), {}

    df = df_raw.copy()

    # Filtra funcionário
    if COL_FUNC in df.columns:
        df = df[df[COL_FUNC].astype(str).str.strip().str.lower() == str(funcionario).strip().lower()]
    else:
        df = df.head(0)

    if df.empty:
        return df, dict(total=0, fiados_total=0, fiados_pagos=0, fiados_nao_pagos=0, considerados=0), {}

    # FIADO/PAGO com dt_ref
    eh_fiado, pago_mask, dbg = detectar_fiado_e_pago(df, dt_ref)

    fiados_total = int(eh_fiado.sum())
    fiados_pagos = int((eh_fiado & pago_mask).sum())
    fiados_nao_pagos = int((eh_fiado & ~pago_mask).sum())

    # Aplica toggle
    if not incluir_fiado_nao_pago:
        df = df[(~eh_fiado) | (eh_fiado & pago_mask)]

    considerados = len(df)

    # Valor e % comissão
    df["Valor_para_comissao"] = df[COL_VALOR].astype(float)
    if COL_PCT in df.columns and df[COL_PCT].notna().any():
        df["Pct_Comissao"] = df[COL_PCT].fillna(DEFAULT_PCT_MAP.get(funcionario, 0.0))
    else:
        df["Pct_Comissao"] = DEFAULT_PCT_MAP.get(funcionario, 0.0)
    df["Comissao_R$"] = (df["Valor_para_comissao"] * df["Pct_Comissao"]).round(2)

    # Partições de tempo
    df["Ano"] = pd.to_datetime(df[COL_DATA]).dt.year
    df["Mes"] = pd.to_datetime(df[COL_DATA]).dt.month
    df["Dia"] = pd.to_datetime(df[COL_DATA]).dt.date

    resumo = dict(
        total=int(len(df_raw[df_raw[COL_FUNC].astype(str).str.strip().str.lower() ==
                             str(funcionario).strip().lower()])) if COL_FUNC in df_raw.columns else 0,
        fiados_total=fiados_total,
        fiados_pagos=fiados_pagos,
        fiados_nao_pagos=fiados_nao_pagos,
        considerados=considerados
    )
    return df, resumo, dbg

def resumo_cards(df, ano=None, mes=None, titulo="Resumo"):
    if df.empty:
        return dict(atend=0, clientes=0, base=0.0, com=0.0, titulo=titulo)
    dfx = df.copy()
    if ano is not None: dfx = dfx[dfx["Ano"] == int(ano)]
    if mes is not None: dfx = dfx[dfx["Mes"] == int(mes)]
    if dfx.empty: return dict(atend=0, clientes=0, base=0.0, com=0.0, titulo=titulo)
    atend = len(dfx)
    clientes = dfx[COL_CLIENTE].astype(str).str.strip().nunique() if COL_CLIENTE in dfx.columns else atend
    base = float(dfx["Valor_para_comissao"].sum().round(2))
    com = float(dfx["Comissao_R$"].sum().round(2))
    return dict(atend=atend, clientes=clientes, base=base, com=com, titulo=titulo)

def fmt_moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def card_html(titulo, v1_label, v1, v2_label, v2):
    return f"""
    <div style="background:#121212;border:1px solid #2a2a2a;border-radius:16px;
                padding:16px;color:#eaeaea;box-shadow:0 2px 10px rgba(0,0,0,0.25);">
      <div style="font-size:13px;opacity:.8;margin-bottom:6px;">{titulo}</div>
      <div style="display:flex;justify-content:space-between;gap:16px;">
        <div><div style="font-size:12px;opacity:.7;">{v1_label}</div>
             <div style="font-size:22px;font-weight:700;">{v1}</div></div>
        <div style="text-align:right;"><div style="font-size:12px;opacity:.7;">{v2_label}</div>
             <div style="font-size:22px;font-weight:700;">{v2}</div></div>
      </div>
    </div>
    """

def presets_periodo(hoje_dt):
    inicio_mes = hoje_dt.replace(day=1)
    inicio_ano = hoje_dt.replace(month=1, day=1)
    return {
        "Mês atual": (inicio_mes.date(), hoje_dt.date()),
        "Últimos 7 dias": ((hoje_dt - timedelta(days=6)).date(), hoje_dt.date()),
        "Últimos 30 dias": ((hoje_dt - timedelta(days=29)).date(), hoje_dt.date()),
        "Trimestre (90d)": ((hoje_dt - timedelta(days=89)).date(), hoje_dt.date()),
        "Ano atual": (inicio_ano.date(), hoje_dt.date()),
    }

def filtrar_por_periodo(df, dt_ini, dt_fim):
    if df.empty: return df
    mask = (pd.to_datetime(df[COL_DATA]).dt.date >= dt_ini) & (pd.to_datetime(df[COL_DATA]).dt.date <= dt_fim)
    return df[mask].copy()

def to_excel_bytes(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="dados")
    return output.getvalue()

def extrair_comissao_vinicius_despesas(desp: pd.DataFrame, dt_ini, dt_fim):
    if desp.empty: return 0.0, 0.0
    d = desp.copy()
    d = d[(pd.to_datetime(d[DESP_COL_DATA]).dt.date >= dt_ini) & (pd.to_datetime(d[DESP_COL_DATA]).dt.date <= dt_fim)]
    total = float(d[DESP_COL_VALOR].sum().round(2)) if DESP_COL_VALOR in d.columns else 0.0
    mask_com_vin = d["_texto"].str.contains(r"comiss", na=False) & d["_texto"].str.contains(r"vini", na=False)
    com_vin = float(d.loc[mask_com_vin, DESP_COL_VALOR].sum().round(2)) if DESP_COL_VALOR in d.columns else 0.0
    return com_vin, total

# =============================
# UI
# =============================
st.set_page_config(page_title="Dashboard Funcionário", layout="wide")
st.title("📊 Dashboard Funcionário")

df_raw = carregar_base()
despesas_raw = carregar_despesas()

# Topbar
top1, top2, top3, top4, top5 = st.columns([1.1, 1.1, 1.4, 1.1, 1.3])
with top1:
    incluir_fiado = st.toggle("Incluir FIADO não pago", value=False,
                              help="Ligado: considera fiados não pagos. Desligado: só não-fiado e fiados quitados.")
with top2:
    if COL_FUNC in df_raw.columns and not df_raw.empty:
        funcoes = (df_raw[COL_FUNC].dropna().astype(str).str.strip()
                   .replace("", pd.NA).dropna().unique().tolist())
        funcoes = sorted(funcoes, key=lambda s: s.lower())
    else:
        funcoes = []
    default_idx = funcoes.index("Vinicius") if "Vinicius" in funcoes else 0
    funcionario = st.selectbox("Funcionário", options=funcoes if funcoes else ["(sem dados)"],
                               index=default_idx if funcoes else 0)

tz = pytz.timezone(TZ)
hoje = datetime.now(tz)
with top3:
    preset_nome = st.selectbox("Período rápido", options=list(presets_periodo(hoje).keys()), index=0)
    dt_ini_preset, dt_fim_preset = presets_periodo(hoje)[preset_nome]
with top4:
    dt_ini = st.date_input("De", value=dt_ini_preset, format="DD/MM/YYYY")
with top5:
    dt_fim = st.date_input("Até", value=dt_fim_preset, format="DD/MM/YYYY")

# Dados do funcionário + FIADO usando dt_fim como referência de pagamento
df_func, resumo_fiado, dbg_cols = preparar_df_funcionario(
    df_raw, funcionario, incluir_fiado_nao_pago=incluir_fiado, dt_ref=dt_fim
)
dfp = filtrar_por_periodo(df_func, dt_ini, dt_fim)

# Banner
st.caption(
    f"**FIADO** — Total (funcionário): **{resumo_fiado['fiados_total']}** | "
    f"Pagos: **{resumo_fiado['fiados_pagos']}** | "
    f"Não pagos: **{resumo_fiado['fiados_nao_pagos']}** | "
    f"**Considerados** no cálculo (após regras/toggle & período): **{len(dfp)}**. "
    + ("Incluindo fiados não pagos." if incluir_fiado else "Excluindo fiados não pagos.")
)
st.caption(
    f"🧪 Detecção FIADO: {', '.join(dbg_cols.get('fiado_cols', []) or ['(sem colunas explícitas)'])} | "
    f"Pago por: {', '.join(dbg_cols.get('status_cols', []) or ['(sem status/data)'])} (DataPagamento ≤ {dt_fim.strftime('%d/%m/%Y')})"
)

# =============================
# CARDS
# =============================
colc1, colc2, colc3, colc4 = st.columns(4)
mes_ref, ano_ref = dt_fim.month, dt_fim.year
res_mes = resumo_cards(dfp, ano=ano_ref, mes=mes_ref, titulo=f"Mês {mes_ref:02d}/{ano_ref}")
res_ano = resumo_cards(dfp, ano=ano_ref, titulo=f"Ano {ano_ref}")

if funcionario.lower() != "jpaulo":
    with colc1:
        st.markdown(card_html(res_mes["titulo"], "Atendimentos", f"{res_mes['atend']}",
                              "Clientes únicos", f"{res_mes['clientes']}"), unsafe_allow_html=True)
    with colc2:
        st.markdown(card_html("Base p/ comissão (Mês)", "Base", fmt_moeda(res_mes["base"]),
                              "Comissão", fmt_moeda(res_mes["com"])), unsafe_allow_html=True)
    with colc3:
        st.markdown(card_html(res_ano["titulo"], "Atendimentos", f"{res_ano['atend']}",
                              "Clientes únicos", f"{res_ano['clientes']}"), unsafe_allow_html=True)
    with colc4:
        st.markdown(card_html("Base p/ comissão (Ano)", "Base", fmt_moeda(res_ano["base"]),
                              "Comissão", fmt_moeda(res_ano["com"])), unsafe_allow_html=True)
else:
    bruto_jp = float(dfp["Valor_para_comissao"].sum().round(2)) if not dfp.empty else 0.0
    df_vin, _, _ = preparar_df_funcionario(df_raw, "Vinicius", incluir_fiado_nao_pago=incluir_fiado, dt_ref=dt_fim)
    df_vin_periodo = filtrar_por_periodo(df_vin, dt_ini, dt_fim)
    bruto_vin = float(df_vin_periodo["Valor_para_comissao"].sum().round(2)) if not df_vin_periodo.empty else 0.0
    com_vin_desp, total_desp = extrair_comissao_vinicius_despesas(despesas_raw, dt_ini, dt_fim)
    if com_vin_desp <= 0 and not df_vin_periodo.empty:
        com_vin_est = float((df_vin_periodo["Valor_para_comissao"] * df_vin_periodo["Pct_Comissao"]).sum().round(2))
        com_vin, fonte_comissao = com_vin_est, "estimada (Base × %)"
    else:
        com_vin, fonte_comissao = com_vin_desp, "Despesas"
    outras_desp = max(total_desp - com_vin, 0.0)
    lucro_pos_com = bruto_jp + (bruto_vin - com_vin)
    lucro_liquido  = lucro_pos_com - outras_desp
    with colc1:
        st.markdown(card_html("Bruto JPaulo (período)", "Receita", fmt_moeda(bruto_jp),
                              "Bruto Vinicius", fmt_moeda(bruto_vin)), unsafe_allow_html=True)
    with colc2:
        st.markdown(card_html(f"Comissão Vinicius ({fonte_comissao})", "Comissão", fmt_moeda(com_vin),
                              "Outras despesas", fmt_moeda(outras_desp)), unsafe_allow_html=True)
    with colc3:
        st.markdown(card_html("Lucro após comissão", "Cálculo", "JP + (VIN − Comissão)",
                              "Valor", fmt_moeda(lucro_pos_com)), unsafe_allow_html=True)
    with colc4:
        st.markdown(card_html("Lucro líquido (período)", "Cálculo",
                              "Lucro pós comissão − Outras despesas", "Valor",
                              fmt_moeda(lucro_liquido)), unsafe_allow_html=True)

st.divider()

# =============================
# GRÁFICOS
# =============================
g1, g2 = st.columns(2)

with g1:
    st.subheader("🔝 Top Serviços (período)")
    if not dfp.empty and COL_SERVICO in dfp.columns:
        top_serv = (dfp.groupby(COL_SERVICO, dropna=False)
                      .agg(Qtde=("Valor_para_comissao","count"),
                           Base=("Valor_para_comissao","sum"),
                           Comissao=("Comissao_R$","sum"))
                      .reset_index()
                      .sort_values(["Base","Qtde"], ascending=[False,False]))
        top_serv["Base"] = top_serv["Base"].round(2)
        fig = px.bar(top_serv.head(12), x="Base", y=COL_SERVICO, orientation="h",
                     labels={"Base":"Base (R$)", COL_SERVICO:"Serviço"})
        fig.update_layout(height=420, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados de serviços no período.")

with g2:
    st.subheader("👥 Top Clientes (período)")
    if not dfp.empty and COL_CLIENTE in dfp.columns:
        top_cli = (dfp.groupby(COL_CLIENTE, dropna=False)
                      .agg(Qtde=("Valor_para_comissao","count"),
                           Base=("Valor_para_comissao","sum"),
                           Comissao=("Comissao_R$","sum"))
                      .reset_index()
                      .sort_values(["Base","Qtde"], ascending=[False,False]))
        top_cli["Base"] = top_cli["Base"].round(2)
        fig = px.bar(top_cli.head(12), x="Base", y=COL_CLIENTE, orientation="h",
                     labels={"Base":"Base (R$)", COL_CLIENTE:"Cliente"})
        fig.update_layout(height=420, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados de clientes no período.")

h1, h2 = st.columns(2)
with h1:
    st.subheader("📈 Evolução mensal (Base e Comissão)")
    if not dfp.empty:
        dfm = (dfp.assign(AnoMes=pd.to_datetime(dfp[COL_DATA]).dt.to_period("M").astype(str))
                  .groupby("AnoMes")
                  .agg(Base=("Valor_para_comissao","sum"),
                       Comissao=("Comissao_R$","sum"),
                       Qtde=("Valor_para_comissao","count"))
                  .reset_index().sort_values("AnoMes"))
        fig = px.line(dfm, x="AnoMes", y=["Base","Comissao"], markers=True,
                      labels={"value":"R$","AnoMes":"Competência","variable":"Métrica"})
        fig.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados para evolução mensal.")

with h2:
    st.subheader("📆 Evolução diária (Base)")
    if not dfp.empty:
        dfd = (dfp.groupby("Dia")
                  .agg(Base=("Valor_para_comissao","sum"),
                       Qtde=("Valor_para_comissao","count"))
                  .reset_index().sort_values("Dia"))
        fig = px.line(dfd, x="Dia", y="Base", markers=True, labels={"Base":"R$","Dia":"Dia"})
        fig.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem dados para evolução diária.")

st.divider()

# =============================
# TABELA DETALHADA + DOWNLOAD
# =============================
st.subheader("📄 Detalhe das linhas (período)")
if not dfp.empty:
    cols_show = [c for c in [COL_DATA, COL_CLIENTE, COL_SERVICO, COL_VALOR,
                             "Valor_para_comissao", "Pct_Comissao", "Comissao_R$",
                             COL_TIPO, COL_STATUSF, COL_DT_PAG, COL_REFID] if c in dfp.columns]
    dfd = dfp[cols_show].copy()
    if COL_DATA in dfd.columns:
        dfd[COL_DATA] = pd.to_datetime(dfd[COL_DATA], errors="coerce").dt.strftime("%d/%m/%Y")
    if "Valor_para_comissao" in dfd.columns:
        dfd["Valor_para_comissao"] = dfd["Valor_para_comissao"].apply(fmt_moeda)
    if "Comissao_R$" in dfd.columns:
        dfd["Comissao_R$"] = dfd["Comissao_R$"].apply(fmt_moeda)
    if "Pct_Comissao" in dfd.columns:
        dfd["Pct_Comissao"] = (pd.to_numeric(dfd["Pct_Comissao"], errors="coerce").fillna(0)*100)\
                                .round(0).astype(int).astype(str) + "%"

    st.dataframe(dfd, hide_index=True, use_container_width=True)

    raw_export = dfp[cols_show].copy()
    if COL_DATA in raw_export.columns:
        raw_export[COL_DATA] = pd.to_datetime(raw_export[COL_DATA], errors="coerce").dt.strftime("%Y-%m-%d")
    if "Pct_Comissao" in raw_export.columns:
        raw_export["Pct_Comissao"] = (pd.to_numeric(raw_export["Pct_Comissao"], errors="coerce").fillna(0).round(4))

    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Baixar CSV (período)",
            data=raw_export.to_csv(index=False).encode("utf-8"),
            file_name=f"dashboard_{funcionario}_{dt_ini.strftime('%Y%m%d')}_{dt_fim.strftime('%Y%m%d')}.csv",
            mime="text/csv")
    with c2:
        st.download_button("⬇️ Baixar Excel (período)",
            data=to_excel_bytes(raw_export),
            file_name=f"dashboard_{funcionario}_{dt_ini.strftime('%Y%m%d')}_{dt_fim.strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("Sem linhas no período selecionado.")

# =============================
# RODAPÉ
# =============================
rodape = f"""
<small>
• Funcionário: <b>{funcionario}</b>. Período: <b>{dt_ini.strftime('%d/%m/%Y')}</b> a <b>{dt_fim.strftime('%d/%m/%Y')}</b>.<br>
• Toggle FIADO: <b>{'inclui' if incluir_fiado else 'exclui'}</b> fiados sem pagamento até {dt_fim.strftime('%d/%m/%Y')}.
</small>
"""
st.markdown(rodape, unsafe_allow_html=True)

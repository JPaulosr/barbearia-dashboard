# -*- coding: utf-8 -*-
# 12_Dashboard_Funcionario.py — Dashboard por Funcionário
# - Comissão padrão
# - Modo especial para JPaulo: Bruto JP, Bruto Vinicius, Comissão Vinicius, Outras despesas, Lucro
# - Exportação CSV + Excel (openpyxl)

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

# % padrão por funcionário
DEFAULT_PCT_MAP = {"Vinicius": 0.50}  # 50% Vinicius; JPaulo e outros = 0%

# Colunas
COL_DATA, COL_SERVICO, COL_VALOR, COL_CLIENTE = "Data", "Serviço", "Valor", "Cliente"
COL_FUNC, COL_TIPO, COL_STATUSF, COL_DT_PAG = "Funcionário", "Tipo", "StatusFiado", "DataPagamento"
COL_PCT, COL_REFID = "% Comissão", "RefID"
DESP_COL_DATA, DESP_COL_VALOR = "Data", "Valor"
DESP_TXT_CANDS = ["Categoria", "Descrição", "Descricao", "Tipo", "Conta", "Histórico"]

# =============================
# CONEXÃO
# =============================
@st.cache_resource(show_spinner=False)
def conectar_sheets():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(st.secrets["GCP_SERVICE_ACCOUNT"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(show_spinner=False, ttl=300)
def carregar_base():
    gc = conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0).dropna(how="all")

    # datas
    if COL_DATA in df.columns:
        def _pd(x):
            if pd.isna(x): return None
            if isinstance(x, (datetime, date)): return pd.to_datetime(x)
            return pd.to_datetime(str(x), dayfirst=True, errors="coerce")
        df[COL_DATA] = df[COL_DATA].apply(_pd)

    if COL_VALOR in df.columns:
        df[COL_VALOR] = pd.to_numeric(df[COL_VALOR], errors="coerce").fillna(0.0)

    if COL_PCT in df.columns:
        def _pct(v):
            if pd.isna(v): return None
            s = str(v).replace(",", ".")
            if s.endswith("%"): return float(s[:-1]) / 100
            try:
                f = float(s)
                return f/100 if f > 1 else f
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
        d[DESP_COL_DATA] = pd.to_datetime(d[DESP_COL_DATA], errors="coerce")

    if DESP_COL_VALOR in d.columns:
        d[DESP_COL_VALOR] = pd.to_numeric(d[DESP_COL_VALOR], errors="coerce").fillna(0.0)

    txt_cols = [c for c in DESP_TXT_CANDS if c in d.columns]
    d["_texto"] = d[txt_cols].astype(str).agg(" ".join, axis=1).str.lower() if txt_cols else ""
    return d

# =============================
# LÓGICA
# =============================
def preparar_df_funcionario(df_raw, funcionario, incluir_fiado):
    if df_raw.empty: return df_raw.head(0)
    df = df_raw.copy()
    df = df[df[COL_FUNC].astype(str).str.lower() == funcionario.lower()]
    if df.empty: return df

    tipo_series = df[COL_TIPO].astype(str).str.lower() if COL_TIPO in df.columns else ""
    eh_fiado = tipo_series.eq("fiado")
    pago_mask = pd.Series([False]*len(df), index=df.index)
    if COL_STATUSF in df.columns:
        pago_mask |= df[COL_STATUSF].astype(str).str.lower().isin(["pago","quitado","liberado"])
    if COL_DT_PAG in df.columns:
        pago_mask |= df[COL_DT_PAG].notna()

    if not incluir_fiado:
        df = df[(~eh_fiado) | (eh_fiado & pago_mask)]

    df["Valor_para_comissao"] = df[COL_VALOR].astype(float)
    if COL_PCT in df.columns and df[COL_PCT].notna().any():
        df["Pct_Comissao"] = df[COL_PCT].fillna(DEFAULT_PCT_MAP.get(funcionario,0.0))
    else:
        df["Pct_Comissao"] = DEFAULT_PCT_MAP.get(funcionario,0.0)
    df["Comissao_R$"] = (df["Valor_para_comissao"] * df["Pct_Comissao"]).round(2)

    df["Ano"] = pd.to_datetime(df[COL_DATA]).dt.year
    df["Mes"] = pd.to_datetime(df[COL_DATA]).dt.month
    df["Dia"] = pd.to_datetime(df[COL_DATA]).dt.date
    return df

def resumo_cards(df, ano=None, mes=None, titulo="Resumo"):
    if df.empty: return dict(atend=0, clientes=0, base=0.0, com=0.0, titulo=titulo)
    dfx = df.copy()
    if ano: dfx = dfx[dfx["Ano"]==ano]
    if mes: dfx = dfx[dfx["Mes"]==mes]
    atend = len(dfx)
    clientes = dfx[COL_CLIENTE].astype(str).str.strip().nunique() if COL_CLIENTE in dfx.columns else atend
    base = dfx["Valor_para_comissao"].sum()
    com = dfx["Comissao_R$"].sum()
    return dict(atend=atend, clientes=clientes, base=base, com=com, titulo=titulo)

def fmt_moeda(v): return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X",".")

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

def presets_periodo(hoje):
    inicio_mes = hoje.replace(day=1)
    inicio_ano = hoje.replace(month=1, day=1)
    return {
        "Mês atual": (inicio_mes.date(), hoje.date()),
        "Últimos 7 dias": ((hoje - timedelta(days=6)).date(), hoje.date()),
        "Últimos 30 dias": ((hoje - timedelta(days=29)).date(), hoje.date()),
        "Ano atual": (inicio_ano.date(), hoje.date()),
    }

def filtrar_por_periodo(df, dt_ini, dt_fim):
    if df.empty: return df
    mask = (df[COL_DATA].dt.date >= dt_ini) & (df[COL_DATA].dt.date <= dt_fim)
    return df[mask]

def to_excel_bytes(df):
    """Tenta gerar Excel com openpyxl; se não existir, retorna None"""
    try:
        import openpyxl
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="dados")
        return output.getvalue()
    except Exception:
        return None

def extrair_comissao_vinicius_despesas(desp, dt_ini, dt_fim):
    if desp.empty: return 0.0, 0.0
    d = desp[(desp[DESP_COL_DATA].dt.date >= dt_ini) & (desp[DESP_COL_DATA].dt.date <= dt_fim)]
    total = d[DESP_COL_VALOR].sum() if DESP_COL_VALOR in d.columns else 0.0
    mask_com_vin = d["_texto"].str.contains("comiss",na=False) & d["_texto"].str.contains("vini",na=False)
    com_vin = d.loc[mask_com_vin, DESP_COL_VALOR].sum() if DESP_COL_VALOR in d.columns else 0.0
    return com_vin, total

# =============================
# UI
# =============================
st.set_page_config(page_title="Dashboard Funcionário", layout="wide")
st.title("📊 Dashboard Funcionário")

df_raw = carregar_base()
despesas_raw = carregar_despesas()

# filtros
col1,col2,col3,col4 = st.columns([1,1,1,1])
with col1: incluir_fiado = st.toggle("Incluir FIADO não pago", False)
with col2:
    funcoes = sorted(df_raw[COL_FUNC].dropna().unique()) if COL_FUNC in df_raw.columns else []
    funcionario = st.selectbox("Funcionário", funcoes, index=funcoes.index("Vinicius") if "Vinicius" in funcoes else 0)
tz = pytz.timezone(TZ); hoje = datetime.now(tz)
with col3:
    preset = st.selectbox("Período rápido", list(presets_periodo(hoje).keys()), index=0)
    dt_ini_preset, dt_fim_preset = presets_periodo(hoje)[preset]
with col4:
    dt_ini = st.date_input("De", dt_ini_preset, format="DD/MM/YYYY")
    dt_fim = st.date_input("Até", dt_fim_preset, format="DD/MM/YYYY")

# dados
df_func = preparar_df_funcionario(df_raw, funcionario, incluir_fiado)
dfp = filtrar_por_periodo(df_func, dt_ini, dt_fim)

# CARDS
c1,c2,c3,c4 = st.columns(4)
mes_ref, ano_ref = dt_fim.month, dt_fim.year
res_mes = resumo_cards(dfp, ano_ref, mes_ref, f"Mês {mes_ref:02d}/{ano_ref}")
res_ano = resumo_cards(dfp, ano_ref, titulo=f"Ano {ano_ref}")

if funcionario.lower() != "jpaulo":
    with c1: st.markdown(card_html(res_mes["titulo"],"Atendimentos",res_mes["atend"],"Clientes únicos",res_mes["clientes"]), unsafe_allow_html=True)
    with c2: st.markdown(card_html("Base p/ comissão (Mês)","Base",fmt_moeda(res_mes["base"]),"Comissão",fmt_moeda(res_mes["com"])), unsafe_allow_html=True)
    with c3: st.markdown(card_html(res_ano["titulo"],"Atendimentos",res_ano["atend"],"Clientes únicos",res_ano["clientes"]), unsafe_allow_html=True)
    with c4: st.markdown(card_html("Base p/ comissão (Ano)","Base",fmt_moeda(res_ano["base"]),"Comissão",fmt_moeda(res_ano["com"])), unsafe_allow_html=True)
else:
    bruto_jp = dfp["Valor_para_comissao"].sum() if not dfp.empty else 0.0
    df_vin = preparar_df_funcionario(df_raw, "Vinicius", incluir_fiado)
    df_vin_p = filtrar_por_periodo(df_vin, dt_ini, dt_fim)
    bruto_vin = df_vin_p["Valor_para_comissao"].sum() if not df_vin_p.empty else 0.0
    com_vin_desp, total_desp = extrair_comissao_vinicius_despesas(despesas_raw, dt_ini, dt_fim)
    if com_vin_desp<=0 and not df_vin_p.empty:
        com_vin = (df_vin_p["Valor_para_comissao"]*df_vin_p["Pct_Comissao"]).sum()
    else:
        com_vin = com_vin_desp
    outras_desp = max(total_desp - com_vin,0)
    lucro_pos_com = bruto_jp + (bruto_vin - com_vin)
    lucro_liquido = lucro_pos_com - outras_desp

    with c1: st.markdown(card_html("Bruto JPaulo","Receita",fmt_moeda(bruto_jp),"Bruto Vinicius",fmt_moeda(bruto_vin)), unsafe_allow_html=True)
    with c2: st.markdown(card_html("Comissão Vinicius","Valor",fmt_moeda(com_vin),"Outras despesas",fmt_moeda(outras_desp)), unsafe_allow_html=True)
    with c3: st.markdown(card_html("Lucro após comissão","Cálculo","JP+(VIN-Comissão)","Valor",fmt_moeda(lucro_pos_com)), unsafe_allow_html=True)
    with c4: st.markdown(card_html("Lucro líquido","Cálculo","Lucro pós - Outras","Valor",fmt_moeda(lucro_liquido)), unsafe_allow_html=True)

st.divider()

# TABELA DETALHADA + DOWNLOAD
st.subheader("📄 Detalhe das linhas (período)")
if not dfp.empty:
    cols_show = [c for c in [COL_DATA,COL_CLIENTE,COL_SERVICO,COL_VALOR,"Valor_para_comissao","Pct_Comissao","Comissao_R$",COL_TIPO,COL_STATUSF,COL_DT_PAG,COL_REFID] if c in dfp.columns]
    dfd = dfp[cols_show].copy()
    if COL_DATA in dfd.columns: dfd[COL_DATA] = pd.to_datetime(dfd[COL_DATA],errors="coerce").dt.strftime("%d/%m/%Y")
    if "Valor_para_comissao" in dfd.columns: dfd["Valor_para_comissao"] = dfd["Valor_para_comissao"].apply(fmt_moeda)
    if "Comissao_R$" in dfd.columns: dfd["Comissao_R$"] = dfd["Comissao_R$"].apply(fmt_moeda)
    if "Pct_Comissao" in dfd.columns: dfd["Pct_Comissao"] = (pd.to_numeric(dfd["Pct_Comissao"], errors="coerce").fillna(0)*100).round(0).astype(int).astype(str)+"%"

    st.dataframe(dfd, hide_index=True, use_container_width=True)

    raw_export = dfp[cols_show].copy()
    if COL_DATA in raw_export.columns: raw_export[COL_DATA] = pd.to_datetime(raw_export[COL_DATA],errors="coerce").dt.strftime("%Y-%m-%d")
    if "Pct_Comissao" in raw_export.columns: raw_export["Pct_Comissao"] = pd.to_numeric(raw_export["Pct_Comissao"],errors="coerce").fillna(0).round(4)

    cexp1,cexp2 = st.columns(2)
    with cexp1:
        st.download_button("⬇️ Baixar CSV (período)", data=raw_export.to_csv(index=False).encode("utf-8"),
                           file_name=f"dashboard_{funcionario}_{dt_ini.strftime('%Y%m%d')}_{dt_fim.strftime('%Y%m%d')}.csv", mime="text/csv")
    with cexp2:
        excel_bytes = to_excel_bytes(raw_export)
        if excel_bytes:
            st.download_button("⬇️ Baixar Excel (período)", data=excel_bytes,
                               file_name=f"dashboard_{funcionario}_{dt_ini.strftime('%Y%m%d')}_{dt_fim.strftime('%Y%m%d')}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.caption("⚠️ Para exportar Excel, instale o pacote **openpyxl**.")

else:
    st.info("Sem linhas no período selecionado.")

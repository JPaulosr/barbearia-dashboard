# -*- coding: utf-8 -*-
# 12_Comissoes_Vinicius.py — Comissão do Vinícius (limpo, direto da Base, com cards mensal/anual)

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime, date
import pytz

# =============================
# CONFIG
# =============================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
TZ = "America/Sao_Paulo"
FUNCIONARIO = "Vinicius"   # <- padrão desta página
DEFAULT_PCT = 0.50         # 50% se a base não trouxer % por linha

# Nomes possíveis de colunas na base (para compatibilidade)
COL_DATA      = "Data"
COL_SERVICO   = "Serviço"
COL_VALOR     = "Valor"
COL_CLIENTE   = "Cliente"
COL_FUNC      = "Funcionário"
COL_TIPO      = "Tipo"              # "Fiado" ou não
COL_STATUSF   = "StatusFiado"       # "Pago" / "A receber" etc, se houver
COL_DT_PAG    = "DataPagamento"     # para fiado quitado, se houver
COL_PCT       = "% Comissão"        # se a base já trouxer % por linha
COL_REFID     = "RefID"             # se existir, apenas exibimos
COL_PERIODO   = "Período"           # opcional, não é usado no cálculo

# =============================
# CONEXÃO
# =============================
@st.cache_resource(show_spinner=False)
def conectar_sheets():
    """Conecta no Google Sheets via Service Account do st.secrets."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(st.secrets["GCP_SERVICE_ACCOUNT"], scopes=scopes)
    return gspread.authorize(creds)

@st.cache_data(show_spinner=False, ttl=300)
def carregar_base(gc):
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    # Higienização mínima
    df = df.dropna(how="all")
    # Normaliza colunas esperadas, quando possíveis
    if COL_DATA in df.columns:
        # aceita dd/mm/aaaa e datetime
        def _parse_data(x):
            if pd.isna(x): return None
            if isinstance(x, (datetime, date)): return pd.to_datetime(x)
            x = str(x).strip()
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
                try:
                    return pd.to_datetime(x, format=fmt, dayfirst=True)
                except Exception:
                    pass
            try:
                return pd.to_datetime(x, dayfirst=True, errors="coerce")
            except Exception:
                return None
        df[COL_DATA] = df[COL_DATA].apply(_parse_data)
    # Valor numérico
    if COL_VALOR in df.columns:
        df[COL_VALOR] = pd.to_numeric(df[COL_VALOR], errors="coerce").fillna(0.0)
    # % comissão (se houver)
    if COL_PCT in df.columns:
        # aceita "50%" ou "0.5"
        def _pct(v):
            if pd.isna(v): return None
            s = str(v).strip().replace(",", ".")
            if s.endswith("%"):
                try:
                    return float(s[:-1]) / 100.0
                except:
                    return None
            try:
                f = float(s)
                return f/100.0 if f > 1 else f
            except:
                return None
        df[COL_PCT] = df[COL_PCT].apply(_pct)
    return df

# =============================
# LÓGICA
# =============================
def filtrar_vinicius(df_raw, incluir_fiado_nao_pago=False):
    """Filtra funcionário Vinícius. Usa valor direto da Base.
       Controle de fiado: só entra fiado quitado, a não ser que o toggle peça para incluir.
    """
    if df_raw.empty:
        return df_raw.copy()

    df = df_raw.copy()

    # Filtra funcionário
    if COL_FUNC in df.columns:
        df = df[df[COL_FUNC].astype(str).str.strip().str.lower() == FUNCIONARIO.lower()]
    else:
        df = df.head(0)  # se não há coluna, retorna vazio

    if df.empty:
        return df

    # Fiado
    tipo_series = df[COL_TIPO].astype(str).str.strip().str.lower() if COL_TIPO in df.columns else pd.Series([""]*len(df), index=df.index)
    eh_fiado = tipo_series.eq("fiado")

    if not incluir_fiado_nao_pago:
        # incluir apenas fiado pago (StatusFiado == "Pago" ou DataPagamento preenchida)
        pago_mask = pd.Series([False]*len(df), index=df.index)
        if COL_STATUSF in df.columns:
            pago_mask |= df[COL_STATUSF].astype(str).str.strip().str.lower().isin(["pago", "paga", "quitado", "quitada", "liberado", "liberada"])
        if COL_DT_PAG in df.columns:
            pago_mask |= df[COL_DT_PAG].notna() & (df[COL_DT_PAG].astype(str).str.strip() != "")
        # mantém: não-fiado OR (fiado & pago)
        df = df[(~eh_fiado) | (eh_fiado & pago_mask)]

    # Valor para comissão: DIRETO da base
    df["Valor_para_comissao"] = df[COL_VALOR].astype(float)

    # % da comissão por linha
    if COL_PCT in df.columns and df[COL_PCT].notna().any():
        pct = df[COL_PCT].fillna(DEFAULT_PCT)
    else:
        pct = DEFAULT_PCT
    df["Pct_Comissao"] = pct

    # Comissão da linha
    df["Comissao_R$"] = (df["Valor_para_comissao"] * df["Pct_Comissao"]).round(2)

    # Campos auxiliares
    tz = pytz.timezone(TZ)
    today = datetime.now(tz)
    df["Ano"] = df[COL_DATA].dt.year
    df["Mes"] = df[COL_DATA].dt.month

    return df

def resumo_cards(df, ano_alvo=None, mes_alvo=None, titulo="Resumo"):
    """Gera métricas básicas para cards."""
    if df.empty:
        return dict(
            atendimentos=0, clientes=0, base=0.0, comissao=0.0,
            titulo=titulo
        )
    dfx = df.copy()
    if ano_alvo:
        dfx = dfx[dfx["Ano"] == ano_alvo]
    if mes_alvo:
        dfx = dfx[(dfx["Mes"] == mes_alvo) & (dfx["Ano"] == ano_alvo if ano_alvo else True)]
    if dfx.empty:
        return dict(atendimentos=0, clientes=0, base=0.0, comissao=0.0, titulo=titulo)

    atend = len(dfx)
    clientes = dfx[COL_CLIENTE].astype(str).str.strip().nunique() if COL_CLIENTE in dfx.columns else atend
    base = dfx["Valor_para_comissao"].sum()
    com = dfx["Comissao_R$"].sum()
    return dict(
        atendimentos=int(atend),
        clientes=int(clientes),
        base=float(round(base, 2)),
        comissao=float(round(com, 2)),
        titulo=titulo
    )

def card_html(titulo, valor1_label, valor1, valor2_label, valor2):
    """Card simples em HTML (dark)."""
    return f"""
    <div style="
        background: #121212;
        border: 1px solid #2a2a2a;
        border-radius: 16px;
        padding: 18px 18px;
        color: #eaeaea;
        box-shadow: 0 2px 10px rgba(0,0,0,0.25);
    ">
      <div style="font-size: 14px; opacity: 0.85; margin-bottom: 6px;">{titulo}</div>
      <div style="display:flex; justify-content: space-between; gap:16px;">
        <div>
          <div style="font-size:12px; opacity:.7;">{valor1_label}</div>
          <div style="font-size:24px; font-weight:700;">{valor1}</div>
        </div>
        <div>
          <div style="font-size:12px; opacity:.7; text-align:right;">{valor2_label}</div>
          <div style="font-size:24px; font-weight:700; text-align:right;">{valor2}</div>
        </div>
      </div>
    </div>
    """

def fmt_moeda(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# =============================
# UI
# =============================
st.set_page_config(page_title="Comissão do Vinícius", layout="wide")
st.title("💈 Comissão do Vinícius — direto da Base")

gc = conectar_sheets()
df_raw = carregar_base(gc)

# Opções de filtro
col_f1, col_f2, col_f3, col_f4 = st.columns([1,1,1,2])
with col_f1:
    incluir_fiado = st.toggle("Incluir FIADO não pago", value=False, help="Quando desligado, só entram fiados quitados.")
with col_f2:
    hoje = datetime.now(pytz.timezone(TZ))
    ano_sel = st.number_input("Ano", min_value=2023, max_value=hoje.year, value=hoje.year, step=1)
with col_f3:
    mes_sel = st.number_input("Mês", min_value=1, max_value=12, value=hoje.month, step=1)
with col_f4:
    st.caption("Obs.: O cálculo usa **Valor** da Base de Dados. % por linha é respeitado se existir; caso contrário, usa 50%.")

df = filtrar_vinicius(df_raw, incluir_fiado_nao_pago=incluir_fiado)

# ===== CARDS (MÊS ATUAL SELECIONADO) =====
res_mes = resumo_cards(df, ano_alvo=int(ano_sel), mes_alvo=int(mes_sel), titulo=f"Mês {mes_sel:02d}/{ano_sel}")
res_ano = resumo_cards(df, ano_alvo=int(ano_sel), titulo=f"Ano {ano_sel}")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(card_html(
        res_mes["titulo"],
        "Atendimentos",
        f'{res_mes["atendimentos"]}',
        "Clientes únicos",
        f'{res_mes["clientes"]}',
    ), unsafe_allow_html=True)
with c2:
    st.markdown(card_html(
        "Base p/ comissão (Mês)",
        "Base",
        fmt_moeda(res_mes["base"]),
        "Comissão",
        fmt_moeda(res_mes["comissao"]),
    ), unsafe_allow_html=True)
with c3:
    st.markdown(card_html(
        res_ano["titulo"],
        "Atendimentos",
        f'{res_ano["atendimentos"]}',
        "Clientes únicos",
        f'{res_ano["clientes"]}',
    ), unsafe_allow_html=True)
with c4:
    st.markdown(card_html(
        "Base p/ comissão (Ano)",
        "Base",
        fmt_moeda(res_ano["base"]),
        "Comissão",
        fmt_moeda(res_ano["comissao"]),
    ), unsafe_allow_html=True)

st.divider()

# ===== QUEBRA POR SERVIÇO (MÊS SELECIONADO) =====
st.subheader("📊 Quebra por serviço — Mês selecionado")
df_mes = df[(df["Ano"] == int(ano_sel)) & (df["Mes"] == int(mes_sel))].copy()
if not df_mes.empty:
    grp = (
        df_mes
        .groupby(COL_SERVICO, dropna=False)
        .agg(
            Qtde=("Valor_para_comissao", "count"),
            Base=("Valor_para_comissao", "sum"),
            Comissao=("Comissao_R$", "sum")
        )
        .reset_index()
        .sort_values(["Base", "Qtde"], ascending=[False, False])
    )
    grp["Base"] = grp["Base"].round(2)
    grp["Comissao"] = grp["Comissao"].round(2)
    # Formatação
    grp_fmt = grp.copy()
    grp_fmt["Base"] = grp_fmt["Base"].apply(fmt_moeda)
    grp_fmt["Comissao"] = grp_fmt["Comissao"].apply(fmt_moeda)
    st.dataframe(grp_fmt, hide_index=True, use_container_width=True)
else:
    st.info("Sem registros para o mês selecionado.")

# ===== TABELA DETALHADA (OPCIONAL) =====
with st.expander("Ver detalhes das linhas (opcional)"):
    cols_show = []
    for c in [COL_DATA, COL_CLIENTE, COL_SERVICO, COL_VALOR, "Valor_para_comissao", "Pct_Comissao", "Comissao_R$", COL_TIPO, COL_STATUSF, COL_DT_PAG, COL_REFID]:
        if c in df.columns:
            cols_show.append(c)
    dfd = df[(df["Ano"] == int(ano_sel)) & (df["Mes"] == int(mes_sel))][cols_show].copy() if cols_show else pd.DataFrame()
    if not dfd.empty:
        # Formatações
        if COL_DATA in dfd.columns:
            dfd[COL_DATA] = dfd[COL_DATA].dt.strftime("%d/%m/%Y")
        for colnum in ["Valor_para_comissao", "Comissao_R$"]:
            if colnum in dfd.columns:
                dfd[colnum] = dfd[colnum].apply(fmt_moeda)
        if "Pct_Comissao" in dfd.columns:
            dfd["Pct_Comissao"] = (dfd["Pct_Comissao"].astype(float) * 100).round(0).astype(int).astype(str) + "%"
        st.dataframe(dfd, hide_index=True, use_container_width=True)
    else:
        st.caption("Sem linhas detalhadas para o período.")

# ===== RODAPÉ =====
st.markdown("""
<small>
• A comissão é calculada **diretamente sobre o Valor da Base de Dados**.<br>
• Fiados **não pagos** são excluídos por padrão. Use o toggle no topo se quiser incluí-los.<br>
• Se a Base tiver a coluna <b>% Comissão</b>, ela é respeitada por linha; senão, aplica-se <b>50%</b>.
</small>
""", unsafe_allow_html=True)

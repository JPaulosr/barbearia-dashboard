# -*- coding: utf-8 -*-
# 15_Atendimentos_Masculino_Por_Dia.py
# Página: escolher um dia e ver TODOS os atendimentos (masculino),
# com contagem de clientes atendidos, KPIs e exportação.

import streamlit as st
import pandas as pd
import gspread
import io
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
    gc = gspread.authorize(creds)
    return gc

@st.cache_data(ttl=300, show_spinner=False)
def carregar_base():
    """Lê a 'Base de Dados' (masculino) direto do Google Sheets.
    OBS: não recebe mais 'gc' para evitar UnhashableParamError no cache."""
    gc = _conectar_sheets()
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(ABA_DADOS)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0)
    # Remover colunas/linhas totalmente vazias
    df = df.dropna(how="all")
    if df.empty:
        return df

    # Normalizar nomes de colunas (tira espaços)
    df.columns = [str(c).strip() for c in df.columns]

    # Garantir colunas principais (se não existirem, cria vazias)
    for col in ["Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
                "Funcionário", "Fase", "Hora Chegada", "Hora Início",
                "Hora Saída", "Hora Saída do Salão", "Tipo"]:
        if col not in df.columns:
            df[col] = None

    # Normalizar Data -> datetime.date
    def parse_data(x):
        if pd.isna(x):
            return None
        if isinstance(x, (datetime, pd.Timestamp)):
            return x.date()
        s = str(x).strip()
        for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"]:
            try:
                return datetime.strptime(s, fmt).date()
            except Exception:
                pass
        return None

    df["Data_norm"] = df["Data"].apply(parse_data)

    # Normalizar Valor -> float
    def parse_valor(v):
        if pd.isna(v):
            return 0.0
        s = str(v).strip().replace("R$", "").replace(" ", "")
        # tratar "1.234,56" e "1234,56"
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        try:
            return float(s)
        except Exception:
            return 0.0

    df["Valor_num"] = df["Valor"].apply(parse_valor)

    # String limpa para campos textuais principais
    for col in ["Cliente", "Serviço", "Funcionário", "Conta", "Combo", "Tipo", "Fase"]:
        df[col] = df[col].astype(str).fillna("").str.strip()

    return df

def filtrar_por_dia(df: pd.DataFrame, dia: date) -> pd.DataFrame:
    if df.empty or dia is None:
        return df.iloc[0:0]
    mask = (df["Data_norm"] == dia)
    return df.loc[mask].copy()

def kpis_do_dia(df_dia: pd.DataFrame):
    servicos = len(df_dia)  # linhas
    clientes = df_dia["Cliente"].nunique() if not df_dia.empty else 0
    receita = float(df_dia["Valor_num"].sum()) if not df_dia.empty else 0.0
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

    # Ordenar por hora de início quando existir, senão por Cliente
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
    """Gera um único .xlsx com duas abas: Linhas e ResumoClientes."""
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
st.caption("Selecione um dia para ver todos os atendimentos do salão masculino, contagem de clientes e totais do dia.")

with st.spinner("Carregando base masculina..."):
    df_base = carregar_base()

col_a, col_b = st.columns([1, 2])
with col_a:
    hoje = _tz_now().date()
    dia_selecionado = st.date_input("Dia", value=hoje, format="DD/MM/YYYY")
with col_b:
    st.write("")

df_dia = filtrar_por_dia(df_base, dia_selecionado)

if df_dia.empty:
    st.info("Nenhum atendimento encontrado para o dia selecionado.")
    st.stop()

# KPIs
clientes, servicos, receita, ticket = kpis_do_dia(df_dia)

k1, k2, k3, k4 = st.columns(4)
k1.metric("👥 Clientes atendidos", f"{clientes}")
k2.metric("✂️ Serviços realizados", f"{servicos}")
k3.metric("💰 Receita do dia", format_moeda(receita))
k4.metric("🧾 Ticket médio", format_moeda(ticket))

st.markdown("---")

# Tabela de linhas
df_exibe = preparar_tabela_exibicao(df_dia)
st.subheader("Registros do dia (linhas)")
st.dataframe(df_exibe, use_container_width=True, hide_index=True)

# Resumo por Cliente (1 atendimento por cliente no dia)
st.subheader("Resumo por Cliente")
grp = (
    df_dia
    .groupby("Cliente", as_index=False)
    .agg(
        Quantidade_Serviços=("Serviço", "count"),
        Valor_Total=("Valor_num", "sum")
    )
    .sort_values(["Valor_Total", "Quantidade_Serviços"], ascending=[False, False])
)
grp["Valor_Total"] = grp["Valor_Total"].apply(format_moeda)
st.dataframe(
    grp.rename(columns={"Quantidade_Serviços": "Qtd. Serviços", "Valor_Total": "Valor Total"}),
    use_container_width=True, hide_index=True
)

# Exportar
st.markdown("### Exportar")
df_lin_export = df_exibe.copy()
df_cli_export = grp.rename(columns={"Quantidade_Serviços": "Qtd. Serviços", "Valor_Total": "Valor Total"}).copy()

# CSV Linhas
csv_lin = df_lin_export.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ Baixar Linhas (CSV)",
    data=csv_lin,
    file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}_linhas.csv",
    mime="text/csv"
)

# CSV Resumo por Cliente
csv_cli = df_cli_export.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "⬇️ Baixar Resumo por Cliente (CSV)",
    data=csv_cli,
    file_name=f"Atendimentos_{dia_selecionado.strftime('%d-%m-%Y')}_resumo_clientes.csv",
    mime="text/csv"
)

# Excel com 2 abas
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

st.caption("• Contagem de clientes considera 1 atendimento por cliente no dia (as linhas de combo não duplicam o cliente). Receita é a soma dos valores do dia.")

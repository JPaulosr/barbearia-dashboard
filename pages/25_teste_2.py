# 15_Editar_Periodo.py — Edição em lote do "Período" por data e clientes
# - Filtra por DIA (date_input)
# - Seleciona múltiplos clientes daquele dia (multiselect + "Selecionar todos")
# - Aplica o "Período" (Manhã/Tarde/Noite/Outro) em lote
# - Atualiza SOMENTE as linhas afetadas na planilha (batch), sem sobrescrever o resto
# - Mostra prévia antes de aplicar
# --------------------------------------------------------------

import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import date

st.set_page_config(page_title="Editar Período (Lote)", page_icon="🕒", layout="wide")
st.title("🕒 Editar Período por Data (Lote)")

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"  # sua planilha principal
# Nomes possíveis da aba base (ajusta aqui se precisar)
BASE_ALVOS = [
    "Base de Dados", "base de dados", "BASE DE DADOS",
    "Base de Dados Masculino", "Base de Dados - Masculino"
]
# Nome exato da coluna de período (ajuste se sua planilha usar outro título)
PERIODO_COL = "Período"   # ou "Periodo" se não tiver acento
# Nome exato da coluna de data e cliente (ajuste se estiver diferente)
DATA_COL = "Data"
CLIENTE_COL = "Cliente"

# =========================
# CONEXÃO GOOGLE SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    # aceita tanto "gcp_service_account" quanto "GCP_SERVICE_ACCOUNT"
    info = st.secrets.get("gcp_service_account") or st.secrets.get("GCP_SERVICE_ACCOUNT")
    if not info:
        st.error("❌ Secrets ausentes. Adicione 'gcp_service_account' nas Secrets do Streamlit.")
        st.stop()
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc

def abrir_aba_base(gc):
    sh = gc.open_by_key(SHEET_ID)
    # tenta encontrar a aba de base por nomes candidatos
    for nome in BASE_ALVOS:
        try:
            ws = sh.worksheet(nome)
            return ws
        except Exception:
            continue
    # se não achou, lista abas disponíveis para debug
    nomes = [w.title for w in sh.worksheets()]
    st.error(f"❌ Aba da Base não encontrada. Ajuste BASE_ALVOS. Abas disponíveis: {nomes}")
    st.stop()

@st.cache_data(ttl=120)
def carregar_base():
    gc = conectar_sheets()
    ws = abrir_aba_base(gc)
    df = get_as_dataframe(ws, evaluate_formulas=True, dtype=str)  # lê como string (mais seguro para normalizar)
    # Remove colunas totalmente vazias e linhas em branco
    df = df.dropna(how="all").reset_index(drop=True)
    df = df.loc[:, ~df.columns.isnull()]
    # Normaliza nomes de colunas (trim)
    df.columns = [str(c).strip() for c in df.columns]
    # Garante colunas necessárias
    faltando = [c for c in [DATA_COL, CLIENTE_COL] if c not in df.columns]
    if faltando:
        st.error(f"❌ Colunas ausentes na base: {faltando}. Ajuste DATA_COL/CLIENTE_COL.")
        st.stop()
    # Cria coluna de Período se não existir
    if PERIODO_COL not in df.columns:
        df[PERIODO_COL] = ""
    # Converte Data
    def to_date(x):
        if pd.isna(x) or str(x).strip() == "":
            return pd.NaT
        # tenta vários formatos comuns
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return pd.to_datetime(x, format=fmt, dayfirst=True)
            except Exception:
                pass
        # fallback genérico
        try:
            return pd.to_datetime(x, dayfirst=True, errors="coerce")
        except Exception:
            return pd.NaT

    df["_DataDT"] = df[DATA_COL].apply(to_date)
    # guarda índice da planilha (linha real) para atualizações (gspread é 1-based + cabeçalho na linha 1)
    df["_row_number"] = df.index + 2  # +2: 1 p/ cabeçalho, 1 p/ 1ª linha de dados
    return df

def get_ws_and_sheet():
    gc = conectar_sheets()
    ws = abrir_aba_base(gc)
    return ws, ws.spreadsheet

# =========================
# UI — FILTROS
# =========================
df = carregar_base()

col_a, col_b = st.columns([1, 2], vertical_alignment="center")

with col_a:
    dia = st.date_input("📅 Selecione o DIA", value=date.today(), format="DD/MM/YYYY")
with col_b:
    st.caption("Dica: primeiro escolha a data, depois selecione os clientes e o período para aplicar em lote.")

# Filtra apenas o dia escolhido (compara por .date())
df_dia = df[df["_DataDT"].dt.date == pd.to_datetime(dia).date()].copy()

st.subheader("Registros encontrados no dia selecionado")
if df_dia.empty:
    st.info("Nenhum registro nesse dia. Escolha outro dia.")
    st.stop()

# Lista de clientes do dia
clientes_dia = sorted([c for c in df_dia[CLIENTE_COL].dropna().astype(str).str.strip().unique() if c != ""])

# Caixa Selecionar Todos
col1, col2 = st.columns([3, 1])
with col1:
    selecionados = st.multiselect("👥 Selecione clientes para aplicar o PERÍODO (múltiplos):",
                                  options=clientes_dia,
                                  default=[])
with col2:
    if st.button("Selecionar todos", use_container_width=True):
        selecionados = clientes_dia

# Escolha do Período
colp1, colp2 = st.columns([2, 2])
with colp1:
    periodo_opcao = st.radio(
        "Período a aplicar",
        options=["Manhã", "Tarde", "Noite", "Integral", "Outro"],
        horizontal=True
    )
with colp2:
    periodo_outro = st.text_input("Se 'Outro', especifique:", value="", placeholder="ex.: Almoço, Pós-Serviço...")
    periodo_final = periodo_outro.strip() if periodo_opcao == "Outro" else periodo_opcao

# Prévia
st.markdown("### 🔎 Pré-visualização da alteração")
if len(selecionados) == 0:
    st.warning("Selecione ao menos **1 cliente** para aplicar.")
else:
    prev = df_dia[df_dia[CLIENTE_COL].isin(selecionados)][[DATA_COL, CLIENTE_COL, PERIODO_COL]].copy()
    prev["Novo Período"] = periodo_final
    st.dataframe(prev, use_container_width=True, hide_index=True)

# Botão de aplicar
aplicar = st.button("✅ Aplicar PERÍODO aos clientes selecionados", type="primary")

# =========================
# APLICAÇÃO (UPDATE EM LOTE)
# =========================
def aplicar_periodo_em_lote(df_base, df_filtrado, clientes_sel, novo_periodo):
    """
    Marca o PERÍODO para todas as linhas do df_base cujo:
      - Data == dia escolhido
      - Cliente ∈ clientes_sel
    Atualiza apenas as células da coluna PERÍODO via batch.
    """
    if not clientes_sel:
        st.warning("Nenhum cliente selecionado.")
        return 0

    # Linhas que serão alteradas (globais no df_base)
    alvo = df_filtrado[df_filtrado[CLIENTE_COL].isin(clientes_sel)]
    if alvo.empty:
        return 0

    # Pega as linhas reais da planilha (números)
    linhas_planilha = alvo["_row_number"].tolist()

    # Conecta e monta batch de células na coluna PERÍODO
    ws, _ = get_ws_and_sheet()

    # Descobre o índice (número da coluna) do PERÍODO (1-based)
    header = ws.row_values(1)
    try:
        col_idx = header.index(PERIODO_COL) + 1
    except ValueError:
        # se a coluna não existir no header (criada localmente), criamos no fim
        ws.update_cell(1, len(header) + 1, PERIODO_COL)
        col_idx = len(header) + 1

    # Monta lista de atualizações como ranges de uma coluna
    # Para perfomar melhor, agrupamos linhas em um único batch_update com várias ranges
    data = []
    for r in linhas_planilha:
        rng = gspread.utils.rowcol_to_a1(r, col_idx)
        data.append({
            "range": rng,
            "values": [[novo_periodo]]
        })

    # Executa batch_update em pedaços (Google tem limites; aqui um chunk simples de 500)
    total = 0
    chunk = 500
    for i in range(0, len(data), chunk):
        ws.batch_update(data[i:i+chunk], value_input_option="USER_ENTERED")
        total += len(data[i:i+chunk])

    return total

if aplicar:
    if len(selecionados) == 0:
        st.error("Selecione clientes antes de aplicar.")
        st.stop()
    if periodo_final == "":
        st.error("Informe um valor para o Período.")
        st.stop()

    alteradas = aplicar_periodo_em_lote(df, df_dia, selecionados, periodo_final)
    if alteradas > 0:
        st.success(f"✅ {alteradas} linha(s) atualizada(s) com Período = **{periodo_final}**.")
        st.cache_data.clear()  # limpa cache para recarregar
        with st.expander("Ver registros atualizados (refrescar)"):
            st.write("Clique no botão abaixo para recarregar a base e conferir.")
            if st.button("🔄 Recarregar base"):
                st.experimental_rerun()
    else:
        st.info("Nenhuma linha foi alterada (verifique clientes e data).")

# =========================
# AÇÃO RÁPIDA (opcional): marcar TODOS do dia
# =========================
st.divider()
st.subheader("⚡ Ação rápida (opcional)")
colq1, colq2, colq3 = st.columns([2,2,2])
with colq1:
    periodo_rapido = st.selectbox("Marcar TODOS os clientes deste dia como:", 
                                  ["", "Manhã", "Tarde", "Noite", "Integral", "Outro"])
with colq2:
    periodo_rapido_outro = st.text_input("Se 'Outro', especifique (ação rápida):", value="")
with colq3:
    if st.button("Aplicar para TODOS do dia", use_container_width=True):
        if periodo_rapido == "":
            st.error("Escolha um período para a ação rápida.")
        else:
            valor = periodo_rapido_outro.strip() if periodo_rapido == "Outro" else periodo_rapido
            if valor == "":
                st.error("Informe o texto do período (Outro).")
            else:
                # usa os clientes do dia inteiro
                alteradas = aplicar_periodo_em_lote(df, df_dia, clientes_dia, valor)
                if alteradas > 0:
                    st.success(f"✅ {alteradas} linha(s) do dia marcadas como **{valor}**.")
                    st.cache_data.clear()
                else:
                    st.info("Nenhuma linha alterada.")

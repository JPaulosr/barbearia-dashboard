# -*- coding: utf-8 -*-
# 11_Adicionar_Atendimento.py
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from gspread.utils import rowcol_to_a1
from datetime import datetime
import pytz
import unicodedata
import requests

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_DADOS = "Base de Dados"
STATUS_ABA = "clientes_status"
TZ = "America/Sao_Paulo"
DATA_FMT = "%d/%m/%Y"

COLS_OFICIAIS = [
    "Data", "Serviço", "Valor", "Conta", "Cliente", "Combo",
    "Funcionário", "Fase", "Tipo", "Período"
]
COLS_CAIXINHAS = ["CaixinhaDia"]  # só mantemos o do dia

# =========================
# UTILS
# =========================
def _cap_first(s: str) -> str:
    return (str(s).strip().lower().capitalize()) if s is not None else ""

def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def _fmt_brl(v: float) -> str:
    try:
        v = float(v)
    except Exception:
        v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# =========================
# SHEETS
# =========================
@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def carregar_base():
    aba = conectar_sheets().worksheet(ABA_DADOS)
    df = get_as_dataframe(aba).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    for c in [*COLS_OFICIAIS, *COLS_CAIXINHAS]:
        if c not in df.columns:
            df[c] = ""
    return df, aba

def salvar_base(df_final: pd.DataFrame):
    aba = conectar_sheets().worksheet(ABA_DADOS)
    headers_existentes = aba.row_values(1)
    colunas_alvo = list(dict.fromkeys([*headers_existentes, *COLS_OFICIAIS, *COLS_CAIXINHAS]))
    for c in colunas_alvo:
        if c not in df_final.columns:
            df_final[c] = ""
    df_final = df_final[colunas_alvo]
    aba.clear()
    set_with_dataframe(aba, df_final, include_index=False, include_column_header=True)

# =========================
# UI
# =========================
st.set_page_config(layout="wide")
st.title("📅 Adicionar Atendimento")

df_existente, _ = carregar_base()
clientes_existentes = sorted(df_existente["Cliente"].dropna().unique())
servicos_existentes = sorted(df_existente["Serviço"].dropna().unique())
servicos_ui = list(dict.fromkeys(["Corte", *servicos_existentes]))

data = st.date_input("Data", value=datetime.today()).strftime("%d/%m/%Y")

c1, c2 = st.columns([2,1])
with c1:
    cliente = st.selectbox("Cliente", clientes_existentes)
    novo = st.text_input("Ou digite um novo cliente")
    cliente = novo if novo else cliente
with c2:
    servico = st.selectbox("Serviço", servicos_ui, index=servicos_ui.index("Corte"))
    valor = st.number_input("Valor", value=0.0, step=1.0)

# 💝 Caixinha do dia
with st.expander("💝 Caixinha (opcional)", expanded=False):
    caixinha_dia = st.number_input("Caixinha do dia (repasse semanal)", value=0.0, step=1.0, format="%.2f")

if st.button("💾 Salvar Atendimento"):
    df_all, _ = carregar_base()
    nova = {
        "Data": data, "Serviço": servico, "Valor": valor,
        "Conta": "Carteira", "Cliente": cliente, "Combo": "",
        "Funcionário": "JPaulo", "Fase": "Dono + funcionário",
        "Tipo": "Serviço", "Período": "Manhã",
        "CaixinhaDia": float(caixinha_dia or 0.0)
    }
    df_final = pd.concat([df_all, pd.DataFrame([nova])], ignore_index=True)
    salvar_base(df_final)
    st.success(f"✅ Atendimento de {cliente} registrado em {data}.")

# -*- coding: utf-8 -*-
# 11b_FundoCaixinhaAnual.py
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from datetime import date

# =========================
# CONFIG
# =========================
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_FUNDO = "FundoCaixinhaAnual"

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credenciais = Credentials.from_service_account_info(info, scopes=escopo)
    cliente = gspread.authorize(credenciais)
    return cliente.open_by_key(SHEET_ID)

def garantir_fundo_sheet():
    sh = conectar_sheets()
    if ABA_FUNDO not in [w.title for w in sh.worksheets()]:
        ws = sh.add_worksheet(title=ABA_FUNDO, rows=100, cols=10)
        ws.append_row(["Ano","DataContagem","ValorTotalContado","RegraDivisao","Parcela_JPaulo","Parcela_Vinicius","Distribuido"])
    return sh.worksheet(ABA_FUNDO)

# =========================
# UI
# =========================
st.set_page_config(layout="wide")
st.title("🎁 Fundo da Caixinha Anual")

ano = st.number_input("Ano", min_value=2023, max_value=2100, value=date.today().year, step=1)
data_contagem = st.date_input("Data da contagem", value=date.today())
valor = st.number_input("Valor total contado na urna (R$)", min_value=0.0, step=1.0, format="%.2f")

if st.button("💾 Registrar contagem"):
    ws = garantir_fundo_sheet()
    metade = round(valor/2, 2)
    ws.append_row([ano, data_contagem.strftime("%d/%m/%Y"), valor, "50/50", metade, metade, "FALSE"])
    st.success(f"✅ Fundo anual {ano} registrado: R$ {valor:.2f} (JPaulo {metade}, Vinicius {metade})")

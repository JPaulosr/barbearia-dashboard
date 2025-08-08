import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Criar coluna Período no Google Sheets", page_icon="🕒", layout="wide")
st.title("🕒 Criar/atualizar a coluna 'Período' usando apenas 'Hora Início'")

# === CONFIG ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"   # sua planilha
ABA = "Base de Dados"                                      # aba de trabalho

@st.cache_resource
def conectar_sheets():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    return client

@st.cache_data
def carregar_df():
    client = conectar_sheets()
    ws = client.open_by_key(SHEET_ID).worksheet(ABA)
    df = get_as_dataframe(ws, evaluate_formulas=True, header=0, dtype=str)
    df = df.loc[:, ~df.columns.str.match(r"^Unnamed")]

    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], errors="coerce").dt.date
    if "Hora Início" in df.columns:
        df["Hora Início"] = pd.to_datetime(df["Hora Início"], errors="coerce")
    return df

df = carregar_df()
st.markdown(f"<small><i>Registros carregados: {len(df)}</i></small>", unsafe_allow_html=True)

# === Criar coluna Período baseado SOMENTE na Hora Início ===
def definir_periodo(horario):
    if pd.isna(horario):
        return "Indefinido"
    h = int(horario.hour)
    if 6 <= h < 12:
        return "Manhã"
    elif 12 <= h < 18:
        return "Tarde"
    else:
        return "Noite"

df["Período"] = df["Hora Início"].apply(definir_periodo)

st.subheader("Prévia (com a coluna 'Período')")
cols_preview = [c for c in ["Data", "Cliente", "Funcionário", "Hora Início", "Período"] if c in df.columns]
st.dataframe(df[cols_preview].head(30), use_container_width=True)

# === Escrever/Atualizar coluna 'Período' no Google Sheets ===
def escrever_coluna_periodo(df_periodo):
    client = conectar_sheets()
    ws = client.open_by_key(SHEET_ID).worksheet(ABA)

    header = ws.row_values(1)
    if not header:
        raise RuntimeError("Não encontrei cabeçalho (linha 1 vazia).")

    try:
        col_idx = header.index("Período") + 1  # já existe
    except ValueError:
        col_idx = len(header) + 1
        ws.update_cell(1, col_idx, "Período")

    valores = [[v] for v in df_periodo["Período"].fillna("").astype(str).tolist()]
    last_row = len(valores) + 1
    cell_range = f"{gspread.utils.rowcol_to_a1(2, col_idx)}:{gspread.utils.rowcol_to_a1(last_row, col_idx)}"
    ws.update(cell_range, valores, value_input_option="USER_ENTERED")

if st.button("✍️ Escrever/Atualizar coluna 'Período' no Google Sheets"):
    try:
        escrever_coluna_periodo(df)
        st.success("Coluna 'Período' criada/atualizada com sucesso na planilha! ✅")
    except Exception as e:
        st.error(f"Erro ao escrever na planilha: {e}")

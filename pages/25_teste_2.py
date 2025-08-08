import re
from datetime import datetime
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

st.set_page_config(page_title="Criar coluna Período", layout="wide")
st.title("🕒 Criar/Atualizar coluna 'Período' (com base em 'Hora Início')")

# ===== Helpers =====
def get_sheet_id_from_url(url: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
    if not m:
        raise ValueError("PLANILHA_URL inválida.")
    return m.group(1)

def classificar_periodo(t):
    # Manhã = 05:00–11:59 | Tarde = 12:00–17:59 | Noite = 18:00–04:59
    if t is None:
        return ""
    total = t.hour*3600 + t.minute*60 + t.second
    if 5*3600 <= total <= 11*3600 + 59*60 + 59:
        return "Manhã"
    if 12*3600 <= total <= 17*3600 + 59*60 + 59:
        return "Tarde"
    return "Noite"

def parse_time(cell):
    if cell is None or cell == "":
        return None
    if isinstance(cell, list) and cell:
        cell = cell[0]
    # Fração de dia do Sheets
    if isinstance(cell, (int, float)) and not isinstance(cell, bool):
        secs = int(round(float(cell) * 86400)) % 86400
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        return datetime(1900,1,1,h,m,s).time()
    # String
    txt = str(cell).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(txt, fmt).time()
        except ValueError:
            pass
    return None

@st.cache_resource
def conectar():
    info = st.secrets["GCP_SERVICE_ACCOUNT"]
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    sheet_id = get_sheet_id_from_url(st.secrets["PLANILHA_URL"])
    return gc.open_by_key(sheet_id)

def run():
    sh = conectar()
    ws = sh.worksheet("Base de Dados")

    headers = ws.row_values(1)
    def col_idx(nome):
        return headers.index(nome) + 1 if nome in headers else None

    col_inicio = col_idx("Hora Início")
    if not col_inicio:
        st.error("Não encontrei a coluna **Hora Início**.")
        return

    col_periodo = col_idx("Período")
    if not col_periodo:
        col_periodo = len(headers) + 1
        ws.update_cell(1, col_periodo, "Período")

    # lê toda a coluna de Hora Início a partir da linha 2
    nrows = ws.row_count
    if nrows <= 1:
        st.info("Nada para processar.")
        return

    rng_inicio = f"{rowcol_to_a1(2, col_inicio)}:{rowcol_to_a1(nrows, col_inicio)}"
    horarios = ws.get(rng_inicio)

    periodos = []
    for row in horarios:
        cell = row[0] if (isinstance(row, list) and row) else ""
        t = parse_time(cell)
        periodos.append([classificar_periodo(t)])

    rng_saida = f"{rowcol_to_a1(2, col_periodo)}:{rowcol_to_a1(1+len(periodos), col_periodo)}"
    ws.update(rng_saida, periodos, value_input_option="USER_ENTERED")
    st.success(f"✅ 'Período' atualizado para {len(periodos)} linhas.")

if st.button("Criar/Atualizar coluna 'Período'"):
    run()

st.caption("Manhã = 05:00–11:59 • Tarde = 12:00–17:59 • Noite = 18:00–04:59")

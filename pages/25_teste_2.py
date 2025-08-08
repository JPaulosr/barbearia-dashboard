# pip install gspread google-auth pandas

import math
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials
from gspread.utils import rowcol_to_a1

# === CONFIGURAÇÕES ===
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"   # ID da sua planilha
WORKSHEET_NAME = "Base de Dados"                            # aba
SERVICE_ACCOUNT_FILE = "service_account.json"               # caminho do JSON (compartilhe a planilha com o e-mail do service account)

# === AUTENTICAÇÃO ===
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
gc = gspread.authorize(creds)

ws = gc.open_by_key(SHEET_ID).worksheet(WORKSHEET_NAME)

# === LOCALIZA COLUNAS ===
headers = ws.row_values(1)
def col_index(nome):
    try:
        return headers.index(nome) + 1  # 1-based
    except ValueError:
        return None

col_hora_inicio = col_index("Hora Início")
if not col_hora_inicio:
    raise RuntimeError("Não encontrei a coluna 'Hora Início' na aba Base de Dados.")

# cria a coluna 'Período' no final, se ainda não existir
col_periodo = col_index("Período")
if not col_periodo:
    col_periodo = len(headers) + 1
    ws.update_cell(1, col_periodo, "Período")

# === LÊ TODOS OS HORÁRIOS DE INÍCIO ===
num_rows = ws.row_count
if num_rows <= 1:
    print("Nada para processar.")
    raise SystemExit

range_inicio = f"{rowcol_to_a1(2, col_hora_inicio)}:{rowcol_to_a1(num_rows, col_hora_inicio)}"
horarios = ws.get(range_inicio)  # matriz Nx1 (ou vazia)

def parse_time(cell):
    """
    Aceita:
      - string 'HH:MM:SS'
      - número do Google Sheets (fração de dia)
      - string vazia / None => None
    """
    if cell is None or cell == "":
        return None
    value = cell
    # valor pode vir como lista [str] dependendo do get(); normalize
    if isinstance(cell, list) and cell:
        value = cell[0]

    # número (fração de dia do Sheets)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        # 1.0 dia = 24h
        segundos = int(round(float(value) * 24 * 60 * 60))
        segundos = segundos % (24 * 60 * 60)
        h = segundos // 3600
        m = (segundos % 3600) // 60
        s = segundos % 60
        return datetime(1900, 1, 1, h, m, s).time()

    # string
    txt = str(value).strip()
    if not txt:
        return None
    # tenta HH:MM:SS
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(txt, fmt).time()
        except ValueError:
            continue
    return None

def classificar_periodo(t):
    """
    Manhã  = 05:00–11:59
    Tarde  = 12:00–17:59
    Noite  = 18:00–04:59 (madrugada incluída)
    """
    if t is None:
        return ""
    total = t.hour * 3600 + t.minute * 60 + t.second
    # Faixas em segundos
    manha_ini, manha_fim = 5*3600, 11*3600 + 59*60 + 59
    tarde_ini, tarde_fim = 12*3600, 17*3600 + 59*60 + 59
    # noite é o resto
    if manha_ini <= total <= manha_fim:
        return "Manhã"
    if tarde_ini <= total <= tarde_fim:
        return "Tarde"
    return "Noite"

# === MONTA A COLUNA DE PERÍODO ===
periodos = []
for row in horarios:
    # cada 'row' pode ser ['13:45:00'] ou [] — normalize
    cell = row[0] if (isinstance(row, list) and row) else ""
    t = parse_time(cell)
    periodos.append([classificar_periodo(t)])  # matriz Nx1

# === ESCREVE NA PLANILHA (coluna "Período") ===
range_periodo = f"{rowcol_to_a1(2, col_periodo)}:{rowcol_to_a1(1 + len(periodos), col_periodo)}"
ws.update(range_periodo, periodos, value_input_option="USER_ENTERED")

print(f"✔ Coluna 'Período' atualizada em {len(periodos)} linhas (aba '{WORKSHEET_NAME}').")

# notify_inline.py
import os, sys, json, pandas as pd, requests, gspread, pytz
from datetime import datetime
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe

def fail(msg):
    print("ERRO:", msg, file=sys.stderr)
    sys.exit(1)

# 1) Envs obrigatórios
need = ["SHEET_ID", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
missing = [k for k in need if not os.getenv(k)]
if missing:
    fail(f"Variáveis ausentes: {', '.join(missing)}")

sheet_id = os.getenv("SHEET_ID")
token = os.getenv("TELEGRAM_TOKEN")
chat_id = os.getenv("TELEGRAM_CHAT_ID")

# 2) Credencial
try:
    with open("sa.json", "r", encoding="utf-8") as f:
        sa_info = json.load(f)
except Exception as e:
    fail(f"Falha lendo sa.json: {e}")

# 3) Google Sheets
try:
    scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(sheet_id)
    print(f"[OK] Conectado no Sheets. Título: {sh.title}")
    titles = [w.title for w in sh.worksheets()]
    print(f"[OK] Abas encontradas: {titles}")
except Exception as e:
    fail(f"Falha conectando no Google Sheets: {e}")

def read_tab(name):
    try:
        ws = sh.worksheet(name)
        df = get_as_dataframe(ws, evaluate_formulas=True, dtype=str).fillna("")
        print(f"[OK] Lida aba '{name}': {df.shape[0]} linhas, {df.shape[1]} colunas")
        print(df.head(5).to_string(index=False))
        return df
    except Exception as e:
        fail(f"Aba '{name}' não encontrada ou erro ao ler: {e}")

base = read_tab("Base de Dados")
try:
    _ = read_tab("clientes_status")
except SystemExit:
    raise
except Exception as e:
    print("[WARN] Não foi possível ler 'clientes_status':", e)

def parse_dt(x):
    x = (x or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(x, fmt).date()
        except Exception:
            pass
    return None

if "Cliente" not in base.columns or "Data" not in base.columns:
    fail("Colunas 'Cliente' e 'Data' não existem na 'Base de Dados'.")

df = base.copy()
df["__dt"] = df["Data"].apply(parse_dt)
df = df.dropna(subset=["__dt"])
df["__dt"] = pd.to_datetime(df["__dt"])

if df.empty:
    msg = "✅ Ninguém com 60+ dias sem vir (base vazia após parse de datas)."
else:
    ultimo = df.groupby("Cliente", as_index=False)["__dt"].max()
    ultimo["dias_sem_vir"] = (pd.Timestamp.now().normalize() - ultimo["__dt"]).dt.days
    atrasados = ultimo[ultimo["dias_sem_vir"] >= 60].sort_values("dias_sem_vir", ascending=False)
    if atrasados.empty:
        msg = "✅ Ninguém com 60+ dias sem vir."
    else:
        now_br = datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
        linhas = [f"📣 {now_br} — Clientes com 60+ dias sem vir:"]
        for _, row in atrasados.iterrows():
            linhas.append(f"• {row['Cliente']}: {int(row['dias_sem_vir'])} dias")
        msg = "\n".join(linhas)

print("[OK] Mensagem montada:")
print(msg)

# 4) Telegram
try:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": msg}, timeout=30)
    print("[DEBUG] Telegram status:", r.status_code)
    if not r.ok:
        fail(f"Falha no Telegram: HTTP {r.status_code} - {r.text}")
    print("[OK] Mensagem enviada ao Telegram.")
    sys.exit(0)
except Exception as e:
    fail(f"Erro ao enviar Telegram: {e}")

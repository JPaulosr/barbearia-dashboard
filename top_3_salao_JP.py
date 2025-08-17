# top_3_salao_JP.py
import os, sys, json, html, unicodedata, requests
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# ======================
# CONFIGURAÇÕES
# ======================
TZ = "America/Sao_Paulo"
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_STATUS = "clientes_status"

# Telegram (canal fixo)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")  # mantenha no secrets
TELEGRAM_CHAT_ID = "-1002953102982"  # ID do canal

# Service Account JSON vem do secrets
GCP_SERVICE_ACCOUNT = json.loads(os.getenv("GCP_SERVICE_ACCOUNT"))

# ======================
# HELPERS
# ======================
def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def tg_send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    r = requests.post(url, json=payload, timeout=30)
    print("↪ Telegram:", r.status_code, r.text[:160])

def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def _fmt_money(v):
    try:
        return f"R$ {float(v):,.2f}".replace(",", "v").replace(".", ",").replace("v",".")
    except:
        return f"R$ {v}"

# ======================
# CONECTAR PLANILHA
# ======================
escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(GCP_SERVICE_ACCOUNT, scopes=escopo)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)

abas = {w.title: w for w in sh.worksheets()}

# ======================
# CALCULAR RANKING
# ======================
GENERIC_NAMES_RE = r"(boliviano|brasileiro|menino|sem preferencia|funcion[aá]rio)"

def carregar_base():
    ws_base = abas[ABA_BASE]
    df = get_as_dataframe(ws_base).dropna(how="all")
    df.columns = [c.strip() for c in df.columns]
    if "Cliente" not in df.columns or "Data" not in df.columns:
        print("Base inválida")
        sys.exit(1)
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    df = df[df["Cliente"] != ""]
    df = df[~df["Cliente"].str.lower().str.contains(GENERIC_NAMES_RE, regex=True)]
    df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0)
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    return df

df = carregar_base()

# agrupa por cliente+data
day_sum = df.groupby(["Cliente","Data"], as_index=False)["Valor"].sum()
total_cliente = day_sum.groupby("Cliente")["Valor"].sum().sort_values(ascending=False)

def top3(df_sub):
    tot = df_sub.groupby("Cliente")["Valor"].sum().sort_values(ascending=False)
    out=[]
    for cli in tot.head(3).index:
        atend = df_sub[df_sub["Cliente"]==cli]["Data"].nunique()
        total = tot[cli]
        out.append((cli, atend, total))
    return out

# --- Top 3 Geral
top3_geral = top3(day_sum)
excluir = {x[0] for x in top3_geral}

# --- Top 3 JPaulo
jp = df[df["Funcionário"]=="JPaulo"]
top3_jp = top3(jp[~jp["Cliente"].isin(excluir)])

# --- Top 3 Vinicius
vi = df[df["Funcionário"]=="Vinicius"]
top3_vi = top3(vi[~vi["Cliente"].isin(excluir)])

# --- Top 3 Família
familias = []
if ABA_STATUS in abas:
    ws_status = abas[ABA_STATUS]
    df_status = get_as_dataframe(ws_status).dropna(how="all")
    df_status.columns = [c.strip() for c in df_status.columns]
    if "Cliente" in df_status.columns and "Família" in df_status.columns:
        fam_map = df_status[["Cliente","Família"]]
        df_fam = day_sum.merge(fam_map, on="Cliente", how="left")
        df_fam = df_fam[df_fam["Família"].notna() & (df_fam["Família"].str.strip()!="")]
        tot_fam = df_fam.groupby("Família")["Valor"].sum().sort_values(ascending=False).head(3)
        for fam in tot_fam.index:
            atend = df_fam[df_fam["Família"]==fam][["Cliente","Data"]].drop_duplicates().shape[0]
            familias.append((fam, atend, tot_fam[fam]))

# ======================
# ENVIAR
# ======================
def fmt_block(title, items):
    medal=["🥇","🥈","🥉"]
    if not items: return f"<b>{title}</b>\n— sem dados —"
    linhas=[]
    for i,(nome,atend,total) in enumerate(items):
        linhas.append(f"{medal[i]} <b>{html.escape(nome)}</b> — {atend} atendimentos | {_fmt_money(total)}")
    return f"<b>{title}</b>\n" + "\n".join(linhas)

msg = [
    "🏆 <b>Top 3 — Salão JP</b>",
    f"Data/hora: {html.escape(now_br())}",
    "",
    fmt_block("Geral", top3_geral),
    "",
    fmt_block("JPaulo", top3_jp),
    "",
    fmt_block("Vinicius", top3_vi),
    "",
    fmt_block("Famílias", familias),
]

tg_send("\n".join(msg))
print("✅ Top 3 enviado para o canal.")

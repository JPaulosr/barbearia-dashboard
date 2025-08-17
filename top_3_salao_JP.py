# top_3_salao_JP.py — estilo Streamlit no Telegram (sem valores)
import os, json, html, unicodedata, requests
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# ======================
# CONFIG
# ======================
TZ = "America/Sao_Paulo"
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_STATUS = "clientes_status"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")             # defina nos secrets/variáveis
TELEGRAM_CHAT_ID = "-1002953102982"                      # canal fixo solicitado
LOGO_PADRAO = "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png"

GCP_SERVICE_ACCOUNT = json.loads(os.getenv("GCP_SERVICE_ACCOUNT"))  # JSON completo

# ======================
# Helpers
# ======================
def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def tg_send(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    r = requests.post(url, json=payload, timeout=30)
    print("↪ sendMessage:", r.status_code, r.text[:160])

def tg_send_photo(photo_url: str, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url,
            "caption": caption, "parse_mode": "HTML"}
    r = requests.post(url, data=data, timeout=30)
    print("↪ sendPhoto:", r.status_code, r.text[:160])

# ======================
# Conexão Sheets
# ======================
escopo = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(GCP_SERVICE_ACCOUNT, scopes=escopo)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
abas = {w.title: w for w in sh.worksheets()}

# ======================
# Carregar dados
# ======================
GENERIC_NAMES_RE = r"(?:^|\b)(boliviano|brasileiro|menino|sem preferencia|funcion[aá]rio)(?:\b|$)"

ws_base = abas[ABA_BASE]
df = get_as_dataframe(ws_base).dropna(how="all")
df.columns = [c.strip() for c in df.columns]

# saneamento mínimo
for col in ("Cliente","Data","Funcionário"):
    if col not in df.columns:
        raise SystemExit(f"Coluna obrigatória ausente na Base: {col}")

df["Cliente"] = df["Cliente"].astype(str).str.strip()
df = df[(df["Cliente"]!="") & (~df["Cliente"].str.lower().str.contains(GENERIC_NAMES_RE, regex=True))]
df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
df = df.dropna(subset=["Data"])

# 1 atendimento por Cliente + Data
day = df.groupby(["Cliente","Data"], as_index=False).size()

# fotos
foto_map = {}
if ABA_STATUS in abas:
    ws_status = abas[ABA_STATUS]
    stt = get_as_dataframe(ws_status).dropna(how="all")
    stt.columns = [c.strip() for c in stt.columns]
    if "Cliente" in stt.columns:
        # coluna de foto tolerante a nomes
        cols_low = {c.lower(): c for c in stt.columns}
        foto_col = None
        for k in ("foto","imagem","link_foto","url_foto","foto_link","link","image"):
            if k in cols_low:
                foto_col = cols_low[k]; break
        if foto_col:
            tmp = stt[["Cliente", foto_col]].copy()
            tmp.columns = ["Cliente","Foto"]
            foto_map = { _norm(r["Cliente"]) : str(r["Foto"]).strip()
                         for _, r in tmp.iterrows() if str(r["Foto"]).strip() }

def foto_do(nome: str) -> str:
    return foto_map.get(_norm(nome), LOGO_PADRAO)

# ======================
# Rankings
# ======================
def top3_from_day(day_df: pd.DataFrame) -> list[tuple[str,int]]:
    # retorna lista [(cliente, atendimentos)]
    tot = (day_df.groupby("Cliente", as_index=False)
                  .agg({"Data":"nunique"})
                  .rename(columns={"Data":"atend"}))
    tot = tot.sort_values("atend", ascending=False).head(3)
    return [(r.Cliente, int(r.atend)) for r in tot.itertuples(index=False)]

# Top 3 Geral
top3_geral = top3_from_day(day)
geral_set = {n for n,_ in top3_geral}

# Top 3 JPaulo (exclui quem já está no Geral)
day_jp = day.merge(df[["Cliente","Funcionário"]].drop_duplicates(),
                   on="Cliente", how="left")
day_jp = day_jp[day_jp["Funcionário"].astype(str).str.strip()=="JPaulo"]
day_jp = day_jp[~day_jp["Cliente"].isin(geral_set)]
top3_jp = top3_from_day(day_jp[["Cliente","Data"]])

# Top 3 Vinicius (exclui quem já está no Geral)
day_vi = day.merge(df[["Cliente","Funcionário"]].drop_duplicates(),
                   on="Cliente", how="left")
day_vi = day_vi[day_vi["Funcionário"].astype(str).str.strip()=="Vinicius"]
day_vi = day_vi[~day_vi["Cliente"].isin(geral_set)]
top3_vi = top3_from_day(day_vi[["Cliente","Data"]])

# Top 3 Famílias
top3_fam = []
if ABA_STATUS in abas:
    ws_status = abas[ABA_STATUS]
    stt = get_as_dataframe(ws_status).dropna(how="all")
    stt.columns = [c.strip() for c in stt.columns]
    if "Cliente" in stt.columns:
        fam_col = None
        cols_low = {c.lower(): c for c in stt.columns}
        for k in ("família","familia","familia_grupo"):
            if k in cols_low:
                fam_col = cols_low[k]; break
        if fam_col:
            fam_map = stt[["Cliente", fam_col]].rename(columns={fam_col:"Familia"})
            fam_day = day.merge(fam_map, on="Cliente", how="left")
            fam_day = fam_day[fam_day["Familia"].notna() & (fam_day["Familia"].astype(str).str.strip()!="")]
            fam_tot = (fam_day.groupby("Familia", as_index=False)
                               .agg({"Cliente":"nunique","Data":"nunique"})
                               .rename(columns={"Data":"atend"}))
            fam_tot = fam_tot.sort_values("atend", ascending=False).head(3)
            top3_fam = [(r.Familia, int(r.atend)) for r in fam_tot.itertuples(index=False)]

# ======================
# Envio no estilo “cards” (foto + legenda)
# ======================
def enviar_categoria(titulo: str, items: list[tuple[str,int]], is_family=False):
    medal = ["🥇","🥈","🥉"]
    tg_send(f"<b>{html.escape(titulo)}</b>")
    for i, (nome, atend) in enumerate(items[:3]):
        foto = foto_do(nome if not is_family else nome)  # família usa primeira foto encontrada do grupo? (fallback logo)
        # legenda sem valores
        cap = f"{medal[i]} <b>{html.escape(nome)}</b> — {atend} atendimentos"
        tg_send_photo(foto, cap)

# Cabeçalho geral
tg_send("Salão JP 🎗️ Premiação\n🏆 <b>Top 3 — Salão JP</b>\nData/hora: " + html.escape(now_br()))

enviar_categoria("Geral", top3_geral)
enviar_categoria("JPaulo", top3_jp)
enviar_categoria("Vinicius", top3_vi)
enviar_categoria("Famílias", top3_fam, is_family=True)

print("✅ Top 3 (estilo Streamlit, sem valores) enviado.")

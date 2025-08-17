# top_3_salao_JP.py — ranking por VALOR (exibe só atendimentos)
import os, json, html, unicodedata, requests
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# ===== CONFIG =====
TZ = "America/Sao_Paulo"
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_STATUS = "clientes_status"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")            # defina nos secrets/vars
TELEGRAM_CHAT_ID = "-1002953102982"                     # canal fixo
LOGO_PADRAO = "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png"

GCP_SERVICE_ACCOUNT = json.loads(os.getenv("GCP_SERVICE_ACCOUNT"))  # JSON completo

# ===== Helpers =====
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
    requests.post(url, json=payload, timeout=30)

def tg_send_photo(photo_url: str, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url,
            "caption": caption, "parse_mode": "HTML"}
    r = requests.post(url, data=data, timeout=30)
    if not r.ok:
        # fallback se a foto falhar
        tg_send(caption + "\n(foto indisponível)")

# ===== Conectar Sheets =====
scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(GCP_SERVICE_ACCOUNT, scopes=scopes)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
abas = {w.title: w for w in sh.worksheets()}

# ===== Carregar Base =====
GENERIC_RE = r"(?:^|\b)(boliviano|brasileiro|menino|sem preferencia|funcion[aá]rio)(?:\b|$)"

ws_base = abas[ABA_BASE]
df = get_as_dataframe(ws_base).dropna(how="all")
df.columns = [c.strip() for c in df.columns]

# saneamento
for col in ("Cliente","Data","Funcionário","Valor"):
    if col not in df.columns:
        raise SystemExit(f"Coluna obrigatória ausente: {col}")

df["Cliente"] = df["Cliente"].astype(str).str.strip()
df = df[(df["Cliente"]!="") &
        (~df["Cliente"].str.lower().isin(["nan","none"])) &
        (~df["Cliente"].str.lower().str.contains(GENERIC_RE, regex=True))]

df["Valor"] = pd.to_numeric(df["Valor"], errors="coerce").fillna(0.0)
df["Data"]  = pd.to_datetime(df["Data"], errors="coerce")
df = df.dropna(subset=["Data"])

# normaliza para data (1 atendimento por dia)
df["_data_dia"] = df["Data"].dt.date

# ===== Fotos =====
foto_map = {}
if ABA_STATUS in abas:
    ws_status = abas[ABA_STATUS]
    stt = get_as_dataframe(ws_status).dropna(how="all")
    stt.columns = [c.strip() for c in stt.columns]
    if "Cliente" in stt.columns:
        cols_low = {c.lower(): c for c in stt.columns}
        foto_col = next((cols_low[k] for k in ("foto","imagem","link_foto","url_foto","foto_link","link","image") if k in cols_low), None)
        if foto_col:
            tmp = stt[["Cliente", foto_col]].copy()
            tmp.columns = ["Cliente","Foto"]
            foto_map = {_norm(r["Cliente"]): str(r["Foto"]).strip()
                        for _, r in tmp.iterrows() if str(r["Foto"]).strip()}

def foto_de(nome: str) -> str:
    return foto_map.get(_norm(nome), LOGO_PADRAO)

# ===== Ranking base: por VALOR (cliente+dia -> sum Valor; depois somar por cliente) =====
def build_ranking(df_base: pd.DataFrame) -> pd.DataFrame:
    if df_base.empty:
        return pd.DataFrame(columns=["Cliente","total_gasto","atendimentos"])
    # soma do dia
    por_dia = (df_base.groupby(["Cliente","_data_dia"], as_index=False)["Valor"].sum())
    # total gasto por cliente (critério de rank)
    tot = por_dia.groupby("Cliente", as_index=False)["Valor"].sum().rename(columns={"Valor":"total_gasto"})
    # atendimentos (exibir)
    atend = por_dia.groupby("Cliente", as_index=False)["_data_dia"].nunique().rename(columns={"_data_dia":"atendimentos"})
    out = tot.merge(atend, on="Cliente", how="left")
    out = out.sort_values("total_gasto", ascending=False)
    return out

# Top 3 Geral
rank_geral = build_ranking(df)
top3_geral = rank_geral.head(3)
excluir = set(top3_geral["Cliente"].tolist())

# Top 3 JPaulo (exclui quem já está no Geral)
df_jp = df[df["Funcionário"].astype(str).str.strip()=="JPaulo"].copy()
rank_jp = build_ranking(df_jp[~df_jp["Cliente"].isin(excluir)])
top3_jp = rank_jp.head(3)

# Top 3 Vinicius (exclui quem já está no Geral)
df_vi = df[df["Funcionário"].astype(str).str.strip()=="Vinicius"].copy()
rank_vi = build_ranking(df_vi[~df_vi["Cliente"].isin(excluir)])
top3_vi = rank_vi.head(3)

# Top 3 Famílias (rankeia por VALOR total da família; mostra atendimentos e nº membros)
top3_fam = []
if ABA_STATUS in abas:
    stt = get_as_dataframe(abas[ABA_STATUS]).dropna(how="all")
    stt.columns = [c.strip() for c in stt.columns]
    if "Cliente" in stt.columns:
        cols_low = {c.lower(): c for c in stt.columns}
        fam_col = next((cols_low[k] for k in ("família","familia","familia_grupo") if k in cols_low), None)
        if fam_col:
            fam_map = stt[["Cliente", fam_col]].rename(columns={fam_col:"Familia"})
            df_fam = df.merge(fam_map, on="Cliente", how="left")
            df_fam = df_fam[df_fam["Familia"].notna() & (df_fam["Familia"].astype(str).str.strip()!="")]

            # soma por dia por cliente (para contar atendimentos)
            por_dia_fam = (df_fam.groupby(["Familia","Cliente","_data_dia"], as_index=False)["Valor"].sum())
            # VALOR total da família (critério de rank)
            fam_val = por_dia_fam.groupby("Familia", as_index=False)["Valor"].sum().rename(columns={"Valor":"total_gasto"})
            # atendimentos = nº de (Cliente, dia) únicos
            fam_atd = por_dia_fam.groupby("Familia", as_index=False).size().rename(columns={"size":"atendimentos"})
            # membros = nº de clientes distintos
            fam_membros = por_dia_fam.groupby("Familia", as_index=False)["Cliente"].nunique().rename(columns={"Cliente":"membros"})

            fam_rank = fam_val.merge(fam_atd, on="Familia").merge(fam_membros, on="Familia")
            fam_rank = fam_rank.sort_values("total_gasto", ascending=False).head(3)
            top3_fam = fam_rank.to_dict("records")

# ===== Envio (sem valores) =====
def enviar_categoria(titulo: str, df_items: pd.DataFrame):
    tg_send(f"<b>{html.escape(titulo)}</b>")
    medal = ["🥇","🥈","🥉"]
    for i, r in enumerate(df_items.itertuples(index=False)):
        nome = getattr(r, "Cliente")
        atend = int(getattr(r, "atendimentos"))
        cap = f"{medal[i]} <b>{html.escape(str(nome))}</b> — {atend} atendimentos"
        tg_send_photo(foto_de(str(nome)), cap)

def enviar_familias():
    tg_send("<b>Famílias</b>")
    medal = ["🥇","🥈","🥉"]
    for i, r in enumerate(top3_fam):
        fam = str(r["Familia"])
        atend = int(r["atendimentos"])
        membros = int(r["membros"])
        # tenta achar foto de alguém da família; se não, usa logo
        foto = LOGO_PADRAO
        # procura algum membro com foto
        try:
            stt = get_as_dataframe(abas[ABA_STATUS]).dropna(how="all")
            stt.columns = [c.strip() for c in stt.columns]
            cols_low = {c.lower(): c for c in stt.columns}
            fcol = next((cols_low[k] for k in ("foto","imagem","link_foto","url_foto","foto_link","link","image") if k in cols_low), None)
            famcol = next((cols_low[k] for k in ("família","familia","familia_grupo") if k in cols_low), None)
            if fcol and famcol:
                cand = stt[stt[famcol].astype(str).str.strip()==fam]
                if not cand.empty:
                    f = str(cand[fcol].dropna().astype(str).str.strip().head(1).values[0])
                    if f: foto = f
        except Exception:
            pass
        cap = f"{medal[i]} <b>{html.escape(fam)}</b> — {atend} atendimentos | {membros} membros"
        tg_send_photo(foto, cap)

# Cabeçalho
tg_send("🎗️ Salão JP — Premiação\n🏆 <b>Top 3 (por gasto)</b>\nData/hora: " + html.escape(now_br()))

enviar_categoria("Geral", top3_geral)
enviar_categoria("JPaulo", top3_jp)
enviar_categoria("Vinicius", top3_vi)
enviar_familias()

print("✅ Top 3 enviado (ranking por valor; exibindo só atendimentos).")

# top_3_salao_JP.py — ranking por VALOR (exibe só atendimentos) + feedback de movimentação
import os, json, html, unicodedata, requests
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# ===== CONFIG =====
TZ = "America/Sao_Paulo"
SHEET_ID = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE = "Base de Dados"
ABA_STATUS = "clientes_status"
ABA_CACHE = "premiacao_cache"   # onde salvamos o snapshot do Top 3

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")            # defina nos secrets/vars
TELEGRAM_CHAT_ID = "-1002953102982"                     # canal fixo
LOGO_PADRAO = "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png"

GCP_SERVICE_ACCOUNT = json.loads(os.getenv("GCP_SERVICE_ACCOUNT"))  # JSON completo

# ===== Helpers =====
def now_br_dt():
    return datetime.now(pytz.timezone(TZ))

def now_br():
    return now_br_dt().strftime("%d/%m/%Y %H:%M:%S")

def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def tg_send(text: str):
    if not TELEGRAM_TOKEN:
        print("[WARN] TELEGRAM_TOKEN ausente; mensagem:\n", text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    requests.post(url, json=payload, timeout=30)

def tg_send_photo(photo_url: str, caption: str):
    if not TELEGRAM_TOKEN:
        print("[WARN] TELEGRAM_TOKEN ausente; caption:\n", caption, "\nFoto:", photo_url)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
    data = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url,
            "caption": caption, "parse_mode": "HTML"}
    r = requests.post(url, data=data, timeout=30)
    if not r.ok:
        tg_send(caption + "\n(foto indisponível)")

# ===== Conectar Sheets =====
scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(GCP_SERVICE_ACCOUNT, scopes=scopes)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
abas = {w.title: w for w in sh.worksheets()}

def get_or_create_cache_ws():
    if ABA_CACHE in abas:
        return abas[ABA_CACHE]
    ws = sh.add_worksheet(title=ABA_CACHE, rows=2000, cols=10)
    abas[ABA_CACHE] = ws
    df_init = pd.DataFrame(columns=["ts", "categoria", "pos", "chave", "extra"])
    set_with_dataframe(ws, df_init, include_index=False)
    return ws

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

# ===== Fotos (clientes) =====
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
    por_dia = (df_base.groupby(["Cliente","_data_dia"], as_index=False)["Valor"].sum())
    tot = por_dia.groupby("Cliente", as_index=False)["Valor"].sum().rename(columns={"Valor":"total_gasto"})
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

# ===== Top 3 Famílias (rank por VALOR) + representante/foto =====
top3_fam = []
fam_rep_map = {}   # Familia -> Cliente representante (p/ foto)
fam_foto_map = {}  # Familia -> Foto direta (se existir coluna foto da família)

if ABA_STATUS in abas:
    stt = get_as_dataframe(abas[ABA_STATUS]).dropna(how="all")
    stt.columns = [c.strip() for c in stt.columns]
    if "Cliente" in stt.columns:
        cols_low = {c.lower(): c for c in stt.columns}
        fam_col = next((cols_low[k] for k in ("família","familia","familia_grupo") if k in cols_low), None)
        foto_fam_col = next((cols_low[k] for k in ("foto_familia","foto família","foto da família","foto da familia") if k in cols_low), None)

        if fam_col:
            if foto_fam_col:
                tmpff = stt[[fam_col, foto_fam_col]].copy()
                tmpff.columns = ["Familia", "FotoFamilia"]
                fam_foto_map = {
                    str(r["Familia"]).strip(): str(r["FotoFamilia"]).strip()
                    for _, r in tmpff.dropna(subset=["Familia","FotoFamilia"]).iterrows()
                    if str(r["FotoFamilia"]).strip()
                }

            fam_map = stt[["Cliente", fam_col]].rename(columns={fam_col:"Familia"})
            df_fam = df.merge(fam_map, on="Cliente", how="left")
            df_fam = df_fam[df_fam["Familia"].notna() & (df_fam["Familia"].astype(str).str.strip()!="")]

            por_dia_fam = (df_fam.groupby(["Familia","Cliente","_data_dia"], as_index=False)["Valor"].sum())

            fam_val = por_dia_fam.groupby("Familia", as_index=False)["Valor"].sum().rename(columns={"Valor":"total_gasto"})
            fam_atd = por_dia_fam.groupby("Familia", as_index=False).size().rename(columns={"size":"atendimentos"})
            fam_membros = por_dia_fam.groupby("Familia", as_index=False)["Cliente"].nunique().rename(columns={"Cliente":"membros"})

            fam_rank = fam_val.merge(fam_atd, on="Familia").merge(fam_membros, on="Familia")
            fam_rank = fam_rank.sort_values("total_gasto", ascending=False).head(3)
            top3_fam = fam_rank.to_dict("records")

            # Escolher representante por família (para foto)
            cli_stats = (por_dia_fam.groupby(["Familia","Cliente"], as_index=False)
                         .agg(gasto=("Valor","sum"),
                              atend=("_data_dia","nunique")))

            cli_stats["prio_nome_igual"] = (
                cli_stats["Familia"].astype(str).str.strip().str.casefold() ==
                cli_stats["Cliente"].astype(str).str.strip().str.casefold()
            )

            pref = cli_stats.sort_values(
                by=["Familia","prio_nome_igual","gasto","atend","Cliente"],
                ascending=[True, False, False, False, True]
            )

            pref_rep = pref.drop_duplicates(subset=["Familia"], keep="first")
            fam_rep_map = dict(zip(pref_rep["Familia"].astype(str), pref_rep["Cliente"].astype(str)))

# ===== Comparação e Cache =====
def list_from_df(df_items: pd.DataFrame, key_col: str) -> list[str]:
    if df_items is None or df_items.empty:
        return []
    return [str(x) for x in df_items[key_col].tolist()]

def familias_list() -> list[str]:
    return [str(r["Familia"]) for r in top3_fam]

def load_prev_top3():
    """Carrega o último snapshot por categoria do cache."""
    ws = get_or_create_cache_ws()
    dfc = get_as_dataframe(ws).dropna(how="all")
    if dfc.empty or "categoria" not in dfc.columns:
        return {}
    # pega último ts por categoria
    dfc["ts"] = pd.to_datetime(dfc["ts"], errors="coerce")
    last = dfc.sort_values("ts").groupby("categoria").tail(3)
    prev = {}
    for cat, g in last.groupby("categoria"):
        g = g.sort_values("pos")
        prev[cat] = g["chave"].astype(str).tolist()
    return prev

def save_current_top3(run_ts: datetime, atuais: dict):
    rows = []
    ts_str = run_ts.isoformat()
    for cat, lista in atuais.items():
        for i, name in enumerate(lista, start=1):
            rows.append({"ts": ts_str, "categoria": cat, "pos": i, "chave": name, "extra": ""})
    ws = get_or_create_cache_ws()
    df_old = get_as_dataframe(ws).dropna(how="all")
    df_new = pd.concat([df_old, pd.DataFrame(rows)], ignore_index=True) if not df_old.empty else pd.DataFrame(rows)
    set_with_dataframe(ws, df_new, include_index=False, resize=True)

def movements(prev: list[str], curr: list[str]):
    """Retorna listas com (name, from_pos, to_pos) para up/down, e listas de new/out."""
    pos_prev = {n: i+1 for i, n in enumerate(prev)}
    pos_curr = {n: i+1 for i, n in enumerate(curr)}
    ups, downs, new, out = [], [], [], []
    for n in curr:
        if n in pos_prev:
            if pos_curr[n] < pos_prev[n]:
                ups.append((n, pos_prev[n], pos_curr[n]))
            elif pos_curr[n] > pos_prev[n]:
                downs.append((n, pos_prev[n], pos_curr[n]))
        else:
            new.append((n, pos_curr[n]))
    for n in prev:
        if n not in pos_curr:
            out.append((n, pos_prev[n]))
    return ups, downs, new, out

def send_movements(cat: str, prev_list: list[str], curr_list: list[str]):
    ups, downs, new, out = movements(prev_list, curr_list)
    if not (ups or downs or new or out):
        return
    lines = [f"<b>Atualização no {html.escape(cat)}</b>"]
    for n, a, b in ups:
        lines.append(f"⬆️ <b>{html.escape(n)}</b> subiu de #{a} para #{b}")
    for n, a, b in downs:
        lines.append(f"⬇️ <b>{html.escape(n)}</b> caiu de #{a} para #{b}")
    for n, p in new:
        lines.append(f"🆕 <b>{html.escape(n)}</b> entrou no Top 3 — agora #{p}")
    for n, p in out:
        lines.append(f"❌ <b>{html.escape(n)}</b> saiu do Top 3 (era #{p})")
    tg_send("\n".join(lines))

# ===== Envio =====
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
        fam = str(r["Familia"]).strip()
        atend = int(r["atendimentos"])
        membros = int(r["membros"])

        foto = fam_foto_map.get(fam, "")
        if not foto:
            rep = fam_rep_map.get(fam, "")
            if rep:
                foto = foto_de(rep)
        if not foto:
            foto = LOGO_PADRAO

        cap = f"{medal[i]} <b>{html.escape(fam)}</b> — {atend} atendimentos | {membros} membros"
        tg_send_photo(foto, cap)

# ===== Execução =====
tg_send("🎗️ Salão JP — Premiação\n🏆 <b>Top 3 (por gasto)</b>\nData/hora: " + html.escape(now_br()))

enviar_categoria("Geral", top3_geral)
enviar_categoria("JPaulo", top3_jp)
enviar_categoria("Vinicius", top3_vi)
enviar_familias()

# Feedback de movimentação
atuais = {
    "Geral": list_from_df(top3_geral, "Cliente"),
    "JPaulo": list_from_df(top3_jp, "Cliente"),
    "Vinicius": list_from_df(top3_vi, "Cliente"),
    "Famílias": familias_list(),
}
prev = load_prev_top3()
for cat, curr_list in atuais.items():
    send_movements(cat, prev.get(cat, []), curr_list)

# Salva snapshot atual
save_current_top3(now_br_dt(), atuais)

print("✅ Top 3 enviado e feedback de movimentação registrado.")

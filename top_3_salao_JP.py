# top_10_salao_JP.py — Top 10 (Valor + Caixinha do Cliente) + Top 3 Famílias + Movimentos
import os, json, html, unicodedata, requests
import pandas as pd
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# ===== CONFIG =====
TZ = "America/Sao_Paulo"
SHEET_ID   = "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE"
ABA_BASE   = "Base de Dados"
ABA_STATUS = "clientes_status"
ABA_CACHE  = "premiacao_cache"

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = "-1002953102982"
LOGO_PADRAO = "https://res.cloudinary.com/db8ipmete/image/upload/v1752463905/Logo_sal%C3%A3o_kz9y9c.png"

GCP_SERVICE_ACCOUNT = json.loads(os.getenv("GCP_SERVICE_ACCOUNT"))

# ===== Helpers =====
def now_br_dt():
    return datetime.now(pytz.timezone(TZ))
def now_br():
    return now_br_dt().strftime("%d/%m/%Y %H:%M:%S")

def _norm(s: str) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.casefold()

def _to_num(series):
    return (pd.to_numeric(
        series.astype(str)
              .str.replace(r"[^\d,.\-]", "", regex=True)
              .str.replace(".", "", regex=False)
              .str.replace(",", ".", regex=False),
        errors="coerce"
    ).fillna(0.0))

def tg_send(text: str):
    if not TELEGRAM_TOKEN:
        print("[WARN] TELEGRAM_TOKEN ausente; mensagem:\n", text)
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text,
                   "parse_mode": "HTML", "disable_web_page_preview": True}
        requests.post(url, json=payload, timeout=30)
    except Exception as e:
        print("[ERR] Telegram sendMessage:", e, "\nConteúdo:", text)

def tg_send_photo(photo_url: str, caption: str):
    if not TELEGRAM_TOKEN:
        print("[WARN] TELEGRAM_TOKEN ausente; caption:\n", caption, "\nFoto:", photo_url)
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        data = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url,
                "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=data, timeout=30)
        if not r.ok:
            tg_send(caption + "\n(foto indisponível)")
    except Exception as e:
        print("[ERR] Telegram sendPhoto:", e, "\nCaption:", caption, "\nFoto:", photo_url)
        tg_send(caption + "\n(falha ao carregar a foto)")

# ===== Sheets =====
scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(GCP_SERVICE_ACCOUNT, scopes=scopes)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
abas = {w.title: w for w in sh.worksheets()}

def get_or_create_cache_ws():
    if ABA_CACHE in abas: return abas[ABA_CACHE]
    ws = sh.add_worksheet(title=ABA_CACHE, rows=2000, cols=10)
    abas[ABA_CACHE] = ws
    set_with_dataframe(ws, pd.DataFrame(columns=["ts","categoria","pos","chave","extra"]), include_index=False)
    return ws

def find_col(df_cols, *candidates):
    low_map = {c.lower(): c for c in df_cols}
    for cand in candidates:
        c = low_map.get(cand.lower())
        if c: return c
    return None

# ===== Base =====
GENERIC_RE = r"(?:^|\b)(boliviano|brasileiro|menino|sem preferencia|funcion[aá]rio)(?:\b|$)"

df = get_as_dataframe(abas[ABA_BASE]).dropna(how="all")
df.columns = [c.strip() for c in df.columns]

for col in ("Cliente","Data","Valor"):
    if col not in df.columns:
        raise SystemExit(f"Coluna obrigatória ausente: {col}")

df["Cliente"] = df["Cliente"].astype(str).str.strip()
df = df[(df["Cliente"]!="") &
        (~df["Cliente"].str.lower().isin(["nan","none"])) &
        (~df["Cliente"].str.lower().str.contains(GENERIC_RE, regex=True))]

# Datas e números primeiro (evita filtrar por string)
df["Data"] = pd.to_datetime(df["Data"], errors="coerce", dayfirst=True)
df = df.dropna(subset=["Data"])
df["_data_dia"] = df["Data"].dt.date
df["Valor"] = _to_num(df["Valor"])

# ===== Caixinha só do CLIENTE =====
col_cx_dia = find_col(df.columns, "CaixinhaDia")
col_cx      = find_col(df.columns, "Caixinha")
col_gorjeta = find_col(df.columns, "Gorjeta")
col_fundo1  = find_col(df.columns, "CaixinhaFundo")
col_fundo2  = find_col(df.columns, "Caixinha_Fundo")
# Total do dia (diagnóstico – não somar)
_ = find_col(df.columns, "CaixinhaDiaTotal")

df["_CaixinhaCliente"] = 0.0
if col_cx_dia: df["_CaixinhaCliente"] += _to_num(df[col_cx_dia])
if col_cx:     df["_CaixinhaCliente"] += _to_num(df[col_cx])
if col_gorjeta:df["_CaixinhaCliente"] += _to_num(df[col_gorjeta])
if col_fundo1: df["_CaixinhaCliente"] -= _to_num(df[col_fundo1])
if col_fundo2: df["_CaixinhaCliente"] -= _to_num(df[col_fundo2])

df["_ValorConsiderado"] = df["Valor"] + df["_CaixinhaCliente"]

# ===== Nome canônico (consolida variações do mesmo cliente) =====
# 1) Mapa vindo do STATUS (preferível)
canon_map = {}     # chave: _norm(Cliente) -> NomePreferido/NomePadrao
display_map = {}   # chave: _norm(Cliente) -> nome para exibir

if ABA_STATUS in abas:
    stt = get_as_dataframe(abas[ABA_STATUS]).dropna(how="all")
    stt.columns = [c.strip() for c in stt.columns]
    if "Cliente" in stt.columns:
        nome_pref_col = find_col(stt.columns, "Nome Preferido", "NomePreferido",
                                 "Nome Padrão", "NomePadrao", "nome_preferido", "nome_padrao")
        if nome_pref_col:
            for _, r in stt.iterrows():
                cli = str(r.get("Cliente","")).strip()
                pref = str(r.get(nome_pref_col,"")).strip()
                if cli:
                    k = _norm(cli)
                    if pref:
                        canon_map[k] = pref
                        display_map[k] = pref

# 2) Fallback: usa a variante mais frequente da própria base
df["_cli_norm"] = df["Cliente"].map(_norm)
if not display_map:
    cont = (df.groupby(["_cli_norm","Cliente"])
              .size().reset_index(name="n")
              .sort_values(["_cli_norm","n"], ascending=[True, False]))
    pref = cont.drop_duplicates(subset=["_cli_norm"], keep="first")
    display_map = dict(zip(pref["_cli_norm"], pref["Cliente"]))

def canonize(nome: str) -> str:
    k = _norm(nome)
    return canon_map.get(k, display_map.get(k, nome.strip()))

df["_cli_canon"] = df["Cliente"].map(canonize)
df["_cli_canon_norm"] = df["_cli_canon"].map(_norm)  # chave única para groupby
# garante display
for k,v in list(display_map.items()):
    display_map[k] = v.strip() or v
# se vier algo novo
for k in df["_cli_canon_norm"].unique():
    display_map.setdefault(k, df.loc[df["_cli_canon_norm"]==k, "Cliente"].iloc[0])

# ===== Filtro Receita (correto) =====
if "Tipo" in df.columns:
    t = df["Tipo"].astype(str).str.strip().str.casefold()
    df = df[(t == "receita") | (df["Valor"] > 0)]
else:
    df = df[df["Valor"] > 0]

# ===== Agregação por ClienteCanon + Data =====
por_dia = (
    df.groupby(["_cli_canon_norm","_data_dia"], as_index=False)["_ValorConsiderado"].sum()
      .rename(columns={"_ValorConsiderado":"total_dia"})
)

rank_geral = (
    por_dia.groupby("_cli_canon_norm", as_index=False)
           .agg(total_gasto=("total_dia","sum"),
                atendimentos=("_data_dia","nunique"))
           .sort_values(["total_gasto","atendimentos","_cli_canon_norm"], ascending=[False, False, True])
           .reset_index(drop=True)
)
rank_geral["Cliente"] = rank_geral["_cli_canon_norm"].map(display_map)
top10 = rank_geral[["Cliente","total_gasto","atendimentos"]].head(10)

# ===== Fotos por cliente =====
foto_map = {}
if ABA_STATUS in abas:
    stt = get_as_dataframe(abas[ABA_STATUS]).dropna(how="all")
    stt.columns = [c.strip() for c in stt.columns]
    if "Cliente" in stt.columns:
        foto_col = find_col(stt.columns, "foto","imagem","link_foto","url_foto","foto_link","link","image")
        if foto_col:
            tmp = stt[["Cliente", foto_col]].copy()
            tmp.columns = ["Cliente","Foto"]
            for _, r in tmp.iterrows():
                k = _norm(str(r["Cliente"]))
                v = str(r["Foto"]).strip()
                if v:
                    foto_map[k] = v

def foto_de(nome: str) -> str:
    return foto_map.get(_norm(nome), LOGO_PADRAO)

# ===== Famílias (usando canônico) =====
top3_fam, fam_rep_map, fam_foto_map = [], {}, {}
if ABA_STATUS in abas:
    stt2 = get_as_dataframe(abas[ABA_STATUS]).dropna(how="all")
    stt2.columns = [c.strip() for c in stt2.columns]
    if "Cliente" in stt2.columns:
        fam_col = find_col(stt2.columns, "família","familia","familia_grupo")
        foto_fam_col = find_col(stt2.columns, "foto_familia","foto família","foto da família","foto da familia")
        if fam_col:
            fam_map = stt2[["Cliente", fam_col]].rename(columns={fam_col:"Familia"}).copy()
            fam_map["_cli_norm"] = fam_map["Cliente"].map(_norm)
            fam_map = fam_map[ fam_map["Familia"].astype(str).str.strip() != "" ]

            cd = por_dia.merge(fam_map[["_cli_norm","Familia"]],
                               left_on="_cli_canon_norm", right_on="_cli_norm", how="left")
            cd = cd[cd["Familia"].notna() & (cd["Familia"].astype(str).str.strip()!="")]

            fam_rank = (
                cd.groupby("Familia", as_index=False)
                  .agg(total_gasto=("total_dia","sum"),
                       atendimentos=("_data_dia","nunique"),
                       membros=("_cli_norm","nunique"))
                  .sort_values(["total_gasto","atendimentos","membros","Familia"], ascending=[False, False, False, True])
                  .reset_index(drop=True)
            )
            top3_fam = fam_rank.head(3).to_dict("records")

            # representante (para foto da família)
            cli_stats = (
                cd.groupby(["Familia","_cli_canon_norm"], as_index=False)
                  .agg(gasto=("total_dia","sum"),
                       atend=("_data_dia","nunique"))
                  .sort_values(["Familia","gasto","atend","_cli_canon_norm"], ascending=[True, False, False, True])
            )
            pref = cli_stats.drop_duplicates(subset=["Familia"], keep="first")
            fam_rep_map = dict(zip(pref["Familia"].astype(str),
                                   pref["_cli_canon_norm"].map(lambda k: display_map.get(k,k))))

            if foto_fam_col:
                tmpff = stt2[[fam_col, foto_fam_col]].copy()
                tmpff.columns = ["Familia", "FotoFamilia"]
                fam_foto_map = {
                    str(r["Familia"]).strip(): str(r["FotoFamilia"]).strip()
                    for _, r in tmpff.dropna(subset=["Familia","FotoFamilia"]).iterrows()
                    if str(r["FotoFamilia"]).strip()
                }

# ===== Cache/Movimentos =====
def list_from_df(df_items, key_col):
    if df_items is None or df_items.empty: return []
    return [str(x) for x in df_items[key_col].tolist()]
def familias_list():
    return [str(r["Familia"]) for r in top3_fam]

def load_prev_lists():
    ws = get_or_create_cache_ws()
    dfc = get_as_dataframe(ws).dropna(how="all")
    if dfc.empty or "categoria" not in dfc.columns: return {}
    dfc["ts"] = pd.to_datetime(dfc["ts"], errors="coerce")
    dfc = dfc.sort_values("ts")
    prev = {}
    for cat, gcat in dfc.groupby("categoria"):
        tail_n = 3 if cat == "Famílias" else 10
        g2 = gcat.tail(tail_n).sort_values("pos")
        prev[cat] = g2["chave"].astype(str).tolist()
    return prev

def save_current_lists(run_ts, atuais: dict):
    rows = []
    ts_str = run_ts.isoformat()
    for cat, lista in atuais.items():
        for i, name in enumerate(lista, start=1):
            rows.append({"ts": ts_str, "categoria": cat, "pos": i, "chave": name, "extra": ""})
    ws = get_or_create_cache_ws()
    df_old = get_as_dataframe(ws).dropna(how="all")
    df_new = pd.concat([df_old, pd.DataFrame(rows)], ignore_index=True) if not df_old.empty else pd.DataFrame(rows)
    set_with_dataframe(ws, df_new, include_index=False, resize=True)

def movements(prev, curr):
    pos_prev = {n: i+1 for i, n in enumerate(prev)}
    pos_curr = {n: i+1 for i, n in enumerate(curr)}
    ups, downs, new, out = [], [], [], []
    for n in curr:
        if n in pos_prev:
            if pos_curr[n] < pos_prev[n]: ups.append((n, pos_prev[n], pos_curr[n]))
            elif pos_curr[n] > pos_prev[n]: downs.append((n, pos_prev[n], pos_curr[n]))
        else:
            new.append((n, pos_curr[n]))
    for n in prev:
        if n not in pos_curr: out.append((n, pos_prev[n]))
    return ups, downs, new, out

def send_movements(cat: str, prev_list, curr_list):
    ups, downs, new, out = movements(prev_list, curr_list)
    if not (ups or downs or new or out): return
    lines = [f"<b>Atualização no {html.escape(cat)}</b>"]
    for n, a, b in ups:   lines.append(f"⬆️ <b>{html.escape(n)}</b> subiu de #{a} para #{b}")
    for n, a, b in downs: lines.append(f"⬇️ <b>{html.escape(n)}</b> caiu de #{a} para #{b}")
    for n, p in new:      lines.append(f"🆕 <b>{html.escape(n)}</b> entrou — agora #{p}")
    for n, p in out:      lines.append(f"❌ <b>{html.escape(n)}</b> saiu (era #{p})")
    tg_send("\n".join(lines))

# ===== Envio =====
def enviar_top10(df_items: pd.DataFrame):
    titulo = "🏆 Top 10 por gasto (Valor + Caixinha do cliente)"
    tg_send(f"<b>{html.escape(titulo)}</b>")
    medal = {1:"🥇", 2:"🥈", 3:"🥉"}
    for i, r in enumerate(df_items.itertuples(index=False), start=1):
        nome  = getattr(r, "Cliente")
        atend = int(getattr(r, "atendimentos"))
        prefix = medal.get(i, f"#{i}")
        cap = f"{prefix} <b>{html.escape(str(nome))}</b> — {atend} atendimentos"
        tg_send_photo(foto_de(str(nome)), cap)

def enviar_familias():
    if not top3_fam: return
    tg_send("<b>👨‍👩‍👧‍👦 Top 3 Famílias (Valor + Caixinha do cliente)</b>")
    medal = ["🥇","🥈","🥉"]
    for i, r in enumerate(top3_fam):
        fam = str(r["Familia"]).strip()
        atend = int(r["atendimentos"])
        membros = int(r["membros"])
        foto = (fam_foto_map.get(fam, "") or foto_de(fam_rep_map.get(fam, ""))) or LOGO_PADRAO
        cap = f"{medal[i]} <b>{html.escape(fam)}</b> — {atend} atendimentos | {membros} membros"
        tg_send_photo(foto, cap)

# ===== Execução =====
tg_send("🎗️ Salão JP — Premiação\n🏆 <b>Top 10 (Valor + Caixinha do cliente)</b>\nData/hora: " + html.escape(now_br()))
enviar_top10(top10)
enviar_familias()

atuais = {"Top10": list_from_df(top10, "Cliente"), "Famílias": familias_list()}
prev = load_prev_lists()
for cat, curr_list in atuais.items():
    send_movements(cat, prev.get(cat, []), curr_list)
save_current_lists(now_br_dt(), atuais)

# Log simples para auditoria nos logs da execução
print("TOP10 CALCULADO:")
print(top10.to_string(index=False))
print("✅ Top 10 & Famílias enviados (Valor + Caixinha do cliente) e movimentos registrados.")

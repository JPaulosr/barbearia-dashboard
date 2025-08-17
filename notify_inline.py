# notify_inline.py — Frequência por MÉDIA + cache + FOTO (cards às 08:00)
import os, sys, json, html, unicodedata, requests, gspread, pytz, pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# -------------------------
# Flags/Parâmetros
# -------------------------
def _b(name, default=False):
    v = os.getenv(name)
    if v is None: return default
    return str(v).strip().lower() in ("1","true","t","yes","y","on")

TZ               = os.getenv("TZ") or os.getenv("TIMEZONE") or "America/Sao_Paulo"
REL_MULT         = float(os.getenv("REL_MULT", "1.5"))
ABA_BASE         = os.getenv("BASE_ABA", "Base de Dados")
ABA_STATUS_CACHE = os.getenv("ABA_STATUS_CACHE", "status_cache")
STATUS_ABA       = os.getenv("STATUS_ABA", "clientes_status")  # Cliente + link da foto
FOTO_COL_ENV     = (os.getenv("FOTO_COL", "") or "").strip()
ABA_TRANSICOES   = os.getenv("ABA_TRANSICOES", "freq_transicoes")

SEND_AT_8_CARDS  = _b("SEND_AT_8_CARDS", False)  # enviar cards às 08h com base na fila
ALLOW_WRITE      = _b("ALLOW_WRITE", True)       # permite escrever nas abas auxiliares
SAFE_TELEGRAM    = _b("SAFE_TELEGRAM", False)    # não falha se Telegram der 400/429
SOFT_FAIL        = _b("SOFT_FAIL", False)        # se der erro inesperado, loga e sai 0

# -------------------------
# Envs obrigatórios
# -------------------------
SHEET_ID        = (os.getenv("SHEET_ID") or "").strip()
TELEGRAM_TOKEN  = (os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID= (os.getenv("TELEGRAM_CHAT_ID") or "").strip()

def die(msg, code=1, exc=None):
    print("💥 ERRO:", msg, file=sys.stderr)
    if exc:
        import traceback; traceback.print_exc()
    if SOFT_FAIL:
        print("⚠️ SOFT_FAIL=1 — finalizando com código 0 para não quebrar o workflow.")
        sys.exit(0)
    sys.exit(code)

missing = [k for k,v in {
    "SHEET_ID": SHEET_ID,
    "TELEGRAM_TOKEN": TELEGRAM_TOKEN,
    "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID
}.items() if not v]
if missing:
    die(f"Variáveis ausentes: {', '.join(missing)}")

# -------------------------
# Credenciais GCP
# -------------------------
try:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        creds = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
        )
    else:
        raw = os.getenv("GCP_SERVICE_ACCOUNT") or os.getenv("GCP_SERVICE_ACCOUNT_JSON") or ""
        if not raw.strip():
            die("Faltam credenciais GCP: defina GOOGLE_APPLICATION_CREDENTIALS ou GCP_SERVICE_ACCOUNT(_JSON).")
        sa_info = json.loads(raw)
        creds = Credentials.from_service_account_info(
            sa_info,
            scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
        )
    gc = gspread.authorize(creds)
except Exception as e:
    die(f"Falha ao autorizar GCP: {e}", exc=e)

# open sheet
try:
    try:
        sh = gc.open_by_key(SHEET_ID)
    except Exception:
        sh = gc.open_by_url(SHEET_ID)
except Exception as e:
    die(f"Não consegui abrir a planilha com SHEET_ID='{SHEET_ID}': {e}", exc=e)

print(f"✅ Conectado no Sheets: {sh.title}")
abas = {w.title: w for w in sh.worksheets()}

# -------------------------
# Utils
# -------------------------
def now_br(): return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")
def today_local_date(): return datetime.now(pytz.timezone(TZ)).date()

def parse_dt_cell(x):
    s = (str(x or "")).strip()
    for fmt in ("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y","%Y/%m/%d"):
        try: return datetime.strptime(s, fmt).date()
        except Exception: pass
    return None

def classificar_relative(dias, media):
    if dias <= media: return ("🟢 Em dia", "Em dia")
    elif dias <= media * REL_MULT: return ("🟠 Pouco atrasado", "Pouco atrasado")
    else: return ("🔴 Muito atrasado", "Muito atrasado")

def _norm(s):
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def _normalize_header(s):
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def _pick_col(cols, candidates):
    norm_map = {_normalize_header(c): c for c in cols if isinstance(c, str)}
    for cand in candidates:
        c = norm_map.get(_normalize_header(cand))
        if c: return c
    return None

def tg_send(text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text,
                   "parse_mode": "HTML", "disable_web_page_preview": True}
        r = requests.post(url, json=payload, timeout=30)
        print("↪ Telegram:", r.status_code, r.text[:160])
        if not r.ok and not SAFE_TELEGRAM:
            raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text}")
    except Exception as e:
        if SAFE_TELEGRAM:
            print("⚠️ Telegram sendMessage falhou, ignorado (SAFE_TELEGRAM=1):", e)
        else:
            raise

def tg_send_photo(photo_url, caption):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url,
                                     "caption": caption, "parse_mode": "HTML"}, timeout=30)
        print("↪ Telegram photo:", r.status_code, r.text[:160])
        if not r.ok:
            raise RuntimeError(f"sendPhoto {r.status_code}: {r.text}")
    except Exception as e:
        print("⚠️ Falha sendPhoto:", e)
        tg_send(caption)

# -------------------------
# Ler BASE (auto)
# -------------------------
ws_base = abas.get(ABA_BASE)
df_base = None
if not ws_base:
    print(f"ℹ️ Aba '{ABA_BASE}' não encontrada. Tentando autodetectar…")
    for w in sh.worksheets():
        df_try = get_as_dataframe(w, evaluate_formulas=True, dtype=str).fillna("")
        if df_try.empty or df_try.columns.size == 0: continue
        cols = list(df_try.columns)
        col_cliente = _pick_col(cols, ["Cliente","cliente","nome","nome cliente","nome_cliente","cliente_nome"])
        col_data    = _pick_col(cols, ["Data","data","dt","data visita","ultima visita","última visita","dia"])
        if col_cliente and col_data:
            ws_base = w
            df_base = df_try.rename(columns={col_cliente:"Cliente", col_data:"Data"})
            print(f"✅ Base autodetectada: {w.title} (cliente={col_cliente} | data={col_data})")
            break
    if not ws_base:
        die(f"Não achei aba com colunas equivalentes a 'Cliente' e 'Data'. Abas: {list(abas.keys())}")
else:
    df_base = get_as_dataframe(ws_base, evaluate_formulas=True, dtype=str).fillna("")
    if "Cliente" not in df_base.columns or "Data" not in df_base.columns:
        cols = list(df_base.columns)
        col_cliente = _pick_col(cols, ["Cliente","cliente","nome","nome cliente","nome_cliente","cliente_nome"])
        col_data    = _pick_col(cols, ["Data","data","dt","data visita","ultima visita","última visita","dia"])
        if not (col_cliente and col_data):
            die(f"Aba '{ws_base.title}' sem colunas equivalentes a 'Cliente' e 'Data'. Colunas: {cols}")
        df_base = df_base.rename(columns={col_cliente:"Cliente", col_data:"Data"})

print(f"🗂️ Usando aba base: {ws_base.title}")

# -------------------------
# Mapa de fotos (opcional)
# -------------------------
foto_map = {}
if STATUS_ABA in abas:
    try:
        ws_status = abas[STATUS_ABA]
        df_status = get_as_dataframe(ws_status, evaluate_formulas=True, dtype=str).fillna("")
        cols_lower = {c.strip().lower(): c for c in df_status.columns if isinstance(c, str)}
        cand = FOTO_COL_ENV.lower() if FOTO_COL_ENV else ""
        foto_candidates = [cand] if cand else ["foto","imagem","link_foto","url_foto","foto_link","link","image"]
        foto_col = next((cols_lower[x] for x in foto_candidates if x in cols_lower), None)
        cli_col  = next((cols_lower[x] for x in ["cliente","nome","nome_cliente"] if x in cols_lower), None)
        if foto_col and cli_col:
            tmp = df_status[[cli_col, foto_col]].copy()
            tmp.columns = ["Cliente","Foto"]
            tmp["k"] = tmp["Cliente"].astype(str).map(_norm)
            foto_map = {r["k"]: str(r["Foto"]).strip() for _, r in tmp.iterrows() if str(r["Foto"]).strip()}
            print(f"🖼️ Fotos encontradas: {len(foto_map)}")
        else:
            print(f"ℹ️ STATUS_ABA '{STATUS_ABA}' sem colunas de foto/cliente detectáveis.")
    except Exception as e:
        print("⚠️ Erro lendo STATUS_ABA:", e)
else:
    print(f"ℹ️ STATUS_ABA '{STATUS_ABA}' inexistente — seguindo sem fotos.")

# -------------------------
# Preparar base (1 visita/dia)
# -------------------------
df = df_base.copy()
df["__dt"] = df["Data"].apply(parse_dt_cell)
df = df.dropna(subset=["__dt"])
if df.empty:
    print("⚠️ Base vazia após parse de datas. Encerrando com sucesso.")
    sys.exit(0)

df["__dt"] = pd.to_datetime(df["__dt"])
df["_date_only"] = df["__dt"].dt.date
df["_cliente_norm"] = df["Cliente"].astype(str).str.strip()
df = df[df["_cliente_norm"] != ""]

rows = []
today_ts = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None)

for cliente, g in df.groupby("_cliente_norm"):
    dias_unicos = sorted(set(g["_date_only"].tolist()))
    if len(dias_unicos) < 2: continue
    dias_ts = [pd.to_datetime(d) for d in dias_unicos]
    diffs = [(dias_ts[i] - dias_ts[i-1]).days for i in range(1, len(dias_ts))]
    diffs_pos = [d for d in diffs if d > 0]
    if not diffs_pos: continue
    media = sum(diffs_pos) / len(diffs_pos)
    dias_desde_ultima = (today_ts - dias_ts[-1]).days
    label_emoji, label = classificar_relative(dias_desde_ultima, media)
    rows.append({
        "Cliente": cliente,
        "ultima_visita": dias_ts[-1],
        "media_dias": round(media, 1),
        "dias_desde_ultima": int(dias_desde_ultima),
        "status_atual": label,
        "status_emoji": label_emoji,
        "visitas_total": len(dias_unicos)
    })

ultimo = pd.DataFrame(rows)
print(f"📦 Clientes com histórico válido (≥2 dias distintos): {len(ultimo)}")
if ultimo.empty: sys.exit(0)
ultimo_by_cli = {r.Cliente.strip().lower(): r for r in ultimo.itertuples(index=False)}

# -------------------------
# Cache
# -------------------------
def ensure_cache():
    try:
        return sh.worksheet(ABA_STATUS_CACHE)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(ABA_STATUS_CACHE, rows=2, cols=6) if ALLOW_WRITE else sh.worksheet(ABA_BASE)
        if ALLOW_WRITE:
            set_with_dataframe(ws, pd.DataFrame(columns=[
                "Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache","visitas_total_cache"
            ]))
        return ws

ws_cache = ensure_cache()
df_cache = get_as_dataframe(ws_cache, evaluate_formulas=True, dtype=str).fillna("")
if df_cache.empty or "Cliente" not in df_cache.columns:
    df_cache = pd.DataFrame(columns=[
        "Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache","visitas_total_cache"
    ])

def parse_cache_dt(x):
    d = parse_dt_cell(x)
    return None if d is None else pd.to_datetime(d)

for c in ["Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache","visitas_total_cache"]:
    if c not in df_cache.columns: df_cache[c] = ""
df_cache = df_cache[["Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache","visitas_total_cache"]].copy()
df_cache["ultima_visita_cache_parsed"] = df_cache["ultima_visita_cache"].apply(parse_cache_dt)
cache_by_cli = {str(r["Cliente"]).strip().lower(): r for _, r in df_cache.iterrows()}

# -------------------------
# Fila de transições
# -------------------------
def ensure_transicoes():
    try:
        return sh.worksheet(ABA_TRANSICOES)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(ABA_TRANSICOES, rows=2, cols=8) if ALLOW_WRITE else sh.worksheet(ABA_BASE)
        if ALLOW_WRITE:
            set_with_dataframe(ws, pd.DataFrame(columns=[
                "cliente","cliente_norm","status_novo","dt_evento","ultima_visita_ref","anunciado","anunciado_em","observacao"
            ]))
        return ws

ws_trans = ensure_transicoes()
df_trans = get_as_dataframe(ws_trans, evaluate_formulas=True, dtype=str).fillna("")
if df_trans.empty or "cliente_norm" not in df_trans.columns:
    df_trans = pd.DataFrame(columns=[
        "cliente","cliente_norm","status_novo","dt_evento","ultima_visita_ref","anunciado","anunciado_em","observacao"
    ])
for col in ["anunciado","anunciado_em","observacao","ultima_visita_ref","dt_evento"]:
    if col not in df_trans.columns: df_trans[col] = ""
df_trans["_cliente_norm"] = df_trans["cliente_norm"].astype(str)
df_trans["_status_novo"]  = df_trans["status_novo"].astype(str)
df_trans["_ultima_ref"]   = df_trans["ultima_visita_ref"].astype(str)

def upsert_transicao(nome, status_novo, ultima_ref_date):
    cliente_norm = _norm(nome)
    chave_ref = (df_trans["_cliente_norm"] == cliente_norm) & \
                (df_trans["_status_novo"]  == status_novo) & \
                (df_trans["_ultima_ref"]   == (ultima_ref_date or ""))
    existe_pendente = (df_trans[chave_ref & (df_trans["anunciado"].astype(str).str.strip() == "")].shape[0] > 0)
    if existe_pendente: return
    novo = {
        "cliente": nome,
        "cliente_norm": cliente_norm,
        "status_novo": status_novo,
        "dt_evento": today_local_date().strftime("%Y-%m-%d"),
        "ultima_visita_ref": (ultima_ref_date or ""),
        "anunciado": "",
        "anunciado_em": "",
        "observacao": ""
    }
    global df_trans
    df_trans = pd.concat([df_trans, pd.DataFrame([novo])], ignore_index=True)

# detectar mudanças
for key, row in ultimo_by_cli.items():
    nome = row.Cliente
    status = row.status_atual
    ultima = pd.to_datetime(row.ultima_visita).strftime("%Y-%m-%d")
    cached = cache_by_cli.get(key)
    cached_status = (cached["status_cache"] if cached is not None else "")
    if cached is not None and status != cached_status and status in ("Pouco atrasado", "Muito atrasado"):
        upsert_transicao(nome, status, ultima)

# persistir fila (se mudou)
if ALLOW_WRITE:
    try:
        ws_trans.clear()
        set_with_dataframe(ws_trans, df_trans)
    except Exception as e:
        die(f"Falha escrevendo fila '{ABA_TRANSICOES}': {e}", exc=e)

# -------------------------
# Disparo às 08:00 (cards)
# -------------------------
def send_cards_from_queue():
    pend = df_trans[df_trans["anunciado"].astype(str).str.strip() == ""].copy()
    if pend.empty:
        print("ℹ️ Sem pendências para anunciar.")
        return
    severidade = {"Muito atrasado": 0, "Pouco atrasado": 1}
    pend["sev"] = pend["status_novo"].map(severidade).fillna(2)
    pend = pend.sort_values(["sev","cliente"], kind="stable")

    for r in pend.itertuples(index=False):
        nome = str(r.cliente).strip()
        status = str(r.status_novo).strip()
        ultima_ref = (str(r.ultima_visita_ref).strip() or "")

        key = nome.strip().lower()
        row_atual = ultimo_by_cli.get(key)
        if not row_atual:
            caption = ( "📣 <b>Atualização de Frequência</b>\n"
                        f"👤 Cliente: <b>{html.escape(nome)}</b>\n"
                        f"📌 Status: <b>{html.escape(status)}</b>\n"
                        f"🗓️ Último: <b>{(ultima_ref or '-')}</b>" )
        else:
            ultima_str = pd.to_datetime(row_atual.ultima_visita).strftime("%d/%m/%Y")
            media_str = f"{float(row_atual.media_dias):.1f}".replace(".", ",")
            dias_int = int(row_atual.dias_desde_ultima)
            emoji = "🟠" if status == "Pouco atrasado" else ("🔴" if status == "Muito atrasado" else "")
            caption = ( f"{emoji} <b>Atualização de Frequência</b>\n"
                        f"👤 Cliente: <b>{html.escape(nome)}</b>\n"
                        f"{emoji} Status: <b>{html.escape(status)}</b>\n"
                        f"🗓️ Último: <b>{ultima_str}</b>\n"
                        f"🔁 Média: <b>{media_str} dias</b>\n"
                        f"⏳ Sem vir há: <b>{dias_int} dias</b>" )

        foto = foto_map.get(_norm(nome))
        if foto: tg_send_photo(foto, caption)
        else:    tg_send(caption)

    if ALLOW_WRITE:
        idx = pend.index
        df_trans.loc[idx, "anunciado"] = "1"
        df_trans.loc[idx, "anunciado_em"] = now_br()
        ws_trans.clear()
        set_with_dataframe(ws_trans, df_trans)

# -------------------------
# Atualizar cache
# -------------------------
def update_cache_state():
    out = ultimo[["Cliente","ultima_visita","status_atual","media_dias","visitas_total"]].copy()
    out["ultima_visita"] = pd.to_datetime(out["ultima_visita"]).dt.strftime("%Y-%m-%d")
    out.rename(columns={
        "ultima_visita":"ultima_visita_cache",
        "status_atual":"status_cache",
        "media_dias":"media_cache",
        "visitas_total":"visitas_total_cache"
    }, inplace=True)
    out["last_notified_at"] = now_br()
    if ALLOW_WRITE:
        ws_cache.clear()
        set_with_dataframe(ws_cache, out)

# -------------------------
# Modo individual (CLIENTE=…)
# -------------------------
CLIENTE = os.getenv("CLIENTE") or os.getenv("INPUT_CLIENTE")
if CLIENTE:
    alvo = _norm(CLIENTE)
    ultimo["_norm"] = ultimo["Cliente"].apply(_norm)
    sel = ultimo[ultimo["_norm"] == alvo]
    if sel.empty: sel = ultimo[ultimo["_norm"].str.contains(alvo, na=False)]
    if sel.empty:
        tg_send(f"⚠️ Cliente '{html.escape(CLIENTE)}' não encontrado com histórico suficiente.")
        sys.exit(0)
    row = sel.sort_values("ultima_visita", ascending=False).iloc[0]
    ultima_str = pd.to_datetime(row["ultima_visita"]).strftime("%d/%m/%Y")
    media_str = f"{row['media_dias']:.1f}".replace(".", ",")
    dias_int = int(row["dias_desde_ultima"])
    caption = ( "⏰ <b>Alerta de Frequência</b>\n"
                f"👤 Cliente: <b>{html.escape(row['Cliente'])}</b>\n"
                f"{row.get('status_emoji','')} Status: <b>{html.escape(row.get('status_atual',''))}</b>\n"
                f"🗓️ Último: <b>{ultima_str}</b>\n"
                f"🔁 Média: <b>{media_str} dias</b>\n"
                f"⏳ Sem vir há: <b>{dias_int} dias</b>" )
    foto = foto_map.get(_norm(row["Cliente"]))
    if foto: tg_send_photo(foto, caption)
    else:    tg_send(caption)
    print("✅ Alerta individual enviado.")
    sys.exit(0)

# -------------------------
# Entrypoint
# -------------------------
if __name__ == "__main__":
    try:
        print("▶️ Iniciando…")
        print(f"• TZ={TZ} | Base={ABA_BASE} | Cache={ABA_STATUS_CACHE} | Fila={ABA_TRANSICOES} "
              f"| ALLOW_WRITE={ALLOW_WRITE} | SAFE_TELEGRAM={SAFE_TELEGRAM} | Worksheet={ws_base.title}")
        if SEND_AT_8_CARDS: send_cards_from_queue()
        update_cache_state()
        print("✅ Execução concluída.")
    except Exception as e:
        die(e, exc=e)

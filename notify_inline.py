# notify_inline.py — Lógica por MÉDIA + bootstrap do cache + feedback com tolerância
import os, sys, json, pandas as pd, requests, gspread, pytz
from datetime import datetime
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# =========================
# PARÂMETROS
# =========================
TZ = "America/Sao_Paulo"
REL_MULT = 1.5                       # Pouco atrasado = dias <= média * REL_MULT; Muito = acima disso
GRACE_DAYS = int(os.getenv("GRACE_DAYS", 3))  # tolerância p/ feedback (dias após a visita)
ABA_BASE = "Base de Dados"           # Colunas: Cliente, Data
ABA_STATUS_CACHE = "status_cache"    # Criada/atualizada por este script
ENVIAR_ALERTA_QUANDO_VOLTAR_EM_DIA = True

# =========================
# UTILS
# =========================
def log(msg): print(msg, flush=True)

def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def fail(msg):
    log(f"ERRO: {msg}")
    sys.exit(1)

def parse_dt(x):
    x = (x or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(x, fmt).date()
        except Exception:
            pass
    return None

def classificar_relative(dias: int, media: float):
    # 🟢 Em dia → dias ≤ média
    # 🟠 Pouco atrasado → dias ≤ média × REL_MULT
    # 🔴 Muito atrasado → dias > média × REL_MULT
    if dias <= media:
        return ("🟢 Em dia", "Em dia")
    elif dias <= media * REL_MULT:
        return ("🟠 Pouco atrasado", "Pouco atrasado")
    else:
        return ("🔴 Muito atrasado", "Muito atrasado")

def frase_retomou(ultima_dt, today):
    delta = (today - ultima_dt).days
    if delta <= 0:
        return "Retomou hoje!"
    if delta == 1:
        return "Retomou ontem!"
    return f"Retomou em {ultima_dt.strftime('%d/%m')} (há {delta} dias)."

def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text}")

def chunk_and_send(token, chat_id, header, lines, max_lines=60):
    if not lines:
        return
    for i in range(0, len(lines), max_lines):
        body = header + "\n" + "\n".join(lines[i:i+max_lines])
        send_telegram(token, chat_id, body)

# =========================
# ENVS / CREDS
# =========================
need = ["SHEET_ID", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
missing = [k for k in need if not os.getenv(k)]
if missing:
    fail(f"Variáveis ausentes: {', '.join(missing)}")

SHEET_ID = os.getenv("SHEET_ID")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

try:
    with open("sa.json", "r", encoding="utf-8") as f:
        sa_info = json.load(f)
except Exception as e:
    fail(f"Falha lendo sa.json: {e}")

# =========================
# CONECTAR SHEETS
# =========================
scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
log(f"[OK] Conectado no Sheets: {sh.title}")

abas = {w.title: w for w in sh.worksheets()}
if ABA_BASE not in abas:
    fail(f"Aba '{ABA_BASE}' não encontrada.")
ws_base = abas[ABA_BASE]

df_base = get_as_dataframe(ws_base, evaluate_formulas=True, dtype=str).fillna("")
if "Cliente" not in df_base.columns or "Data" not in df_base.columns:
    fail("Faltam colunas 'Cliente' e/ou 'Data' na Base de Dados.")

# =========================
# PROCESSAR BASE (datas, média por cliente, status)
# =========================
df = df_base.copy()
df["__dt"] = df["Data"].apply(parse_dt)
df = df.dropna(subset=["__dt"])
df["__dt"] = pd.to_datetime(df["__dt"])

if df.empty:
    log("[WARN] Base vazia após parse de datas.")
    sys.exit(0)

today_sp = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None)

rows = []
for cliente, g in df.groupby("Cliente"):
    datas = g.sort_values("__dt")["__dt"].tolist()
    if len(datas) < 2:
        # sem histórico suficiente pra média; pula nas notificações
        continue
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media = sum(diffs) / len(diffs)
    ultima = datas[-1]
    dias = int((today_sp - ultima).days)
    label_emoji, label = classificar_relative(dias, media)
    rows.append({
        "Cliente": cliente,
        "ultima_visita": ultima,
        "media_dias": round(media, 1),
        "dias_desde_ultima": dias,
        "status_atual": label,
        "status_emoji": label_emoji
    })

ultimo = pd.DataFrame(rows)
if ultimo.empty:
    log("[WARN] Nenhum cliente com histórico suficiente (≥2 visitas).")
    sys.exit(0)

# =========================
# CACHE
# =========================
def ensure_cache():
    try:
        return sh.worksheet(ABA_STATUS_CACHE)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(ABA_STATUS_CACHE, rows=2, cols=5)
        set_with_dataframe(ws, pd.DataFrame(columns=[
            "Cliente", "ultima_visita_cache", "status_cache", "last_notified_at", "media_cache"
        ]))
        return ws

ws_cache = ensure_cache()
df_cache = get_as_dataframe(ws_cache, evaluate_formulas=True, dtype=str).fillna("")
is_bootstrap = df_cache.empty or "Cliente" not in df_cache.columns

def write_full_cache():
    out = ultimo[["Cliente", "ultima_visita", "status_atual", "media_dias"]].copy()
    out["ultima_visita"] = pd.to_datetime(out["ultima_visita"]).dt.strftime("%Y-%m-%d")
    out.rename(columns={
        "ultima_visita": "ultima_visita_cache",
        "status_atual": "status_cache",
        "media_dias": "media_cache"
    }, inplace=True)
    out["last_notified_at"] = now_br()
    ws_cache.clear()
    set_with_dataframe(ws_cache, out)

# =========================
# DIÁRIO (09h SP) — heurística
# =========================
hour_now_utc = datetime.utcnow().hour
is_daily_window = hour_now_utc in (11, 12, 13)

def daily_summary_and_lists():
    total = len(ultimo)
    em_dia = (ultimo["status_atual"] == "Em dia").sum()
    pouco  = (ultimo["status_atual"] == "Pouco atrasado").sum()
    muito  = (ultimo["status_atual"] == "Muito atrasado").sum()

    header = (
        f"📊 Relatório de Frequência — Salão JP\n"
        f"Data/hora: {now_br()}\n\n"
        f"👥 Ativos (c/ média): {total}\n"
        f"🟢 Em dia: {em_dia}\n"
        f"🟠 Pouco atrasado: {pouco}\n"
        f"🔴 Muito atrasado: {muito}"
    )
    send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, header)

    def lista(bucket_name, emoji):
        sub = ultimo.loc[ultimo["status_atual"] == bucket_name, ["Cliente", "media_dias", "dias_desde_ultima"]]
        if sub.empty:
            return
        lines = [
            f"- {r.Cliente} (média {r.media_dias}d, {int(r.dias_desde_ultima)}d sem vir)"
            for r in sub.itertuples(index=False)
        ]
        chunk_and_send(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, f"{emoji} {bucket_name}", lines, max_lines=60)

    lista("Pouco atrasado", "🟠")
    lista("Muito atrasado", "🔴")

# =========================
# BOOTSTRAP
# =========================
if is_bootstrap:
    log("[INFO] Bootstrap do cache: preenchendo status_cache pela primeira vez.")
    write_full_cache()
    if is_daily_window:
        try:
            daily_summary_and_lists()
        except Exception as e:
            log(f"[WARN] Falha ao enviar resumo no bootstrap: {e}")
    log("[OK] Bootstrap concluído. Saindo sem alertas/feedback.")
    sys.exit(0)

# =========================
# MUDANÇAS + FEEDBACK (com tolerância)
# =========================
df_cache = df_cache[["Cliente", "ultima_visita_cache", "status_cache", "last_notified_at", "media_cache"]].copy()

def parse_cache_dt(x):
    d = parse_dt(x)
    return None if d is None else pd.to_datetime(d)

df_cache["ultima_visita_cache_parsed"] = df_cache["ultima_visita_cache"].apply(parse_cache_dt)
cache_by_cli = {str(r["Cliente"]).strip().lower(): r for _, r in df_cache.iterrows()}
ultimo_by_cli = {r.Cliente.strip().lower(): r for r in ultimo.itertuples(index=False)}

transicoes, feedbacks = [], []

if is_daily_window:
    try:
        daily_summary_and_lists()
    except Exception as e:
        log(f"[WARN] Falha no resumo diário: {e}")

for key, row in ultimo_by_cli.items():
    nome = row.Cliente
    dias = int(row.dias_desde_ultima)
    media = float(row.media_dias)
    status = row.status_atual
    ultima = pd.to_datetime(row.ultima_visita)

    cached = cache_by_cli.get(key)
    if cached is None:
        continue

    cached_status = cached["status_cache"]
    cached_dt = cached["ultima_visita_cache_parsed"]

    # Nova visita = data maior que a do cache E dentro da janela de tolerância
    dentro_janela = 0 <= (today_sp.date() - ultima.date()).days <= GRACE_DAYS
    new_visit = (cached_dt is not None) and (ultima > cached_dt) and dentro_janela

    if new_visit:
        retomou = frase_retomou(ultima, today_sp)
        if status == "Em dia":
            text = (f"✅ Cliente *{nome}* está em dia.\n"
                    f"Última visita: *{dias} dias atrás* (média ~*{media}* dias).\n"
                    f"{retomou}")
        elif status == "Pouco atrasado":
            text = (f"📣 Feedback de Frequência\n"
                    f"*{nome}* estava *pouco atrasado*: *{dias} dias* (média ~*{media}*).\n"
                    f"{retomou} Sugira próximo em ~{int(round(media))} dias.")
        else:
            text = (f"📣 Feedback de Frequência\n"
                    f"*{nome}* estava *muito atrasado*: *{dias} dias* (média ~*{media}*).\n"
                    f"{retomou} Combine reforço e lembrete em ~{int(round(media))} dias.")
        feedbacks.append(text)

    # Mudança de status
    if status != cached_status:
        if status in ("Pouco atrasado", "Muito atrasado") or (ENVIAR_ALERTA_QUANDO_VOLTAR_EM_DIA and status == "Em dia"):
            if status == "Pouco atrasado":
                t = (f"📣 Atualização de Frequência\n"
                     f"*{nome}* entrou em *Pouco atrasado*.\n"
                     f"Última visita: *{dias}* (média ~*{media}*).")
            elif status == "Muito atrasado":
                t = (f"📣 Atualização de Frequência\n"
                     f"*{nome}* entrou em *Muito atrasado*.\n"
                     f"Última visita: *{dias}* (média ~*{media}*).")
            else:
                t = (f"✅ Atualização de Frequência\n"
                     f"*{nome}* voltou para *Em dia*.\n"
                     f"Última visita: *{dias}* (média ~*{media}*).")
            transicoes.append(t)

# Enviar mensagens (com limites)
for txt in transicoes[:30]:
    try:
        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, txt)
    except Exception as e:
        log(f"[WARN] Falha ao enviar transição: {e}")

for txt in feedbacks[:30]:
    try:
        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, txt)
    except Exception as e:
        log(f"[WARN] Falha ao enviar feedback: {e}")

# Atualizar cache
write_full_cache()
log("[OK] Execução concluída (média × 1.5, bootstrap e tolerância para feedback).")

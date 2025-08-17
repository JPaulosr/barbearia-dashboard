# notify_inline.py — Classificação por MÉDIA (relative)
import os, sys, json, pandas as pd, requests, gspread, pytz
from datetime import datetime
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# =========================
# PARÂMETROS
# =========================
TZ = "America/Sao_Paulo"
REL_MULT = 1.5  # Pouco atrasado = dias <= média * REL_MULT; Muito = acima disso

ABA_BASE = "Base de Dados"          # Colunas obrigatórias: Cliente, Data
ABA_STATUS_CACHE = "status_cache"   # Cache criado/atualizado por este script
ENVIAR_ALERTA_QUANDO_VOLTAR_EM_DIA = True

# =========================
# UTILS
# =========================
def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def fail(msg):
    print("ERRO:", msg, file=sys.stderr)
    sys.exit(1)

def parse_dt(x):
    x = (x or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(x, fmt).date()
        except Exception:
            pass
    return None

def classificar_relative(dias_desde_ultimo: int, media: float):
    # 🟢 Em dia → dias ≤ média
    # 🟠 Pouco atrasado → dias ≤ média × REL_MULT
    # 🔴 Muito atrasado → dias > média × REL_MULT
    if dias_desde_ultimo <= media:
        return ("🟢 Em dia", "Em dia")
    elif dias_desde_ultimo <= media * REL_MULT:
        return ("🟠 Pouco atrasado", "Pouco atrasado")
    else:
        return ("🔴 Muito atrasado", "Muito atrasado")

def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=30)
    if not r.ok:
        raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text}")

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
scopes = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
print(f"[OK] Conectado no Sheets: {sh.title}")

abas = {w.title: w for w in sh.worksheets()}
if ABA_BASE not in abas:
    fail(f"Aba '{ABA_BASE}' não encontrada.")

ws_base = abas[ABA_BASE]
df_base = get_as_dataframe(ws_base, evaluate_formulas=True, dtype=str).fillna("")
if "Cliente" not in df_base.columns or "Data" not in df_base.columns:
    fail("Colunas obrigatórias ausentes na 'Base de Dados' (Cliente, Data).")

# =========================
# ÚLTIMA VISITA, MÉDIA POR CLIENTE e STATUS (por MÉDIA)
# =========================
df = df_base.copy()
df["__dt"] = df["Data"].apply(parse_dt)
df = df.dropna(subset=["__dt"])
df["__dt"] = pd.to_datetime(df["__dt"])

if df.empty:
    print("[WARN] Base vazia após parse de datas.")
    sys.exit(0)

# Agrupar por Cliente e calcular:
# - última visita
# - média de intervalo (em dias) entre visitas
# - dias desde a última visita
rows = []
today = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None)
for cliente, g in df.groupby("Cliente"):
    datas = g.sort_values("__dt")["__dt"].tolist()
    if len(datas) < 2:
        # sem histórico suficiente pra calcular média → ignora nas notificações
        continue
    # diferenças sucessivas (em dias)
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media = sum(diffs) / len(diffs)
    ultima = datas[-1].to_pydatetime()
    dias = (today - datas[-1]).days
    label_emoji, label = classificar_relative(dias, media)
    rows.append({
        "Cliente": cliente,
        "ultima_visita": datas[-1],
        "media_dias": round(media, 1),
        "dias_desde_ultima": dias,
        "status_atual": label,
        "status_emoji": label_emoji
    })

ultimo = pd.DataFrame(rows)
if ultimo.empty:
    print("[WARN] Nenhum cliente com histórico suficiente (≥2 visitas).")
    sys.exit(0)

# =========================
# CACHE (status_cache)
# =========================
def ensure_cache():
    try:
        return sh.worksheet(ABA_STATUS_CACHE)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(ABA_STATUS_CACHE, rows=2, cols=5)
        set_with_dataframe(ws, pd.DataFrame(columns=[
            "Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache"
        ]))
        return ws

ws_cache = ensure_cache()
df_cache = get_as_dataframe(ws_cache, evaluate_formulas=True, dtype=str).fillna("")
if df_cache.empty or "Cliente" not in df_cache.columns:
    df_cache = pd.DataFrame(columns=["Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache"])

# normalizar cache
def parse_cache_dt(x):
    d = parse_dt(x)
    return None if d is None else pd.to_datetime(d)

df_cache = df_cache[["Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache"]].copy()
df_cache["ultima_visita_cache_parsed"] = df_cache["ultima_visita_cache"].apply(parse_cache_dt)
cache_by_cli = {str(r["Cliente"]).strip().lower(): r for _, r in df_cache.iterrows()}

# =========================
# MENSAGENS
# =========================
def daily_summary_and_lists():
    total = len(ultimo)
    em_dia = (ultimo["status_atual"]=="Em dia").sum()
    pouco = (ultimo["status_atual"]=="Pouco atrasado").sum()
    muito = (ultimo["status_atual"]=="Muito atrasado").sum()

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
        # mostra nome + (média / dias desde)
        subset = ultimo.loc[ultimo["status_atual"]==bucket_name, ["Cliente","media_dias","dias_desde_ultima"]]
        if subset.empty:
            return
        linhas = "\n".join(
            f"- {r.Cliente} (média {r.media_dias}d, {int(r.dias_desde_ultima)}d sem vir)"
            for r in subset.itertuples(index=False)
        )
        body = f"{emoji} {bucket_name}\n{linhas}"
        # limita tamanho: Telegram ~4096 chars. Se ficar muito grande, envia em blocos.
        if len(body) <= 3500:
            send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, body)
        else:
            # divide por ~60 nomes por mensagem
            nomes = linhas.split("\n")
            for i in range(0, len(nomes), 60):
                chunk = "\n".join(nomes[i:i+60])
                send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, f"{emoji} {bucket_name}\n{chunk}")

    lista("Pouco atrasado","🟠")
    lista("Muito atrasado","🔴")

def changes_and_feedback():
    transicoes = []
    feedbacks = []

    # index pra busca rápida
    ultimo_by_cli = {r.Cliente.strip().lower(): r for r in ultimo.itertuples(index=False)}
    for key, row in ultimo_by_cli.items():
        nome = row.Cliente
        dias = int(row.dias_desde_ultima)
        media = float(row.media_dias)
        status = row.status_atual
        ultima = row.ultima_visita

        cached = cache_by_cli.get(key)
        cached_status = (cached["status_cache"] if cached is not None else "")
        cached_dt = cached["ultima_visita_cache_parsed"] if cached is not None else None

        # Nova visita? (última > cache)
        new_visit = False
        if cached_dt is None:
            new_visit = True
        else:
            try:
                new_visit = pd.to_datetime(ultima) > cached_dt
            except Exception:
                new_visit = True

        # FEEDBACK: quando registrar um atendimento novo, manda contexto por média
        if new_visit:
            if status == "Em dia":
                text = (f"✅ Cliente *{nome}* está em dia.\n"
                        f"Última visita: *{dias} dias atrás* (média ~*{media}* dias).")
            elif status == "Pouco atrasado":
                text = (f"📣 Feedback de Frequência\n"
                        f"*{nome}* estava *pouco atrasado*: *{dias} dias* (média ~*{media}*).\n"
                        f"➡️ Retomou hoje! Sugira próximo em ~{int(round(media))} dias.")
            else:
                text = (f"📣 Feedback de Frequência\n"
                        f"*{nome}* estava *muito atrasado*: *{dias} dias* (média ~*{media}*).\n"
                        f"➡️ Retomou hoje! Combine reforço e lembrete em ~{int(round(media))} dias.")
            feedbacks.append(text)

        # Mudança de status?
        if cached is not None and status != cached_status:
            if status in ("Pouco atrasado","Muito atrasado") or (ENVIAR_ALERTA_QUANDO_VOLTAR_EM_DIA and status=="Em dia"):
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

    # Enviar (limite pra não floodar)
    for txt in transicoes[:30]:
        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, txt)
    for txt in feedbacks[:30]:
        send_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, txt)

    # Atualizar cache
    out = ultimo[["Cliente","ultima_visita","status_atual","media_dias"]].copy()
    out["ultima_visita"] = pd.to_datetime(out["ultima_visita"]).dt.strftime("%Y-%m-%d")
    out.rename(columns={
        "ultima_visita":"ultima_visita_cache",
        "status_atual":"status_cache",
        "media_dias":"media_cache"
    }, inplace=True)
    out["last_notified_at"] = now_br()

    ws = ws_cache
    ws.clear()
    set_with_dataframe(ws, out)

# =========================
# ENTRYPOINT
# =========================
# Heurística pra decidir o "daily": 12 UTC ~ 09h SP (tolerância +-1h)
hour_now_utc = datetime.utcnow().hour
is_daily = hour_now_utc in (11, 12, 13)

try:
    if is_daily:
        daily_summary_and_lists()
    changes_and_feedback()
    print("[OK] Execução concluída (lógica por MÉDIA).")
except Exception as e:
    fail(e)

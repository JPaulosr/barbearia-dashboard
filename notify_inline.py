# notify_inline.py — Frequência por MÉDIA (relative) + cache + alertas

import os
import sys
import json
import html
import requests
import gspread
import pytz
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# =========================
# PARÂMETROS
# =========================
TZ = os.getenv("TIMEZONE", "America/Sao_Paulo")
REL_MULT = 1.5                       # Pouco atrasado = dias <= média * REL_MULT; Muito = acima disso
ABA_BASE = os.getenv("BASE_ABA", "Base de Dados")
ABA_STATUS_CACHE = "status_cache"    # cache criado/atualizado por este script
ENVIAR_ALERTA_QUANDO_VOLTAR_EM_DIA = True

# =========================
# ENVS / CREDS (GitHub Secrets)
# =========================
SHEET_ID = (os.getenv("SHEET_ID") or "").strip()
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
GCP_SERVICE_ACCOUNT_JSON = (os.getenv("GCP_SERVICE_ACCOUNT_JSON") or "").strip()

def fail(msg):
    print(f"💥 {msg}", file=sys.stderr)
    sys.exit(1)

need = ["SHEET_ID", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "GCP_SERVICE_ACCOUNT_JSON"]
missing = [k for k in need if not os.getenv(k)]
if missing:
    fail(f"Variáveis ausentes: {', '.join(missing)}")

# =========================
# HELPERS
# =========================
def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def parse_dt_cell(x):
    s = (str(x or "")).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    return None

def classificar_relative(dias, media):
    if dias <= media:
        return ("🟢 Em dia", "Em dia")
    elif dias <= media * REL_MULT:
        return ("🟠 Pouco atrasado", "Pouco atrasado")
    else:
        return ("🔴 Muito atrasado", "Muito atrasado")

def tg_send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    r = requests.post(url, json=payload, timeout=30)
    print("↪ Telegram:", r.status_code, r.text[:200])
    if not r.ok:
        raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text}")

# =========================
# CONECTAR SHEETS
# =========================
try:
    sa_info = json.loads(GCP_SERVICE_ACCOUNT_JSON)
except Exception as e:
    fail(f"GCP_SERVICE_ACCOUNT_JSON inválido: {e}")

scopes = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
print(f"✅ Conectado no Sheets: {sh.title}")

abas = {w.title: w for w in sh.worksheets()}
if ABA_BASE not in abas:
    fail(f"Aba '{ABA_BASE}' não encontrada.")

ws_base = abas[ABA_BASE]
df_base = get_as_dataframe(ws_base, evaluate_formulas=True, dtype=str).fillna("")

if "Cliente" not in df_base.columns or "Data" not in df_base.columns:
    fail("Aba 'Base de Dados' precisa das colunas 'Cliente' e 'Data'.")

# =========================
# ÚLTIMA VISITA, MÉDIA e STATUS
# =========================
df = df_base.copy()
df["__dt"] = df["Data"].apply(parse_dt_cell)
df = df.dropna(subset=["__dt"])
df["__dt"] = pd.to_datetime(df["__dt"])

if df.empty:
    print("⚠️ Base vazia após parse de datas.")
    sys.exit(0)

rows = []
today = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None)
for cliente, g in df.groupby("Cliente"):
    datas = g.sort_values("__dt")["__dt"].tolist()
    if len(datas) < 2:
        continue
    diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
    media = sum(diffs) / len(diffs)
    dias = (today - datas[-1]).days
    label_emoji, label = classificar_relative(dias, media)
    rows.append({
        "Cliente": str(cliente),
        "ultima_visita": datas[-1],
        "media_dias": round(media, 1),
        "dias_desde_ultima": int(dias),
        "status_atual": label,
        "status_emoji": label_emoji
    })

ultimo = pd.DataFrame(rows)
print(f"📦 Clientes com histórico ≥2 visitas: {len(ultimo)}")
if ultimo.empty:
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

def parse_cache_dt(x):
    d = parse_dt_cell(x)
    return None if d is None else pd.to_datetime(d)

df_cache = df_cache[["Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache"]].copy()
df_cache["ultima_visita_cache_parsed"] = df_cache["ultima_visita_cache"].apply(parse_cache_dt)
cache_by_cli = {str(r["Cliente"]).strip().lower(): r for _, r in df_cache.iterrows()}

# =========================
# MENSAGENS: resumo + listas
# =========================
def daily_summary_and_lists():
    total = len(ultimo)
    em_dia = (ultimo["status_atual"]=="Em dia").sum()
    pouco  = (ultimo["status_atual"]=="Pouco atrasado").sum()
    muito  = (ultimo["status_atual"]=="Muito atrasado").sum()

    header = (
        "<b>📊 Relatório de Frequência — Salão JP</b>\n"
        f"Data/hora: {html.escape(now_br())}\n\n"
        f"👥 Ativos (c/ média): <b>{total}</b>\n"
        f"🟢 Em dia: <b>{em_dia}</b>\n"
        f"🟠 Pouco atrasado: <b>{pouco}</b>\n"
        f"🔴 Muito atrasado: <b>{muito}</b>"
    )
    tg_send(header)

    def lista(bucket_name, emoji):
        subset = ultimo.loc[ultimo["status_atual"]==bucket_name, ["Cliente","media_dias","dias_desde_ultima"]]
        if subset.empty:
            return
        linhas = "\n".join(
            f"- {html.escape(str(r.Cliente))} (média {r.media_dias}d, {int(r.dias_desde_ultima)}d sem vir)"
            for r in subset.itertuples(index=False)
        )
        body = f"<b>{emoji} {bucket_name}</b>\n{linhas}"
        if len(body) <= 3500:
            tg_send(body)
        else:
            nomes = linhas.split("\n")
            for i in range(0, len(nomes), 60):
                tg_send(f"<b>{emoji} {bucket_name}</b>\n" + "\n".join(nomes[i:i+60]))

    lista("Pouco atrasado","🟠")
    lista("Muito atrasado","🔴")

# =========================
# MENSAGENS: transições + feedback de nova visita
# =========================
def changes_and_feedback():
    transicoes, feedbacks = [], []
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

        # Nova visita?
        new_visit = True if cached_dt is None else (pd.to_datetime(ultima) > cached_dt)

        # Feedback no registro da nova visita
        if new_visit:
            if status == "Em dia":
                feedbacks.append(
                    f"✅ Cliente <b>{html.escape(nome)}</b> está em dia.\n"
                    f"Última visita: <b>{dias} dias atrás</b> (média ~<b>{int(round(media))}</b> dias)."
                )
            elif status == "Pouco atrasado":
                feedbacks.append(
                    "📣 Feedback de Frequência\n"
                    f"<b>{html.escape(nome)}</b> estava <b>pouco atrasado</b>: <b>{dias} dias</b> (média ~<b>{int(round(media))}</b>).\n"
                    f"➡️ Retomou hoje! Sugira próximo em ~{int(round(media))} dias."
                )
            else:
                feedbacks.append(
                    "📣 Feedback de Frequência\n"
                    f"<b>{html.escape(nome)}</b> estava <b>muito atrasado</b>: <b>{dias} dias</b> (média ~<b>{int(round(media))}</b>).\n"
                    f"➡️ Retomou hoje! Combine reforço e lembrete em ~{int(round(media))} dias."
                )

        # Mudança de status?
        if cached is not None and status != cached_status:
            if status in ("Pouco atrasado","Muito atrasado") or (ENVIAR_ALERTA_QUANDO_VOLTAR_EM_DIA and status=="Em dia"):
                if status == "Pouco atrasado":
                    transicoes.append(
                        "📣 Atualização de Frequência\n"
                        f"<b>{html.escape(nome)}</b> entrou em <b>Pouco atrasado</b>.\n"
                        f"Última visita: <b>{dias}</b> (média ~<b>{int(round(media))}</b>)."
                    )
                elif status == "Muito atrasado":
                    transicoes.append(
                        "📣 Atualização de Frequência\n"
                        f"<b>{html.escape(nome)}</b> entrou em <b>Muito atrasado</b>.\n"
                        f"Última visita: <b>{dias}</b> (média ~<b>{int(round(media))}</b>)."
                    )
                else:
                    transicoes.append(
                        "✅ Atualização de Frequência\n"
                        f"<b>{html.escape(nome)}</b> voltou para <b>Em dia</b>.\n"
                        f"Última visita: <b>{dias}</b> (média ~<b>{int(round(media))}</b>)."
                    )

    # Enviar com limite (anti-flood)
    for txt in transicoes[:30]:
        tg_send(txt)
    for txt in feedbacks[:30]:
        tg_send(txt)

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
if __name__ == "__main__":
    try:
        print("▶️ Iniciando execução…")
        print(f"• Timezone: {TZ}")
        print(f"• Aba base: {ABA_BASE} | Cache: {ABA_STATUS_CACHE}")
        daily_summary_and_lists()     # 1) resumo + listas (agendado ~08:00 BRT)
        changes_and_feedback()        # 2) transições + feedback por nova visita
        print("✅ Execução concluída.")
    except Exception as e:
        fail(e)

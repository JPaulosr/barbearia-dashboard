# notify_inline.py — Frequência por MÉDIA + cache + foto + alertas (08:00 BRT)
import os
import sys
import json
import html
import unicodedata
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
TZ = os.getenv("TZ") or os.getenv("TIMEZONE") or "America/Sao_Paulo"
REL_MULT = 1.5
ABA_BASE = os.getenv("BASE_ABA", "Base de Dados")
ABA_STATUS_CACHE = os.getenv("ABA_STATUS_CACHE", "status_cache")
STATUS_ABA = os.getenv("STATUS_ABA", "clientes_status")
FOTO_COL_ENV = (os.getenv("FOTO_COL") or "").strip()

def _bool_env(name, default=False):
    v = os.getenv(name)
    if v is None: return default
    return str(v).strip().lower() in ("1","true","t","yes","y","on")

# ======== CONTROLES (fixos para 08:00) ========
SEND_DAILY_HEADER = _bool_env("SEND_DAILY_HEADER", True)
SEND_LIST_POUCO   = _bool_env("SEND_LIST_POUCO", True)
SEND_LIST_MUITO   = _bool_env("SEND_LIST_MUITO", True)
SEND_FEEDBACK_ON_NEW_VISIT_ALL  = _bool_env("SEND_FEEDBACK_ON_NEW_VISIT_ALL", False)
SEND_FEEDBACK_ONLY_IF_WAS_LATE  = _bool_env("SEND_FEEDBACK_ONLY_IF_WAS_LATE", True)
SEND_TRANSITION_BACK_TO_EM_DIA  = _bool_env("SEND_TRANSITION_BACK_TO_EM_DIA", True)

# =========================
# ENVS obrigatórios
# =========================
SHEET_ID = (os.getenv("SHEET_ID") or "").strip()
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
for k,v in {"SHEET_ID":SHEET_ID,"TELEGRAM_TOKEN":TELEGRAM_TOKEN,"TELEGRAM_CHAT_ID":TELEGRAM_CHAT_ID}.items():
    if not v: print(f"💥 Variável ausente: {k}", file=sys.stderr); sys.exit(1)

# =========================
# Credenciais GCP
# =========================
try:
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        creds = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
        )
    else:
        raw = os.getenv("GCP_SERVICE_ACCOUNT") or os.getenv("GCP_SERVICE_ACCOUNT_JSON") or ""
        sa_info = json.loads(raw)
        creds = Credentials.from_service_account_info(
            sa_info,
            scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
        )
except Exception as e:
    print(f"💥 Erro credenciais GCP: {e}", file=sys.stderr); sys.exit(1)

gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
print(f"✅ Conectado no Sheets: {sh.title}")

# =========================
# Helpers
# =========================
def now_br():
    return datetime.now(pytz.timezone(TZ)).strftime("%d/%m/%Y %H:%M:%S")

def parse_dt_cell(x):
    s = (str(x or "")).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try: return datetime.strptime(s, fmt).date()
        except: pass
    return None

def classificar_relative(dias, media):
    if dias <= media: return ("🟢 Em dia","Em dia")
    if dias <= media * REL_MULT: return ("🟠 Pouco atrasado","Pouco atrasado")
    return ("🔴 Muito atrasado","Muito atrasado")

def _norm(s:str)->str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch)!="Mn")

def tg_send(text):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode":"HTML","disable_web_page_preview":True},
        timeout=30
    )
    print("↪ Telegram:", r.status_code, r.text[:160])
    if not r.ok: raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text}")

def tg_send_photo(photo_url, caption):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto",
            data={"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url, "caption": caption, "parse_mode":"HTML"},
            timeout=30
        )
        print("↪ Telegram photo:", r.status_code, r.text[:160])
        if not r.ok: raise RuntimeError(f"sendPhoto {r.status_code}: {r.text}")
    except Exception as e:
        print("⚠️ Falha sendPhoto, envia texto:", e)
        tg_send(caption)

# =========================
# Ler abas
# =========================
abas = {w.title:w for w in sh.worksheets()}
if ABA_BASE not in abas: print(f"💥 Aba '{ABA_BASE}' não encontrada.", file=sys.stderr); sys.exit(1)
ws_base = abas[ABA_BASE]
df_base = get_as_dataframe(ws_base, evaluate_formulas=True, dtype=str).fillna("")
if "Cliente" not in df_base.columns or "Data" not in df_base.columns:
    print("💥 'Base de Dados' precisa de colunas Cliente e Data.", file=sys.stderr); sys.exit(1)

# Mapa de fotos (opcional)
foto_map = {}
if STATUS_ABA in abas:
    try:
        ws_status = abas[STATUS_ABA]
        df_status = get_as_dataframe(ws_status, evaluate_formulas=True, dtype=str).fillna("")
        cols_lower = {c.strip().lower(): c for c in df_status.columns if isinstance(c,str)}
        prefer = FOTO_COL_ENV.lower() if FOTO_COL_ENV else ""
        foto_candidates = [prefer] if prefer else ["foto","imagem","link_foto","url_foto","foto_link","link","image"]
        foto_col = next((cols_lower[x] for x in foto_candidates if x in cols_lower), None)
        cli_col  = next((cols_lower[x] for x in ["cliente","nome","nome_cliente"] if x in cols_lower), None)
        if foto_col and cli_col:
            tmp = df_status[[cli_col, foto_col]].copy()
            tmp.columns = ["Cliente","Foto"]
            tmp["k"] = tmp["Cliente"].astype(str).map(_norm)
            foto_map = {r["k"]: str(r["Foto"]).strip() for _,r in tmp.iterrows() if str(r["Foto"]).strip()}
            print(f"🖼️ Fotos: {len(foto_map)}")
        else:
            print("ℹ️ Colunas de foto/cliente não localizadas em", STATUS_ABA)
    except Exception as e:
        print("⚠️ Erro lendo STATUS_ABA:", e)
else:
    print(f"ℹ️ STATUS_ABA '{STATUS_ABA}' inexistente — sem fotos.")

# =========================
# Preparar base (1 visita por dia)
# =========================
df = df_base.copy()
df["__dt"] = df["Data"].apply(parse_dt_cell)
df = df.dropna(subset=["__dt"])
if df.empty: print("⚠️ Base vazia após parse de datas."); sys.exit(0)

df["_date_only"] = pd.to_datetime(df["__dt"]).dt.date
df["_cliente_norm"] = df["Cliente"].astype(str).str.strip()
df = df[df["_cliente_norm"]!=""]

rows = []
today = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None)
for cliente, g in df.groupby("_cliente_norm"):
    dias_unicos = sorted(set(g["_date_only"].tolist()))
    if len(dias_unicos) < 2:  # precisa de >=2 para calcular média
        continue
    dias_ts = [pd.to_datetime(d) for d in dias_unicos]
    diffs = [(dias_ts[i]-dias_ts[i-1]).days for i in range(1,len(dias_ts))]
    diffs = [d for d in diffs if d>0]
    if not diffs: continue
    media = sum(diffs)/len(diffs)
    dias_desde_ultima = (today - dias_ts[-1]).days
    label_emoji, label = classificar_relative(dias_desde_ultima, media)
    rows.append({
        "Cliente": cliente,
        "ultima_visita": dias_ts[-1],
        "media_dias": round(media,1),
        "dias_desde_ultima": int(dias_desde_ultima),
        "status_atual": label,
        "status_emoji": label_emoji,
        "visitas_total": len(dias_unicos),
    })

ultimo = pd.DataFrame(rows)
print(f"📦 Clientes com histórico válido (≥2 dias distintos): {len(ultimo)}")
if ultimo.empty: sys.exit(0)

# =========================
# Cache
# =========================
def ensure_cache():
    try: return sh.worksheet(ABA_STATUS_CACHE)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(ABA_STATUS_CACHE, rows=2, cols=6)
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

need_cols = ["Cliente","ultima_visita_cache","status_cache","last_notified_at","media_cache","visitas_total_cache"]
for c in need_cols:
    if c not in df_cache.columns: df_cache[c] = ""

df_cache = df_cache[need_cols].copy()
df_cache["ultima_visita_cache_parsed"] = df_cache["ultima_visita_cache"].apply(parse_cache_dt)
cache_by_cli = {str(r["Cliente"]).strip().lower(): r for _,r in df_cache.iterrows()}

# =========================
# Resumo + listas (08:00)
# =========================
def daily_summary_and_lists():
    total = len(ultimo)
    em_dia = (ultimo["status_atual"]=="Em dia").sum()
    pouco  = (ultimo["status_atual"]=="Pouco atrasado").sum()
    muito  = (ultimo["status_atual"]=="Muito atrasado").sum()

    if SEND_DAILY_HEADER:
        header = (
            "<b>📊 Relatório de Frequência — Salão JP</b>\n"
            f"Data/hora: {html.escape(now_br())}\n\n"
            f"👥 Ativos (c/ média): <b>{total}</b>\n"
            f"🟢 Em dia: <b>{em_dia}</b>\n"
            f"🟠 Pouco atrasado: <b>{pouco}</b>\n"
            f"🔴 Muito atrasado: <b>{muito}</b>"
        )
        tg_send(header)

    def lista(bucket, emoji):
        subset = ultimo.loc[ultimo["status_atual"]==bucket, ["Cliente","media_dias","dias_desde_ultima"]]
        titulo = f"<b>{emoji} {bucket}</b>"
        if subset.empty:
            tg_send(titulo + "\n(nenhum)")
            return
        linhas = "\n".join(
            f"- {html.escape(str(r.Cliente))} (média {r.media_dias}d, {int(r.dias_desde_ultima)}d sem vir)"
            for r in subset.itertuples(index=False)
        )
        body = f"{titulo}\n{linhas}"
        if len(body) <= 3500:
            tg_send(body)
        else:
            nomes = linhas.split("\n")
            for i in range(0, len(nomes), 60):
                tg_send(f"{titulo}\n" + "\n".join(nomes[i:i+60]))

    if SEND_LIST_POUCO: lista("Pouco atrasado","🟠")
    if SEND_LIST_MUITO: lista("Muito atrasado","🔴")

# =========================
# Transições + Feedback (mudanças desde ontem)
# =========================
def changes_and_feedback():
    transicoes = []
    ultimo_by_cli = {r.Cliente.strip().lower(): r for r in ultimo.itertuples(index=False)}

    for key, row in ultimo_by_cli.items():
        nome = row.Cliente
        dias = int(row.dias_desde_ultima)
        media = float(row.media_dias)
        status = row.status_atual
        ultima = row.ultima_visita
        visitas_total = int(row.visitas_total)

        cached = cache_by_cli.get(key)
        cached_status = (cached["status_cache"] if cached is not None else "")
        cached_visitas = int(cached["visitas_total_cache"]) if (cached is not None and str(cached.get("visitas_total_cache","")).strip().isdigit()) else 0

        # 1) Feedback de ATENDIMENTO (novo dia distinto)
        new_visit = visitas_total > cached_visitas
        estava_atrasado = cached_status in ("Pouco atrasado","Muito atrasado")
        enviar_feedback = (SEND_FEEDBACK_ON_NEW_VISIT_ALL or (SEND_FEEDBACK_ONLY_IF_WAS_LATE and estava_atrasado))
        if new_visit and enviar_feedback:
            ultima_str = pd.to_datetime(ultima).strftime("%d/%m/%Y")
            media_str = f"{media:.1f}".replace(".", ",")
            caption = (
                "✅ <b>Retorno registrado</b>\n"
                f"👤 Cliente: <b>{html.escape(nome)}</b>\n"
                (f"⚠️ Estava: <b>{html.escape(cached_status)}</b>\n" if estava_atrasado else "")
                f"🗓️ Atendimento registrado em: <b>{ultima_str}</b>\n"
                f"🔁 Média: <b>{media_str} dias</b>\n"
                f"⏳ Estava há: <b>{dias} dias</b>"
            )
            foto = foto_map.get(_norm(nome))
            tg_send_photo(foto, caption) if foto else tg_send(caption)

        # 2) Transições de status
        if cached is not None and status != cached_status:
            if status in ("Pouco atrasado","Muito atrasado"):
                transicoes.append(
                    "📣 Atualização de Frequência\n"
                    f"<b>{html.escape(nome)}</b> entrou em <b>{html.escape(status)}</b>."
                )
            elif SEND_TRANSITION_BACK_TO_EM_DIA and status == "Em dia":
                transicoes.append(
                    "✅ Atualização de Frequência\n"
                    f"<b>{html.escape(nome)}</b> voltou para <b>Em dia</b>."
                )

    # Envia transições (limite simples)
    for txt in transicoes[:50]:
        tg_send(txt)

    # Atualiza cache
    out = ultimo[["Cliente","ultima_visita","status_atual","media_dias","visitas_total"]].copy()
    out["ultima_visita"] = pd.to_datetime(out["ultima_visita"]).dt.strftime("%Y-%m-%d")
    out.rename(columns={
        "ultima_visita":"ultima_visita_cache",
        "status_atual":"status_cache",
        "media_dias":"media_cache",
        "visitas_total":"visitas_total_cache"
    }, inplace=True)
    out["last_notified_at"] = now_br()
    ws_cache.clear()
    set_with_dataframe(ws_cache, out)

# =========================
# ENTRYPOINT
# =========================
if __name__ == "__main__":
    try:
        print("▶️ Iniciando…")
        print(f"• TZ={TZ} | Base={ABA_BASE} | Cache={ABA_STATUS_CACHE} | Status/Fotos={STATUS_ABA}")
        # Como só rodamos às 08:00, sempre manda o resumo/listas e depois as mudanças
        daily_summary_and_lists()
        changes_and_feedback()
        print("✅ Execução concluída.")
    except Exception as e:
        print(f"💥 {e}", file=sys.stderr); sys.exit(1)

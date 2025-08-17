# notify_inline.py — Frequência por MÉDIA + cache + foto + alertas (resumo/entradas/retorno)
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
STATUS_ABA = os.getenv("STATUS_ABA", "clientes_status")  # onde está Cliente + link da foto
FOTO_COL_ENV = (os.getenv("FOTO_COL") or "").strip()

def _bool_env(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "t", "yes", "y", "on")

# ======== CONTROLES DE ENVIO ========
SEND_DAILY_HEADER = _bool_env("SEND_DAILY_HEADER", False)
SEND_LIST_POUCO   = _bool_env("SEND_LIST_POUCO", False)
SEND_LIST_MUITO   = _bool_env("SEND_LIST_MUITO", False)

# Feedback ao registrar nova visita (aumentou nº de dias distintos):
# >>> NOVO PADRÃO: sempre enviar feedback (com foto) <<<
SEND_FEEDBACK_ON_NEW_VISIT_ALL  = _bool_env("SEND_FEEDBACK_ON_NEW_VISIT_ALL", True)
SEND_FEEDBACK_ONLY_IF_WAS_LATE  = _bool_env("SEND_FEEDBACK_ONLY_IF_WAS_LATE", False)

# Transições:
SEND_TRANSITION_BACK_TO_EM_DIA  = _bool_env("SEND_TRANSITION_BACK_TO_EM_DIA", False)

# Evitar feedback duplicado por visita
FEEDBACK_ONCE_PER_VISIT = True

# =========================
# ENVS obrigatórios
# =========================
SHEET_ID = (os.getenv("SHEET_ID") or "").strip()
TELEGRAM_TOKEN = (os.getenv("TELEGRAM_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()

def fail(msg):
    print(f"💥 {msg}", file=sys.stderr)
    sys.exit(1)

need = ["SHEET_ID", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]
missing = [k for k in need if not os.getenv(k)]
if missing:
    fail(f"Variáveis ausentes: {', '.join(missing)}")

# =========================
# Credenciais GCP
# =========================
if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
    try:
        creds = Credentials.from_service_account_file(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
            scopes=["https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"]
        )
    except Exception as e:
        fail(f"Erro ao ler GOOGLE_APPLICATION_CREDENTIALS: {e}")
else:
    raw = os.getenv("GCP_SERVICE_ACCOUNT") or os.getenv("GCP_SERVICE_ACCOUNT_JSON") or ""
    if not raw.strip():
        fail("Faltam credenciais GCP: defina GOOGLE_APPLICATION_CREDENTIALS ou GCP_SERVICE_ACCOUNT(_JSON).")
    try:
        sa_info = json.loads(raw)
        creds = Credentials.from_service_account_info(
            sa_info,
            scopes=["https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"]
        )
    except Exception as e:
        fail(f"GCP service account JSON inválido: {e}")

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

def _norm(s: str) -> str:
    s = (s or "").strip().casefold()
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def tg_send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    r = requests.post(url, json=payload, timeout=30)
    print("↪ Telegram:", r.status_code, r.text[:160])
    if not r.ok:
        raise RuntimeError(f"Telegram HTTP {r.status_code}: {r.text}")

def tg_send_photo(photo_url, caption):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "photo": photo_url,
                   "caption": caption, "parse_mode": "HTML"}
        r = requests.post(url, data=payload, timeout=30)
        print("↪ Telegram photo:", r.status_code, r.text[:160])
        if not r.ok:
            raise RuntimeError(f"sendPhoto {r.status_code}: {r.text}")
    except Exception as e:
        print("⚠️ Falha sendPhoto, enviando texto. Motivo:", e)
        tg_send(caption)

# =========================
# Ler abas
# =========================
abas = {w.title: w for w in sh.worksheets()}
if ABA_BASE not in abas:
    fail(f"Aba '{ABA_BASE}' não encontrada.")
ws_base = abas[ABA_BASE]

df_base = get_as_dataframe(ws_base, evaluate_formulas=True, dtype=str).fillna("")
if "Cliente" not in df_base.columns or "Data" not in df_base.columns:
    fail("Aba base precisa das colunas 'Cliente' e 'Data'.")

# Foto por cliente (opcional)
foto_map = {}
if STATUS_ABA in abas:
    try:
        ws_status = abas[STATUS_ABA]
        df_status = get_as_dataframe(ws_status, evaluate_formulas=True, dtype=str).fillna("")
        cols_lower = {c.strip().lower(): c for c in df_status.columns if isinstance(c, str)}
        cand = FOTO_COL_ENV.lower() if FOTO_COL_ENV else ""
        foto_candidates = [cand] if cand else ["foto", "imagem", "link_foto", "url_foto", "foto_link", "link", "image"]
        foto_col = next((cols_lower[x] for x in foto_candidates if x in cols_lower), None)
        cli_col  = next((cols_lower[x] for x in ["cliente", "nome", "nome_cliente"] if x in cols_lower), None)
        if foto_col and cli_col:
            tmp = df_status[[cli_col, foto_col]].copy()
            tmp.columns = ["Cliente", "Foto"]
            tmp["k"] = tmp["Cliente"].astype(str).map(_norm)
            foto_map = {r["k"]: str(r["Foto"]).strip() for _, r in tmp.iterrows() if str(r["Foto"]).strip()}
            print(f"🖼️ Fotos encontradas: {len(foto_map)}")
        else:
            print("ℹ️ Não achei colunas de foto/cliente na", STATUS_ABA)
    except Exception as e:
        print("⚠️ Erro lendo STATUS_ABA:", e)
else:
    print(f"ℹ️ STATUS_ABA '{STATUS_ABA}' não existe — seguindo sem fotos.")

# =========================
# Preparar base (1 visita por dia)
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
df["_date_only"] = pd.to_datetime(df["__dt"]).dt.date
df["_cliente_norm"] = df["Cliente"].astype(str).str.strip()
df = df[df["_cliente_norm"] != ""]

for cliente, g in df.groupby("_cliente_norm"):
    dias_unicos = sorted(set(g["_date_only"].tolist()))
    if len(dias_unicos) < 2:
        continue
    dias_ts = [pd.to_datetime(d) for d in dias_unicos]
    diffs = [(dias_ts[i] - dias_ts[i-1]).days for i in range(1, len(dias_ts))]
    diffs_pos = [d for d in diffs if d > 0]
    if not diffs_pos:
        continue
    media = sum(diffs_pos) / len(diffs_pos)
    dias_desde_ultima = (today - dias_ts[-1]).days
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
if ultimo.empty:
    sys.exit(0)

# =========================
# Cache
# =========================
def ensure_cache():
    try:
        return sh.worksheet(ABA_STATUS_CACHE)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(ABA_STATUS_CACHE, rows=2, cols=7)
        set_with_dataframe(ws, pd.DataFrame(columns=[
            "Cliente","ultima_visita_cache","status_cache","last_notified_at",
            "media_cache","visitas_total_cache","feedback_sent_for_date"
        ]))
        return ws

ws_cache = ensure_cache()
df_cache = get_as_dataframe(ws_cache, evaluate_formulas=True, dtype=str).fillna("")
if df_cache.empty or "Cliente" not in df_cache.columns:
    df_cache = pd.DataFrame(columns=[
        "Cliente","ultima_visita_cache","status_cache","last_notified_at",
        "media_cache","visitas_total_cache","feedback_sent_for_date"
    ])

def parse_cache_dt(x):
    d = parse_dt_cell(x)
    return None if d is None else pd.to_datetime(d)

need_cols = ["Cliente","ultima_visita_cache","status_cache","last_notified_at",
             "media_cache","visitas_total_cache","feedback_sent_for_date"]
for c in need_cols:
    if c not in df_cache.columns:
        df_cache[c] = ""

df_cache = df_cache[need_cols].copy()
df_cache["ultima_visita_cache_parsed"] = df_cache["ultima_visita_cache"].apply(parse_cache_dt)
cache_by_cli = {str(r["Cliente"]).strip().lower(): r for _, r in df_cache.iterrows()}

# =========================
# Resumo + listas (para 08:00, conforme flags)
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

    if SEND_LIST_POUCO:
        lista("Pouco atrasado","🟠")
    if SEND_LIST_MUITO:
        lista("Muito atrasado","🔴")

# =========================
# Transições + Feedback (retorno com foto)
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
        cached_dt = cached["ultima_visita_cache_parsed"] if cached is not None else None
        cached_visitas = int(cached["visitas_total_cache"]) if (cached is not None and str(cached.get("visitas_total_cache","")).strip().isdigit()) else 0

        # controle de 1 feedback por visita (chave = data da última visita)
        ultima_key = pd.to_datetime(ultima).strftime("%Y-%m-%d")
        feedback_already_sent = False
        if FEEDBACK_ONCE_PER_VISIT and cached is not None:
            sent_for = (cached.get("feedback_sent_for_date") or "").strip()
            feedback_already_sent = (sent_for == ultima_key)

        # Nova visita = aumentou nº de dias distintos
        new_visit = visitas_total > cached_visitas

        # regras para enviar feedback (com foto)
        estava_atrasado = cached_status in ("Pouco atrasado", "Muito atrasado")
        enviar_feedback = False
        if SEND_FEEDBACK_ON_NEW_VISIT_ALL:
            enviar_feedback = True
        elif SEND_FEEDBACK_ONLY_IF_WAS_LATE and estava_atrasado:
            enviar_feedback = True

        if new_visit and enviar_feedback and not feedback_already_sent:
            ultima_str = pd.to_datetime(ultima).strftime("%d/%m/%Y")
            media_str = f"{media:.1f}".replace(".", ",")
            if estava_atrasado:
                caption = (
                    "✅ <b>Retorno registrado</b>\n"
                    f"👤 Cliente: <b>{html.escape(nome)}</b>\n"
                    f"⚠️ Estado: <b>{html.escape(cached_status)}</b>\n"
                    f"🗓️ Atendimento registrado em: <b>{ultima_str}</b>\n"
                    f"🔁 Média: <b>{media_str} dias</b>\n"
                    f"⏳ Estava há: <b>{dias} dias</b>"
                )
            else:
                caption = (
                    "📌 <b>Atendimento registrado</b>\n"
                    f"👤 Cliente: <b>{html.escape(nome)}</b>\n"
                    f"{row.status_emoji or ''} Status: <b>{html.escape(status)}</b>\n"
                    f"🗓️ Data: <b>{ultima_str}</b>\n"
                    f"🔁 Média: <b>{media_str} dias</b>\n"
                    f"⏳ Distância da última: <b>{dias} dias</b>"
                )
            foto = foto_map.get(_norm(nome))
            if foto:
                tg_send_photo(foto, caption)
            else:
                tg_send(caption)

            if cached is not None:
                cached["feedback_sent_for_date"] = ultima_key  # marca como enviado

        # Transições de status
        if cached is not None and status != cached_status:
            if status in ("Pouco atrasado", "Muito atrasado"):
                transicoes.append(
                    "📣 Atualização de Frequência\n"
                    f"<b>{html.escape(nome)}</b> entrou em <b>{html.escape(status)}</b>."
                )
            elif SEND_TRANSITION_BACK_TO_EM_DIA and status == "Em dia":
                transicoes.append(
                    "✅ Atualização de Frequência\n"
                    f"<b>{html.escape(nome)}</b> voltou para <b>Em dia</b>."
                )

    # Envia transições (anti-flood simples)
    for txt in transicoes[:30]:
        tg_send(txt)

    # Atualiza cache (preserva feedback_sent_for_date quando possível)
    out = ultimo[["Cliente","ultima_visita","status_atual","media_dias","visitas_total"]].copy()
    out["ultima_visita"] = pd.to_datetime(out["ultima_visita"]).dt.strftime("%Y-%m-%d")
    out.rename(columns={
        "ultima_visita":"ultima_visita_cache",
        "status_atual":"status_cache",
        "media_dias":"media_cache",
        "visitas_total":"visitas_total_cache"
    }, inplace=True)
    out["last_notified_at"] = now_br()

    sent_map = {k: (v.get("feedback_sent_for_date") or "") for k, v in cache_by_cli.items()}
    out["key_lower"] = out["Cliente"].astype(str).str.strip().str.lower()
    out["feedback_sent_for_date"] = out["key_lower"].map(sent_map).fillna("")
    def _maybe_update_sent(row):
        k = row["key_lower"]
        cached = cache_by_cli.get(k)
        if cached is None:
            return row["feedback_sent_for_date"]
        mark = (cached.get("feedback_sent_for_date") or "").strip()
        return mark or row["feedback_sent_for_date"]
    out["feedback_sent_for_date"] = out.apply(_maybe_update_sent, axis=1)
    out.drop(columns=["key_lower"], inplace=True)

    ws_cache.clear()
    set_with_dataframe(ws_cache, out[[
        "Cliente","ultima_visita_cache","status_cache","last_notified_at",
        "media_cache","visitas_total_cache","feedback_sent_for_date"
    ]])

# =========================
# MODO INDIVIDUAL (opcional)
# =========================
CLIENTE = os.getenv("CLIENTE") or os.getenv("INPUT_CLIENTE")
if CLIENTE:
    alvo = _norm(CLIENTE)
    ultimo["_norm"] = ultimo["Cliente"].apply(_norm)
    sel = ultimo[ultimo["_norm"] == alvo]
    if sel.empty:
        sel = ultimo[ultimo["_norm"].str.contains(alvo, na=False)]
    if sel.empty:
        tg_send(f"⚠️ Cliente '{html.escape(CLIENTE)}' não encontrado com histórico suficiente.")
        sys.exit(0)
    row = sel.sort_values("ultima_visita", ascending=False).iloc[0]
    ultima_str = pd.to_datetime(row["ultima_visita"]).strftime("%d/%m/%Y")
    media_str = f"{row['media_dias']:.1f}".replace(".", ",")
    dias_int = int(row["dias_desde_ultima"])
    status_emoji = row.get("status_emoji") or ""
    status_txt = row.get("status_atual") or ""
    caption = (
        "⏰ <b>Alerta de Frequência</b>\n"
        f"👤 Cliente: <b>{html.escape(row['Cliente'])}</b>\n"
        f"{status_emoji} Status: <b>{html.escape(status_txt)}</b>\n"
        f"🗓️ Último: <b>{ultima_str}</b>\n"
        f"🔁 Média: <b>{media_str} dias</b>\n"
        f"⏳ Sem vir há: <b>{dias_int} dias</b>"
    )
    foto = foto_map.get(_norm(row["Cliente"]))
    if foto:
        tg_send_photo(foto, caption)
    else:
        tg_send(caption)
    print("✅ Alerta individual enviado.")
    sys.exit(0)

# =========================
# ENTRYPOINT
# =========================
if __name__ == "__main__":
    try:
        print("▶️ Iniciando…")
        print(f"• TZ={TZ} | Base={ABA_BASE} | Cache={ABA_STATUS_CACHE} | Status/Fotos={STATUS_ABA}")
        if SEND_DAILY_HEADER or SEND_LIST_POUCO or SEND_LIST_MUITO:
            daily_summary_and_lists()   # para 08:00
        changes_and_feedback()          # para transições + retorno (1 feedback por visita)
        print("✅ Execução concluída.")
    except Exception as e:
        fail(e)

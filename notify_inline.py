# notify_inline.py — Frequência por MÉDIA + cache + foto + alertas (resumo/entradas/retorno/fiados)
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
FOTO_COL_ENV = os.getenv("FOTO_COL", "").strip()

# --- FIADOS ---
ABA_FIADO = os.getenv("ABA_FIADO", "Fiados")
ABA_FIADO_CACHE = os.getenv("ABA_FIADO_CACHE", "fiado_cache")
FIADO_ID_COL_ENV = os.getenv("FIADO_ID_COL", "").strip()

def _bool_env(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "t", "yes", "y", "on")

# ======== CONTROLES DE ENVIO ========
# (para 08:00 enviar listas; no watch frequente, não)
SEND_DAILY_HEADER = _bool_env("SEND_DAILY_HEADER", False)
SEND_LIST_POUCO   = _bool_env("SEND_LIST_POUCO", False)
SEND_LIST_MUITO   = _bool_env("SEND_LIST_MUITO", False)

# Feedback ao registrar nova visita (aumentou nº de dias distintos):
SEND_FEEDBACK_ON_NEW_VISIT_ALL  = _bool_env("SEND_FEEDBACK_ON_NEW_VISIT_ALL", False)  # todos
SEND_FEEDBACK_ONLY_IF_WAS_LATE  = _bool_env("SEND_FEEDBACK_ONLY_IF_WAS_LATE", True)   # ou só se estava atrasado

# Transições:
SEND_TRANSITION_BACK_TO_EM_DIA  = _bool_env("SEND_TRANSITION_BACK_TO_EM_DIA", False)  # “voltou pra Em dia”

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

def fmt_date(x):
    d = parse_dt_cell(x)
    return datetime.strftime(d, "%d/%m/%Y") if d else (str(x or "").strip())

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
# Cache (status + visitas)
# =========================
def ensure_cache():
    try:
        return sh.worksheet(ABA_STATUS_CACHE)
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

        # Nova visita = aumentou nº de dias distintos (captura retroativo também)
        new_visit = visitas_total > cached_visitas

        # FEEDBACK de atendimento (retorno)
        estava_atrasado = cached_status in ("Pouco atrasado", "Muito atrasado")
        enviar_feedback = False
        if SEND_FEEDBACK_ON_NEW_VISIT_ALL:
            enviar_feedback = True
        elif SEND_FEEDBACK_ONLY_IF_WAS_LATE and estava_atrasado:
            enviar_feedback = True

        if new_visit and enviar_feedback:
            ultima_str = pd.to_datetime(ultima).strftime("%d/%m/%Y")
            media_str = f"{media:.1f}".replace(".", ",")
            if estava_atrasado:
                caption = (
                    "✅ <b>Retorno registrado</b>\n"
                    f"👤 Cliente: <b>{html.escape(nome)}</b>\n"
                    f"⚠️ Estava: <b>{html.escape(cached_status)}</b>\n"
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

        # Transições de status:
        if cached is not None and status != cached_status:
            # Entrou em atraso (Em dia -> Pouco/Muito) → sempre avisar
            if status in ("Pouco atrasado", "Muito atrasado"):
                transicoes.append(
                    "📣 Atualização de Frequência\n"
                    f"<b>{html.escape(nome)}</b> entrou em <b>{html.escape(status)}</b>."
                )
            # Voltou para Em dia → só se flag ligada
            elif SEND_TRANSITION_BACK_TO_EM_DIA and status == "Em dia":
                transicoes.append(
                    "✅ Atualização de Frequência\n"
                    f"<b>{html.escape(nome)}</b> voltou para <b>Em dia</b>."
                )

    # Envia transições (anti-flood simples)
    for txt in transicoes[:30]:
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
# FIADOS: detectar novos e enviar cartão com foto
# =========================
def process_fiados():
    if ABA_FIADO not in abas:
        print(f"ℹ️ ABA_FIADO '{ABA_FIADO}' não existe — pulando fiados.")
        return

    ws_fiado = abas[ABA_FIADO]
    df_fiado = get_as_dataframe(ws_fiado, evaluate_formulas=True, dtype=str).fillna("")

    if df_fiado.empty:
        print("ℹ️ Aba de fiados vazia.")
        return

    # Normaliza nomes de colunas
    cols_lower = {c.strip().lower(): c for c in df_fiado.columns if isinstance(c, str)}
    col_cliente = next((cols_lower[x] for x in ["cliente","nome","nome_cliente"] if x in cols_lower), None)
    col_serv    = next((cols_lower[x] for x in ["serviços","servicos","servico","serviço","servico(s)"] if x in cols_lower), None)
    col_total   = next((cols_lower[x] for x in ["total","valor","preco","preço","amount"] if x in cols_lower), None)
    col_atend   = next((cols_lower[x] for x in ["atendimento","data","data_atendimento"] if x in cols_lower), None)
    col_venc    = next((cols_lower[x] for x in ["vencimento","vcto","venc"] if x in cols_lower), None)

    # Coluna de ID (pode ser override via env)
    if FIADO_ID_COL_ENV:
        col_id = cols_lower.get(FIADO_ID_COL_ENV.strip().lower())
    else:
        col_id = next((cols_lower[x] for x in ["id","fiado_id","codigo","código","uid"] if x in cols_lower), None)

    if not col_cliente or not col_id:
        print("⚠️ Fiados: precisa ao menos de 'Cliente' e 'ID'.")
        return

    # Cache de fiados já notificados
    try:
        ws_fcache = sh.worksheet(ABA_FIADO_CACHE)
    except gspread.exceptions.WorksheetNotFound:
        ws_fcache = sh.add_worksheet(ABA_FIADO_CACHE, rows=2, cols=3)
        set_with_dataframe(ws_fcache, pd.DataFrame(columns=["fiado_id","cliente","last_notified_at"]))

    df_fcache = get_as_dataframe(ws_fcache, evaluate_formulas=True, dtype=str).fillna("")
    enviados = set(df_fcache["fiado_id"].astype(str).tolist()) if "fiado_id" in df_fcache.columns else set()

    novos = []
    for _, r in df_fiado.iterrows():
        fiado_id = str(r.get(col_id, "")).strip()
        if not fiado_id or fiado_id in enviados:
            continue
        cliente = str(r.get(col_cliente, "")).strip()
        if not cliente:
            continue

        serv  = str(r.get(col_serv, "")).strip() if col_serv else ""
        total = str(r.get(col_total, "")).strip() if col_total else ""
        atend = fmt_date(r.get(col_atend, "")) if col_atend else ""
        venc  = fmt_date(r.get(col_venc, "")) if col_venc else ""

        caption = (
            "🧾 <b>Novo fiado criado</b>\n"
            f"👤 Cliente: <b>{html.escape(cliente)}</b>\n"
            f"{'🧰 Serviços: ' + html.escape(serv) + '\\n' if serv else ''}"
            f"{'💵 Total: R$ ' + html.escape(total) + '\\n' if total else ''}"
            f"{'📅 Atendimento: <b>' + html.escape(atend) + '</b>\\n' if atend else ''}"
            f"{'⏳ Vencimento: <b>' + html.escape(venc) + '</b>\\n' if venc else ''}"
            f"🆔 ID: <code>{html.escape(fiado_id)}</code>"
        )

        foto = foto_map.get(_norm(cliente))
        if foto:
            tg_send_photo(foto, caption)
        else:
            tg_send(caption)

        novos.append({"fiado_id": fiado_id, "cliente": cliente, "last_notified_at": now_br()})

    # Atualiza cache de fiados
    if novos:
        df_out = pd.DataFrame(novos)
        if df_fcache.empty:
            out = df_out
        else:
            out = pd.concat([df_fcache[["fiado_id","cliente","last_notified_at"]], df_out], ignore_index=True)
            out = out.drop_duplicates(subset=["fiado_id"], keep="last")
        ws_fcache.clear()
        set_with_dataframe(ws_fcache, out)

# =========================
# MODO INDIVIDUAL (opcional)
# =========================
CLIENTE = os.getenv("CLIENTE") or os.getenv("INPUT_CLIENTE")
def modo_individual():
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
        print(f"• TZ={TZ} | Base={ABA_BASE} | Cache={ABA_STATUS_CACHE} | Status/Fotos={STATUS_ABA} | Fiados={ABA_FIADO}")
        if SEND_DAILY_HEADER or SEND_LIST_POUCO or SEND_LIST_MUITO:
            daily_summary_and_lists()   # para 08:00
        changes_and_feedback()          # transições + retorno
        process_fiados()                # 🧾 novos fiados (com foto)
        if CLIENTE:
            modo_individual()
        print("✅ Execução concluída.")
    except Exception as e:
        fail(e)

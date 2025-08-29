# -*- coding: utf-8 -*-
# notify_inline.py — Frequência por MÉDIA + cache + foto + alertas (cards por cliente)
# - Lê "Base de Dados" e "clientes_status" (Cliente | Status | Foto | Família)
# - Filtra somente clientes com Status = "Ativo"
# - Envia cards detalhados (com foto quando existir)
# - Mantém cache de transições/feedback
# - Agenda para rodar todo dia às 08:00 America/Sao_Paulo (sem cron) — controle por env
#   * RUN_ONCE=1   -> executa uma vez e sai (teste manual)
#   * RUN_LOOP=1   -> entra no laço diário (default se RUN_ONCE não for 1)

import os
import sys
import json
import html
import time
import unicodedata
import requests
import gspread
import pytz
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# =========================
# PARÂMETROS
# =========================
TZ = os.getenv("TZ") or os.getenv("TIMEZONE") or "America/Sao_Paulo"
REL_MULT = 1.5
ABA_BASE = os.getenv("BASE_ABA", "Base de Dados")
ABA_STATUS_CACHE = os.getenv("ABA_STATUS_CACHE", "status_cache")
STATUS_ABA = os.getenv("STATUS_ABA", "clientes_status")  # Espera: Cliente | Status | Foto | Família
FOTO_COL_ENV = (os.getenv("FOTO_COL") or "").strip()     # ignorado aqui, usamos "Foto" direto
RUN_AT_HOUR = int(os.getenv("RUN_AT_HOUR", "8"))         # 8h (local)
RUN_ONCE = str(os.getenv("RUN_ONCE", "0")).strip().lower() in ("1","true","t","yes","y","on")
RUN_LOOP = str(os.getenv("RUN_LOOP", "1")).strip().lower() in ("1","true","t","yes","y","on")

def _bool_env(name, default=False):
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "t", "yes", "y", "on")

# ======== CONTROLES DE ENVIO ========
SEND_DAILY_HEADER = _bool_env("SEND_DAILY_HEADER", False)
SEND_LIST_POUCO   = _bool_env("SEND_LIST_POUCO", False)   # envia cards de "Pouco atrasado"
SEND_LIST_MUITO   = _bool_env("SEND_LIST_MUITO", False)   # envia cards de "Muito atrasado"

# Feedback ao registrar nova visita (aumentou nº de dias distintos):
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
def _get_creds():
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        try:
            return Credentials.from_service_account_file(
                os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
                scopes=["https://spreadsheets.google.com/feeds",
                        "https://www.googleapis.com/auth/drive"]
            )
        except Exception as e:
            fail(f"Erro ao ler GOOGLE_APPLICATION_CREDENTIALS: {e}")
    raw = os.getenv("GCP_SERVICE_ACCOUNT") or os.getenv("GCP_SERVICE_ACCOUNT_JSON") or ""
    if not raw.strip():
        fail("Faltam credenciais GCP: defina GOOGLE_APPLICATION_CREDENTIALS ou GCP_SERVICE_ACCOUNT(_JSON).")
    try:
        sa_info = json.loads(raw)
        return Credentials.from_service_account_info(
            sa_info,
            scopes=["https://spreadsheets.google.com/feeds",
                    "https://www.googleapis.com/auth/drive"]
        )
    except Exception as e:
        fail(f"GCP service account JSON inválido: {e}")

creds = _get_creds()
gc = gspread.authorize(creds)
sh = gc.open_by_key(SHEET_ID)
print(f"✅ Conectado no Sheets: {sh.title}")

# =========================
# Helpers
# =========================
def now_br_str():
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

def make_card_caption(nome, status_label, status_emoji, ultima_dt, media, dias_desde_ultima):
    ultima_str = pd.to_datetime(ultima_dt).strftime("%d/%m/%Y")
    media_str = f"{media:.1f}".replace(".", ",")
    dias_int = int(dias_desde_ultima)
    return (
        "📌 <b>Atendimento registrado</b>\n"
        f"👤 Cliente: <b>{html.escape(nome)}</b>\n"
        f"{status_emoji or ''} Status: <b>{html.escape(status_label)}</b>\n"
        f"🗓️ Data: <b>{ultima_str}</b>\n"
        f"🔁 Média: <b>{media_str} dias</b>\n"
        f"⏳ Distância da última: <b>{dias_int} dias</b>"
    )

# =========================
# Ler abas auxiliares (status/foto)
# =========================
def _col_find(df, wanted_names):
    """Procura coluna por nome exato; se não achar, tolera sem acento e casefold."""
    cols = list(df.columns)
    for w in wanted_names:
        if w in cols:
            return w
    def _key(s):
        s = (s or "").strip()
        s = unicodedata.normalize("NFD", s)
        s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
        return s.casefold()
    wanted_keys = {_key(w): w for w in wanted_names}
    for c in cols:
        if _key(c) in wanted_keys:
            return c
    return None

def load_status_and_photos(worksheets_map):
    foto_map = {}
    active_set = set()
    if STATUS_ABA not in worksheets_map:
        print(f"ℹ️ STATUS_ABA '{STATUS_ABA}' não existe — sem fotos/status.")
        return foto_map, active_set

    try:
        ws_status = worksheets_map[STATUS_ABA]
        df_status = get_as_dataframe(ws_status, evaluate_formulas=True, dtype=str).fillna("")
        col_cliente = _col_find(df_status, ["Cliente"])
        col_status  = _col_find(df_status, ["Status"])
        col_foto    = _col_find(df_status, ["Foto"])
        col_familia = _col_find(df_status, ["Família", "Familia"])  # opcional

        if not col_cliente:
            print("ℹ️ Coluna 'Cliente' não encontrada em clientes_status — sem filtro de ativos nem fotos.")
            return foto_map, active_set

        tmp_cols = [col_cliente]
        if col_status:  tmp_cols.append(col_status)
        if col_foto:    tmp_cols.append(col_foto)
        if col_familia: tmp_cols.append(col_familia)

        tmp = df_status[tmp_cols].copy()
        rename_map = {col_cliente: "Cliente"}
        if col_status:  rename_map[col_status] = "Status"
        if col_foto:    rename_map[col_foto] = "Foto"
        if col_familia: rename_map[col_familia] = "Família"
        tmp.rename(columns=rename_map, inplace=True)

        tmp["k"] = tmp["Cliente"].astype(str).map(_norm)

        if "Foto" in tmp.columns:
            foto_map = {r["k"]: str(r.get("Foto","")).strip()
                        for _, r in tmp.iterrows() if str(r.get("Foto","")).strip()}
            print(f"🖼️ Fotos encontradas: {len(foto_map)}")

        if "Status" in tmp.columns:
            def is_ativo(v):
                v = (str(v or "").strip())
                v_norm = unicodedata.normalize("NFD", v)
                v_norm = "".join(ch for ch in v_norm if unicodedata.category(ch) != "Mn")
                return v_norm.casefold() == "ativo"
            active_set = {r["k"] for _, r in tmp.iterrows() if is_ativo(r.get("Status",""))}
            print(f"✅ Clientes marcados como ATIVOS: {len(active_set)}")
        else:
            print("ℹ️ Coluna 'Status' não encontrada — sem filtro de ativos.")
    except Exception as e:
        print("⚠️ Erro lendo STATUS_ABA:", e)

    return foto_map, active_set

# =========================
# Núcleo do processamento (1 execução)
# =========================
def run_once():
    print(f"▶️ Iniciando run_once… ({now_br_str()})")
    abas = {w.title: w for w in sh.worksheets()}
    if ABA_BASE not in abas:
        fail(f"Aba '{ABA_BASE}' não encontrada.")
    ws_base = abas[ABA_BASE]

    df_base = get_as_dataframe(ws_base, evaluate_formulas=True, dtype=str).fillna("")
    if "Cliente" not in df_base.columns or "Data" not in df_base.columns:
        fail("Aba base precisa das colunas 'Cliente' e 'Data'.")

    # Status/Fotos/Ativos
    foto_map, active_set = load_status_and_photos(abas)

    # Preparar base (1 visita por dia / por cliente)
    df = df_base.copy()
    df["__dt"] = df["Data"].apply(parse_dt_cell)
    df = df.dropna(subset=["__dt"])
    df["__dt"] = pd.to_datetime(df["__dt"])
    if df.empty:
        print("⚠️ Base vazia após parse de datas.")
        return

    df["_date_only"] = pd.to_datetime(df["__dt"]).dt.date
    df["_cliente_norm"] = df["Cliente"].astype(str).str.strip()
    df = df[df["_cliente_norm"] != ""]

    # Aplica filtro de ATIVOS
    if active_set:
        before = len(df)
        df = df[df["_cliente_norm"].map(lambda x: _norm(x) in active_set)]
        print(f"🧹 Filtro de ativos aplicado: {before} → {len(df)} linhas.")
        if df.empty:
            print("ℹ️ Nenhuma linha após filtro de ativos.")
            return

    # Monta métricas por cliente
    rows = []
    today = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().tz_localize(None)

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
        return

    # Cache
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

    # Relatório diário (cards)
    def daily_summary_and_lists():
        total = len(ultimo)
        em_dia = (ultimo["status_atual"]=="Em dia").sum()
        pouco  = (ultimo["status_atual"]=="Pouco atrasado").sum()
        muito  = (ultimo["status_atual"]=="Muito atrasado").sum()

        if SEND_DAILY_HEADER:
            header = (
                "<b>📊 Relatório de Frequência — Salão JP</b>\n"
                f"Data/hora: {html.escape(now_br_str())}\n\n"
                f"👥 Ativos (c/ média): <b>{total}</b>\n"
                f"🟢 Em dia: <b>{em_dia}</b>\n"
                f"🟠 Pouco atrasado: <b>{pouco}</b>\n"
                f"🔴 Muito atrasado: <b>{muito}</b>"
            )
            tg_send(header)

        def enviar_cards(bucket_name, emoji):
            subset = ultimo.loc[ultimo["status_atual"]==bucket_name].copy()
            if subset.empty:
                return
            subset = subset.sort_values("dias_desde_ultima", ascending=False)
            for r in subset.itertuples(index=False):
                caption = make_card_caption(
                    nome=r.Cliente,
                    status_label=bucket_name,
                    status_emoji=emoji + " ",
                    ultima_dt=r.ultima_visita,
                    media=float(r.media_dias),
                    dias_desde_ultima=int(r.dias_desde_ultima),
                )
                foto = foto_map.get(_norm(r.Cliente))
                if foto:
                    tg_send_photo(foto, caption)
                else:
                    tg_send(caption)

        if SEND_LIST_POUCO:
            enviar_cards("Pouco atrasado", "🟠")
        if SEND_LIST_MUITO:
            enviar_cards("Muito atrasado", "🔴")

    # Transições + Feedback
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
            # cached_dt = cached["ultima_visita_cache_parsed"] if cached is not None else None
            cached_visitas = int(cached["visitas_total_cache"]) if (cached is not None and str(cached.get("visitas_total_cache","")).strip().isdigit()) else 0

            # controle de 1 feedback por visita
            ultima_key = pd.to_datetime(ultima).strftime("%Y-%m-%d")
            feedback_already_sent = False
            if FEEDBACK_ONCE_PER_VISIT and cached is not None:
                sent_for = (cached.get("feedback_sent_for_date") or "").strip()
                feedback_already_sent = (sent_for == ultima_key)

            # Nova visita
            new_visit = visitas_total > cached_visitas

            # regras para enviar feedback (com foto)
            estava_atrasado = cached_status in ("Pouco atrasado", "Muito atrasado")
            enviar_feedback = False
            if SEND_FEEDBACK_ON_NEW_VISIT_ALL:
                enviar_feedback = True
            elif SEND_FEEDBACK_ONLY_IF_WAS_LATE and estava_atrasado:
                enviar_feedback = True

            if new_visit and enviar_feedback and not feedback_already_sent:
                caption = make_card_caption(
                    nome=nome,
                    status_label=status if not estava_atrasado else cached_status,
                    status_emoji=(row.status_emoji or ""),
                    ultima_dt=ultima,
                    media=media,
                    dias_desde_ultima=dias
                )
                foto = foto_map.get(_norm(nome))
                if foto:
                    tg_send_photo(foto, caption)
                else:
                    tg_send(caption)

                if cached is not None:
                    cached["feedback_sent_for_date"] = ultima_key

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

        for txt in transicoes[:30]:
            tg_send(txt)

        # Atualiza cache preservando feedback_sent_for_date quando possível
        out = ultimo[["Cliente","ultima_visita","status_atual","media_dias","visitas_total"]].copy()
        out["ultima_visita"] = pd.to_datetime(out["ultima_visita"]).dt.strftime("%Y-%m-%d")
        out.rename(columns={
            "ultima_visita":"ultima_visita_cache",
            "status_atual":"status_cache",
            "media_dias":"media_cache",
            "visitas_total":"visitas_total_cache"
        }, inplace=True)
        out["last_notified_at"] = now_br_str()

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

    # MODO INDIVIDUAL
    CLIENTE = os.getenv("CLIENTE") or os.getenv("INPUT_CLIENTE")
    if CLIENTE:
        alvo = _norm(CLIENTE)
        if active_set and (alvo not in active_set):
            tg_send(f"⚠️ Cliente '{html.escape(CLIENTE)}' está marcado como inativo — nenhum alerta enviado.")
            print("ℹ️ Cliente inativo; execução individual encerrada.")
            return
        ultimo["_norm"] = ultimo["Cliente"].apply(_norm)
        sel = ultimo[ultimo["_norm"] == alvo]
        if sel.empty:
            sel = ultimo[ultimo["_norm"].str.contains(alvo, na=False)]
        if sel.empty:
            tg_send(f"⚠️ Cliente '{html.escape(CLIENTE)}' não encontrado com histórico suficiente.")
            return
        row = sel.sort_values("ultima_visita", ascending=False).iloc[0]
        caption = make_card_caption(
            nome=row["Cliente"],
            status_label=row.get("status_atual") or "",
            status_emoji=row.get("status_emoji") or "",
            ultima_dt=row["ultima_visita"],
            media=float(row["media_dias"]),
            dias_desde_ultima=int(row["dias_desde_ultima"])
        )
        foto = foto_map.get(_norm(row["Cliente"]))
        if foto:
            tg_send_photo(foto, caption)
        else:
            tg_send(caption)
        print("✅ Alerta individual enviado.")
        return

    # Execução padrão (lista + mudanças)
    if SEND_DAILY_HEADER or SEND_LIST_POUCO or SEND_LIST_MUITO:
        daily_summary_and_lists()
    changes_and_feedback()
    print("✅ run_once concluído.")

# =========================
# Scheduler simples (sem libs externas)
# =========================
def _seconds_until_next_run(hour_local: int) -> int:
    tz = pytz.timezone(TZ)
    now = datetime.now(tz)
    run_today = now.replace(hour=hour_local, minute=0, second=0, microsecond=0)
    if now >= run_today:
        run_today = run_today + timedelta(days=1)
    delta = (run_today - now).total_seconds()
    return int(delta)

def main():
    if RUN_ONCE:
        run_once()
        return

    if not RUN_LOOP:
        print("ℹ️ RUN_LOOP desativado e RUN_ONCE=0 — nada a fazer. Saindo.")
        return

    print(f"🕗 Agendado para rodar diariamente às {RUN_AT_HOUR:02d}:00 ({TZ}). Ctrl+C para sair.")
    while True:
        try:
            secs = _seconds_until_next_run(RUN_AT_HOUR)
            hrs = secs // 3600
            mins = (secs % 3600) // 60
            print(f"⏳ Próxima execução em ~{hrs}h{mins:02d}m ({now_br_str()}).")
            # Dorme em blocos para poder imprimir algo de tempos em tempos
            while secs > 0:
                step = min(secs, 300)  # dorme no máximo 5 min por vez
                time.sleep(step)
                secs -= step
            # Hora de rodar
            run_once()
        except KeyboardInterrupt:
            print("\n🛑 Encerrado pelo usuário.")
            break
        except Exception as e:
            print(f"⚠️ Erro no loop principal: {e}")
            # espera 1 minuto antes de tentar de novo
            time.sleep(60)

# =========================
# ENTRYPOINT
# =========================
if __name__ == "__main__":
    main()

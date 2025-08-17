# notify_frequencia.py
# Lê Google Sheets, calcula frequência e envia resumo + listas no Telegram.

import os, json, html
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime
import pytz

# ====== VARS (dos GitHub Secrets) ======
SHEET_ID   = os.getenv("SHEET_ID", "")
BASE_ABA   = os.getenv("BASE_ABA", "Base de Dados")
STATUS_ABA = os.getenv("STATUS_ABA", "clientes_status")
GCP_SERVICE_ACCOUNT_JSON = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
TZ = os.getenv("TIMEZONE", "America/Sao_Paulo")

def tlog(*args): print("🔎", *args)

# ====== TELEGRAM (parse_mode=HTML) ======
def tg_send(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        tlog("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID ausentes.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",                # << HTML mais estável que Markdown
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=25)
    tlog("Telegram resp:", r.text)
    return r.ok

# ====== SHEETS ======
def conectar_sheets():
    if not GCP_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON não configurado.")
    info = json.loads(GCP_SERVICE_ACCOUNT_JSON)
    scopes = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def carregar_base():
    sh = conectar_sheets()
    ws = sh.worksheet(BASE_ABA)
    df = get_as_dataframe(ws).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    if "Data" not in df.columns or "Cliente" not in df.columns:
        raise RuntimeError("Aba 'Base de Dados' precisa de colunas 'Data' e 'Cliente'.")
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    tlog(f"Base: {len(df)} linhas válidas.")
    return df

def carregar_status():
    sh = conectar_sheets()
    try:
        ws = sh.worksheet(STATUS_ABA)
    except Exception:
        tlog("Aba de status não encontrada; seguindo sem filtro de 'Ativo'.")
        return pd.DataFrame(columns=["Cliente", "Status"])
    stt = get_as_dataframe(ws).dropna(how="all")
    stt.columns = [str(c).strip() for c in stt.columns]
    if "Cliente" not in stt.columns or "Status" not in stt.columns:
        raise RuntimeError("Aba 'clientes_status' precisa de colunas 'Cliente' e 'Status'.")
    stt["Cliente"] = stt["Cliente"].astype(str).str.strip()
    stt["Status"]  = stt["Status"].astype(str).str.strip()
    tlog(f"Status: {len(stt)} linhas.")
    return stt[["Cliente","Status"]]

# ====== FREQUÊNCIA ======
def calcular_frequencia(df_base, df_status):
    if not df_status.empty:
        ativos = set(df_status[df_status["Status"].str.lower()=="ativo"]["Cliente"])
        df_base = df_base[df_base["Cliente"].isin(ativos)]
        tlog(f"Filtrados 'Ativo': {len(df_base)} linhas.")
    atend = df_base.drop_duplicates(subset=["Cliente","Data"]).copy()
    hoje = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize().date()
    out = []
    for cliente, g in atend.groupby("Cliente"):
        datas = sorted(g["Data"].tolist())
        if len(datas) < 2:   # precisa de 2 para média
            continue
        diffs = [(datas[i]-datas[i-1]).days for i in range(1,len(datas))]
        media = sum(diffs)/len(diffs)
        ultimo = datas[-1].date()
        dias = (hoje - ultimo).days
        if dias <= media:
            label, emoji = "Em dia", "🟢"
        elif dias <= media*1.5:
            label, emoji = "Pouco atrasado", "🟠"
        else:
            label, emoji = "Muito atrasado", "🔴"
        out.append({
            "Cliente": cliente,
            "Status_Label": label,
            "Status": f"{emoji} {label}",
            "Último Atendimento": ultimo,
            "Qtd Atendimentos": len(datas),
            "Frequência Média (dias)": round(media,1),
            "Dias Desde Último": dias,
        })
    df = pd.DataFrame(out)
    tlog(f"Clientes com frequência calculada: {len(df)}")
    return df

# ====== MENSAGENS ======
def enviar_resumo_e_listas(freq_df: pd.DataFrame) -> bool:
    tot   = freq_df["Cliente"].nunique()
    n_ok  = freq_df[freq_df["Status_Label"]=="Em dia"]["Cliente"].nunique()
    n_p   = freq_df[freq_df["Status_Label"]=="Pouco atrasado"]["Cliente"].nunique()
    n_m   = freq_df[freq_df["Status_Label"]=="Muito atrasado"]["Cliente"].nunique()

    # resumo (HTML)
    msg_resumo = (
        "<b>📊 Relatório de Frequência — Salão JP</b>\n"
        f"👥 Ativos: <b>{tot}</b>\n"
        f"🟢 Em dia: <b>{n_ok}</b>\n"
        f"🟠 Pouco atrasado: <b>{n_p}</b>\n"
        f"🔴 Muito atrasado: <b>{n_m}</b>"
    )
    tlog("Resumo:\n", msg_resumo)
    ok1 = tg_send(msg_resumo)

    def lista(titulo, df):
        if df.empty:
            tlog(f"Lista vazia: {titulo}")
            return True
        nomes = "\n".join(f"- {html.escape(str(n))}" for n in df["Cliente"].tolist())
        msg = f"<b>{titulo}</b>\n{nomes}"
        tlog("Lista:\n", msg)
        return tg_send(msg)

    ok2 = lista("🟠 Pouco atrasados",
                freq_df[freq_df["Status_Label"]=="Pouco atrasado"][["Cliente"]])
    ok3 = lista("🔴 Muito atrasados",
                freq_df[freq_df["Status_Label"]=="Muito atrasado"][["Cliente"]])

    return ok1 and ok2 and ok3

# ====== MAIN ======
if __name__ == "__main__":
    try:
        agora = datetime.now(pytz.timezone(TZ))
        tlog("Rodando em:", agora.isoformat())

        if not SHEET_ID:
            raise RuntimeError("SHEET_ID ausente nos Secrets.")

        df_base = carregar_base()
        df_stat = carregar_status()
        freq_df = calcular_frequencia(df_base, df_stat)
        if freq_df.empty:
            tlog("Nenhum cliente com dados suficientes para cálculo (freq_df vazio).")
            raise SystemExit(2)

        ok = enviar_resumo_e_listas(freq_df)
        if not ok:
            tlog("Falha no envio (Telegram).")
            raise SystemExit(3)

        tlog("✅ Envio concluído.")
    except Exception as e:
        tlog("💥 ERRO:", e)
        raise

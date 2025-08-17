# scripts/notify_frequencia.py
import os
import sys
import json
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime
import pytz

def env_or_fail(key: str) -> str:
    val = os.getenv(key)
    if not val:
        raise RuntimeError(f"Variável de ambiente ausente: {key}")
    return val

def connect_gsheet(sheet_id: str, sa_info: dict):
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(sa_info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(sheet_id)

def br_now(tz="America/Sao_Paulo") -> str:
    return datetime.now(pytz.timezone(tz)).strftime("%d/%m/%Y %H:%M:%S")

def load_dataframe(sh, tab_names=("Base de Dados", "clientes_status")):
    # Lê as abas; se alguma não existir, lança erro claro
    abas = {w.title.lower(): w for w in sh.worksheets()}
    def pick(name_options):
        for name in name_options:
            w = abas.get(name.lower())
            if w:
                return get_as_dataframe(w, evaluate_formulas=True, dtype=str).fillna("")
        raise RuntimeError(f"Aba não encontrada: {name_options}")
    base = pick([tab_names[0]])
    status = pick([tab_names[1]])
    return base, status

def build_message(df_base: pd.DataFrame) -> str:
    # EXEMPLO simples: clientes com mais de 60 dias sem vir
    if "Cliente" not in df_base.columns or "Data" not in df_base.columns:
        raise RuntimeError("Colunas esperadas 'Cliente' e 'Data' não encontradas na Base de Dados.")
    # normaliza datas
    def parse_dt(x):
        x = (x or "").strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(x, fmt).date()
            except Exception:
                pass
        return None

    df = df_base.copy()
    df["__dt"] = df["Data"].apply(parse_dt)
    df = df.dropna(subset=["__dt"])
    df["__dt"] = pd.to_datetime(df["__dt"])

    ultimo = df.groupby("Cliente", as_index=False)["__dt"].max()
    dias = (pd.Timestamp.now().normalize() - ultimo["__dt"]).dt.days
    ultimo["dias_sem_vir"] = dias

    atrasados = ultimo[ultimo["dias_sem_vir"] >= 60].sort_values("dias_sem_vir", ascending=False)
    if atrasados.empty:
        return f"✅ {br_now()} — Ninguém com 60+ dias sem vir."

    linhas = [f"📣 {br_now()} — Clientes com 60+ dias sem vir:"]
    for _, row in atrasados.iterrows():
        linhas.append(f"• {row['Cliente']}: {int(row['dias_sem_vir'])} dias")
    return "\n".join(linhas)

def send_telegram(token: str, chat_id: str, text: str):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": text})
    if not resp.ok:
        raise RuntimeError(f"Falha no Telegram: {resp.status_code} {resp.text}")

def main():
    try:
        sheet_id = env_or_fail("SHEET_ID")
        token = env_or_fail("TELEGRAM_TOKEN")
        chat_id = env_or_fail("TELEGRAM_CHAT_ID")
        sa_json = env_or_fail("GCP_SERVICE_ACCOUNT")

        try:
            sa_info = json.loads(sa_json)
        except json.JSONDecodeError:
            # caso o secret tenha vindo com quebras/escapes estranhos
            sa_info = json.loads(sa_json.encode("utf-8").decode("unicode_escape"))

        sh = connect_gsheet(sheet_id, sa_info)
        base, _status = load_dataframe(sh, ("Base de Dados", "clientes_status"))

        msg = build_message(base)
        send_telegram(token, chat_id, msg)

        print("OK:", msg.splitlines()[0] if msg else "Mensagem enviada.")
        sys.exit(0)  # sucesso

    except Exception as e:
        # Nunca sai com 3; sempre 1 em erro para padronizar no Actions
        print(f"ERRO: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

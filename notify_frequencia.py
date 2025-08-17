# notify_frequencia.py
# Executa diariamente: lê Google Sheets, calcula frequência e envia resumo/listas no Telegram.

import os
import json
import pandas as pd
import requests
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
from datetime import datetime
import pytz
import re

# =========================
# CONFIG POR VARIÁVEIS DE AMBIENTE (use GitHub Secrets)
# =========================
SHEET_ID   = os.getenv("SHEET_ID", "1qtOF1I7Ap4By2388ySThoVlZHbI3rAJv_haEcil0IUE")
BASE_ABA   = os.getenv("BASE_ABA", "Base de Dados")
STATUS_ABA = os.getenv("STATUS_ABA", "clientes_status")

# JSON do Service Account inteiro em uma única variável
GCP_SERVICE_ACCOUNT_JSON = os.getenv("GCP_SERVICE_ACCOUNT_JSON", "")
# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Timezone (Brasil)
TZ = os.getenv("TIMEZONE", "America/Sao_Paulo")

# ---------------- Markdown helpers ----------------
MD_CHARS = r"_*[]()~`>#+-=|{}.!"
MD_ESCAPER = re.compile("([\\_\\*\\[\\]\\(\\)\\~\\`\\>\\#\\+\\-\\=\\|\\{\\}\\.\\!])")

def md_escape(text: str) -> str:
    if text is None:
        return ""
    return MD_ESCAPER.sub(r"\\\1", str(text))

# ---------------- Telegram ----------------
def notificar(mensagem: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID ausentes.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    try:
        print("➡️ Enviando para Telegram...")
        r = requests.post(url, json=payload, timeout=20)
        print("Resposta do Telegram:", r.text)
        return r.ok
    except Exception as e:
        print("❌ Erro Telegram:", e)
        return False

# ---------------- Sheets ----------------
def conectar_sheets():
    if not GCP_SERVICE_ACCOUNT_JSON:
        raise RuntimeError("GCP_SERVICE_ACCOUNT_JSON não configurado.")
    info = json.loads(GCP_SERVICE_ACCOUNT_JSON)
    scopes = ["https://spreadsheets.google.com/feeds",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    return gc.open_by_key(SHEET_ID)

def carregar_dados():
    sh = conectar_sheets()
    ws = sh.worksheet(BASE_ABA)
    df = get_as_dataframe(ws).dropna(how="all")
    df.columns = [str(c).strip() for c in df.columns]
    if "Data" not in df.columns:
        raise RuntimeError("Coluna 'Data' não encontrada na aba Base de Dados.")
    if "Cliente" not in df.columns:
        raise RuntimeError("Coluna 'Cliente' não encontrada na aba Base de Dados.")
    df["Data"] = pd.to_datetime(df["Data"], errors="coerce")
    df = df.dropna(subset=["Data"])
    df["Cliente"] = df["Cliente"].astype(str).str.strip()
    print(f"✅ Base carregada: {len(df)} linhas válidas.")
    return df

def carregar_status():
    sh = conectar_sheets()
    try:
        ws = sh.worksheet(STATUS_ABA)
    except Exception:
        print("ℹ️ Aba de status não encontrada; seguindo sem filtro de 'Ativo'.")
        return pd.DataFrame(columns=["Cliente", "Status"])
    stt = get_as_dataframe(ws).dropna(how="all")
    stt.columns = [str(c).strip() for c in stt.columns]
    if "Cliente" not in stt.columns or "Status" not in stt.columns:
        poss_cliente = [c for c in stt.columns if c.lower() == "cliente"]
        poss_status  = [c for c in stt.columns if c.lower() == "status"]
        if poss_cliente:
            stt = stt.rename(columns={poss_cliente[0]: "Cliente"})
        if poss_status:
            stt = stt.rename(columns={poss_status[0]: "Status"})
    stt["Cliente"] = stt.get("Cliente", "").astype(str).str.strip()
    stt["Status"]  = stt.get("Status", "").astype(str).str.strip()
    print(f"✅ Status carregado: {len(stt)} linhas.")
    return stt[["Cliente", "Status"]]

# ---------------- Lógica de frequência ----------------
def calcular_frequencia(df_base, df_status):
    if not df_status.empty:
        ativos = set(df_status[df_status["Status"].str.lower() == "ativo"]["Cliente"].tolist())
        df_base = df_base[df_base["Cliente"].isin(ativos)]
        print(f"🧹 Filtrados 'Ativo': {len(df_base)} linhas sobram.")

    atendimentos = df_base.drop_duplicates(subset=["Cliente", "Data"]).copy()

    hoje = pd.Timestamp.now(tz=pytz.timezone(TZ)).normalize()
    resultados = []

    for cliente, grupo in atendimentos.groupby("Cliente"):
        datas = sorted(grupo["Data"].tolist())
        if len(datas) < 2:
            continue
        diffs = [(datas[i] - datas[i-1]).days for i in range(1, len(datas))]
        media = sum(diffs) / len(diffs)
        ultimo = datas[-1]
        dias_sem_vir = (hoje.date() - ultimo.date()).days

        if dias_sem_vir <= media:
            status = ("🟢 Em dia", "Em dia")
        elif dias_sem_vir <= media * 1.5:
            status = ("🟠 Pouco atrasado", "Pouco atrasado")
        else:
            status = ("🔴 Muito atrasado", "Muito atrasado")

        resultados.append({
            "Status": status[0],
            "Status_Label": status[1],
            "Cliente": cliente,
            "Último Atendimento": ultimo.date(),
            "Qtd Atendimentos": len(datas),
            "Frequência Média (dias)": round(media, 1),
            "Dias Desde Último": dias_sem_vir
        })

    df_out = pd.DataFrame(resultados)
    print(f"📦 Clientes com frequência calculada: {len(df_out)}")
    return df_out

def enviar_resumo_e_listas(freq_df: pd.DataFrame):
    tot = freq_df["Cliente"].nunique()
    n_ok = freq_df[freq_df["Status_Label"] == "Em dia"]["Cliente"].nunique()
    n_pouco = freq_df[freq_df["Status_Label"] == "Pouco atrasado"]["Cliente"].nunique()
    n_muito = freq_df[freq_df["Status_Label"] == "Muito atrasado"]["Cliente"].nunique()

    msg_resumo = (
        "*📊 Relatório de Frequência — Salão JP*\n"
        f"👥 Ativos: *{tot}*\n"
        f"🟢 Em dia: *{n_ok}*\n"
        f"🟠 Pouco atrasado: *{n_pouco}*\n"
        f"🔴 Muito atrasado: *{n_muito}*"
    )
    print("📝 Resumo:\n", msg_resumo)
    ok1 = notificar(msg_resumo)

    def lista(txt, df):
        if df.empty:
            print(f"ℹ️ Lista vazia: {txt}")
            return True
        nomes = "\n".join(f"- {md_escape(n)}" for n in df["Cliente"].tolist())
        msg = f"*{txt}*\n{nomes}"
        print("📝 Lista:\n", msg)
        return notificar(msg)

    ok2 = lista("🟠 Pouco atrasados", freq_df[freq_df["Status_Label"] == "Pouco atrasado"][["Cliente"]])
    ok3 = lista("🔴 Muito atrasados", freq_df[freq_df["Status_Label"] == "Muito atrasado"][["Cliente"]])

    return ok1 and ok2 and ok3

# ---------------- Main ----------------
if __name__ == "__main__":
    try:
        tz = pytz.timezone(TZ)
        agora = datetime.now(tz)
        print("🕗 Rodando em:", agora.isoformat())

        df_base = carregar_dados()
        df_stt  = carregar_status()

        freq_df = calcular_frequencia(df_base, df_stt)
        if freq_df.empty:
            print("⚠️ Nenhum cliente com dados suficientes para cálculo de frequência.")
            raise SystemExit(2)

        sucesso = enviar_resumo_e_listas(freq_df)
        if not sucesso:
            print("❌ Envio teve falhas (verifique token/chat do Telegram e formatação).")
            raise SystemExit(3)

        print("✅ Envio concluído.")
    except Exception as e:
        print("💥 Erro fatal:", e)
        raise

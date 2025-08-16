import requests

TELEGRAM_BOT_TOKEN = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
TELEGRAM_CHAT_ID   = 439747253

def send_telegram(text: str) -> tuple[bool, str]:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=15)
        if r.ok:
            return True, "ok"
        return False, f"{r.status_code}: {r.text[:200]}"
    except Exception as e:
        return False, str(e)

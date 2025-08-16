import requests

TOKEN = "8257359388:AAGayJElTPT0pQadtamVf8LoL7R6EfWzFGE"
CHAT_ID = 439747253

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = {"chat_id": CHAT_ID, "text": "🔔 Funcionou agora pelo Python!"}

r = requests.post(url, json=data, timeout=15)
print(r.status_code, r.text)

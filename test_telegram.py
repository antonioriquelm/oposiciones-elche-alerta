import os
import urllib.request
import urllib.parse

token = os.environ["TELEGRAM_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

mensaje = "✅ Monitor de oposiciones conectado correctamente."

url = f"https://api.telegram.org/bot{token}/sendMessage"

datos = urllib.parse.urlencode({
    "chat_id": chat_id,
    "text": mensaje
}).encode()

urllib.request.urlopen(url, data=datos)

print("Mensaje enviado correctamente")

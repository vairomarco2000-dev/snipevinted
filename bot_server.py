import os
import json
import time
import requests
from flask import Flask, request
import gspread

app = Flask(__name__)

# Recupera le configurazioni dalle variabili d'ambiente di Render
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

# Configurazione Google Sheets con gspread
def get_sheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open_by_key(SPREADSHEET_ID)
        return sh.sheet1
    except Exception as e:
        print(f"Errore connessione Google Sheets: {e}")
        return None

# Funzione per inviare messaggi su Telegram con i 3 pulsanti
def send_telegram_alert(text, item_url, item_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    reply_markup = {
        "inline_keyboard": [
            [{"text": "🔗 Apri su Vinted", "url": item_url}],
            [
                {"text": "✅ Acquistato", "callback_data": f"buy_{item_id}"},
                {"text": "⭐ Salva", "callback_data": f"save_{item_id}"},
                {"text": "❌ Scarta", "callback_data": f"dismiss_{item_id}"}
            ]
        ]
    }
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(reply_markup)
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

# Webhook per ricevere i clic dai pulsanti di Telegram
@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    
    # Gestione dei clic sui pulsanti (Callback Query)
    if "callback_query" in update:
        query = update["callback_query"]
        callback_data = query["data"]
        chat_id = query["message"]["chat"]["id"]
        message_id = query["message"]["message_id"]
        original_text = query["message"]["text"]
        
        # 1. Pulsante SCARTA (Elimina il messaggio)
        if callback_data.startswith("dismiss_"):
            delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
            requests.post(delete_url, json={"chat_id": chat_id, "message_id": message_id})
            
        # 2. Pulsante SALVA (Mette la stella)
        elif callback_data.startswith("save_"):
            edit_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
            new_text = f"⭐ <b>[SALVATO]</b>\n\n{original_text}"
            requests.post(edit_url, json={
                "chat_id": chat_id, 
                "message_id": message_id, 
                "text": new_text, 
                "parse_mode": "HTML"
            })
            
        # 3. Pulsante ACQUISTATO (Chiede il prezzo e registra sul foglio)
        elif callback_data.startswith("buy_"):
            # Per semplicità immediata, salviamo una riga di test sul foglio
            sheet = get_sheet()
            if sheet:
                today = time.strftime("%d/%m/%Y")
                # Esempio di riga inserita: [Data, Sorgente, Titolo, Prezzo, ...]
                sheet.append_row([today, "Bot Telegram", "Articolo Vinted", 15.00, 0, 15.00, "", "", "", "", "In Arrivo", ""])
            
            edit_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
            new_text = f"✅ <b>[REGISTRATO NEL FOGLIO]</b>\n\n{original_text}"
            requests.post(edit_url, json={
                "chat_id": chat_id, 
                "message_id": message_id, 
                "text": new_text, 
                "parse_mode": "HTML"
            })
            
        # Risponde a Telegram per chiudere l'animazione di caricamento del pulsante
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id": query["id"]})
        
    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "Bot Vinted Interattivo attivo h24!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

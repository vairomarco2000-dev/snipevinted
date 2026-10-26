import os
import json
import time
import requests
from flask import Flask, request
import gspread

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

# Dizionario temporaneo per ricordare l'articolo che stai registrando
PENDING_PURCHASES = {}

def get_sheet():
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        gc = gspread.service_account_from_dict(creds_dict)
        sh = gc.open_by_key(SPREADSHEET_ID)
        return sh.sheet1
    except Exception as e:
        print(f"Errore connessione Google Sheets: {e}")
        return None

@app.route(f"/{TELEGRAM_TOKEN}", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    
    # 1. GESTIONE PULSANTI INTERATTIVI
    if "callback_query" in update:
        query = update["callback_query"]
        callback_data = query["data"]
        chat_id = str(query["message"]["chat"]["id"])
        message_id = query["message"]["message_id"]
        original_text = query["message"]["text"]
        
        # ❌ SCARTA
        if callback_data.startswith("dismiss_"):
            delete_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage"
            requests.post(delete_url, json={"chat_id": chat_id, "message_id": message_id})
            
        # ⭐ SALVA
        elif callback_data.startswith("save_"):
            edit_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
            new_text = f"⭐ <b>[SALVATO NEI PREFERITI]</b>\n\n{original_text}"
            requests.post(edit_url, json={
                "chat_id": chat_id, 
                "message_id": message_id, 
                "text": new_text, 
                "parse_mode": "HTML"
            })
            
        # ✅ ACQUISTATO
        elif callback_data.startswith("buy_"):
            # Memorizza il messaggio e l'ID della chat
            PENDING_PURCHASES[chat_id] = {
                "original_text": original_text,
                "message_id": message_id
            }
            
            # Chiede unicamente il prezzo d'acquisto effettivo
            msg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(msg_url, json={
                "chat_id": chat_id,
                "text": "💰 <b>Inserisci il prezzo pagato d'acquisto</b> (es. 15 o 17.50):",
                "parse_mode": "HTML"
            })
            
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id": query["id"]})
        
    # 2. GESTIONE PREZZO E REGISTRAZIONE
    elif "message" in update:
        message = update["message"]
        chat_id = str(message["chat"]["id"])
        
        if chat_id in PENDING_PURCHASES and "text" in message:
            text_input = message["text"].replace(",", ".").strip()
            
            try:
                buy_price = float(text_input)
                purchase_info = PENDING_PURCHASES.pop(chat_id)
                original_text = purchase_info["original_text"]
                message_id = purchase_info["message_id"]
                
                # 1. Scrittura su Google Sheets (Registra Data, Titolo/Dettagli originali, Prezzo d'acquisto e Stato)
                sheet = get_sheet()
                if sheet:
                    today = time.strftime("%d/%m/%Y")
                    sheet.append_row([
                        today, 
                        "Vinted Bot", 
                        original_text[:100].replace('\n', ' '), 
                        buy_price, 
                        0, 
                        buy_price, 
                        "", 
                        "", "", "", 
                        "In Arrivo", 
                        ""
                    ])
                
                # 2. Aggiornamento del messaggio su Telegram (Mantiene l'articolo e la stima originale, aggiungendo il prezzo d'acquisto)
                edit_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText"
                updated_card = (
                    f"✅ <b>[ARTICOLO ACQUISTATO]</b>\n\n"
                    f"{original_text}\n\n"
                    f"-------------------------------\n"
                    f"💳 <b>Prezzo d'acquisto effettivo:</b> {buy_price:.2f}€\n"
                    f"📊 <b>Stato:</b> Registrato su Google Sheets (In Arrivo)"
                )
                requests.post(edit_url, json={
                    "chat_id": chat_id, 
                    "message_id": message_id, 
                    "text": updated_card, 
                    "parse_mode": "HTML"
                })
                
                # 3. Messaggio rapido di conferma
                msg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                requests.post(msg_url, json={
                    "chat_id": chat_id,
                    "text": f"🎉 <b>Acquisto registrato con successo a {buy_price:.2f}€!</b>",
                    "parse_mode": "HTML"
                })
                
            except ValueError:
                msg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                requests.post(msg_url, json={
                    "chat_id": chat_id,
                    "text": "⚠️ Inserisci un numero valido per il prezzo d'acquisto (es. 15 o 12.50):"
                })

    return "OK", 200

@app.route("/", methods=["GET"])
def home():
    return "Bot Vinted Interattivo attivo h24!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

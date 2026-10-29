import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")
SHEET_NAME = os.environ.get("SHEET_NAME", "Vinted_Resell")

def get_gspread_client():
    if not GOOGLE_CREDENTIALS_JSON:
        return None
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def log_to_sheets(action, item_id, price, profit):
    try:
        client = get_gspread_client()
        if not client:
            return False
        sheet = client.open(SHEET_NAME).sheet1
        sheet.append_row([action, item_id, price, profit])
        return True
    except Exception as e:
        print(f"Errore scrittura Google Sheets: {e}")
        return False

@app.route("/", methods=["GET"])
def home():
    return "Server Telegram/Sheets Attivo", 200

@app.route("/telegram-webhook", methods=["POST"])
def telegram_webhook():
    update = request.get_json()
    if "callback_query" in update:
        callback = update["callback_query"]
        data = callback.get("data", "")
        callback_id = callback.get("id")
        
        parts = data.split("_")
        action = parts[0]
        item_id = parts[1] if len(parts) > 1 else ""
        price = parts[2] if len(parts) > 2 else "0"
        profit = parts[3] if len(parts) > 3 else "0"

        if action in ["buy", "save"]:
            log_to_sheets(action.upper(), item_id, price, profit)
            text_response = f"Registrato come {action.upper()} su Google Sheets!"
        else:
            text_response = "Articolo scartato."

        # Rispondi a Telegram per chiudere l'animazione di caricamento del pulsante
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
        requests.post(url, json={"callback_query_id": callback_id, "text": text_response})

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

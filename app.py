import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

@app.route("/", methods=["GET"])
def home():
    return "Il Bot Vinted Webhook è attivo!", 200

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error"}}, 400

    # Gestione dei click sui bottoni (Callback Query)
    if "callback_query" in data:
        callback = data["callback_query"]
        callback_id = callback["id"]
        data_text = callback["data"]
        chat_id = callback["message"]["chat"]["id"]
        message_id = callback["message"]["message_id"]

        # Interpretiamo l'azione del bottone
        parts = data_text.split("_")
        action = parts[0]

        answer_text = "Operazione registrata!"
        if action == "buy":
            answer_text = "✅ Segnato come acquistato!"
        elif action == "save":
            answer_text = "⭐ Articolo salvato nei preferiti!"
        elif action == "dismiss":
            answer_text = "❌ Articolo scartato."
            try:
                requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage", json={
                    "chat_id": chat_id,
                    "message_id": message_id
                })
            except:
                pass

        # Rispondi a Telegram per fermare la rotellina sul bottone
        answer_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery"
        requests.post(answer_url, json={"callback_query_id": callback_id, "text": answer_text})

    return jsonify({"status": "ok"}}, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

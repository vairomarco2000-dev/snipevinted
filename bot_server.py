import os
import json
import time
import random
import threading
from flask import Flask, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import cloudscraper

app = Flask(__name__)

# --- VARIABILI D'AMBIENTE & CONFIGURAZIONE ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")
SHEET_NAME = os.environ.get("SHEET_NAME", "Vinted_Resell")

SENT_ITEMS_FILE = "sent_items.json"
PENDING_PURCHASES_FILE = "pending_purchases.json"

# Definiamo le ricerche tramite le parole chiave per l'API JSON di Vinted
TARGET_QUERIES = [
    {"name": "Streetwear - Weekend Offender", "query": "weekend offender", "price_to": 45},
    {"name": "Workwear & Denim (Carhartt/Dickies)", "query": "carhartt dickies", "price_to": 45},
    {"name": "Outdoor & Gorpcore (Patagonia/TNF)", "query": "patagonia arcteryx tnf", "price_to": 50},
    {"name": "Collezionismo - Diabolik & Fumetti", "query": "lotto diabolik fumetti vintage", "price_to": 25},
    {"name": "Collezionismo - Album Panini Vintage", "query": "album panini calciatori", "price_to": 35},
    {"name": "Collezionismo - Retrogaming", "query": "giochi ps1 ps2 nintendo", "price_to": 30},
    {"name": "Maglie da Calcio Vintage", "query": "maglia calcio vintage", "price_to": 30},
    {"name": "Sneakers / Brand Selezionati", "query": "sneakers nike adidas jordan", "price_to": 50},
    {"name": "Streetwear Generico", "query": "felpa carhartt stussy supreme", "price_to": 50}
]

def create_scraper():
    return cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )

# --- GOOGLE SHEETS INTEGRATION ---
def get_sheet():
    if not GOOGLE_CREDENTIALS_JSON:
        return None
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        print(f"Errore connessione Google Sheet: {e}", flush=True)
        return None

def append_to_sheet(title, buy_price, est_resell, item_url):
    sheet = get_sheet()
    if not sheet:
        return False
    try:
        today = time.strftime("%Y-%m-%d")
        negative_buy_price = -abs(float(buy_price))
        row = [today, title, negative_buy_price, "", "", est_resell, "=C{row}+E{row}", "In Vendita", item_url]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"Errore scrittura su Google Sheet: {e}", flush=True)
        return False

# --- GESTIONE STATO ---
def load_sent_items():
    if os.path.exists(SENT_ITEMS_FILE):
        try:
            with open(SENT_ITEMS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_sent_item(item_id):
    sent = load_sent_items()
    sent.add(str(item_id))
    sent_list = list(sent)[-500:]
    try:
        with open(SENT_ITEMS_FILE, "w") as f:
            json.dump(sent_list, f)
    except Exception as e:
        print(f"Errore salvataggio sent_items: {e}", flush=True)

def load_pending():
    if os.path.exists(PENDING_PURCHASES_FILE):
        try:
            with open(PENDING_PURCHASES_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_pending(data):
    try:
        with open(PENDING_PURCHASES_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Errore salvataggio pending: {e}", flush=True)

# --- TELEGRAM ---
def send_telegram_alert_with_buttons(title, price, est_price, profit, item_url, item_id):
    scraper = create_scraper()
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    msg = (
        f"🚨 <b>NUOVA OPPORTUNITÀ RESELL!</b>\n\n"
        f"📦 <b>Articolo:</b> {title}\n"
        f"💸 <b>Prezzo Vinted:</b> {price} €\n"
        f"📈 <b>Valore stimato:</b> {est_price} €\n"
        f"💰 <b>Margine netto stimato:</b> +{profit} €\n\n"
        f"🔗 <a href='{item_url}'>Visualizza su Vinted</a>"
    )
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Acquistato", "callback_data": f"buy_{item_id}"},
                {"text": "⭐ Salva", "callback_data": f"save_{item_id}"},
                {"text": "❌ Scarta", "callback_data": f"dismiss_{item_id}"}
            ]
        ]
    }
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "reply_markup": json.dumps(reply_markup)
    }
    try:
        scraper.post(url, data=payload, timeout=5)
        pending = load_pending()
        pending[str(item_id)] = {"title": title, "vinted_price": price, "est_resell": est_price, "url": item_url}
        save_pending(pending)
    except Exception as e:
        print(f"Errore invio Telegram: {e}", flush=True)

def send_telegram_message(chat_id, text):
    scraper = create_scraper()
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        scraper.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"Errore invio messaggio semplice: {e}", flush=True)

# --- GROQ AI ---
def evaluate_deal_with_groq(title, price):
    if not GROQ_API_KEY:
        return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}
        
    scraper = create_scraper()
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    prompt = f"""
    Sei un reseller professionista ed estremamente scettico.
    Analizza questo articolo in vendita su Vinted:
    - Titolo: {title}
    - Prezzo di vendita su Vinted: {price} EUR

    Compito:
    Stima il REALE valore di mercato attuale dell'usato su Vinted/Subito (NON il prezzo da nuovo). 
    Rispondi STRICTLY in formato JSON privo di qualsiasi testo extra con questa struttura esatta:
    {{"estimated_resell_price": 0}}
    """
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    try:
        res = scraper.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            estimated_resell = float(data.get("estimated_resell_price", 0))
            net_profit = estimated_resell - price - 5.0
            is_deal = net_profit >= 10.0
            
            status_str = "APPROVATO (Notifica Inviata!)" if is_deal else "SCARTATO (Margine < 10€)"
            print(f"   └─ [GROQ] Prezzo: {price}€ | Est: {estimated_resell}€ | Profitto: {round(net_profit, 2)}€ -> {status_str}", flush=True)
            return {"is_deal": is_deal, "estimated_resell_price": estimated_resell, "estimated_profit": round(net_profit, 2)}
    except Exception as e:
        print(f"Errore chiamata Groq: {e}", flush=True)
    return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

# --- SCRAPING TRAMITE API JSON UFFICIALE DI VINTED ---
def scrape_and_check():
    sent_items = load_sent_items()
    scraper = create_scraper()
    
    # Inizializziamo la sessione prendendo i cookie iniziali dalla home di Vinted
    try:
        init_res = scraper.get("https://www.vinted.it", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}, timeout=10)
        cookies = scraper.get_cookie_jar()
    except Exception as e:
        print(f"Errore inizializzazione sessione Vinted: {e}", flush=True)
        cookies = None

    for index, target in enumerate(TARGET_QUERIES, 1):
        print(f"--- Controllo {target['name']} ({index}/{len(TARGET_QUERIES)}) ---", flush=True)
        try:
            # Chiamata diretta all'API JSON di Vinted (evita totalmente il blocco HTML/Cloudflare)
            api_url = f"https://www.vinted.it/api/v2/catalog/items?search_text={target['query']}&price_to={target['price_to']}&currency=EUR&order=newest_first"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://www.vinted.it/"
            }
            
            res = scraper.get(api_url, headers=headers, cookies=cookies, timeout=12)
            
            if res.status_code != 200:
                print(f"   └─ Errore API Vinted (Status {res.status_code})", flush=True)
                time.sleep(3)
                continue
                
            data = res.json()
            items = data.get("items", [])
            
            if not items:
                print("   └─ Nessun articolo trovato in questa ricerca.", flush=True)
                continue

            for item in items[:10]:
                item_id = str(item.get("id"))
                if item_id in sent_items:
                    continue
                    
                title = item.get("title", "Articolo Vinted")
                item_url = item.get("url", "")
                
                # Estrazione prezzo dal JSON dell'API
                price_dict = item.get("price", {})
                try:
                    price = float(price_dict.get("amount", 0))
                except (ValueError, TypeError):
                    price = 0.0
                    
                if price <= 0:
                    continue

                lower_text = title.lower()
                bad_keywords = ["ricambi", "non funziona", "rotto", "difettoso", "danneggiato", "da sistemare", "bloccato", "replica", "fake"]
                if any(kw in lower_text for kw in bad_keywords):
                    continue

                print(f"👉 [ESAMINO] {title[:35]} | Prezzo Vinted: {price}€", flush=True)

                eval_res = evaluate_deal_with_groq(title, price)
                
                if eval_res.get("is_deal"):
                    profit = eval_res.get("estimated_profit")
                    est_price = eval_res.get("estimated_resell_price")
                    send_telegram_alert_with_buttons(title, price, est_price, profit, item_url, item_id)
                    save_sent_item(item_id)
                    sent_items.add(item_id)
                
                time.sleep(random.uniform(2.0, 3.5))
                
        except Exception as e:
            print(f"Errore scraping {target['name']}: {e}", flush=True)

def controlla_vinted_periodicamente():
    print(">>> SCRAPER API VINTED AVVIATO SU RENDER (H24) <<<", flush=True)
    while True:
        try:
            scrape_and_check()
        except Exception as e:
            print(f"Errore ciclo generale: {e}", flush=True)
        time.sleep(random.uniform(90.0, 120.0))

# --- AVVIO THREAD ---
thread_scraper = threading.Thread(target=controlla_vinted_periodicamente, daemon=True)
thread_scraper.start()

# --- MESSAGGIO AVVIO ---
try:
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram_message(TELEGRAM_CHAT_ID, "🟢 <b>Bot Vinted (Motore API) avviato!</b>\nNiente più blocchi 403, caccia agli affari attiva.")
except Exception as e:
    print(f"Errore invio test Telegram: {e}", flush=True)

# --- SERVER FLASK ---
user_states = {}

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return "Bot Vinted API attivo h24 su Render!", 200

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json(silent=True)
    if not data:
        return "OK", 200

    if "callback_query" in data:
        cb = data["callback_query"]
        cb_id = cb["id"]
        cb_data = cb.get("data", "")
        chat_id = cb["message"]["chat"]["id"]
        message_id = cb["message"]["message_id"]

        scraper = create_scraper()
        scraper.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb_id})

        if cb_data.startswith("buy_"):
            item_id = cb_data.replace("buy_", "")
            pending = load_pending()
            item_info = pending.get(item_id, {})
            user_states[chat_id] = {"action": "waiting_price", "item_id": item_id, "item_info": item_info}
            send_telegram_message(chat_id, "💰 <b>Inserisci il prezzo pagato d'acquisto</b> (es. 15 o 17.50):")
        elif cb_data.startswith("save_"):
            send_telegram_message(chat_id, "⭐ <b>Articolo salvato nei preferiti!</b>")
        elif cb_data.startswith("dismiss_"):
            scraper.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id})
        return "OK", 200

    if "message" in data and "text" in data["message"]:
        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg["text"].strip()

        if chat_id in user_states and user_states[chat_id].get("action") == "waiting_price":
            state = user_states.pop(chat_id)
            item_info = state.get("item_info", {})
            clean_text = text.replace(",", ".")
            try:
                buy_price = float(clean_text)
                title = item_info.get("title", "Articolo Vinted")
                est_resell = item_info.get("est_resell", 0)
                url = item_info.get("url", "")

                success = append_to_sheet(title, buy_price, est_resell, url)
                if success:
                    send_telegram_message(chat_id, f"✅ <b>Acquisto registrato!</b>\n📦 {title}\n💸 Prezzo registrato: <code>-{buy_price:.2f} €</code> su Google Sheet.")
                else:
                    send_telegram_message(chat_id, "⚠️ Errore Google Sheet.")
            except ValueError:
                send_telegram_message(chat_id, "❌ Prezzo non valido. Riprova.")
        return "OK", 200

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

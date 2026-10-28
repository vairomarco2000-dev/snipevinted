import os
import json
import re
import time
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# --- VARIABILI D'AMBIENTE & CONFIGURAZIONE ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GOOGLE_CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")
SHEET_NAME = os.environ.get("SHEET_NAME", "Vinted_Resell")

SENT_ITEMS_FILE = "sent_items.json"
PENDING_PURCHASES_FILE = "pending_purchases.json"

TARGET_URLS = [
    {
        "name": "Streetwear - Weekend Offender", 
        "url": "https://www.vinted.it/catalog?search_text=weekend+offender&price_to=45.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Workwear & Denim (Carhartt WIP, Dickies)", 
        "url": "https://www.vinted.it/catalog?brand_ids[]=53&brand_ids[]=371&catalog[]=1452&catalog[]=257&catalog[]=30&price_to=45.00&currency=EUR&status_ids[]=1&status_ids[]=2&status_ids[]=6&order=newest_first"
    },
    {
        "name": "Outdoor & Gorpcore (Patagonia, Arc'teryx, Mammut, TNF)", 
        "url": "https://www.vinted.it/catalog?brand_ids[]=2703&brand_ids[]=1775&brand_ids[]=5977&brand_ids[]=364&catalog[]=1452&catalog[]=30&price_to=50.00&currency=EUR&status_ids[]=1&status_ids[]=2&status_ids[]=6&order=newest_first"
    },
    {
        "name": "Collezionismo - Diabolik & Fumetti D'Autore", 
        "url": "https://www.vinted.it/catalog?search_text=lotto+diabolik+fumetti+vintage&price_to=25.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Collezionismo - Album Panini Vintage", 
        "url": "https://www.vinted.it/catalog?search_text=album+panini+calciatori&price_to=35.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Collezionismo - Retrogaming (PS1, PS2, Nintendo)", 
        "url": "https://www.vinted.it/catalog?search_text=giochi+ps1+ps2+nintendo&price_to=30.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Maglie da Calcio & Sportwear Vintage", 
        "url": "https://www.vinted.it/catalog?search_text=maglia+calcio+vintage&price_to=30.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Sneakers / Brand Selezionati", 
        "url": "https://www.vinted.it/catalog?search_text=sneakers+nike+adidas+jordan&price_to=50.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Streetwear Generico", 
        "url": "https://www.vinted.it/catalog?search_text=felpa+carhartt+stussy+supreme&price_to=50.00&currency=EUR&order=newest_first"
    }
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
})

# --- GOOGLE SHEETS INTEGRATION ---
def get_sheet():
    if not GOOGLE_CREDENTIALS_JSON:
        print("Credenziali Google Sheets non trovate nelle variabili d'ambiente.", flush=True)
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
        
        row = [
            today,                  # Data
            title,                  # Nome Articolo
            negative_buy_price,     # Prezzo d'Acquisto (-)
            "",                     # Spese Spedizione/Commissioni
            "",                     # Prezzo Vendita Reale (vuoto)
            est_resell,             # Valore Stimato
            "=C{row}+E{row}",       # Profitto Netto (Formula)
            "In Vendita",           # Stato
            item_url                # Link Vinted
        ]
        
        sheet.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        print(f"Errore scrittura su Google Sheet: {e}", flush=True)
        return False

# --- GESTIONE STATO TRACCIAMENTO ---
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
        print(f"Errore salvataggio pending_purchases: {e}", flush=True)

# --- INVIO TELEGRAM CON PULSANTI ---
def send_telegram_alert_with_buttons(title, price, est_price, profit, item_url, item_id):
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
        requests.post(url, data=payload, timeout=5)
        pending = load_pending()
        pending[str(item_id)] = {
            "title": title,
            "vinted_price": price,
            "est_resell": est_price,
            "url": item_url
        }
        save_pending(pending)
    except Exception as e:
        print(f"Errore invio Telegram: {e}", flush=True)

def send_telegram_message(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"Errore invio messaggio semplice: {e}", flush=True)

# --- VALUTAZIONE GROQ AI ---
def get_dynamic_model():
    return "llama-3.3-70b-versatile"

def evaluate_deal_with_groq(title, price, model_name):
    if not GROQ_API_KEY:
        print("[GROQ ERROR] API Key mancante nelle variabili d'ambiente.", flush=True)
        return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
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
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    wait_times = [15, 25]
    for attempt in range(len(wait_times) + 1):
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                content = res.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                estimated_resell = float(data.get("estimated_resell_price", 0))
                
                net_profit = estimated_resell - price - 5.0
                is_deal = net_profit >= 10.0
                
                status_str = "APPROVATO (Notifica Inviata!)" if is_deal else "SCARTATO (Margine < 10€)"
                print(f"   └─ [GROQ] Prezzo: {price}€ | Est: {estimated_resell}€ | Profitto: {round(net_profit, 2)}€ -> {status_str}", flush=True)
                
                return {
                    "is_deal": is_deal,
                    "estimated_resell_price": estimated_resell,
                    "estimated_profit": round(net_profit, 2)
                }
            elif res.status_code == 429:
                if attempt < len(wait_times):
                    time.sleep(wait_times[attempt])
                    continue
                else:
                    break
            else:
                print(f"   └─ [GROQ ERROR] Status code {res.status_code}: {res.text}", flush=True)
                break
        except Exception as e:
            print(f"Errore chiamata Groq: {e}", flush=True)
            break
        
    return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

# --- SCRAPING VINTED & CICLO AUTOMATICO ---
def init_session():
    try:
        session.get("https://www.vinted.it", timeout=10)
    except Exception as e:
        print(f"Errore inizializzazione sessione: {e}", flush=True)

def scrape_and_check():
    sent_items = load_sent_items()
    model_name = get_dynamic_model()
    init_session()
    
    for index, target in enumerate(TARGET_URLS, 1):
        print(f"--- Controllo {target['name']} ({index}/{len(TARGET_URLS)}) ---", flush=True)
        try:
            res = session.get(target['url'], timeout=10)
            if res.status_code != 200:
                print(f"   └─ Errore risposta Vinted (Status {res.status_code})", flush=True)
                continue
            
            soup = BeautifulSoup(res.text, "html.parser")
            all_links = soup.find_all("a", href=lambda h: h and "/items/" in h)
            
            unique_items = []
            seen_urls = set()
            for link in all_links:
                href = link.get("href")
                if href not in seen_urls:
                    seen_urls.add(href)
                    unique_items.append(link)
            
            if not unique_items:
                print("   └─ Nessun articolo trovato in questa ricerca.", flush=True)
                continue

            for i, link_tag in enumerate(unique_items[:10], 1):
                item_url = link_tag.get("href")
                if not item_url.startswith("http"):
                    item_url = "https://www.vinted.it" + item_url
                
                item_id_match = re.search(r'/items/(\d+)', item_url)
                item_id = item_id_match.group(1) if item_id_match else item_url

                if item_id in sent_items:
                    continue

                card = link_tag
                for _ in range(3):
                    if card and card.parent:
                        card = card.parent
                
                card_text = card.get_text(separator=" ", strip=True) if card else link_tag.get_text(separator=" ", strip=True)
                lower_text = card_text.lower()
                
                bad_keywords = ["ricambi", "non funziona", "rotto", "difettoso", "danneggiato", "da sistemare", "bloccato", "replica", "fake"]
                if any(kw in lower_text for kw in bad_keywords):
                    continue

                if "figurina" in lower_text and "album" not in lower_text and "lotto" not in lower_text:
                    continue

                price = 0.0
                price_match = re.search(r'(\d+[\.,]\d{2})\s*€|€\s*(\d+[\.,]\d{2})|(\d+)\s*€|€\s*(\d+)', card_text)
                if price_match:
                    groups = [g for g in price_match.groups() if g is not None]
                    if groups:
                        try:
                            price = float(groups[0].replace(",", "."))
                        except ValueError:
                            pass
                
                if price <= 0:
                    continue
                
                parts = item_url.split('/')[-1].split('?')[0].split('-')
                title = " ".join(parts[1:]).title() if len(parts) > 1 else "Articolo Vinted"

                print(f"👉 [ESAMINO] {title[:35]} | Prezzo Vinted: {price}€", flush=True)

                eval_res = evaluate_deal_with_groq(title, price, model_name)
                
                if eval_res.get("is_deal"):
                    profit = eval_res.get("estimated_profit")
                    est_price = eval_res.get("estimated_resell_price")
                    send_telegram_alert_with_buttons(title, price, est_price, profit, item_url, item_id)
                    save_sent_item(item_id)
                    sent_items.add(str(item_id))
                
                time.sleep(3)
                
        except Exception as e:
            print(f"Errore scraping {target['name']}: {e}", flush=True)

def controlla_vinted_periodicamente():
    print(">>> SCRAPER VINTED AVVIATO SU RENDER (H24) <<<", flush=True)
    while True:
        try:
            scrape_and_check()
        except Exception as e:
            print(f"Errore ciclo generale: {e}", flush=True)
        time.sleep(90)

# --- AVVIO THREAD SCRAPER ---
thread_scraper = threading.Thread(target=controlla_vinted_periodicamente, daemon=True)
thread_scraper.start()

# --- MESSAGGIO DI TEST ALL'AVVIO ---
try:
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram_message(TELEGRAM_CHAT_ID, "🟢 <b>Bot Vinted avviato e collegato!</b>\nSe vedi questo messaggio, le notifiche Telegram funzionano al 100%.")
except Exception as e:
    print(f"Errore invio test Telegram: {e}", flush=True)

# --- SERVER FLASK & WEBHOOK TELEGRAM ---
user_states = {}

@app.route('/', methods=['GET', 'HEAD'])
def index():
    return "Bot Vinted Interattivo attivo h24 su Render!", 200

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

        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery", json={"callback_query_id": cb_id})

        if cb_data.startswith("buy_"):
            item_id = cb_data.replace("buy_", "")
            pending = load_pending()
            item_info = pending.get(item_id, {})
            
            user_states[chat_id] = {
                "action": "waiting_price",
                "item_id": item_id,
                "item_info": item_info
            }
            send_telegram_message(chat_id, "💰 <b>Inserisci il prezzo pagato d'acquisto</b> (es. 15 o 17.50):")

        elif cb_data.startswith("save_"):
            send_telegram_message(chat_id, "⭐ <b>Articolo salvato nei preferiti!</b>")

        elif cb_data.startswith("dismiss_"):
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id})

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
                    send_telegram_message(chat_id, "⚠️ Errore durante la registrazione su Google Sheet. Verifica la configurazione.")
            except ValueError:
                send_telegram_message(chat_id, "❌ Prezzo non valido. Inserisci solo un numero (es. 15 o 17.50). Ripeti l'operazione cliccando nuovamente su Acquistato.")

        return "OK", 200

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

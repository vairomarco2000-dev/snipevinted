import os
import json
import time
import random
import requests
import cloudscraper

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

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

SENT_ITEMS_FILE = "sent_items.json"

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
    try:
        with open(SENT_ITEMS_FILE, "w") as f:
            json.dump(list(sent)[-500:], f)
    except Exception as e:
        print(f"Errore salvataggio sent_items: {e}", flush=True)

def evaluate_deal_with_groq(title, price):
    if not GROQ_API_KEY:
        return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}
        
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
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            data = json.loads(content)
            estimated_resell = float(data.get("estimated_resell_price", 0))
            net_profit = estimated_resell - price - 5.0
            is_deal = net_profit >= 10.0
            print(f"   └─ [GROQ] Prezzo: {price}€ | Est: {estimated_resell}€ | Profitto: {round(net_profit, 2)}€", flush=True)
            return {"is_deal": is_deal, "estimated_resell_price": estimated_resell, "estimated_profit": round(net_profit, 2)}
    except Exception as e:
        print(f"Errore Groq: {e}", flush=True)
    return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

def send_telegram_alert(title, price, est_price, profit, item_url, item_id):
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
    except Exception as e:
        print(f"Errore invio Telegram: {e}", flush=True)

def main_loop():
    print(">>> KOYEB SCRAPER WORKER AVVIATO (H24) <<<", flush=True)
    sent_items = load_sent_items()
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )

    while True:
        for target in TARGET_QUERIES:
            print(f"--- Controllo {target['name']} ---", flush=True)
            try:
                api_url = f"https://www.vinted.it/api/v2/catalog/items?search_text={target['query']}&price_to={target['price_to']}&currency=EUR&order=newest_first"
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://www.vinted.it/"
                }
                res = scraper.get(api_url, headers=headers, timeout=12)
                
                if res.status_code != 200:
                    print(f"   └─ Status {res.status_code}", flush=True)
                    time.sleep(3)
                    continue

                items = res.json().get("items", [])
                for item in items[:10]:
                    item_id = str(item.get("id"))
                    if item_id in sent_items:
                        continue
                        
                    title = item.get("title", "Articolo Vinted")
                    item_url = item.get("url", "")
                    price = float(item.get("price", {}).get("amount", 0))

                    if price <= 0:
                        continue

                    eval_res = evaluate_deal_with_groq(title, price)
                    if eval_res.get("is_deal"):
                        profit = eval_res.get("estimated_profit")
                        est_price = eval_res.get("estimated_resell_price")
                        send_telegram_alert(title, price, est_price, profit, item_url, item_id)
                        save_sent_item(item_id)
                        sent_items.add(item_id)

                    time.sleep(random.uniform(2.0, 3.5))
            except Exception as e:
                print(f"Errore scraping: {e}", flush=True)

        time.sleep(random.uniform(90.0, 120.0))

if __name__ == "__main__":
    main_loop()

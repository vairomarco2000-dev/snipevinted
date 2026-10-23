import os
import json
import requests
from google import genai

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

# Configurazione sessione con impostazioni browser
session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
})

# Mappa delle categorie/filtri per l'API di Vinted
TARGET_SEARCHES = [
    {"name": "Elettronica / Tech", "url": "https://www.vinted.it/api/v2/catalog/items?catalog_ids[]=3661&status_ids[]=6&status_ids[]=1&status_ids[]=2&order=newest_first&page=1&per_page=10"},
    {"name": "Sneakers / Brand 1", "url": "https://www.vinted.it/api/v2/catalog/items?catalog_ids[]=2050&size_ids[]=207&size_ids[]=208&size_ids[]=209&brand_ids[]=53&brand_ids[]=14&brand_ids[]=94&brand_ids[]=304&brand_ids[]=88&brand_ids[]=4273&brand_ids[]=2319&brand_ids[]=255&brand_ids[]=73306&brand_ids[]=214&brand_ids[]=161&brand_ids[]=2929&brand_ids[]=139&status_ids[]=6&status_ids[]=1&status_ids[]=2&price_to=50.00&currency=EUR&order=newest_first&page=1&per_page=10"},
    {"name": "Streetwear 1", "url": "https://www.vinted.it/api/v2/catalog/items?catalog_ids[]=1452&brand_ids[]=53&brand_ids[]=14&brand_ids[]=2703&brand_ids[]=1775&brand_ids[]=5977&brand_ids[]=370427&size_ids[]=784&size_ids[]=786&price_to=50.00&currency=EUR&order=newest_first&page=1&per_page=10"},
    {"name": "Streetwear 2", "url": "https://www.vinted.it/api/v2/catalog/items?catalog_ids[]=30&size_ids[]=207&size_ids[]=208&size_ids[]=209&size_ids[]=210&brand_ids[]=53&brand_ids[]=14&status_ids[]=6&status_ids[]=1&status_ids[]=2&price_to=50.00&currency=EUR&order=newest_first&page=1&per_page=10"},
    {"name": "Categoria 1206", "url": "https://www.vinted.it/api/v2/catalog/items?catalog_ids[]=1206&order=newest_first&page=1&per_page=10"},
    {"name": "Categoria 34", "url": "https://www.vinted.it/api/v2/catalog/items?catalog_ids[]=34&order=newest_first&page=1&per_page=10"}
]

def init_vinted_session():
    """Inizializza la sessione scaricando i cookie necessari dalla homepage."""
    try:
        session.get("https://www.vinted.it", timeout=10)
    except Exception as e:
        print(f"Errore inizializzazione sessione Vinted: {e}", flush=True)

def send_telegram_alert(item_title, price, estimated_price, profit, item_url):
    message = (
        f"🚨 <b>NUOVA OPPORTUNITÀ RESELL!</b>\n\n"
        f"📦 <b>Articolo:</b> {item_title}\n"
        f"💸 <b>Prezzo Vinted:</b> {price} €\n"
        f"📈 <b>Valore stimato:</b> {estimated_price} €\n"
        f"💰 <b>Margine netto stimato:</b> +{profit} €\n\n"
        f"🔗 <a href='{item_url}'>Visualizza su Vinted</a>"
    )
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    requests.post(url, data=payload)

def evaluate_deal_with_gemini(title, price):
    prompt = f"""
    Sei un esperto di reselling di usati (sneakers, streetwear ed elettronica).
    Analizza questo articolo:
    Titolo: {title}
    Prezzo di vendita su Vinted: {price} EUR

    Compito:
    1. Stima il valore medio di rivendita di questo articolo sul mercato dell'usato.
    2. Calcola se acquistandolo a {price} EUR c'è un margine netto reale di ALMENO 10 EUR (considerando circa 3-5 EUR tra spedizione e commissioni).
    
    Rispondi STRICTLY in formato JSON privo di markup markdown con questa struttura:
    {{
        "is_deal": true o false,
        "estimated_resell_price": numero,
        "estimated_profit": numero
    }}
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        text_resp = response.text.replace("```json", "").replace("```", "").strip()
        data = json.loads(text_resp)
        return data
    except Exception as e:
        print(f"Errore valutazione Gemini: {e}", flush=True)
        return {"is_deal": False}

def scrape_and_check():
    print(">>> BOT AVVIATO CORRETTAMENTE <<<", flush=True)
    init_vinted_session()
    
    for index, target in enumerate(TARGET_SEARCHES, 1):
        print(f"\n--- Controllo {target['name']} ({index}/{len(TARGET_SEARCHES)}) ---", flush=True)
        try:
            res = session.get(target['url'], timeout=10)
            print(f"Status Code API Vinted: {res.status_code}", flush=True)
            
            if res.status_code != 200:
                continue
            
            data = res.json()
            items = data.get("items", [])
            print(f"Articoli trovati nell'API: {len(items)}", flush=True)
            
            for item in items[:5]:
                title = item.get("title", "Senza Titolo")
                price_str = item.get("price", {}).get("amount", "0")
                item_url = item.get("url") or f"https://www.vinted.it/items/{item.get('id')}"
                
                try:
                    price = float(price_str)
                except ValueError:
                    continue

                print(f"Analisi per: '{title}' ({price}€)", flush=True)
                eval_res = evaluate_deal_with_gemini(title, price)
                print(f"Risposta Gemini: {eval_res}", flush=True)
                
                if eval_res.get("is_deal"):
                    print("--> Affare trovato! Invio notifica Telegram...", flush=True)
                    send_telegram_alert(
                        title,
                        price,
                        eval_res.get("estimated_resell_price"),
                        eval_res.get("estimated_profit"),
                        item_url
                    )
        except Exception as e:
            print(f"Errore durante la scansione di {target['name']}: {e}", flush=True)

if __name__ == "__main__":
    scrape_and_check()

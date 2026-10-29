import os
import json
import time
import re
from bs4 import BeautifulSoup
import requests
import cloudscraper
from groq import Groq

# Variabili d'ambiente gestite dai GitHub Secrets
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
RENDER_SERVER_URL = os.environ.get("RENDER_SERVER_URL", "").rstrip('/')

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

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

def evaluate_deal_with_groq(title, price):
    if not groq_client:
        print("        [DEBUG] Groq Client non inizializzato!")
        return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

    prompt = f"""
    Sei un reseller professionista ed estremamente scettico.
    Analizza questo articolo in vendita su Vinted:
    - Titolo/Descrizione: {title}
    - Prezzo di vendita su Vinted: {price} EUR

    Compito:
    Stima il REALE valore di mercato attuale dell'usato su Vinted/Subito (NON il prezzo da nuovo).
    Rispondi SOLO ed ESCLUSIVAMENTE con un oggetto JSON valido in questo formato esatto:
    {{"estimated_resell_price": 25.0}}
    """

    candidate_models = [
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "llama3-70b-8192",
        "gemma2-9b-it"
    ]

    for model_name in candidate_models:
        try:
            completion = groq_client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            raw_content = completion.choices[0].message.content.strip()
            data = json.loads(raw_content)
            val = data.get("estimated_resell_price", 0)
            
            if isinstance(val, str):
                val_clean = re.sub(r'[^\d\.]', '', val.replace(',', '.'))
                estimated_resell = float(val_clean) if val_clean else 0.0
            else:
                estimated_resell = float(val)

            net_profit = estimated_resell - price - 5.0
            is_deal = net_profit >= 10.0
            
            # Se ha funzionato, stampiamo quale modello ha risposto
            # print(f"        [OK Modello usato: {model_name}]")
            return {
                "is_deal": is_deal,
                "estimated_resell_price": round(estimated_resell, 2),
                "estimated_profit": round(net_profit, 2)
            }
        except Exception as e:
            # Stampiamo il dettaglio esatto di cosa fallisce
            print(f"        [FALLITO su {model_name}]: {e}")

    return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

def send_telegram_alt(title, price, est_price, profit, item_url, item_id):
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
                {"text": "✅ Acquistato", "callback_data": f"buy_{item_id}_{price}_{profit}"},
                {"text": "⭐ Salva", "callback_data": f"save_{item_id}_{price}_{profit}"},
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
        print(f"Notifica Telegram inviata per: {title}")
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def run_scan():
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )

    print(">>> AVVIO SCANSIONE VINTED (VERBOSE DEBUG AI) <<<")

    for target in TARGET_QUERIES:
        print(f"--- Scansione: {target['name']} ---")
        try:
            query_str = target['query'].replace(' ', '%20')
            catalog_url = f"https://www.vinted.it/catalog?search_text={query_str}&price_to={target['price_to']}&order=newest_first"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://www.vinted.it/"
            }
            
            res = scraper.get(catalog_url, headers=headers, timeout=15)

            if res.status_code != 200:
                print(f"  └─ Errore caricamento pagina (Status {res.status_code})")
                continue

            soup = BeautifulSoup(res.text, 'html.parser')
            items = []

            for a_tag in soup.find_all('a', href=re.compile(r'/items/\d+')):
                href = a_tag.get('href', '')
                if not href.startswith('http'):
                    item_url = f"https://www.vinted.it{href}"
                else:
                    item_url = href

                id_match = re.search(r'/items/(\d+)-?([^?#]*)', item_url)
                if not id_match:
                    continue
                item_id = id_match.group(1)
                slug_title = id_match.group(2).replace('-', ' ').strip()

                title = ""
                if slug_title and len(slug_title) > 2:
                    title = slug_title.capitalize()

                img_tag = a_tag.find('img')
                if (not title or title.lower() == "item") and img_tag and img_tag.get('alt'):
                    title = img_tag.get('alt').strip()

                if not title:
                    title = target['query'].capitalize()

                price = 0.0
                parent = a_tag.parent
                for _ in range(4):
                    if not parent:
                        break
                    text_content = parent.get_text()
                    price_match = re.search(r'([\d,\.]+)\s*€', text_content)
                    if price_match:
                        price_str = price_match.group(1).replace(',', '.')
                        try:
                            price = float(price_str)
                            break
                        except:
                            pass
                    parent = parent.parent

                if not any(it['id'] == item_id for it in items):
                    if price > 0 and price <= target['price_to']:
                        items.append({
                            "id": item_id,
                            "title": title,
                            "url": item_url,
                            "price": price
                        })

            print(f"  └─ Trovati {len(items)} articoli validi. Analizzo i primi 5:")

            for item in items[:5]:
                item_id = item["id"]
                title = item["title"]
                item_url = item["url"]
                price = item["price"]

                print(f"     👉 Analizzo: {title[:40]}... | Prezzo: {price}€")

                eval_res = evaluate_deal_with_groq(title, price)
                est_val = eval_res.get('estimated_resell_price', 0)
                profit = eval_res.get('estimated_profit', 0)
                
                print(f"        Groq -> Valore stimato: {est_val}€ | Profitto netto: {profit}€")

                if eval_res.get("is_deal"):
                    print(f"        🔥 AFFARE TROVATO! Invio notifica Telegram...")
                    send_telegram_alt(title, price, est_val, profit, item_url, item_id)
                else:
                    print(f"        ❌ Scartato (margine inferiore a 10€ o non conveniente)")

                time.sleep(1)
        except Exception as e:
            print(f"  └─ Eccezione durante la scansione: {e}")

if __name__ == "__main__":
    run_scan()

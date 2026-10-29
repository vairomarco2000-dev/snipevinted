import os
import json
import time
import re
from bs4 import BeautifulSoup
import requests
import cloudscraper

# Variabili d'ambiente gestite dai GitHub Secrets
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
RENDER_SERVER_URL = os.environ.get("RENDER_SERVER_URL", "").rstrip('/')

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
            return {
                "is_deal": is_deal,
                "estimated_resell_price": estimated_resell,
                "estimated_profit": round(net_profit, 2)
            }
        else:
            print(f"        [Errore API Groq Status {res.status_code}]: {res.text}")
    except Exception as e:
        print(f"        [Eccezione Groq]: {e}")
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

    print(">>> AVVIO SCANSIONE VINTED (HTML PARSER CORRETTO) <<<")

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

                id_match = re.search(r'/items/(\d+)', item_url)
                if not id_match:
                    continue
                item_id = id_match.group(1)

                # Estrazione migliorata del titolo dai tag visibili nella card Vinted
                title = ""
                # 1. Cerca nell'attributo alt dell'immagine
                img_tag = a_tag.find('img')
                if img_tag and img_tag.get('alt'):
                    title = img_tag.get('alt').strip()
                
                # 2. Se vuoto, cerca nei titoli/testi interni al link o nel blocco adiacente
                if not title or title == "item":
                    for tag_name in ['h4', 'h3', 'p', 'span', 'div']:
                        found = a_tag.find(tag_name)
                        if found and len(found.text.strip()) > 3:
                            title = found.text.strip()
                            break

                if not title:
                    title = target['name'] # Fallback sul nome della query se proprio non trova altro

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

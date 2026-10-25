import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

TARGET_URLS = [
    {"name": "Elettronica / Tech", "url": "https://www.vinted.it/catalog?search_id=4905807413&catalog[]=3661&status_ids[]=6&status_ids[]=1&status_ids[]=2&page=1&sim_lock_ids[]=1313&order=newest_first"},
    {"name": "Sneakers / Brand 1", "url": "https://www.vinted.it/catalog?search_id=4905681358&catalog[]=2050&size_ids[]=207&size_ids[]=208&size_ids[]=209&page=1&brand_ids[]=53&brand_ids[]=14&brand_ids[]=94&brand_ids[]=304&brand_ids[]=88&brand_ids[]=4273&brand_ids[]=2319&brand_ids[]=255&brand_ids[]=73306&brand_ids[]=214&brand_ids[]=161&brand_ids[]=2929&brand_ids[]=139&status_ids[]=6&status_ids[]=1&status_ids[]=2&price_to=50.00&currency=EUR&order=newest_first"},
    {"name": "Streetwear 1", "url": "https://www.vinted.it/catalog?search_id=4908212226&catalog[]=1452&page=1&brand_ids[]=53&brand_ids[]=14&brand_ids[]=2703&brand_ids[]=1775&brand_ids[]=5977&brand_ids[]=370427&size_ids[]=784&size_ids[]=786&price_to=50.00&currency=EUR&order=newest_first"},
    {"name": "Streetwear 2", "url": "https://www.vinted.it/catalog?search_id=4908284469&catalog[]=30&size_ids[]=207&size_ids[]=208&size_ids[]=209&size_ids[]=210&page=1&brand_ids[]=53&brand_ids[]=14&status_ids[]=6&status_ids[]=1&status_ids[]=2&price_to=50.00&currency=EUR&order=newest_first"},
    {"name": "Categoria 1206", "url": "https://www.vinted.it/catalog?search_id=4908439558&catalog[]=1206&order=newest_first&page=1"},
    {"name": "Categoria 34", "url": "https://www.vinted.it/catalog?search_id=4908477902&catalog[]=34&order=newest_first&page=1"}
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
})

def init_session():
    try:
        session.get("https://www.vinted.it", timeout=10)
    except Exception as e:
        print(f"Errore inizializzazione sessione: {e}", flush=True)

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

def get_dynamic_model():
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            models = [m["id"] for m in res.json().get("data", [])]
            print(f"Modelli disponibili su Groq: {models}", flush=True)
            for m in models:
                if "llama" in m and ("instant" in m or "versatile" in m or "8b" in m or "70b" in m):
                    return m
            if models:
                return models[0]
    except Exception as e:
        print(f"Errore ricerca modelli: {e}", flush=True)
    return "llama-3.1-8b-instant"

def evaluate_deal_with_groq(title, price, model_name):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""
    Sei un esperto di reselling di usati (sneakers, streetwear ed elettronica).
    Analizza questo articolo:
    Titolo: {title}
    Prezzo di vendita su Vinted: {price} EUR

    Compito:
    1. Stima il valore medio di rivendita di questo articolo sul mercato dell'usato.
    2. Calcola se acquistandolo a {price} EUR c'è un margine netto reale di ALMENO 10 EUR (considerando circa 3-5 EUR tra spedizione e commissioni).
    
    Rispondi STRICTLY in formato JSON privo di qualsiasi testo extra con questa struttura:
    {{"is_deal": true, "estimated_resell_price": 50, "estimated_profit": 15}}
    """

    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "response_format": {"type": "json_object"}
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        else:
            print(f"Errore Groq API ({res.status_code}): {res.text}", flush=True)
    except Exception as e:
        print(f"Errore chiamata Groq: {e}", flush=True)
        
    return {"is_deal": False}

def scrape_and_check():
    print(">>> BOT AVVIATO CORRETTAMENTE CON GROQ <<<", flush=True)
    model_name = get_dynamic_model()
    print(f">>> MODELLO SELEZIONATO AUTOMATICAMENTE: {model_name} <<<", flush=True)
    init_session()
    
    for index, target in enumerate(TARGET_URLS, 1):
        print(f"\n--- Controllo {target['name']} ({index}/{len(TARGET_URLS)}) ---", flush=True)
        try:
            res = session.get(target['url'], timeout=10)
            if res.status_code != 200:
                print(f"Status Code errato: {res.status_code}", flush=True)
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
            
            print(f"Annunci unici trovati: {len(unique_items)}", flush=True)
            
            for i, link_tag in enumerate(unique_items[:5], 1):
                item_url = link_tag.get("href")
                if not item_url.startswith("http"):
                    item_url = "https://www.vinted.it" + item_url
                
                card = link_tag
                for _ in range(3):
                    if card and card.parent:
                        card = card.parent
                
                card_text = card.get_text(separator=" ", strip=True) if card else link_tag.get_text(separator=" ", strip=True)
                
                price = 0.0
                price_match = re.search(r'(\d+[\.,]\d{2})\s*€|€\s*(\d+[\.,]\d{2})|(\d+)\s*€|€\s*(\d+)', card_text)
                if price_match:
                    groups = [g for g in price_match.groups() if g is not None]
                    if groups:
                        p_str = groups[0].replace(",", ".")
                        try:
                            price = float(p_str)
                        except ValueError:
                            pass
                
                if price <=0:
                    continue
                
                parts = item_url.split('/')[-1].split('?')[0].split('-')
                if len(parts) > 1:
                    title = " ".join(parts[1:]).title()
                else:
                    title = "Articolo Vinted"

                print(f"[{i}/5] Analisi per: '{title[:35]}' ({price}€)...", flush=True)
                eval_res = evaluate_deal_with_groq(title, price, model_name)
                print(f"Esito Groq: {eval_res}", flush=True)
                
                if eval_res.get("is_deal"):
                    print("--> Affare trovato! Invio notifica Telegram...", flush=True)
                    send_telegram_alert(
                        title,
                        price,
                        eval_res.get("estimated_resell_price"),
                        eval_res.get("estimated_profit"),
                        item_url
                    )
                
                time.sleep(2)
                
        except Exception as e:
            print(f"Errore durante lo scraping di {target['name']}: {e}", flush=True)

if __name__ == "__main__":
    scrape_and_check()

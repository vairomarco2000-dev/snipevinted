import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# Categorie orientate a lotti o parole generiche (dove si nascondono gli invenduti da trattare)
TARGET_URLS_INVENDUTI = [
    {
        "name": "Lotti Carhartt / Workwear", 
        "url": "https://www.vinted.it/catalog?search_text=lotto+carhartt+vintage&currency=EUR"
    },
    {
        "name": "Lotti Retrogaming / Console", 
        "url": "https://www.vinted.it/catalog?search_text=lotto+giochi+ps1+ps2&currency=EUR"
    },
    {
        "name": "Lotti Diabolik / Fumetti", 
        "url": "https://www.vinted.it/catalog?search_text=lotto+fumetti+diabolik&currency=EUR"
    },
    {
        "name": "Giacche Outdoor (Patagonia, Arc'teryx)", 
        "url": "https://www.vinted.it/catalog?search_text=giacca+patagonia+arcteryx&currency=EUR"
    }
]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
})

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"Errore Telegram: {e}", flush=True)

def evaluate_negotiation_with_groq(title, price):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # Offerta target calcolata al 70-75% del prezzo attuale
    target_offer = round(price * 0.72, 2)
    
    prompt = f"""
    Sei un esperto di reselling e trattative.
    Un venditore ha messo questo oggetto a {price} EUR:
    - Titolo: {title}

    Stima il reale valore di mercato dell'usato. 
    Se proponiamo un'offerta al ribasso a {target_offer} EUR, stimi un margine netto finale di almeno 15 EUR?
    Rispondi STRICTLY in JSON:
    {{"estimated_resell_price": 0, "worth_making_offer": true/false}}
    """

    payload = {
        "model": "qwen/qwen3.8-27b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            data = json.loads(res.json()["choices"][0]["message"]["content"])
            est_resell = float(data.get("estimated_resell_price", 0))
            worth = data.get("worth_making_offer", False)
            
            # Calcolo profitto ipotetico se l'offerta a -28% viene accettata
            potential_profit = est_resell - target_offer - 5.0
            
            return {
                "worth": worth and (potential_profit >= 15.0),
                "target_offer": target_offer,
                "potential_profit": round(potential_profit, 2),
                "est_resell": est_resell
            }
    except Exception as e:
        print(f"Errore Groq: {e}", flush=True)
        
    return {"worth": False, "target_offer": 0, "potential_profit": 0, "est_resell": 0}

def run_negotiation_hunter():
    print(">>> AVVIO SEARCH TRATTATIVE / INVENDUTI <<<", flush=True)
    report_items = []
    
    for target in TARGET_URLS_INVENDUTI:
        try:
            res = session.get(target['url'], timeout=10)
            if res.status_code != 200:
                continue
            
            soup = BeautifulSoup(res.text, "html.parser")
            all_links = soup.find_all("a", href=lambda h: h and "/items/" in h)
            
            seen_urls = set()
            unique_items = []
            for link in all_links:
                href = link.get("href")
                if href not in seen_urls:
                    seen_urls.add(href)
                    unique_items.append(link)
            
            # Analizza 4 oggetti per categoria
            for link_tag in unique_items[:4]:
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
                        price = float(groups[0].replace(",", "."))
                
                if price <= 10.0:  # Trattiamo solo oggetti sopra i 10€
                    continue
                
                parts = item_url.split('/')[-1].split('?')[0].split('-')
                title = " ".join(parts[1:]).title() if len(parts) > 1 else "Articolo"
                
                res_eval = evaluate_negotiation_with_groq(title, price)
                
                if res_eval["worth"]:
                    report_items.append({
                        "title": title,
                        "price": price,
                        "offer": res_eval["target_offer"],
                        "profit": res_eval["potential_profit"],
                        "url": item_url
                    })
                
                time.sleep(10)
                
        except Exception as e:
            print(f"Errore su {target['name']}: {e}", flush=True)

    # Invia un unico report riepilogativo su Telegram
    if report_items:
        msg = "🤝 <b>REPORT SERALE TRATTATIVE CONSIGLIATE</b>\n\n"
        for item in report_items[:5]:  # max 5 proposte
            msg += (
                f"📦 <b>{item['title']}</b>\n"
                f"💵 Prezzo attuale: {item['price']} € | 🎯 <b>Offerta da fare: {item['offer']} €</b>\n"
                f"💰 Margine se accettata: +{item['profit']} €\n"
                f"🔗 <a href='{item['url']}'>Fai la proposta su Vinted</a>\n\n"
            )
        send_telegram_alert(msg)
    else:
        print("Nessuna opportunità di trattativa rilevata oggi.", flush=True)

if __name__ == "__main__":
    run_negotiation_hunter()

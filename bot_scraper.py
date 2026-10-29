import os
import json
import re
import time
import subprocess
import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SENT_ITEMS_FILE = "sent_items.json"

# Le tue ricerche ad alto margine basate su query mirate
TARGET_QUERIES = [
    {"name": "Gorpcore & Techwear", "query": "arcteryx gore tex jacket", "price_to": 110},
    {"name": "Streetwear Vintage / Terrace", "query": "stone island cp company vintage", "price_to": 90},
    {"name": "Lotti Streetwear & Denim", "query": "lotto carhartt stussy dickies", "price_to": 55},
    {"name": "Retrogaming di Nicchia", "query": "gameboy color advance nintendo ps1", "price_to": 45},
    {"name": "Lotti Fumetti & Collezionismo", "query": "lotto diabolik tex fumetti vintage", "price_to": 35},
    {"name": "Maglie Calcio Anni 90/2000", "query": "maglia calcio vintage 90s", "price_to": 40},
    {"name": "Streetwear Raro / T-Shirt", "query": "stussy supreme vintage t shirt", "price_to": 45}
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

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"Errore invio Telegram: {e}", flush=True)

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
        
        subprocess.run(["git", "config", "--global", "user.name", "VintedBot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "config", "--global", "user.email", "bot@users.noreply.github.com"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "add", SENT_ITEMS_FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "Update sent items memory [skip ci]"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "push"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        print(f"Impossibile salvare lo stato su git: {e}", flush=True)

def get_dynamic_model():
    url = "https://api.groq.com/openai/v1/models"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            models = [m["id"] for m in res.json().get("data", [])]
            valid_models = [
                m for m in models 
                if not any(x in m.lower() for x in ["guard", "classify", "embed", "whisper", "audio", "tool", "orpheus"])
            ]
            for m in valid_models:
                if "qwen" in m or "gpt-oss-20b" in m:
                    return m
            if valid_models:
                return valid_models[0]
            if models:
                return models[0]
    except Exception as e:
        print(f"Errore ricerca modelli: {e}", flush=True)
    return "qwen/qwen3.8-27b"

def evaluate_deal_with_groq(title, price, model_name):
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

    Stima il REALE valore di mercato attuale dell'usato su Vinted/Subito. 
    Rispondi STRICTLY in formato JSON privo di qualsiasi testo extra con questa struttura esatta:
    {{"estimated_resell_price": 0}}
    """

    payload = {
        "model": model_name,
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
            
            net_profit = estimated_resell - price - 3.5
            is_deal = net_profit >= 8.0
            
            return {
                "is_deal": is_deal,
                "estimated_resell_price": estimated_resell,
                "estimated_profit": round(net_profit, 2)
            }
    except Exception as e:
        print(f"Errore chiamata Groq: {e}", flush=True)
        
    return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

def scrape_and_check():
    sent_items = load_sent_items()
    print(f">>> BOT AVVIATO (Memoria: {len(sent_items)} articoli tracciati) <<<", flush=True)
    
    model_name = get_dynamic_model()
    print(f">>> MODELLO SELEZIONATO: {model_name} <<<", flush=True)
    init_session()
    
    for index, target in enumerate(TARGET_QUERIES, 1):
        print(f"\n--- Scansione: {target['name']} ({index}/{len(TARGET_QUERIES)}) ---", flush=True)
        try:
            query_str = target['query'].replace(' ', '%20')
            catalog_url = f"https://www.vinted.it/catalog?search_text={query_str}&price_to={target['price_to']}&order=newest_first"
            
            res = session.get(catalog_url, timeout=15)
            if res.status_code != 200:
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
            
            for i, link_tag in enumerate(unique_items[:5], 1):
                item_url = link_tag.get("href")
                if not item_url.startswith("http"):
                    item_url = "https://www.vinted.it" + item_url
                
                item_id_match = re.search(r'/items/(\d+)', item_url)
                if item_id_match:
                    item_id = item_id_match.group(1)
                else:
                    item_id = item_url

                if item_id in sent_items:
                    continue

                card = link_tag
                for _ in range(3):
                    if card and card.parent:
                        card = card.parent
                
                card_text = card.get_text(separator=" ", strip=True) if card else link_tag.get_text(separator=" ", strip=True)
                lower_text = card_text.lower()
                
                # Filtro parole chiave negative
                bad_keywords = ["ricambi", "non funziona", "rotto", "difettoso", "danneggiato", "da sistemare", "bloccato", "replica", "fake"]
                if any(kw in lower_text for kw in bad_keywords):
                    continue

                # ESTRAZIONE TITOLO MIGLIORATA: Cerca l'immagine o l'attributo alt nel card
                title = ""
                img_tag = card.find("img") if card else None
                if img_tag and img_tag.get("alt"):
                    title = img_tag.get("alt").strip()

                if not title:
                    parts = item_url.split('/')[-1].split('?')[0].split('-')
                    if len(parts) > 1 and len(parts[1]) > 2:
                        title = " ".join(parts[1:]).title()
                    else:
                        title = target['name']

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

                print(f"   👉 Analizzo: '{title[:35]}' ({price}€)")
                eval_res = evaluate_deal_with_groq(title, price, model_name)
                
                if eval_res.get("is_deal"):
                    print("   🔥 Affare trovato! Invio notifica...")
                    profit = eval_res.get("estimated_profit")
                    est_price = eval_res.get("estimated_resell_price")
                    
                    msg = (
                        f"🚨 <b>NUOVA OPPORTUNITÀ RESELL!</b>\n\n"
                        f"📦 <b>Articolo:</b> {title}\n"
                        f"💸 <b>Prezzo Vinted:</b> {price} €\n"
                        f"📈 <b>Valore stimato:</b> {est_price} €\n"
                        f"💰 <b>Margine netto stimato:</b> +{profit} €\n\n"
                        f"🔗 <a href='{item_url}'>Visualizza su Vinted</a>"
                    )
                    send_telegram_alert(msg)
                    save_sent_item(item_id)
                    sent_items.add(str(item_id))
                
                time.sleep(2)
                
        except Exception as e:
            print(f"Errore durante lo scraping di {target['name']}: {e}", flush=True)

if __name__ == "__main__":
    scrape_and_check()

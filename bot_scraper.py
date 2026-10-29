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

# Query mirate ad alto margine e ricerca lotti
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

def send_telegram_with_buttons(title, price, est_price, profit, item_url, item_id):
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
        "disable_web_page_preview": True,
        "reply_markup": json.dumps(reply_markup)
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Errore invio Telegram con bottoni: {e}", flush=True)

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
        subprocess.run(["git", "commit", -m, "Update sent items memory [skip ci]"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
    Sei un reseller esperto. Analizza questo articolo/lotto in vendita su Vinted:
    - Titolo: {title}
    - Prezzo di vendita su Vinted: {price} EUR

    Stima il REALE valore di mercato dell'usato. Se è un lotto, stima il valore cumulativo.
    Rispondi STRICTLY in formato JSON privo di testo extra:
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
            items = []

            for a_tag in soup.find_all('a', href=re.compile(r'/items/\d+')):
                href = a_tag.get('href', '')
                item_url = f"https://www.vinted.it{href}" if not href.startswith('http') else href

                id_match = re.search(r'/items/(\d+)', item_url)
                if not id_match:
                    continue
                item_id = id_match.group(1)

                if item_id in sent_items:
                    continue

                slug_title = item_url.split('/')[-1].split('?')[0].replace('-', ' ').strip()
                title = slug_title.capitalize() if len(slug_title) > 2 else target['query'].capitalize()

                img_tag = a_tag.find('img')
                if img_tag and img_tag.get('alt'):
                    title = img_tag.get('alt').strip()

                price = 0.0
                parent = a_tag.parent
                for _ in range(4):
                    if not parent:
                        break
                    text_content = parent.get_text()
                    price_match = re.search(r'([\d,\.]+)\s*€', text_content)
                    if price_match:
                        try:
                            price = float(price_match.group(1).replace(',', '.'))
                            break
                        except:
                            pass
                    parent = parent.parent

                if not any(it['id'] == item_id for it in items):
                    if price > 0 and price <= target['price_to']:
                        items.append({"id": item_id, "title": title, "url": item_url, "price": price})

            for item in items[:4]:
                print(f"   👉 Analizzo: {item['title'][:35]} | {item['price']}€")
                eval_res = evaluate_deal_with_groq(item['title'], item['price'], model_name)
                
                if eval_res.get("is_deal"):
                    print(f"   🔥 Affare trovato! Invio notifica con bottoni...")
                    send_telegram_with_buttons(
                        item['title'], 
                        item['price'], 
                        eval_res.get('estimated_resell_price'), 
                        eval_res.get('estimated_profit'), 
                        item['url'], 
                        item['id']
                    )
                    save_sent_item(item['id'])
                    sent_items.add(str(item['id']))
                
                time.sleep(1)
        except Exception as e:
            print(f"Errore durante la query {target['name']}: {e}", flush=True)

if __name__ == "__main__":
    scrape_and_check()

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

TARGET_URLS = [
    # --- Collezionismo SICURO (Zero Fakes, Alta Richiesta) ---
    {
        "name": "Collezionismo - Album Panini Vintage", 
        "url": "https://www.vinted.it/catalog?search_text=album+panini+calciatori&price_to=35.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Collezionismo - Retrogaming (PS1, PS2, Nintendo)", 
        "url": "https://www.vinted.it/catalog?search_text=giochi+ps1+ps2+nintendo&price_to=30.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Collezionismo - Fumetti & Lotti Vintage", 
        "url": "https://www.vinted.it/catalog?search_text=lotto+fumetti+vintage+topolino&price_to=25.00&currency=EUR&order=newest_first"
    },

    # --- Categorie Streetwear & Outdoor Sicure ---
    {
        "name": "Outdoor & Gorpcore (Patagonia, Arc'teryx, Mammut, TNF)", 
        "url": "https://www.vinted.it/catalog?brand_ids[]=2703&brand_ids[]=1775&brand_ids[]=5977&brand_ids[]=364&catalog[]=1452&catalog[]=30&price_to=50.00&currency=EUR&status_ids[]=1&status_ids[]=2&status_ids[]=6&order=newest_first"
    },
    {
        "name": "Workwear & Denim (Carhartt WIP, Dickies)", 
        "url": "https://www.vinted.it/catalog?brand_ids[]=53&brand_ids[]=371&catalog[]=1452&catalog[]=257&catalog[]=30&price_to=45.00&currency=EUR&status_ids[]=1&status_ids[]=2&status_ids[]=6&order=newest_first"
    },
    {
        "name": "Maglie da Calcio & Sportwear Vintage", 
        "url": "https://www.vinted.it/catalog?search_text=maglia+calcio+vintage&price_to=30.00&currency=EUR&order=newest_first"
    },

    # --- Le tue ricerche originarie pulite ---
    {
        "name": "Sneakers / Brand Selezionati", 
        "url": "https://www.vinted.it/catalog?search_id=4905681358&catalog[]=2050&size_ids[]=207&size_ids[]=208&size_ids[]=209&page=1&brand_ids[]=53&brand_ids[]=14&brand_ids[]=94&brand_ids[]=304&brand_ids[]=88&brand_ids[]=4273&brand_ids[]=2319&brand_ids[]=255&brand_ids[]=73306&brand_ids[]=214&brand_ids[]=161&brand_ids[]=2929&brand_ids[]=139&status_ids[]=6&status_ids[]=1&status_ids[]=2&price_to=50.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Streetwear Generico (Filtro Taglie)", 
        "url": "https://www.vinted.it/catalog?search_id=4908212226&catalog[]=1452&page=1&brand_ids[]=53&brand_ids[]=14&brand_ids[]=2703&brand_ids[]=1775&brand_ids[]=5977&brand_ids[]=370427&size_ids[]=784&size_ids[]=786&price_to=50.00&currency=EUR&order=newest_first"
    },
    {
        "name": "Abbigliamento Categoria 1206", 
        "url": "https://www.vinted.it/catalog?search_id=4908439558&catalog[]=1206&order=newest_first&page=1"
    },
    {
        "name": "Abbigliamento Categoria 34", 
        "url": "https://www.vinted.it/catalog?search_id=4908477902&catalog[]=34&order=newest_first&page=1"
    }
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
        "parse_mode": "HTML"
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
            for m in valid_models:
                if "gpt-oss" in m or "allam" in m:
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

    for attempt in range(2):
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                content = res.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
                estimated_resell = float(data.get("estimated_resell_price", 0))
                
                net_profit = estimated_resell - price - 5.0
                is_deal = net_profit >= 20.0
                
                return {
                    "is_deal": is_deal,
                    "estimated_resell_price": estimated_resell,
                    "estimated_profit": round(net_profit, 2)
                }
            elif res.status_code == 429:
                print(f"Rate limit raggiunto (429), attendo 10 secondi...", flush=True)
                time.sleep(10)
                continue
            else:
                print(f"Errore Groq API ({res.status_code}): {res.text}", flush=True)
                break
        except Exception as e:
            print(f"Errore chiamata Groq: {e}", flush=True)
            break
        
    return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

def scrape_and_check():
    sent_items = load_sent_items()
    print(f">>> BOT AVVIATO CORRETTAMENTE CON GROQ (Memoria: {len(sent_items)} articoli tracciati) <<<", flush=True)
    
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
                
                item_id_match = re.search(r'/items/(\d+)', item_url)
                if item_id_match:
                    item_id = item_id_match.group(1)
                else:
                    item_id = item_url

                if item_id in sent_items:
                    print(f"[{i}/5] Articolo {item_id} già notificato in precedenza. Salto.", flush=True)
                    continue

                card = link_tag
                for _ in range(3):
                    if card and card.parent:
                        card = card.parent
                
                card_text = card.get_text(separator=" ", strip=True) if card else link_tag.get_text(separator=" ", strip=True)
                
                lower_text = card_text.lower()
                bad_keywords = ["ricambi", "non funziona", "rotto", "difettoso", "danneggiato", "da sistemare", "bloccato", "replica", "fake"]
                if any(kw in lower_text for kw in bad_keywords):
                    print(f"[{i}/5] Scartato per presenza parole chiave di difetti/ricambi/fake.", flush=True)
                    continue

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
                
                if price <= 0:
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
                
                time.sleep(5)
                
        except Exception as e:
            print(f"Errore durante lo scraping di {target['name']}: {e}", flush=True)

if __name__ == "__main__":
    try:
        scrape_and_check()
    except Exception as fatal_error:
        error_msg = f"⚠️ <b>ATTENZIONE: Bot Vinted in crash!</b>\nErrore critico: <code>{str(fatal_error)}</code>"
        print(error_msg, flush=True)
        send_telegram_alert(error_msg)

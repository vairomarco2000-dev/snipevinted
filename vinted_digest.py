import os
import json
import time
import re
from bs4 import BeautifulSoup
import requests
import cloudscraper
from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Categorie mirate con l'aggiunta di Felpe & Brand Sportivi
DIGEST_QUERIES = [
    {"name": "Felpe & Brand Sportivi", "query": "felpa nike adidas vintage", "price_to": 30},
    {"name": "Streetwear di Pregio", "query": "supreme stussy carhartt wip", "price_to": 60},
    {"name": "Collezionismo & Retrogaming", "query": "pokemon giochi nintendo ps1", "price_to": 40},
    {"name": "Maglie Calcio Vintage", "query": "maglia calcio vintage retro", "price_to": 35}
]

def get_working_chat_models():
    if not groq_client:
        return []
    try:
        models = groq_client.models.list()
        valid_models = []
        for m in models.data:
            m_id = m.id.lower()
            if "guard" in m_id or "whisper" in m_id or "safetensor" in m_id or "embedding" in m_id:
                continue
            if any(k in m_id for k in ["llama", "mixtral", "gemma", "qwen"]):
                valid_models.append(m.id)
        return valid_models
    except:
        return []

AVAILABLE_MODELS = get_working_chat_models()

def evaluate_deal_with_groq(title, price):
    if not groq_client or not AVAILABLE_MODELS:
        return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

    prompt = f"""
Sei un reseller esperto ed estremamente analitico specializzato in Streetwear, Vintage e Collezionismo.
Analizza questo articolo popolare o datato presente su Vinted:
- Titolo: {title}
- Prezzo Vinted: {price} EUR

Il tuo compito è stimare il REALE valore di mercato dell'usato su Vinted/Subito.
REGOLE FONDAMENTALI:
1. Se il capo/oggetto appartiene a brand/franchise noti (es. Nike, Adidas, Supreme, Stussy, Carhartt, Pokemon, Nintendo, Maglie Vintage) ed è a prezzo conveniente, stimane attentamente il valore di mercato.
2. NON impostare mai 0 come 'estimated_resell_price' se si tratta di un articolo con valore di mercato reale.

Rispondi STRICTLY in formato JSON privo di testo extra con questa struttura esatta:
{{
    "estimated_resell_price": 30.0,
    "reasoning": "Breve spiegazione della stima di rivendita"
}}
"""

    for model_name in AVAILABLE_MODELS:
        try:
            try:
                completion = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=180,
                    response_format={"type": "json_object"}
                )
            except:
                completion = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=180
                )
            
            raw_content = completion.choices[0].message.content.strip()
            estimated_resell = 0.0
            try:
                data = json.loads(raw_content)
                val = data.get("estimated_resell_price", 0)
                val_clean = re.sub(r'[^\d\.]', '', str(val).replace(',', '.'))
                estimated_resell = float(val_clean) if val_clean else 0.0
            except:
                num_match = re.search(r'([\d\.]+)', raw_content)
                if num_match:
                    estimated_resell = float(num_match.group(1))

            # Calcolo profitto netto (sottraendo 3.5€)
            net_profit = estimated_resell - price - 3.5
            
            # 🎯 SOGLIA MINIMA A 20.0€
            is_deal = net_profit >= 20.0
            
            return {
                "is_deal": is_deal,
                "estimated_resell_price": round(estimated_resell, 2),
                "estimated_profit": round(net_profit, 2)
            }
        except Exception as e:
            if "rate_limit_exceeded" in str(e) or "OTPM" in str(e):
                continue

    return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

def send_telegram_recap(deals_list):
    if not deals_list:
        print("Nessun affare da inserire nel recap.")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    msg = "📊 <b>RECAP AFFARI VINTED (POPOLARI / DATATI)</b> 📊\n\nEcco i migliori margini trovati (Profitto minimo +20€):\n\n"
    
    for item in deals_list:
        msg += (
            f"📦 <b>{item['title']}</b>\n"
            f"💸 Prezzo: {item['price']} € | 📈 Valore: {item['est_price']} €\n"
            f"💰 Margine Netto: <b>+{item['profit']} €</b>\n"
            f"🔗 <a href='{item['url']}'>Apri su Vinted</a>\n\n"
        )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, data=payload, timeout=10)
        print("Recap Telegram inviato con successo!")
    except Exception as e:
        print(f"Errore invio recap Telegram: {e}")

def run_digest():
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )

    print(">>> AVVIO DIGEST VINTED (RILEVANZA / POPOLARITÀ) <<<")
    found_deals = []

    for target in DIGEST_QUERIES:
        print(f"--- Analisi per rilevanza: {target['name']} ---")
        try:
            query_str = target['query'].replace(' ', '%20')
            # Filtro per rilevanza + condizioni premium (Nuovo / Ottime condizioni)
            catalog_url = f"https://www.vinted.it/catalog?search_text={query_str}&price_to={target['price_to']}&order=relevance&status_ids[]=1&status_ids[]=2&status_ids[]=6"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8",
                "Referer": "https://www.vinted.it/"
            }
            
            res = scraper.get(catalog_url, headers=headers, timeout=15)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, 'html.parser')
            items = []

            for a_tag in soup.find_all('a', href=re.compile(r'/items/\d+')):
                href = a_tag.get('href', '')
                item_url = f"https://www.vinted.it{href}" if not href.startswith('http') else href

                id_match = re.search(r'/items/(\d+)-?([^?#]*)', item_url)
                if not id_match:
                    continue
                item_id = id_match.group(1)
                slug_title = id_match.group(2).replace('-', ' ').strip()

                title = slug_title.capitalize() if len(slug_title) > 2 else target['query'].capitalize()
                img_tag = a_tag.find('img')
                if (title.lower() == "item") and img_tag and img_tag.get('alt'):
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

            # Analizziamo i primi articoli più popolari
            for item in items[:4]:
                eval_res = evaluate_deal_with_groq(item["title"], item["price"])
                if eval_res.get("is_deal"):
                    found_deals.append({
                        "title": item["title"],
                        "price": item["price"],
                        "est_price": eval_res.get('estimated_resell_price'),
                        "profit": eval_res.get('estimated_profit'),
                        "url": item["url"]
                    })
                time.sleep(1)
        except Exception as e:
            print(f"Errore nella query {target['name']}: {e}")

    # Invia il riepilogo cumulativo
    send_telegram_recap(found_deals)

if __name__ == "__main__":
    run_digest()

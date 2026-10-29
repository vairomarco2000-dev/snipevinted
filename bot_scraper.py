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

# Nicchie ad alto margine e ricerca lotti
TARGET_QUERIES = [
    {"name": "Gorpcore & Techwear", "query": "arcteryx gore tex jacket", "price_to": 110},
    {"name": "Streetwear Vintage / Terrace", "query": "stone island cp company vintage", "price_to": 90},
    {"name": "Lotti Streetwear & Denim", "query": "lotto carhartt stussy dickies", "price_to": 55},
    {"name": "Retrogaming di Nicchia", "query": "gameboy color advance nintendo ps1", "price_to": 45},
    {"name": "Lotti Fumetti & Collezionismo", "query": "lotto diabolik tex fumetti vintage", "price_to": 35},
    {"name": "Maglie Calcio Anni 90/2000", "query": "maglia calcio vintage 90s", "price_to": 40},
    {"name": "Streetwear Raro / T-Shirt", "query": "stussy supreme vintage t shirt", "price_to": 45}
]

def get_working_chat_models():
    """Filtra ed estrae solo i modelli generativi di Chat validi da Groq"""
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
    except Exception as e:
        print(f"        [DEBUG] Errore recupero modelli: {e}")
    return []

AVAILABLE_MODELS = get_working_chat_models()

def evaluate_deal_with_groq(title, price):
    if not groq_client or not AVAILABLE_MODELS:
        return {"is_deal": False, "estimated_resell_price": 0, "estimated_profit": 0}

    prompt = f"""
    Sei un reseller esperto e un cacciatore di affari su Vinted, Subito ed eBay.
    Analizza questo articolo/lotto in vendita:
    - Titolo/Descrizione: {title}
    - Prezzo di acquisto su Vinted: {price} EUR

    Istruzioni di valutazione:
    1. Se si tratta di brand ricercati (Arc'teryx, Stone Island, Stussy, Retrogaming, Maglie Calcio Anni '90) o di un LOTTO composto da più pezzi, considera il valore cumulativo reale di mercato dell'usato in buone condizioni.
    2. Mantieni un approccio realistico ma riconosci i reali prezzi di mercato.
    
    Rispondi SOLO ed ESCLUSIVAMENTE con un oggetto JSON valido in questo formato esatto:
    {{"estimated_resell_price": 35.0}}
    """

    for model_name in AVAILABLE_MODELS:
        try:
            try:
                completion = groq_client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=150,
                    response_format={"type": "json_object"}
                )
            except Exception as json_err:
                if "JSON output" in str(json_err):
                    completion = groq_client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=150
                    )
                else:
                    raise json_err
            
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

            # Spese realistiche stimate (3.5€) e margine minimo di 8.0€
            net_profit = estimated_resell - price - 3.5
            is_deal = net_profit >= 8.0
            
            return {
                "is_deal": is_deal,
                "estimated_resell_price": round(estimated_resell, 2),
                "estimated_profit": round(net_profit, 2)
            }
        except Exception as e:
            if "rate_limit_exceeded" in str(e) or "OTPM" in str(e):
                continue
            print(f"        [Errore Groq con {model_name}]: {e}")

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

    print(">>> AVVIO SCANSIONE VINTED OPTIMIZED <<<")

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
                item_url = f"https://www.vinted.it{href}" if not href.startswith('http') else href

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
                    print(f"        ❌ Scartato (margine inferiore a 8€ o non conveniente)")

                time.sleep(1)
        except Exception as e:
            print(f"  └─ Eccezione durante la scansione: {e}")

if __name__ == "__main__":
    run_scan()

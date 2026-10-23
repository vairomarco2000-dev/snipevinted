import os
import json
import requests
from bs4 import BeautifulSoup
from google import genai

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

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
    init_session()
    
    for index, target in enumerate(TARGET_URLS, 1):
        print(f"\n--- Controllo {target['name']} ({index}/{len(TARGET_URLS)}) ---", flush=True)
        try:
            res = session.get(target['url'], timeout=10)
            print(f"Status Code Vinted: {res.status_code}", flush=True)
            
            if res.status_code != 200:
                continue
            
            soup = BeautifulSoup(res.text, "html.parser")
            
            # Trova direttamente tutti i link unici che puntano agli articoli
            all_links = soup.find_all("a", href=lambda h: h and "/items/" in h)
            unique_items = []
            seen_urls = set()
            for link in all_links:
                href = link.get("href")
                if href not in seen_urls:
                    seen_urls.add(href)
                    unique_items.append(link)
            
            print(f"Annunci unici trovati: {len(unique_items)}", flush=True)
            
            for link_tag in unique_items[:5]:
                item_url = link_tag.get("href")
                if not item_url.startswith("http"):
                    item_url = "https://www.vinted.it" + item_url
                
                # Prende il contenitore principale dell'annuncio
                container = link_tag.find_parent("div", class_=lambda c: c and ("item" in c or "card" in c or "box" in c)) or link_tag.parent
                
                title_tag = container.find(["p", "h2", "span", "div"], class_=lambda c: c and ("title" in c or "description" in c))
                price_tag = container.find(["p", "span", "div"], class_=lambda c: c and ("price" in c or "amount" in c))
                
                title = title_tag.text.strip() if title_tag else link_tag.get("title", "Articolo Vinted")
                
                price_str = "0"
                if price_tag:
                    price_str = price_tag.text.strip().replace("€", "").replace(",", ".").strip()
                else:
                    text_content = container.get_text()
                    if "€" in text_content:
                        parts = text_content.split("€")
                        for p in parts:
                            clean_p = ''.join(c for c in p if c.isdigit() or c == '.')
                            if clean_p:
                                try:
                                    price_val = float(clean_p)
                                    if 0.5 <= price_val <= 1000:
                                        price_str = str(price_val)
                                        break
                                except:
                                    pass
                
                try:
                    price = float(price_str)
                except ValueError:
                    continue

                if price <= 0:
                    continue

                print(f"Analisi per: '{title[:35]}' ({price}€)", flush=True)
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
            print(f"Errore durante lo scraping di {target['name']}: {e}", flush=True)

if __name__ == "__main__":
    scrape_and_check()

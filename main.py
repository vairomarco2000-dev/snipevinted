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
    """Inizializza i cookie visitando la homepage di Vinted."""
    try:
        res = session.get("https://www.vinted.it", timeout=10)
        print(f"Inizializzazione sessione Vinted: {res.status_code}", flush=True)
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

def parse_items_from_soup(soup):
    """Cerca gli elementi usando molteplici selettori CSS possibili."""
    # Prova selettori multipli usati da Vinted per i singoli articoli
    items = soup.find_all("div", class_=lambda c: c and ("feed-grid__item" in c or "grid__item" in c or "item-box" in c))
    if not items:
        items = soup.find_all("div", attrs={"data-testid": lambda v: v and "item" in v})
    return items

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
            items = parse_items_from_soup(soup)
            print(f"Articoli individuati nell'HTML: {len(items)}", flush=True)
            
            for item in items[:5]:
                link_tag = item.find("a", href=lambda h: h and "/items/" in h)
                title_tag = item.find(["p", "h2", "span"], class_=lambda c: c and "title" in c)
                price_tag = item.find(["p", "span"], class_=lambda c: c and "price" in c)
                
                if not (link_tag and price_tag):
                    continue
                
                item_url = link_tag.get("href")
                if not item_url.startswith("http"):
                    item_url = "https://www.vinted.it" + item_url
                
                title = title_tag.text.strip() if title_tag else "Articolo senza titolo"
                price_str = price_tag.text.strip().replace("€", "").replace(",", ".").strip()
                
                try:
                    price = float(price_str)
                except ValueError:
                    continue

                print(f"Analisi per: '{title}' ({price}€)", flush=True)
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

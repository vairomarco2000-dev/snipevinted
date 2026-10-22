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
    "https://www.vinted.it/catalog?search_id=4905530694&catalog[]=1452&brand_ids[]=53&brand_ids[]=14&page=1&size_ids[]=784&status_ids[]=6&status_ids[]=1&status_ids[]=2&price_to=50&currency=EUR",
    "https://www.vinted.it/catalog?search_id=4905698326&search_text=weekend%20offender%20uomo&catalog[]=2050&page=1",
    "https://www.vinted.it/catalog?search_id=4905732263&search_text=the%20nort%20face&catalog[]=2050&page=1&status_ids[]=6&status_ids[]=1&status_ids[]=2&color_ids[]=1",
    "https://www.vinted.it/catalog?search_id=4905807413&catalog[]=3661&status_ids[]=6&status_ids[]=1&status_ids[]=2&page=1&sim_lock_ids[]=1313"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
}

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
    2. Calcola se acquistandolo a {price} EUR c'è un margine netto reale di almeno 15 EUR (considerando anche circa 3-5 EUR tra spedizione e commissioni).

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
        print(f"Errore valutazione Gemini: {e}")
        return {"is_deal": False}

def scrape_and_check():
    for url in TARGET_URLS:
        try:
            res = requests.get(url, headers=HEADERS)
            if res.status_code != 200:
                continue

            soup = BeautifulSoup(res.text, "html.parser")
            items = soup.find_all("div", class_="feed-grid__item")

            for item in items[:5]:
                link_tag = item.find("a", class_="new-item-box__overlay-link")
                title_tag = item.find("p", class_="new-item-box__title")
                price_tag = item.find("p", class_="new-item-box__price")

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

                eval_res = evaluate_deal_with_gemini(title, price)
                if eval_res.get("is_deal"):
                    send_telegram_alert(
                        title,
                        price,
                        eval_res.get("estimated_resell_price"),
                        eval_res.get("estimated_profit"),
                        item_url
                    )
        except Exception as e:
            print(f"Errore durante lo scraping dell'URL {url}: {e}")

if __name__ == "__main__":
    scrape_and_check()

import os
import json
import requests
import time

# --- CONFIGURAZIONI AMBIENTE ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

SENT_ITEMS_FILE = "sent_items.json"

# --- PROMPT GROQ AVANZATO RESELLING ---
GROQ_SYSTEM_PROMPT = """
Sei un esperto di reselling specializzato in: Streetwear, Abbigliamento Vintage, Outdoor/Techwear, Retrogaming, Sneakers, Giubbini di marca e Collezionismo.
Il tuo compito è analizzare le inserzioni Vinted ed evidenziare SOLO i veri affari con reale margine di profitto.

REGOLE DI VALUTAZIONE RIGIDE:
1. CALCOLO COSTI REALI: Considera sempre che il costo finale d'acquisto è (Prezzo Articolo + ~15% di commissioni/spedizione).
2. CONDIZIONI & DIFETTI: Scarta o penalizza pesantemente articoli che descrivono macchie permanenti, buchi, cerniere rotte, scuciture o prodotti "molto usati / rovinati".
3. TAGLIE GOLD (Abbigliamento/Scarpe): 
   - Vestiario: S, M, L, XL hanno priorità alta e liquidità veloce.
   - Scarpe: Taglie dal 41 al 44.5 si rivendono meglio.
4. RETROGAMING & COLLEZIONISMO: Valuta se l'articolo è completo (CIB: Scatola + Manuale) o "Loose" (solo cartuccia/disco). I lotti da dividere hanno priorità altissima se il prezzo per singolo pezzo è basso.

Rispondi in modo sintetico con questo formato esatto:
- **Margine Stimato:** [Esempio: Compri a 20€ totali -> Rivendi a 45-50€ -> Profitto netto ~20-25€]
- **Liquidità:** [Alta / Media / Bassa]
- **Note chiave:** [Taglia, condizioni, presenza di difetti o lotti]
- **Verdetto:** [CONSIGLIATO / RISCHIOSO / SCARTARE]
"""

# --- LISTA QUERY DI RICERCA COMPLETA (PRECEDENTI + NUOVE STRATEGIE) ---
TARGET_SEARCHES = [
    # --- RICERCHE PRECEDENTI (Outdoor, Techwear & Streetwear) ---
    {"query": "goretex", "max_price": 35},
    {"query": "gore-tex", "max_price": 35},
    {"query": "salomon", "max_price": 40},
    {"query": "oakley", "max_price": 30},
    {"query": "arcteryx", "max_price": 50},
    {"query": "carhartt jacket", "max_price": 45},
    {"query": "stussy tshirt", "max_price": 20},
    {"query": "stone island", "max_price": 60},
    {"query": "patagonia fleece", "max_price": 35},
    {"query": "north face puffer", "max_price": 50},

    # --- NUOVE: ERRORI DI BATTITURA (TYPOS & MISSPELLED BRANDS) ---
    {"query": "Stusy", "max_price": 20},
    {"query": "Stone Islan", "max_price": 50},
    {"query": "Carhat", "max_price": 25},
    {"query": "Arcterix", "max_price": 45},
    {"query": "Tnfe", "max_price": 30},
    {"query": "Patagoni", "max_price": 25},
    {"query": "Armax", "max_price": 35},
    {"query": "Pokmon", "max_price": 20},
    {"query": "Doc martens", "max_price": 40},

    # --- NUOVE: GIUBBINI & BRAND SPECIFICI ---
    {"query": "giacca carhartt", "max_price": 45},
    {"query": "giubbotto north face", "max_price": 50},
    {"query": "giacca stussy", "max_price": 45},

    # --- NUOVE: RETROGAMING & COLLEZIONISMO ---
    {"query": "lotto giochi", "max_price": 30},
    {"query": "Gameboy", "max_price": 35},
    {"query": "Ps1 lotto", "max_price": 25},

    # --- NUOVE: SNEAKERS ---
    {"query": "Jordan 1", "max_price": 45},

    # --- NUOVE: KEYWORD SGOMBERO & SVUOTO ARMADIO ---
    {"query": "svuoto armadio", "max_price": 15},
    {"query": "svendo lotto", "max_price": 25},
    {"query": "pulisco cantina", "max_price": 20}
]

def load_sent_items():
    if os.path.exists(SENT_ITEMS_FILE):
        try:
            with open(SENT_ITEMS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_sent_items(sent_items):
    with open(SENT_ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(sent_items[-500:], f, ensure_ascii=False, indent=2)

def evaluate_with_groq(item_title, description, price):
    if not GROQ_API_KEY:
        return "Analisi IA non disponibile (API Key mancante)."
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    prompt_user = f"Titolo: {item_title}\nPrezzo: {price}€\nDescrizione: {description}"
    
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": GROQ_SYSTEM_PROMPT},
            {"role": "user", "content": prompt_user}
        ],
        "temperature": 0.2
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Errore Groq: {e}")
    
    return "Analisi IA fallita."

def send_telegram_alert(item, ai_analysis):
    title = item.get("title", "N/A")
    price = item.get("price", "N/A")
    url = item.get("url", "")
    item_id = item.get("id")
    
    text = (
        f"🔥 **NUOVO AFFARE INDIVIDUATO** 🔥\n\n"
        f"📌 **Titolo:** {title}\n"
        f"💰 **Prezzo:** {price}€\n\n"
        f"🤖 **Analisi Groq AI:**\n{ai_analysis}\n\n"
        f"🔗 [Apri su Vinted]({url})"
    )
    
    # Tastiera inline per Webhook su Render
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Acquistato", "callback_data": f"buy_{item_id}"},
                {"text": "⭐ Salva", "callback_data": f"save_{item_id}"},
                {"text": "❌ Scarta", "callback_data": f"dismiss_{item_id}"}
            ]
        ]
    }
    
    tg_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": reply_markup
    }
    requests.post(tg_url, json=payload)

def main():
    sent_items = load_sent_items()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    for target in TARGET_SEARCHES:
        query = target["query"]
        max_price = target["max_price"]
        
        vinted_api_url = f"https://www.vinted.it/api/v2/catalog/items?search_text={query}&order=newest_first&per_page=10"
        
        try:
            res = requests.get(vinted_api_url, headers=headers, timeout=10)
            if res.status_code != 200:
                continue
                
            items = res.json().get("items", [])
            for item in items:
                item_id = str(item.get("id"))
                price = float(item.get("price", 999))
                
                # Controllo duplication + filtro severo sul prezzo max
                if item_id in sent_items or price > max_price:
                    continue
                
                title = item.get("title", "")
                description = item.get("description", "")
                item_url = item.get("url", f"https://www.vinted.it/items/{item_id}")
                
                # Valutazione Groq AI
                ai_analysis = evaluate_with_groq(title, description, price)
                
                # Se il verdetto è scartare, non inviamo la notifica ma lo tracciamo
                if "SCARTARE" in ai_analysis and "CONSIGLIATO" not in ai_analysis:
                    sent_items.append(item_id)
                    continue
                
                # Invio Notifica Telegram
                item_data = {
                    "id": item_id,
                    "title": title,
                    "price": price,
                    "url": item_url
                }
                send_telegram_alert(item_data, ai_analysis)
                sent_items.append(item_id)
                time.sleep(1)
                
        except Exception as e:
            print(f"Errore durante lo scraping della query '{query}': {e}")
            
    save_sent_items(sent_items)

if __name__ == "__main__":
    main()

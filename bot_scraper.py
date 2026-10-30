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

# --- LISTA QUERY DI RICERCA COMPLETA ---
TARGET_SEARCHES = [
    # Outdoor & Techwear
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

    # Typos & Errore Battitura
    {"query": "Stusy", "max_price": 20},
    {"query": "Stone Islan", "max_price": 50},
    {"query": "Carhat", "max_price": 25},
    {"query": "Arcterix", "max_price": 45},
    {"query": "Tnfe", "max_price": 30},
    {"query": "Patagoni", "max_price": 25},
    {"query": "Armax", "max_price": 35},
    {"query": "Pokmon", "max_price": 20},
    {"query": "Doc martens", "max_price": 40},

    # Giubbini & Brand
    {"query": "giacca carhartt", "max_price": 45},
    {"query": "giubbotto north face", "max_price": 50},
    {"query": "giacca stussy", "max_price": 45},

    # Retrogaming & Sneakers
    {"query": "lotto giochi", "max_price": 30},
    {"query": "Gameboy", "max_price": 35},
    {"query": "Ps1 lotto", "max_price": 25},
    {"query": "Jordan 1", "max_price": 45},

    # Keyword Sgombero
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
        print("   ⚠️ GROQ_API_KEY non trovata nelle variabili d'ambiente.")
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
        else:
            print(f"   ⚠️ Groq Error Code {res.status_code}: {res.text}")
    except Exception as e:
        print(f"   ❌ Errore durante la chiamata a Groq: {e}")
    
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
    resp = requests.post(tg_url, json=payload)
    if resp.status_code == 200:
        print(f"   ✅ Notifica Telegram inviata per: {title}")
    else:
        print(f"   ❌ Errore invio Telegram ({resp.status_code}): {resp.text}")

def get_vinted_session():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7"
    })
    try:
        # Chiamata alla homepage per ottenere i cookie di sessione indispensabili
        session.get("https://www.vinted.it", timeout=10)
    except Exception as e:
        print(f"⚠️ Errore inizializzazione sessione Vinted: {e}")
    return session

def main():
    print("🚀 Avvio della scansione Vinted...")
    sent_items = load_sent_items()
    print(f"📦 Caricati {len(sent_items)} articoli già visti nel file di memoria.")
    
    session = get_vinted_session()
    
    for target in TARGET_SEARCHES:
        query = target["query"]
        max_price = target["max_price"]
        print(f"\n🔍 Ricerca: '{query}' (Prezzo max: {max_price}€)")
        
        vinted_api_url = f"https://www.vinted.it/api/v2/catalog/items?search_text={query}&order=newest_first&per_page=10"
        
        try:
            res = session.get(vinted_api_url, timeout=10)
            if res.status_code != 200:
                print(f"   ⚠️ Risposta Vinted non valida (Status: {res.status_code}). Salto query.")
                continue
                
            items = res.json().get("items", [])
            print(f"   found {len(items)} articoli nell'API.")
            
            for item in items:
                item_id = str(item.get("id"))
                price = float(item.get("price", 999))
                title = item.get("title", "")
                
                if item_id in sent_items:
                    continue
                
                if price > max_price:
                    print(f"   ⏩ Scartato '{title[:30]}...' -> Prezzo ({price}€) > Max ({max_price}€)")
                    continue
                
                print(f"   🎯 Analizzo con Groq: '{title}' ({price}€)...")
                description = item.get("description", "")
                item_url = item.get("url", f"https://www.vinted.it/items/{item_id}")
                
                ai_analysis = evaluate_with_groq(title, description, price)
                
                if "SCARTARE" in ai_analysis and "CONSIGLIATO" not in ai_analysis:
                    print(f"   🚫 Groq ha scartato l'articolo.")
                    sent_items.append(item_id)
                    continue
                
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
            print(f"   ❌ Errore durante la scansione di '{query}': {e}")
            
        # Pausa per evitare rate limit da Vinted
        time.sleep(1.5)
            
    save_sent_items(sent_items)
    print("\n✅ Scansione completata con successo!")

if __name__ == "__main__":
    main()

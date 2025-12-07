# dormdeck_engine.py
import json
import os
from datetime import datetime as dt, time as dttime
from functools import lru_cache
from dotenv import load_dotenv
import google.generativeai as genai

# --- CONFIGURATION ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY_DORMDECK")
if not API_KEY or API_KEY == "YOUR_GEMINI_API_KEY":
    print("⚠️ WARNING: GEMINI API key missing in environment variables.")
genai.configure(api_key=API_KEY)

SERVICES_PATH = "services.json"

# --- UTIL ---
def safe_load_services():
    try:
        with open(SERVICES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        print("⚠️ Error: services.json is malformed. Returning empty list.")
        return []

def safe_write_services(services):
    # Atomic write to avoid corruption during concurrent writes
    tmp = SERVICES_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(services, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SERVICES_PATH)

# --- 1. TIME FILTERING LOGIC (robust) ---
def parse_time(t):
    if not t or not isinstance(t, str):
        return None
    t = t.strip().lower()
    if t in ("24/7", "247", "always", "always open"):
        return "24/7"
    # Accept "HH:MM" or "H:MM"
    try:
        return dttime.fromisoformat(t)
    except Exception:
        # try fallback formats
        for fmt in ("%H:%M", "%H.%M", "%H%M"):
            try:
                return dt.strptime(t, fmt).time()
            except Exception:
                continue
    return None

def is_shop_open(open_str, close_str, now_dt=None):
    """
    Return True if shop is open now.
    - "24/7" or open==close -> always open
    - Handles midnight crossing: e.g., 18:00 -> 03:00
    """
    if now_dt is None:
        now_dt = dt.now()
    now = now_dt.time()

    o = parse_time(open_str)
    c = parse_time(close_str)

    # 24/7 detection
    if o == "24/7" or c == "24/7":
        return True
    if o is None or c is None:
        # If times malformed, assume closed (safer)
        return False

    # If equal times, treat as 24/7 by convention (you can change)
    if o == c:
        return True

    # Standard interval (no midnight crossing)
    if o < c:
        return o <= now <= c
    # Midnight crossing e.g., 20:00 -> 03:00
    return now >= o or now <= c

# --- 2. LOCATION SCORE (unchanged but clearer return) ---
def calculate_location_score(shop_loc, user_loc):
    if not user_loc or not shop_loc:
        return 0.0
    shop = shop_loc.lower().strip()
    user = user_loc.lower().strip()
    if shop == user:
        return 1.0
    # Try numeric adjacency (H-5 style)
    try:
        shop_num = int(''.join(filter(str.isdigit, shop)))
        user_num = int(''.join(filter(str.isdigit, user)))
        if abs(shop_num - user_num) <= 1:
            return 0.4
    except Exception:
        pass
    return 0.0

# --- 3. LLM Intent Analysis with simple caching ---
@lru_cache(maxsize=512)
def analyze_intent_cached(user_query_clean):
    prompt = f"""
You are a campus-concierge assistant. Analyze student query and return strict JSON.
Query: \"\"\"{user_query_clean}\"\"\"

Return ONLY a JSON object with:
- category: one of ["Food","Stationery","Services","Medicine","Transport","General"]
- intent: short 2-4 word summary
- urgency: integer 1-10
- keywords: list of up to 5 keywords (lowercase)
"""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash",
                                      generation_config={"response_mime_type": "application/json"})
        resp = model.generate_content(prompt)
        text = resp.text.strip()
        # Some models return JSON with extra text; attempt to parse first JSON blob
        import re, json
        m = re.search(r'(\{.*\})', text, re.S)
        if m:
            jtext = m.group(1)
        else:
            jtext = text
        return json.loads(jtext)
    except Exception as e:
        print(f"[LLM error] {e}")
        # graceful fallback
        words = [w.lower().strip(".,!?") for w in user_query_clean.split()][:5]
        return {"category": "General", "intent": " ".join(words[:3]) or "unknown", "urgency": 5, "keywords": words}

def analyze_intent(user_query):
    # Normalize lightly to make caching effective
    cleaned = " ".join(user_query.strip().split())
    return analyze_intent_cached(cleaned)

# --- 4. RANKING & MATCHING (improved) ---
def _service_keywords(service):
    kw = []
    kw += [k.lower() for k in service.get("keywords", []) if isinstance(k, str)]
    desc = service.get("description", "") or ""
    kw += [w.strip(".,()").lower() for w in desc.split() if len(w) > 2]
    kw += [service.get("category", "").lower()]
    return set(kw)

def get_recommendations(user_query, user_location):
    services = safe_load_services()
    print(f"🧠 Query: {user_query} | Location: {user_location}")
    ai = analyze_intent(user_query)
    print("🤖 AI:", ai)
    results = []

    for s in services:
        sem_score = 0.0
        if s.get("category", "").lower() == ai.get("category", "").lower():
            sem_score = 1.0
        else:
            serv_kw = _service_keywords(s)
            query_kw = set(ai.get("keywords", []))
            if not serv_kw.isdisjoint(query_kw):
                sem_score = 0.6

        loc_score = calculate_location_score(s.get("location"), user_location)
        open_flag = is_shop_open(s.get("open_time"), s.get("close_time"))
        status_score = 1.0 if open_flag else 0.0

        if sem_score > 0:
            total = (sem_score * 50) + (loc_score * 30) + (status_score * 20)
            if total > 10:
                results.append({
                    "service": s,
                    "score": total,
                    "is_open": open_flag,
                    "match_type": "smart"
                })

    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:3]

def get_fallback_suggestions(user_location):
    services = safe_load_services()
    cand = []
    for s in services:
        open_flag = is_shop_open(s.get("open_time"), s.get("close_time"))
        loc_score = calculate_location_score(s.get("location"), user_location)
        score = (50 if open_flag else 10) + (loc_score * 50)
        cand.append({"service": s, "score": score, "is_open": open_flag, "match_type": "fallback"})
    cand.sort(key=lambda r: r["score"], reverse=True)
    if not cand:
        return [{"service": s, "score": 0, "is_open": False, "match_type": "fallback"} for s in services[:3]]
    return cand[:3]

def get_all_recommendations(user_query, user_location):
    smart = get_recommendations(user_query, user_location)
    if smart:
        return {"type": "smart", "results": smart, "message": "Here are the best matches for your request!"}
    else:
        fall = get_fallback_suggestions(user_location)
        return {"type": "fallback", "results": fall, "message": "No exact matches — showing popular open spots nearby."}

# --- 5. Seller onboarding helper (call from Streamlit) ---
def add_service_entry(entry):
    """
    entry: dict with keys id (optional), name, category, location, open_time, close_time, description, keywords(list), whatsapp, form_url(optional)
    """
    services = safe_load_services()
    # assign id
    max_id = max([s.get("id", 0) for s in services], default=0)
    entry["id"] = max_id + 1
    services.append(entry)
    safe_write_services(services)
    return entry

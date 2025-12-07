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

    Duplicate detection logic:
    - If an existing service has the same whatsapp number (exact match) -> considered duplicate.
    - Or if existing service has same name AND same location (case-insensitive) -> considered duplicate.
    """
    services = safe_load_services()

    # Normalize incoming values for comparison
    incoming_name = (entry.get("name") or "").strip().lower()
    incoming_location = (entry.get("location") or "").strip().lower()
    incoming_whatsapp = (entry.get("whatsapp") or "").strip()

    # Check duplicates
    for s in services:
        s_name = (s.get("name") or "").strip().lower()
        s_loc = (s.get("location") or "").strip().lower()
        s_wa = (s.get("whatsapp") or "").strip()

        # Duplicate by whatsapp (strong signal)
        if incoming_whatsapp and s_wa and incoming_whatsapp == s_wa:
            raise ValueError(f"Duplicate service detected: same WhatsApp number already exists (id={s.get('id')}).")

        # Duplicate by name + location
        if incoming_name and incoming_location and s_name == incoming_name and s_loc == incoming_location:
            raise ValueError(f"Duplicate service detected: a service with the same name already exists at this location (id={s.get('id')}).")

    # assign id
    max_id = max([int(s.get("id", 0)) for s in services], default=0)
    entry["id"] = max_id + 1

    # Normalize keywords: ensure list of trimmed strings
    kws = entry.get("keywords", [])
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",") if k.strip()]
    elif isinstance(kws, list):
        kws = [str(k).strip() for k in kws if str(k).strip()]
    else:
        kws = []
    entry["keywords"] = kws

    services.append(entry)
    safe_write_services(services)
    return entry




# dormdeck_engine.py (append these helpers)

def get_all_services():
    """Return all services (list) from services.json"""
    return safe_load_services()

def update_service(service_id, updated_fields):
    """
    Update service with given id using keys in updated_fields dict.
    Returns the updated service dict, or raises ValueError if id not found.
    """
    services = safe_load_services()
    found = False
    for idx, s in enumerate(services):
        if int(s.get("id", -1)) == int(service_id):
            found = True
            # update fields (only provided keys)
            for k, v in updated_fields.items():
                if k == "keywords" and isinstance(v, str):
                    # accept comma-separated string
                    services[idx][k] = [x.strip() for x in v.split(",") if x.strip()]
                else:
                    services[idx][k] = v
            updated = services[idx]
            break
    if not found:
        raise ValueError(f"Service with id={service_id} not found.")
    safe_write_services(services)
    return updated

def delete_service(service_id):
    """
    Remove service with given id. Returns True if removed, False if not found.
    """
    services = safe_load_services()
    new_services = [s for s in services if int(s.get("id", -1)) != int(service_id)]
    if len(new_services) == len(services):
        return False
    safe_write_services(new_services)
    return True

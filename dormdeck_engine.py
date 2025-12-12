# dormdeck_engine.py
import sqlite3
import json
import os
from datetime import datetime as dt, time as dttime
from functools import lru_cache
from dotenv import load_dotenv
import google.generativeai as genai
import io
import csv

# --- CONFIGURATION ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY_DORMDECK")
if not API_KEY or API_KEY == "YOUR_GEMINI_API_KEY":
    print("⚠️ WARNING: GEMINI API key missing in environment variables.")
genai.configure(api_key=API_KEY)

# Database Configuration
DB_PATH = "dormdeck.db"

# --- DATABASE UTIL ---
def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    return conn

def init_db():
    """Initializes the database tables if they do not exist."""
    conn = get_db_connection()
    
    # 1. Services Table
    conn.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            location TEXT,
            open_time TEXT,
            close_time TEXT,
            description TEXT,
            keywords TEXT, -- Stored as JSON string
            whatsapp TEXT,
            form_url TEXT
        )
    ''')

    # 2. Sessions Table (Events)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            timestamp TEXT,
            query TEXT,
            user_location TEXT,
            result_type TEXT,
            top_service_ids TEXT, -- Stored as JSON string
            results_snapshot TEXT -- Stored as JSON string
        )
    ''')

    # 3. Actions Table (Clicks/Conversions)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            timestamp TEXT,
            action_type TEXT,
            service_id INTEGER,
            note TEXT,
            FOREIGN KEY(session_id) REFERENCES sessions(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize DB immediately on module load
init_db()

# --- 1. TIME FILTERING LOGIC (robust) ---
def parse_time(t):
    if not t or not isinstance(t, str):
        return None
    t = t.strip().lower()
    if t in ("24/7", "247", "always", "always open"):
        return "24/7"
    try:
        return dttime.fromisoformat(t)
    except Exception:
        for fmt in ("%H:%M", "%H.%M", "%H%M"):
            try:
                return dt.strptime(t, fmt).time()
            except Exception:
                continue
    return None

def is_shop_open(open_str, close_str, now_dt=None):
    if now_dt is None:
        now_dt = dt.now()
    now = now_dt.time()
    o = parse_time(open_str)
    c = parse_time(close_str)

    if o == "24/7" or c == "24/7": return True
    if o is None or c is None: return False
    if o == c: return True
    if o < c: return o <= now <= c
    return now >= o or now <= c

# --- 2. LOCATION SCORE (UPDATED FOR REMOTE) ---
def calculate_location_score(shop_loc, user_loc):
    if not user_loc or not shop_loc:
        return 0.0
    shop = shop_loc.lower().strip()
    user = user_loc.lower().strip()

    # --- UPGRADE: Remote/Online Support ---
    # If the service is remote, it is relevant to EVERYONE (High score)
    if shop in ("remote", "online", "virtual", "anywhere"):
        return 0.9  # Score 0.9 to ensure visibility (just below exact same-hostel match)

    # Exact Match (Same Hostel)
    if shop == user:
        return 1.0
    
    # Adjacency Logic (H-5 near H-6)
    try:
        shop_num = int(''.join(filter(str.isdigit, shop)))
        user_num = int(''.join(filter(str.isdigit, user)))
        if abs(shop_num - user_num) <= 1:
            return 0.4
    except Exception:
        pass
    return 0.0

# --- 3. LLM Intent Analysis ---
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
        import re
        m = re.search(r'(\{.*\})', text, re.S)
        jtext = m.group(1) if m else text
        return json.loads(jtext)
    except Exception as e:
        print(f"[LLM error] {e}")
        words = [w.lower().strip(".,!?") for w in user_query_clean.split()][:5]
        return {"category": "General", "intent": " ".join(words[:3]) or "unknown", "urgency": 5, "keywords": words}

def analyze_intent(user_query):
    cleaned = " ".join(user_query.strip().split())
    return analyze_intent_cached(cleaned)

# --- 4. RANKING & MATCHING ---
def _service_keywords(service):
    kw = []
    # Handle DB list vs string
    db_kw = service.get("keywords", [])
    if isinstance(db_kw, str):
        try: db_kw = json.loads(db_kw)
        except: db_kw = []
    
    kw += [k.lower() for k in db_kw if isinstance(k, str)]
    desc = service.get("description", "") or ""
    kw += [w.strip(".,()").lower() for w in desc.split() if len(w) > 2]
    kw += [service.get("category", "").lower()]
    return set(kw)

def get_all_services():
    """Fetch all services from SQLite and convert to list of dicts."""
    conn = get_db_connection()
    rows = conn.execute('SELECT * FROM services').fetchall()
    conn.close()
    
    services = []
    for row in rows:
        svc = dict(row)
        # Parse JSON fields
        try:
            svc['keywords'] = json.loads(svc['keywords']) if svc['keywords'] else []
        except:
            svc['keywords'] = []
        services.append(svc)
    return services

# Compatibility alias
safe_load_services = get_all_services

def get_recommendations(user_query, user_location):
    services = get_all_services()
    print(f"🧠 Query: {user_query} | Location: {user_location}")
    ai = analyze_intent(user_query)
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
    services = get_all_services()
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
        return {"type": "fallback", "results": fall, "message": "No exact matches — showing popular open spots nearby.(Fallback)"}

# --- 5. SERVICE MANAGEMENT (CRUD via SQL) ---

def add_service_entry(entry):
    """Adds a new service to the DB."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Data prep
    incoming_name = (entry.get("name") or "").strip().lower()
    incoming_location = (entry.get("location") or "").strip().lower()
    incoming_whatsapp = (entry.get("whatsapp") or "").strip()
    
    # 1. Check duplicate WhatsApp
    if incoming_whatsapp:
        dup = cur.execute("SELECT id FROM services WHERE whatsapp = ?", (incoming_whatsapp,)).fetchone()
        if dup:
            conn.close()
            raise ValueError(f"Duplicate service detected: same WhatsApp number already exists (id={dup['id']}).")
            
    # 2. Check duplicate Name + Location
    dup = cur.execute("SELECT id FROM services WHERE LOWER(name) = ? AND LOWER(location) = ?", 
                      (incoming_name, incoming_location)).fetchone()
    if dup:
        conn.close()
        raise ValueError(f"Duplicate service detected: same name exists at this location (id={dup['id']}).")

    # Serialize keywords
    kws = entry.get("keywords", [])
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",") if k.strip()]
    kws_json = json.dumps(kws)

    cur.execute('''
        INSERT INTO services (name, category, location, open_time, close_time, description, keywords, whatsapp, form_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        entry.get("name"), entry.get("category"), entry.get("location"),
        entry.get("open_time"), entry.get("close_time"), entry.get("description"),
        kws_json, incoming_whatsapp, entry.get("form_url")
    ))
    
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    entry['id'] = new_id
    entry['keywords'] = kws
    return entry

def update_service(service_id, updated_fields):
    """Updates specific fields of a service in DB."""
    conn = get_db_connection()
    
    # Check existence
    if not conn.execute("SELECT id FROM services WHERE id = ?", (service_id,)).fetchone():
        conn.close()
        raise ValueError(f"Service with id={service_id} not found.")

    set_clauses = []
    values = []
    
    for k, v in updated_fields.items():
        if k == 'id': continue
        if k == 'keywords':
            # Handle keywords specially
            if isinstance(v, str):
                v = [x.strip() for x in v.split(",") if x.strip()]
            set_clauses.append("keywords = ?")
            values.append(json.dumps(v))
        else:
            set_clauses.append(f"{k} = ?")
            values.append(v)
            
    values.append(service_id)
    sql = f"UPDATE services SET {', '.join(set_clauses)} WHERE id = ?"
    
    conn.execute(sql, values)
    conn.commit()
    conn.close()
    return updated_fields

def delete_service(service_id):
    """Deletes a service from DB."""
    conn = get_db_connection()
    cur = conn.execute("DELETE FROM services WHERE id = ?", (service_id,))
    conn.commit()
    success = cur.rowcount > 0
    conn.close()
    return success

# --- 6. EVENTS & METRICS (SQL Version) ---

def _now_iso():
    return dt.now().isoformat()

def record_search(user_query, user_location, result_data):
    """Records session to 'sessions' table."""
    conn = get_db_connection()
    
    # Extract IDs
    top_ids = []
    for r in result_data.get("results", []):
        try:
            sid = r.get("service", {}).get("id")
            if sid is not None: top_ids.append(int(sid))
        except: pass
        
    cur = conn.execute('''
        INSERT INTO sessions (type, timestamp, query, user_location, result_type, top_service_ids, results_snapshot)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        "search_session", _now_iso(), user_query, user_location, result_data.get("type"),
        json.dumps(top_ids), json.dumps(result_data.get("results", []))
    ))
    
    sid = cur.lastrowid
    conn.commit()
    conn.close()
    return sid

def record_action(session_id, action_type, service_id=None, note=None):
    """Records action to 'actions' table."""
    conn = get_db_connection()
    
    # Verify session exists
    if not conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone():
        conn.close()
        return False
        
    conn.execute('''
        INSERT INTO actions (session_id, timestamp, action_type, service_id, note)
        VALUES (?, ?, ?, ?, ?)
    ''', (session_id, _now_iso(), action_type, service_id, note))
    
    conn.commit()
    conn.close()
    return True

def get_all_events():
    """
    Reconstructs the original nested event structure from SQL relational tables.
    Returns: List of session dicts, each containing an 'actions' list.
    """
    conn = get_db_connection()
    sessions_rows = conn.execute("SELECT * FROM sessions").fetchall()
    actions_rows = conn.execute("SELECT * FROM actions").fetchall()
    conn.close()

    # Convert sessions to dict and index by ID
    sessions_map = {}
    for r in sessions_rows:
        s = dict(r)
        # Parse JSON fields back
        try: s['top_service_ids'] = json.loads(s['top_service_ids'])
        except: s['top_service_ids'] = []
        try: s['results_snapshot'] = json.loads(s['results_snapshot'])
        except: s['results_snapshot'] = []
        
        s['actions'] = []
        sessions_map[s['id']] = s

    # Attach actions to their sessions
    for r in actions_rows:
        a = dict(r)
        sid = a['session_id']
        if sid in sessions_map:
            sessions_map[sid]['actions'].append(a)

    return list(sessions_map.values())

# Compatibility alias for metrics functions
safe_load_events = get_all_events

# --- METRICS CALCULATION (Unchanged logic, now powered by SQL data) ---

def _filter_events_timeframe(events, start_iso=None, end_iso=None):
    if not start_iso and not end_iso:
        return events
    out = []
    for e in events:
        t = e.get("timestamp")
        if not t: continue
        if start_iso and t < start_iso: continue
        if end_iso and t > end_iso: continue
        out.append(e)
    return out

def compute_CCR(start_iso=None, end_iso=None):
    events = get_all_events()
    events = _filter_events_timeframe(events, start_iso, end_iso)
    sessions = [e for e in events if e.get("type") == "search_session"]
    if not sessions:
        return {"CCR": 0.0, "sessions": 0, "conversions": 0}
    conv = 0
    for s in sessions:
        acts = s.get("actions", [])
        if any(a.get("action_type") in ("wa_click", "form_click") for a in acts):
            conv += 1
    rate = (conv / len(sessions)) * 100.0
    return {"CCR": round(rate, 2), "sessions": len(sessions), "conversions": conv}

def compute_dead_end_rate(start_iso=None, end_iso=None):
    events = get_all_events()
    events = _filter_events_timeframe(events, start_iso, end_iso)
    sessions = [e for e in events if e.get("type") == "search_session"]
    if not sessions:
        return {"dead_end_rate": 0.0, "sessions": 0, "dead_ends": 0}
    dead = sum(1 for s in sessions if s.get("result_type") == "fallback")
    rate = (dead / len(sessions)) * 100.0
    return {"dead_end_rate": round(rate, 2), "sessions": len(sessions), "dead_ends": dead}

def compute_location_sensitivity(start_iso=None, end_iso=None):
    events = get_all_events()
    events = _filter_events_timeframe(events, start_iso, end_iso)
    sessions = [e for e in events if e.get("type") == "search_session"]
    if not sessions:
        return {"same_clicks": 0, "other_clicks": 0, "ratio": None, "total_clicks": 0}

    same = 0
    other = 0
    services = {s.get("id"): s for s in get_all_services()}
    
    for s in sessions:
        loc = (s.get("user_location") or "").strip().lower()
        for a in s.get("actions", []):
            if a.get("action_type") not in ("wa_click", "form_click"):
                continue
            sid = a.get("service_id")
            svc = services.get(sid)
            svc_loc = (svc.get("location") or "").strip().lower() if svc else None
            score = calculate_location_score(svc_loc, loc)
            if score >= 1.0:
                same += 1
            else:
                other += 1
    total = same + other
    ratio = None
    if total > 0:
        ratio = round(same / total, 3)
    return {"same_clicks": same, "other_clicks": other, "ratio": ratio, "total_clicks": total}

def compute_all_metrics(start_iso=None, end_iso=None):
    c = compute_CCR(start_iso, end_iso)
    d = compute_dead_end_rate(start_iso, end_iso)
    l = compute_location_sensitivity(start_iso, end_iso)
    return {"CCR": c, "DeadEnd": d, "LocationSensitivity": l}

def events_to_csv_bytes(start_iso=None, end_iso=None):
    events = _filter_events_timeframe(get_all_events(), start_iso, end_iso)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["session_id","session_timestamp","query","user_location","result_type","action_timestamp","action_type","service_id","note"])
    for s in events:
        sid = s.get("id")
        stime = s.get("timestamp")
        q = s.get("query","")
        loc = s.get("user_location","")
        rtype = s.get("result_type","")
        acts = s.get("actions", []) or []
        if not acts:
            writer.writerow([sid, stime, q, loc, rtype, "","","",""])
        else:
            for a in acts:
                writer.writerow([sid, stime, q, loc, rtype, a.get("timestamp",""), a.get("action_type",""), a.get("service_id",""), a.get("note","")])
    return out.getvalue().encode("utf-8")
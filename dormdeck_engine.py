import json
import datetime
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime as dt

# --- CONFIGURATION ---
# TODO: Brother, replace this with your actual API Key from Google AI Studio
# Load environment variables from .env file
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY_DORMDECK")

if API_KEY == "YOUR_GEMINI_API_KEY":
    print("⚠️ WARNING: You haven't set your Gemini API Key in dormdeck_engine.py yet!")

# Configure Gemini
genai.configure(api_key=API_KEY)

# --- 1. LOAD DATABASE ---
def load_services():
    try:
        with open('services.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# --- 2. TIME FILTERING LOGIC ---
def is_shop_open(open_str, close_str):
    """
    Checks if a shop is open right now.
    Handles midnight crossing (e.g., Open 18:00, Close 03:00).
    """
    now = dt.now().time()
    open_time = dt.strptime(open_str, "%H:%M").time()
    close_time = dt.strptime(close_str, "%H:%M").time()

    if open_time < close_time:
        # Standard hours (e.g., 09:00 to 17:00)
        return open_time <= now <= close_time
    else:
        # Midnight crossing (e.g., 18:00 to 03:00)
        # It's open if it's after opening time OR before closing time
        return now >= open_time or now <= close_time

# --- 3. LOCATION WEIGHTING SYSTEM ---
def calculate_location_score(shop_loc, user_loc):
    """
    Simple distance logic for the MVP.
    Same hostel = 1.0 (Full match)
    Adjacent = 0.4 (Partial match) - Can be expanded with a map later
    Far = 0.0
    """
    if not user_loc:
        return 0.0
    
    shop_loc = shop_loc.lower().strip()
    user_loc = user_loc.lower().strip()

    if shop_loc == user_loc:
        return 1.0 # Perfect match
    
    # Simple adjacency logic (example: H-1 is close to H-2)
    # Extract numbers: "h-5" -> 5
    try:
        shop_num = int(''.join(filter(str.isdigit, shop_loc)))
        user_num = int(''.join(filter(str.isdigit, user_loc)))
        if abs(shop_num - user_num) <= 1:
            return 0.4 # Adjacent match
    except:
        pass
        
    return 0.0

# --- 4. SEMANTIC MATCHING WITH LLM ---
def analyze_intent(user_query):
    """
    Uses Gemini 1.5 Flash to extract structured intent from the user's messy text.
    Returns a JSON object.
    """
    prompt = f"""
    You are the brain of a campus concierge app. specific services.
    Analyze this student query: "{user_query}"
    
    Return a JSON object with:
    - "category": The likely service category (Food, Stationery, Services, Medicine, Transport).
    - "intent": A 3-word summary of what they want.
    - "urgency": A score 1-10 of how urgent this sounds.
    - "keywords": A list of 3 relevant search keywords expanded from the query.
    """

    try:
        model = genai.GenerativeModel("gemini-2.5-flash", 
                                      generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)
        return json.loads(response.text)
    except Exception as e:
        print(f"Error calling LLM: {e}")
        # Fallback if LLM fails
        return {"category": "General", "intent": "unknown", "urgency": 5, "keywords": user_query.split()}

# --- 5. RANKING ENGINE ---
def get_recommendations(user_query, user_location):
    services = load_services()
    
    print(f"🧠 Thinking... Analyzing query: '{user_query}' at '{user_location}'")
    
    # A. Get AI Understanding
    ai_analysis = analyze_intent(user_query)
    print(f"🤖 AI Analysis: {ai_analysis}")
    
    ranked_results = []
    
    for service in services:
        # --- SCORING FACTORS ---
        
        # 1. Semantic Score (50 points)
        # Check if category matches OR if keywords overlap
        semantic_score = 0.0
        if service['category'].lower() == ai_analysis['category'].lower():
            semantic_score = 1.0
        else:
            # Check keyword overlap
            service_tags = set(service['keywords'] + [service['description'].lower()])
            query_tags = set(ai_analysis['keywords'])
            if not service_tags.isdisjoint(query_tags):
                semantic_score = 0.5 # Partial match on keywords
        
        # 2. Location Score (30 points)
        loc_score = calculate_location_score(service['location'], user_location)
        
        # 3. Open Status Score (20 points)
        is_open = is_shop_open(service['open_time'], service['close_time'])
        status_score = 1.0 if is_open else 0.0
        
        # --- FINAL FORMULA ---
        # Score = (semantic * 50) + (location * 30) + (open * 20)
        total_score = (semantic_score * 50) + (loc_score * 30) + (status_score * 20)
        
        ranked_results.append({
            "service": service,
            "score": total_score,
            "is_open": is_open,
            "reasons": {
                "semantic": semantic_score,
                "location": loc_score,
                "open": is_open
            }
        })
    
    # Sort by score descending
    ranked_results.sort(key=lambda x: x['score'], reverse=True)
    
    return ranked_results[:3] # Return top 3

# --- MAIN BLOCK FOR TESTING DAY 1 ---
if __name__ == "__main__":
    # Simulate a user test
    test_query = "I really need some fries right now"
    test_location = "H-5"
    
    print("--- DORMDECK BACKEND TEST ---")
    results = get_recommendations(test_query, test_location)
    
    print("\n--- TOP RECOMMENDATIONS ---")
    for res in results:
        s = res['service']
        status = "🟢 OPEN" if res['is_open'] else "🔴 CLOSED"
        print(f"[{res['score']} pts] {s['name']} ({status})")
        print(f"   📍 {s['location']} | 📝 {s['description']}")
        print(f"   💡 Match details: Loc: {res['reasons']['location']}, Sem: {res['reasons']['semantic']}")
        print("-" * 30)
import json
import datetime
import os
from dotenv import load_dotenv
import google.generativeai as genai
from datetime import datetime as dt

# --- CONFIGURATION ---
# Load environment variables from .env file
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY_DORMDECK")

if not API_KEY or API_KEY == "YOUR_GEMINI_API_KEY":
    print("⚠️ WARNING: You haven't set your Gemini API Key in environment variables!")
    print("Make sure your .env file contains: GEMINI_API_KEY_DORMDECK=your_actual_api_key_here")

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
    Uses Gemini 2.5 Flash to extract structured intent from the user's messy text.
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

# --- 5. SMART RANKING ENGINE ---
def get_recommendations(user_query, user_location):
    """
    Main recommendation engine that uses semantic matching to find relevant services.
    Only returns services that are semantically related to the query.
    """
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
        
        # --- THE KEY FIX ---
        # We enforce that semantic_score MUST be > 0.
        # If the service has nothing to do with the query, we discard it,
        # even if it is right next door.
        if semantic_score > 0:
            # --- FINAL FORMULA ---
            # Score = (semantic * 50) + (location * 30) + (open * 20)
            total_score = (semantic_score * 50) + (loc_score * 30) + (status_score * 20)
            
            # Only include if there is at least SOME relevance or location match
            if total_score > 10:
                ranked_results.append({
                    "service": service,
                    "score": total_score,
                    "is_open": is_open,
                    "match_type": "smart"
                })
    
    # Sort by score descending
    ranked_results.sort(key=lambda x: x['score'], reverse=True)
    
    # Return top 3 smart recommendations if found
    return ranked_results[:3]

# --- 6. FALLBACK ENGINE ---
def get_fallback_suggestions(user_location):
    """
    Returns generic popular open places if the AI finds nothing specific.
    This serves as a backup when no semantically relevant services are found.
    """
    services = load_services()
    open_services = []
    
    for service in services:
        is_open = is_shop_open(service['open_time'], service['close_time'])
        
        # Prioritize Open shops
        if is_open:
            # Boost score slightly if close to user
            loc_score = calculate_location_score(service['location'], user_location)
            score = 50 + (loc_score * 50) 
            open_services.append({
                "service": service,
                "score": score,
                "is_open": True,
                "match_type": "fallback"
            })
    
    # Sort by location relevance
    open_services.sort(key=lambda x: x['score'], reverse=True)
    
    # Return top 3 open, or just top 3 random if everything is closed
    if not open_services:
        return [{"service": s, "score": 0, "is_open": False, "match_type": "fallback"} for s in services[:3]]
        
    return open_services[:3]

# --- 7. MAIN API FUNCTION ---
def get_all_recommendations(user_query, user_location):
    """
    Main function that combines smart recommendations with fallback.
    Returns either smart matches or fallback suggestions.
    """
    # First try to get smart recommendations
    smart_results = get_recommendations(user_query, user_location)
    
    if smart_results:
        print(f"✅ Found {len(smart_results)} smart recommendations")
        return {
            "type": "smart",
            "results": smart_results,
            "message": "Here are the best matches for your request!"
        }
    else:
        print(f"🤔 No smart matches found, showing fallback suggestions")
        fallback_results = get_fallback_suggestions(user_location)
        return {
            "type": "fallback",
            "results": fallback_results,
            "message": "We couldn't find exactly what you're looking for. Here are some popular open spots nearby:"
        }

# --- MAIN BLOCK FOR TESTING ---
if __name__ == "__main__":
    # Test Case 1: Specific query that should find matches
    test_query = "I really need some fries right now"
    test_location = "H-5"
    
    print("=" * 50)
    print("TEST CASE 1: Specific Food Query")
    print("=" * 50)
    result = get_all_recommendations(test_query, test_location)
    
    print(f"\n📊 Result Type: {result['type']}")
    print(f"💬 Message: {result['message']}")
    
    print("\n--- TOP RECOMMENDATIONS ---")
    for idx, res in enumerate(result['results'], 1):
        s = res['service']
        status = "🟢 OPEN" if res['is_open'] else "🔴 CLOSED"
        print(f"\n{idx}. [{res['score']} pts] {s['name']} ({status})")
        print(f"   📍 {s['location']} | 📝 {s['description']}")
        print(f"   ⏰ Hours: {s['open_time']} - {s['close_time']}")
        print(f"   🎯 Match Type: {res['match_type']}")
    
    print("\n" + "=" * 50)
    
    # Test Case 2: Random query that might not find matches
    test_query2 = "I want to learn quantum physics"
    print(f"\nTEST CASE 2: Unusual Query - '{test_query2}'")
    print("=" * 50)
    
    result2 = get_all_recommendations(test_query2, test_location)
    
    print(f"\n📊 Result Type: {result2['type']}")
    print(f"💬 Message: {result2['message']}")
    
    print("\n--- FALLBACK SUGGESTIONS ---")
    for idx, res in enumerate(result2['results'], 1):
        s = res['service']
        status = "🟢 OPEN" if res['is_open'] else "🔴 CLOSED"
        print(f"\n{idx}. [{res['score']} pts] {s['name']} ({status})")
        print(f"   📍 {s['location']} | 📝 {s['description']}")
        print(f"   ⏰ Hours: {s['open_time']} - {s['close_time']}")
        print(f"   🎯 Match Type: {res['match_type']}")
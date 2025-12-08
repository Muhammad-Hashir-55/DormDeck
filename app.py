# app.py (full file) - Admin Panel with metrics + AUTOMATED logging buttons
import streamlit as st
import streamlit.components.v1 as components
import time
import dormdeck_engine
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

# load env (for admin credentials)
load_dotenv()
ADMIN_USER = os.getenv("ADMIN_USER_DORMDECK")
ADMIN_PASS = os.getenv("ADMIN_PASS_DORMDECK")

# --- 1. PAGE CONFIG & STYLING ---
st.set_page_config(
    page_title="DormDeck AI",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="expanded"
)

# Custom CSS for premium look
st.markdown("""
<style>
    .block-container {padding-top: 2rem;}
    .stChatMessage {border-radius: 15px; padding: 10px; margin-bottom: 10px;}
    /* Style for the Smart Buttons to look like Call-to-Actions */
    .stButton button {
        width: 100%;
        border-radius: 8px !important;
        font-weight: bold !important;
        transition: all 0.2s ease;
    }
    .status-open { color: #25D366; font-weight: bold; border: 1px solid #25D366; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; display: inline-block; margin-bottom: 5px; }
    .status-closed { color: #FF4B4B; font-weight: bold; border: 1px solid #FF4B4B; padding: 2px 8px; border-radius: 12px; font-size: 0.8rem; display: inline-block; margin-bottom: 5px; }
    .stProgress > div > div > div { background-color: #25D366; }
    .stChatInput {border-radius: 20px !important;}
</style>
""", unsafe_allow_html=True)

# --- Helper: Improved JavaScript Redirect ---
# Uses anchor tag click to reduce popup blocking issues
def open_link_js(url):
    js = f"""
    <script>
        var a = window.document.createElement("a");
        a.target = '_blank';
        a.href = "{url}";
        a.click();
    </script>
    """
    components.html(js, height=0)

# --- Helper: get current page param (modern API) ---
params = st.query_params
page = params.get("page", ["main"])[0]

# --- Sidebar ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4712/4712009.png", width=80)
    st.title("DormDeck")
    st.caption("Campus Concierge v2.0")
    st.markdown("---")

    st.subheader("📍 Your Context")
    user_location = st.selectbox(
        "Current Location",
        ["H-1", "H-2", "H-3", "H-4", "H-5", "H-6", "H-7", "H-8", "H-12", "Library", "Cafeteria"],
        index=4
    )
    st.info(f"Finding services best for **{user_location}**")
    st.markdown("---")

    # Debug toggle
    if st.checkbox("Show Debug Information"):
        st.session_state['debug_mode'] = True
        st.success("Debug mode enabled - showing match scores and logic")
    else:
        st.session_state['debug_mode'] = st.session_state.get('debug_mode', False)

    st.markdown("---")
    # SELLER ONBOARDING FORM (Quick)
    st.subheader("🧾 Seller Onboarding (Quick)")
    with st.expander("Add / Update your service (no login required)"):
        with st.form("seller_form"):
            s_name = st.text_input("Seller / Shop Name", "")
            s_category = st.selectbox("Category", ["Food", "Stationery", "Services", "Medicine", "Transport", "General"])
            s_location = st.selectbox("Location", ["H-1","H-2","H-3","H-4","H-5","H-6","H-7","H-8","H-12","Library","Cafeteria"])
            s_open = st.text_input("Open Time (HH:MM) or '24/7'", "18:00")
            s_close = st.text_input("Close Time (HH:MM) or '24/7'", "03:00")
            s_whatsapp = st.text_input("WhatsApp (country code + number, e.g. 92300xxxxxxx)")
            s_desc = st.text_area("Short Description", "")
            s_keywords = st.text_input("Keywords (comma separated)", "")
            s_form = st.text_input("Optional Google Form URL", "")

            submitted = st.form_submit_button("➕ Add Service")
            if submitted:
                errors = []
                if not s_name.strip():
                    errors.append("Name required.")
                if not s_whatsapp.strip() or not s_whatsapp.strip().isdigit():
                    errors.append("WhatsApp must be digits only (include country code).")
                if errors:
                    for e in errors:
                        st.error(e)
                else:
                    entry = {
                        "name": s_name.strip(),
                        "category": s_category,
                        "location": s_location,
                        "open_time": s_open.strip(),
                        "close_time": s_close.strip(),
                        "description": s_desc.strip(),
                        "keywords": [k.strip() for k in s_keywords.split(",") if k.strip()],
                        "whatsapp": s_whatsapp.strip(),
                        "form_url": s_form.strip() or None
                    }
                    try:
                        added = dormdeck_engine.add_service_entry(entry)
                        st.success(f"Service added ✅ (id: {added['id']}). It will appear in search immediately.")
                    except ValueError as dup_err:
                        st.warning(str(dup_err))
                    except Exception as ex:
                        st.error(f"Failed to add service: {ex}")


    st.markdown("---")

    # ADMIN LOGIN area
    st.subheader("🔒 Admin Panel")
    if st.session_state.get("is_admin"):
        st.info("You are logged in as admin.")
        if st.button("Open Admin Panel"):
            st.query_params = {"page": ["admin"]}
            st.rerun()
        if st.button("Logout Admin"):
            st.session_state["is_admin"] = False
            st.query_params = {"page": ["main"]}
            st.rerun()
    else:
        with st.form("admin_login_form"):
            a_user = st.text_input("Admin User")
            a_pass = st.text_input("Admin Password", type="password")
            login = st.form_submit_button("Login")
            if login:
                if str(a_user).strip() == str(ADMIN_USER) and str(a_pass).strip() == str(ADMIN_PASS):
                    st.success("Admin login successful.")
                    st.session_state["is_admin"] = True
                    st.query_params = {"page": ["admin"]}
                    st.rerun()
                else:
                    st.error("Invalid credentials.")

    st.markdown("---")
    
    # --- FIX 1: Clear Chat using Callback ---
    def clear_chat_history():
        st.rerun()
        st.session_state.messages = [
            {"role": "assistant", "content": f"Chat cleared! I'm ready to help. What do you need near **{user_location}**?"}
        ]
    
    st.button("🗑️ Clear Chat History", on_click=clear_chat_history)

# --- 3. SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": f"🎓 **Welcome to DormDeck AI!**\n\nI'm your campus concierge. I can find food, stationary, services, medicine, or transport near **{user_location}**.\n\nTry asking for:\n• *'I need spicy wings right now'*\n• *'Printing near H-5'*\n• *'Emergency medicine delivery'*"}
    ]

if "pending_quick_query" not in st.session_state:
    st.session_state.pending_quick_query = None

if "last_session_id" not in st.session_state:
    st.session_state.last_session_id = None

# --- ADMIN PAGE ---
if page == "admin" and st.session_state.get("is_admin"):

    # --- METRICS SECTION (Actionable Metrics) ---
    st.title("🔧 Admin Panel — DormDeck Services")

    st.markdown("### 📈 Actionable Metrics")
    st.info("These metrics track the 'Measure' phase assumptions: Connection Conversion (Intent), Dead Ends (Supply), and Location Sensitivity.")
    
    time_option = st.selectbox("Time range", ["All time", "Last 7 days", "Last 30 days", "Custom"], index=0)
    start_iso = None
    end_iso = None
    if time_option == "Last 7 days":
        end_iso = datetime.now().isoformat()
        start_iso = (datetime.now() - timedelta(days=7)).isoformat()
    elif time_option == "Last 30 days":
        end_iso = datetime.now().isoformat()
        start_iso = (datetime.now() - timedelta(days=30)).isoformat()
    elif time_option == "Custom":
        c1 = st.date_input("Start date")
        c2 = st.date_input("End date")
        if c1:
            start_iso = datetime.combine(c1, datetime.min.time()).isoformat()
        if c2:
            end_iso = datetime.combine(c2, datetime.max.time()).isoformat()

    try:
        metrics = dormdeck_engine.compute_all_metrics(start_iso, end_iso)
        c = metrics["CCR"]
        d = metrics["DeadEnd"]
        l = metrics["LocationSensitivity"]
    except Exception as e:
        st.error(f"Failed to compute metrics: {e}")
        metrics = None
        c = {"CCR": 0.0, "sessions": 0, "conversions": 0}
        d = {"dead_end_rate": 0.0, "sessions": 0, "dead_ends": 0}
        l = {"same_clicks": 0, "other_clicks": 0, "ratio": None, "total_clicks": 0}

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Connection Conversion Rate (CCR)", 
            f"{c['CCR']} %", 
            delta=f"{c.get('conversions',0)}/{c.get('sessions',0)} conversions",
            help="Target > 15%. Formula: (Unique Clicks on WA/Form / Total Queries) * 100"
        )
    with col2:
        st.metric(
            "Search Dead End Rate", 
            f"{d['dead_end_rate']} %", 
            delta=f"{d.get('dead_ends',0)}/{d.get('sessions',0)} dead-ends",
            help="Target < 40%. Frequency of 'fallback' results."
        )
    with col3:
        ratio_str = f"{l['ratio']:.2f}" if l.get("ratio") is not None else "N/A"
        st.metric(
            "Location Sensitivity (Same/Total)", 
            ratio_str, 
            delta=f"{l.get('same_clicks',0)}/{l.get('total_clicks',0)} clicks",
            help="Target NOT 1:1. Ratio of clicks on Same-Hostel vs Adjacent/Far."
        )

    st.markdown("---")
    # Export CSV of events
    try:
        csv_bytes = dormdeck_engine.events_to_csv_bytes(start_iso, end_iso)
        st.download_button("⬇️ Download events CSV", csv_bytes, file_name="dormdeck_events.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Failed to prepare CSV export: {e}")

    st.markdown("### Raw Events")
    events = dormdeck_engine.get_all_events()
    if events:
        import pandas as pd
        rows = []
        for s in events:
            sid = s.get("id")
            acts = s.get("actions") or []
            if acts:
                for a in acts:
                    rows.append({
                        "session_id": sid,
                        "session_ts": s.get("timestamp"),
                        "query": s.get("query"),
                        "user_location": s.get("user_location"),
                        "result_type": s.get("result_type"),
                        "action_ts": a.get("timestamp"),
                        "action_type": a.get("action_type"),
                        "service_id": a.get("service_id"),
                        "note": a.get("note")
                    })
            else:
                rows.append({
                    "session_id": sid,
                    "session_ts": s.get("timestamp"),
                    "query": s.get("query"),
                    "user_location": s.get("user_location"),
                    "result_type": s.get("result_type"),
                    "action_ts": None,
                    "action_type": None,
                    "service_id": None,
                    "note": None
                })
        df = pd.DataFrame(rows)
        st.dataframe(df)
    else:
        st.info("No events recorded yet.")

    st.markdown("---")
    # --- END METRICS SECTION ---

    st.markdown("Manage `services.json` entries: view, edit, add, delete.")
    services = dormdeck_engine.get_all_services()

    # show dataset
    if services:
        st.dataframe(services)
    else:
        st.info("No services found.")

    st.markdown("---")
    st.subheader("Edit / Delete Service")
    ids = [s.get("id") for s in services if s.get("id") is not None]
    if ids:
        sel_id = st.selectbox("Select service id to edit", ids)
        sel_service = next((s for s in services if s.get("id") == sel_id), None)
        if sel_service:
            with st.form("edit_service_form"):
                e_name = st.text_input("Name", sel_service.get("name", ""))
                e_category = st.selectbox("Category", ["Food", "Stationery", "Services", "Medicine", "Transport", "General"], index=["Food","Stationery","Services","Medicine","Transport","General"].index(sel_service.get("category","Food")) if sel_service.get("category") else 0)
                e_location = st.text_input("Location", sel_service.get("location",""))
                e_open = st.text_input("Open Time", sel_service.get("open_time",""))
                e_close = st.text_input("Close Time", sel_service.get("close_time",""))
                e_whatsapp = st.text_input("WhatsApp", sel_service.get("whatsapp",""))
                e_description = st.text_area("Description", sel_service.get("description",""))
                e_keywords = st.text_input("Keywords (comma separated)", ", ".join(sel_service.get("keywords", [])))
                e_form = st.text_input("Form URL", sel_service.get("form_url",""))
                update_btn = st.form_submit_button("Update Service")
                delete_btn = st.form_submit_button("Delete Service")

                if update_btn:
                    try:
                        updated = {
                            "name": e_name.strip(),
                            "category": e_category,
                            "location": e_location.strip(),
                            "open_time": e_open.strip(),
                            "close_time": e_close.strip(),
                            "description": e_description.strip(),
                            "keywords": e_keywords.strip(),
                            "whatsapp": e_whatsapp.strip(),
                            "form_url": e_form.strip() or None
                        }
                        dormdeck_engine.update_service(sel_id, updated)
                        st.success("Service updated.")
                        st.query_params = {"page": ["admin"]}  # keep admin page visible
                        st.rerun()
                    except Exception as ex:
                        st.error(f"Update failed: {ex}")

                if delete_btn:
                    try:
                        ok = dormdeck_engine.delete_service(sel_id)
                        if ok:
                            st.success("Service deleted.")
                            st.query_params = {"page": ["admin"]}
                            st.rerun()
                        else:
                            st.error("Delete failed (id not found).")
                    except Exception as ex:
                        st.error(f"Delete failed: {ex}")
    else:
        st.info("No editable services (missing id fields).")

    st.markdown("---")
    st.subheader("Add New Service (Admin)")
    with st.form("admin_add_form"):
        a_name = st.text_input("Seller / Shop Name", "")
        a_category = st.selectbox("Category", ["Food", "Stationery", "Services", "Medicine", "Transport", "General"], index=0)
        a_location = st.text_input("Location", "H-5")
        a_open = st.text_input("Open Time", "09:00")
        a_close = st.text_input("Close Time", "21:00")
        a_whatsapp = st.text_input("WhatsApp", "")
        a_desc = st.text_area("Short Description", "")
        a_keywords = st.text_input("Keywords (comma separated)", "")
        a_form = st.text_input("Optional Google Form URL", "")

        add_ok = st.form_submit_button("Add Service (Admin)")
        if add_ok:
            try:
                entry = {
                    "name": a_name.strip(),
                    "category": a_category,
                    "location": a_location.strip(),
                    "open_time": a_open.strip(),
                    "close_time": a_close.strip(),
                    "description": a_desc.strip(),
                    "keywords": [k.strip() for k in a_keywords.split(",") if k.strip()],
                    "whatsapp": a_whatsapp.strip(),
                    "form_url": a_form.strip() or None
                }
                added = dormdeck_engine.add_service_entry(entry)
                st.success(f"Added (id: {added['id']}).")
                st.query_params = {"page": ["admin"]}
                st.rerun()
            except Exception as ex:
                st.error(f"Add failed: {ex}")

    # admin footer / back button
    if st.button("← Back to main app"):
        st.query_params = {"page": ["main"]}
        st.rerun()

    st.stop()  # stop further rendering of main app when on admin page

# --- MAIN APP UI (default) ---
st.title("🎓 DormDeck AI - Campus Concierge")
st.markdown("### ⚡ Quick Actions")

quick_actions = [
    {"label": "🍔 Food", "query": "I need food delivery options", "key": "quick_food"},
    {"label": "📚 Printing", "query": "Where can I print documents?", "key": "quick_print"},
    {"label": "💊 Medicine", "query": "Need emergency medicine delivery", "key": "quick_med"},
    {"label": "🚗 Transport", "query": "Need transport service", "key": "quick_transport"},
    {"label": "🛠️ Services", "query": "What services are available?", "key": "quick_services"}
]

quick_cols = st.columns(5)
for idx, action in enumerate(quick_actions):
    with quick_cols[idx]:
        if st.button(action["label"], key=action["key"], use_container_width=True):
            st.session_state.pending_quick_query = action["query"]
            st.rerun()

st.markdown("---")

# Render chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 1. HANDLE NEW SEARCH (from input or quick action)
if st.session_state.pending_quick_query:
    prompt = st.session_state.pending_quick_query
    st.session_state.pending_quick_query = None
else:
    prompt = st.chat_input("Tell me what you need... (Ex: I need fries, medicine delivery, printing)")

if prompt:
    # Append User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    with st.chat_message("assistant"):
        with st.spinner("🧠 Scanning campus services..."):
            time.sleep(0.7)
            # Perform Search
            result_data = dormdeck_engine.get_all_recommendations(prompt, user_location)
            
            # --- METRIC 2: DEAD END & LOGGING ---
            # Record the session (generates session_id)
            try:
                session_id = dormdeck_engine.record_search(prompt, user_location, result_data)
                st.session_state['last_session_id'] = session_id
                # Save results to session state so they persist when buttons are clicked (which triggers rerun)
                st.session_state['last_results'] = result_data
            except Exception as e:
                session_id = None
                st.error(f"Logging session failed: {e}")

            # Prepare Display Message
            results = result_data["results"]
            message = result_data["message"]
            result_type = result_data["type"]
            
            if result_type == "smart":
                if results:
                    intro = f"✅ {message}\n\n**Best match:** {results[0]['service']['name']}"
                else:
                    intro = "🤔 No perfect matches. Here are nearby options:"
            else:
                intro = f"💡 {message}"
            
            # Append Assistant Response
            st.session_state.messages.append({"role": "assistant", "content": intro})
            st.rerun()

# 2. RENDER RESULTS (Persistent across reruns)
# We check if there are results from the last search to display them below the chat
if 'last_results' in st.session_state and st.session_state['last_results']:
    results = st.session_state['last_results'].get("results", [])
    
    # We display them in a container below the chat history
    with st.container():
        st.markdown("### 🔍 Search Results")
        
        if not results:
            st.warning("No services found.")
        
        for idx, item in enumerate(results, 1):
            service = item['service']
            score = int(item['score'])
            is_open = item['is_open']
            
            badge_class = "status-open" if is_open else "status-closed"
            badge_text = "🟢 OPEN NOW" if is_open else "🔴 CLOSED"
            
            emoji = {
                "Food": "🍔", "Stationery": "📚", "Services": "🛠️",
                "Medicine": "💊", "Transport": "🚗"
            }.get(service.get('category'), "📍")

            with st.container():
                st.markdown(f"#### {idx}. {service.get('name')} {emoji}")
                col1, col2 = st.columns([0.65, 0.35])
                
                with col1:
                    st.markdown(f"<span class='{badge_class}'>{badge_text}</span>", unsafe_allow_html=True)
                    st.caption(f"📍 **{service.get('location')}** • {service.get('category')}")
                    st.write(f"_{service.get('description')}_")
                    st.caption(f"⏰ {service.get('open_time')} - {service.get('close_time')}")
                    st.progress(score / 100, text=f"Match Score: {score}%")
                
                with col2:
                    # --- FIX 2: Better Link Formatting & Redirection ---
                    
                    # 1. Clean the WhatsApp number (Remove spaces, +, -)
                    raw_wa = str(service.get('whatsapp', ''))
                    clean_wa = raw_wa.replace('+', '').replace(' ', '').replace('-', '')
                    
                    wa_msg = f"Hi {service.get('name')}! 👋 I found you on DormDeck. I'm in {user_location}. I need help."
                    wa_link = f"https://wa.me/{clean_wa}?text={wa_msg}"
                    
                    # Whatsapp Button
                    # Unique Key is vital: session_id + service_id
                    sid = st.session_state.get('last_session_id')
                    svc_id = service.get('id')
                    
                    # Smart Button 1: WhatsApp
                    if st.button("💬 Chat on WhatsApp", key=f"btn_wa_{sid}_{svc_id}", type="primary"):
                        if sid:
                            # 1. Log the metric
                            dormdeck_engine.record_action(sid, "wa_click", svc_id)
                            st.toast("Redirecting to WhatsApp... (Action Logged)", icon="🚀")
                            # 2. Open Link via JS (Improved)
                            open_link_js(wa_link)
                    
                    # Smart Button 2: Google Form (if exists)
                    form_url = service.get("form_url")
                    if form_url:
                        if st.button("📝 Fill Order Form", key=f"btn_form_{sid}_{svc_id}"):
                            if sid:
                                # 1. Log the metric
                                dormdeck_engine.record_action(sid, "form_click", svc_id)
                                st.toast("Opening Order Form... (Action Logged)", icon="📝")
                                # 2. Open Link via JS (Improved)
                                open_link_js(form_url)
                
                st.markdown("---")

# Footer
st.markdown("---")
st.caption("🎓 DormDeck AI v2.0 | Smart Campus Concierge | Using Gemini 2.5 Flash AI")
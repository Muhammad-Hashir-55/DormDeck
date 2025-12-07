import streamlit as st
import time
import dormdeck_engine

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
    header {visibility: hidden;}
    .block-container {padding-top: 2rem;}

    .stChatMessage {
        border-radius: 15px;
        padding: 10px;
        margin-bottom: 10px;
    }

    .stButton button {
        background-color: #25D366 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
    }
    .stButton button:hover {
        background-color: #128C7E !important;
    }

    .status-open {
        color: #25D366;
        font-weight: bold;
        border: 1px solid #25D366;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        display: inline-block;
        margin-bottom: 5px;
    }
    .status-closed {
        color: #FF4B4B;
        font-weight: bold;
        border: 1px solid #FF4B4B;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8rem;
        display: inline-block;
        margin-bottom: 5px;
    }

    .stProgress > div > div > div {
        background-color: #25D366;
    }

    .stChatInput {border-radius: 20px !important;}
</style>
""", unsafe_allow_html=True)

# --- 2. SIDEBAR ---
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

    if st.checkbox("Show Debug Information"):
        st.session_state['debug_mode'] = True
        st.success("Debug mode enabled - showing match scores and logic")
    else:
        st.session_state['debug_mode'] = False

    st.markdown("---")

    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = [
            {"role": "assistant", "content": f"Chat cleared! I'm ready to help. What do you need near **{user_location}**?"}
        ]
        st.rerun()

# --- 3. SESSION STATE ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": f"🎓 **Welcome to DormDeck AI!**\n\nI'm your campus concierge. I can find food, stationary, services, medicine, or transport near **{user_location}**.\n\nTry asking for:\n• *'I need spicy wings right now'*\n• *'Printing near H-5'*\n• *'Emergency medicine delivery'*"}
    ]

if "pending_quick_query" not in st.session_state:
    st.session_state.pending_quick_query = None

# --- 4. QUICK ACTION BUTTONS ---
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

# --- 5. RENDER CHAT HISTORY ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 6. PROCESS QUICK ACTION ---
if st.session_state.pending_quick_query:
    q = st.session_state.pending_quick_query
    st.session_state.pending_quick_query = None

    st.session_state.messages.append({"role": "user", "content": q})

    with st.chat_message("assistant"):
        with st.spinner("🧠 Scanning campus services..."):
            time.sleep(0.7)

            result_data = dormdeck_engine.get_all_recommendations(q, user_location)
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

            st.markdown(intro)
            st.session_state.messages.append({"role": "assistant", "content": intro})

            if results:
                for idx, item in enumerate(results, 1):
                    service = item['service']
                    score = int(item['score'])
                    is_open = item['is_open']

                    badge_class = "status-open" if is_open else "status-closed"
                    badge_text = "🟢 OPEN NOW" if is_open else "🔴 CLOSED"

                    emoji = {
                        "Food": "🍔",
                        "Stationery": "📚",
                        "Services": "🛠️",
                        "Medicine": "💊",
                        "Transport": "🚗"
                    }.get(service['category'], "📍")

                    with st.container(border=True):
                        col1, col2 = st.columns([0.7, 0.3])

                        with col1:
                            st.markdown(f"### {idx}. {service['name']} {emoji}")
                            st.markdown(f"<span class='{badge_class}'>{badge_text}</span>", unsafe_allow_html=True)
                            st.caption(f"📍 **Location:** {service['location']} • **Category:** {service['category']}")
                            st.write(f"📝 **Description:** {service['description']}")
                            st.caption(f"⏰ **Hours:** {service['open_time']} - {service['close_time']}")
                            st.progress(score / 100, text=f"Match Score: {score}%")

                        with col2:
                            wa_msg = f"Hi {service['name']}! 👋 I found you on DormDeck. I'm in {user_location}. I need: {q}"
                            wa_link = f"https://wa.me/{service['whatsapp']}?text={wa_msg}"
                            st.link_button("💬 Chat on WhatsApp", wa_link, use_container_width=True)

                            # --- GOOGLE FORM BUTTON ADDED ---
                            if service.get("form_url"):
                                st.link_button("📝 Fill Google Form", service["form_url"], use_container_width=True)

            st.rerun()

# --- 7. MAIN CHAT INPUT ---
if prompt := st.chat_input("Tell me what you need... (Ex: I need fries, medicine delivery, printing)"):

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("🧠 Scanning campus services..."):
            time.sleep(0.7)

            result_data = dormdeck_engine.get_all_recommendations(prompt, user_location)
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

            st.markdown(intro)
            st.session_state.messages.append({"role": "assistant", "content": intro})

            if results:
                for idx, item in enumerate(results, 1):
                    service = item['service']
                    score = int(item['score'])
                    is_open = item['is_open']

                    badge_class = "status-open" if is_open else "status-closed"
                    badge_text = "🟢 OPEN NOW" if is_open else "🔴 CLOSED"

                    emoji = {
                        "Food": "🍔",
                        "Stationery": "📚",
                        "Services": "🛠️",
                        "Medicine": "💊",
                        "Transport": "🚗"
                    }.get(service['category'], "📍")

                    with st.container(border=True):
                        col1, col2 = st.columns([0.7, 0.3])

                        with col1:
                            st.markdown(f"### {idx}. {service['name']} {emoji}")
                            st.markdown(f"<span class='{badge_class}'>{badge_text}</span>", unsafe_allow_html=True)
                            st.caption(f"📍 **Location:** {service['location']} • **Category:** {service['category']}")
                            st.write(f"📝 **Description:** {service['description']}")
                            st.caption(f"⏰ **Hours:** {service['open_time']} - {service['close_time']}")
                            st.progress(score / 100, text=f"Match Score: {score}%")

                        with col2:
                            wa_msg = f"Hi {service['name']}! 👋 I found you on DormDeck. I'm in {user_location}. I need: {prompt}"
                            wa_link = f"https://wa.me/{service['whatsapp']}?text={wa_msg}"
                            st.link_button("💬 Chat on WhatsApp", wa_link, use_container_width=True)

                            # --- GOOGLE FORM BUTTON ADDED ---
                            if service.get("form_url"):
                                st.link_button("📝 Fill Google Form", service["form_url"], use_container_width=True)

# --- 8. FOOTER ---
st.markdown("---")
st.caption("🎓 DormDeck AI v2.0 | Smart Campus Concierge | Using Gemini 2.5 Flash AI")

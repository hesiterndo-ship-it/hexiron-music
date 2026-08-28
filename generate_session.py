"""One-time interactive script to log in with the userbot's phone number
and print a session string. Run this manually once:

    python3 generate_session.py

It will ask for the phone number, then the login code Telegram sends
(and a 2FA password if that account has one enabled). Paste the printed
STRING_SESSION value into your environment variables afterward. You can
delete this file / never run it again once you have the string.
"""
from pyrogram import Client

from config import API_HASH, API_ID

with Client("hexiron_userbot_setup", api_id=API_ID, api_hash=API_HASH, in_memory=True) as app:
    session_string = app.export_session_string()
    print("\n\n=== COPY EVERYTHING BELOW THIS LINE INTO STRING_SESSION ===\n")
    print(session_string)
    print("\n=== COPY EVERYTHING ABOVE THIS LINE ===\n\n")

"""
Run this script ONCE in the Shell to generate your Telethon session.
After running, session.txt will be created and the bot will work automatically.

How to run:
    cd bot && python3 generate_session.py
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
SESSION_FILE = Path("session.txt")


async def main():
    print("\n=== Telethon Session Generator ===")
    print("Bu script faqat BIR MARTA ishga tushiriladi.\n")

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.start()

    session_string = client.session.save()
    SESSION_FILE.write_text(session_string)

    me = await client.get_me()
    print(f"\n✅ Muvaffaqiyat! Salom, {me.first_name}!")
    print(f"📁 Session saqlandi: {SESSION_FILE.resolve()}")
    print("\nEndi botni ishga tushiring — telefon raqami endi so'ralmaydi.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

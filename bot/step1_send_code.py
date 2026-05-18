"""Step 1: Send OTP code to phone number. Usage: python3 step1_send_code.py +998901234567"""
import asyncio, os, sys, json
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

async def main():
    phone = sys.argv[1]
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    result = await client.send_code_request(phone)
    # Save temporary state
    state = {"phone": phone, "phone_code_hash": result.phone_code_hash,
             "session": client.session.save()}
    with open("login_state.json", "w") as f:
        json.dump(state, f)
    await client.disconnect()
    print(f"✅ Kod yuborildi: {phone}")
    print("Telegramdan kelgan kodni step2_verify_code.py ga bering.")

asyncio.run(main())

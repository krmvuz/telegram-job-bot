"""Step 2: Verify OTP code. Usage: python3 step2_verify_code.py 12345 mypassword"""
import asyncio, os, sys, json
from pathlib import Path
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

load_dotenv()
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

async def main():
    code = sys.argv[1]
    password = sys.argv[2] if len(sys.argv) > 2 else None

    with open("login_state.json") as f:
        state = json.load(f)

    client = TelegramClient(StringSession(state["session"]), API_ID, API_HASH)
    await client.connect()

    try:
        await client.sign_in(phone=state["phone"],
                             code=code,
                             phone_code_hash=state["phone_code_hash"])
    except SessionPasswordNeededError:
        if not password:
            print("❌ 2FA paroli kerak! Qaytadan ishga tushiring:")
            print("   python3 step2_verify_code.py <kod> <parol>")
            await client.disconnect()
            return
        await client.sign_in(password=password)

    session_string = client.session.save()
    Path("session.txt").write_text(session_string)
    Path("login_state.json").unlink(missing_ok=True)

    me = await client.get_me()
    await client.disconnect()
    print(f"✅ Muvaffaqiyat! Salom, {me.first_name}!")
    print("session.txt saqlandi. Bot endi ishlaydi!")

asyncio.run(main())

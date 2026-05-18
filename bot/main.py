import asyncio
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telethon import TelegramClient
from telethon.sessions import StringSession

from search_engine import format_result, search_jobs

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
API_ID: int = int(os.environ["API_ID"])
API_HASH: str = os.environ["API_HASH"]

SESSION_FILE = Path("session.txt")
CHANNELS_FILE = Path("channels.json")

# ConversationHandler states
WAITING_CHANNEL = 1

# ---------------------------------------------------------------------------
# Telethon helpers
# ---------------------------------------------------------------------------

def load_session_string() -> str:
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    return ""


def save_session_string(session_string: str) -> None:
    SESSION_FILE.write_text(session_string)


async def create_telethon_client() -> TelegramClient:
    session_string = load_session_string()
    if not session_string:
        raise RuntimeError("session.txt topilmadi! Avval generate_session.py ni ishga tushiring.")

    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        raise RuntimeError("Session yaroqsiz. Qaytadan generate_session.py ni ishga tushiring.")

    new_session = client.session.save()
    if new_session != session_string:
        save_session_string(new_session)

    logger.info("Telethon client tayyor.")
    return client

# ---------------------------------------------------------------------------
# Channel storage
# ---------------------------------------------------------------------------

def load_channels() -> list[str]:
    if not CHANNELS_FILE.exists():
        return []
    try:
        return json.loads(CHANNELS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def save_channels(channels: list[str]) -> None:
    CHANNELS_FILE.write_text(json.dumps(channels, ensure_ascii=False, indent=2))

# ---------------------------------------------------------------------------
# Bot lifecycle
# ---------------------------------------------------------------------------

async def post_init(application: Application) -> None:
    client = await create_telethon_client()
    application.bot_data["telethon"] = client
    logger.info("Telethon client tayyor va saqlandi.")


async def post_shutdown(application: Application) -> None:
    client: TelegramClient | None = application.bot_data.get("telethon")
    if client and client.is_connected():
        await client.disconnect()

# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Salom! 👋 Ish vakansiyalarini qidirish boti.\n\n"
        "➕ Kanal qo'shish: /addchannel\n"
        "📋 Kanallar ro'yxati: /listchannels\n"
        "🗑 Kanal o'chirish: /removechannel\n"
        "❓ Yordam: /help"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Qidiruv misollari:\n"
        "• yunusobod afitsant\n"
        "• chilonzor haydovchi\n"
        "• toshkent oshpaz\n"
        "• mirzo ulugbek kassir\n\n"
        "Buyruqlar:\n"
        "/addchannel — kanal qo'shish\n"
        "/removechannel — kanal o'chirish\n"
        "/listchannels — kanallar ro'yxati"
    )


# ---------------------------------------------------------------------------
# /addchannel — conversation flow
# ---------------------------------------------------------------------------

async def cmd_addchannel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start add-channel conversation — ask user for username."""
    # If username already passed as argument, handle directly
    if context.args:
        return await _process_channel_input(update, context, context.args[0])

    await update.message.reply_text(
        "➕ Qo'shmoqchi bo'lgan kanal username'ini yozing.\n\n"
        "Misol: @tashkent_ish\n\n"
        "Bekor qilish uchun /cancel yozing."
    )
    return WAITING_CHANNEL


async def cmd_addchannel_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Receive channel username from user and add it."""
    text = update.message.text.strip()
    result = await _process_channel_input(update, context, text)
    return result


async def _process_channel_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, username: str
) -> int:
    """Validate and save a channel."""
    if not username.startswith("@"):
        username = "@" + username

    telethon: TelegramClient = context.bot_data["telethon"]

    checking_msg = await update.message.reply_text(f"🔍 {username} tekshirilmoqda...")

    try:
        await telethon.get_entity(username)
    except Exception:
        await checking_msg.delete()
        await update.message.reply_text(
            f"❌ {username} topilmadi yoki kanal yopiq.\n\n"
            "Kanal username'ini to'g'ri yozdingizmi?\n"
            "Misol: @tashkent_ish\n\n"
            "Qaytadan yozing yoki /cancel."
        )
        return WAITING_CHANNEL

    await checking_msg.delete()

    channels = load_channels()
    if username in channels:
        await update.message.reply_text(
            f"ℹ️ {username} allaqachon ro'yxatda bor.\n\n"
            "Yana kanal qo'shish uchun username yozing yoki /cancel."
        )
        return WAITING_CHANNEL

    channels.append(username)
    save_channels(channels)

    await update.message.reply_text(
        f"✅ {username} qo'shildi!\n\n"
        f"📋 Jami kanallar: {len(channels)} ta\n\n"
        "Yana kanal qo'shish uchun username yozing,\n"
        "yoki tugatish uchun /cancel."
    )
    return WAITING_CHANNEL


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel current conversation."""
    channels = load_channels()
    await update.message.reply_text(
        f"✅ Tayyor! Hozir {len(channels)} ta kanal saqlangan.\n\n"
        "Ish qidirish uchun matn yozing, masalan:\n"
        "yunusobod afitsant"
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /removechannel — conversation flow
# ---------------------------------------------------------------------------

WAITING_REMOVE = 2


async def cmd_removechannel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show saved channels and ask which to remove."""
    if context.args:
        return await _process_remove_input(update, context, context.args[0])

    channels = load_channels()
    if not channels:
        await update.message.reply_text(
            "Hali kanal qo'shilmagan.\n/addchannel buyrug'ini ishlating."
        )
        return ConversationHandler.END

    lines = [f"{i + 1}. {ch}" for i, ch in enumerate(channels)]
    await update.message.reply_text(
        "🗑 Qaysi kanalni o'chirmoqchisiz?\n\n"
        + "\n".join(lines)
        + "\n\nUsername yozing (masalan @tashkent_ish)\nBekor qilish: /cancel"
    )
    return WAITING_REMOVE


async def cmd_removechannel_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    return await _process_remove_input(update, context, text)


async def _process_remove_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, username: str
) -> int:
    if not username.startswith("@"):
        username = "@" + username

    channels = load_channels()
    if username not in channels:
        await update.message.reply_text(
            f"❌ {username} ro'yxatda yo'q.\n\nBoshqa username yozing yoki /cancel."
        )
        return WAITING_REMOVE

    channels.remove(username)
    save_channels(channels)
    await update.message.reply_text(
        f"✅ {username} o'chirildi!\n\nQolgan kanallar: {len(channels)} ta"
    )
    return ConversationHandler.END


# ---------------------------------------------------------------------------
# /listchannels
# ---------------------------------------------------------------------------

async def cmd_listchannels(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    channels = load_channels()
    if not channels:
        await update.message.reply_text(
            "Hali kanal qo'shilmagan.\n/addchannel buyrug'ini ishlating."
        )
        return
    lines = [f"{i + 1}. {ch}" for i, ch in enumerate(channels)]
    await update.message.reply_text("📋 Saqlangan kanallar:\n\n" + "\n".join(lines))


# ---------------------------------------------------------------------------
# Text search handler
# ---------------------------------------------------------------------------

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.message.text.strip()
    channels = load_channels()

    if not channels:
        await update.message.reply_text(
            "❗ Hali kanal qo'shilmagan.\n"
            "/addchannel buyrug'i bilan kanal qo'shing."
        )
        return

    loading_msg = await update.message.reply_text("🔍 Qidirilmoqda...")
    telethon: TelegramClient = context.bot_data["telethon"]

    try:
        results, district = await search_jobs(telethon, channels, query)
    except Exception as e:
        logger.exception("Search error: %s", e)
        await loading_msg.delete()
        await update.message.reply_text(
            "❌ Qidirishda xatolik yuz berdi. Keyinroq urinib ko'ring."
        )
        return

    await loading_msg.delete()

    if not results:
        await update.message.reply_text(
            "😔 Hech narsa topilmadi.\n"
            "💡 Boshqa kalit so'z ishlating.\n"
            "Misol: 'yunusobod ofitsiant'"
        )
        return

    for result in results:
        text = format_result(result, query, district)
        await update.message.reply_text(text)
        await asyncio.sleep(0.3)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # /addchannel conversation
    add_conv = ConversationHandler(
        entry_points=[CommandHandler("addchannel", cmd_addchannel_start)],
        states={
            WAITING_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_addchannel_receive)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    # /removechannel conversation
    remove_conv = ConversationHandler(
        entry_points=[CommandHandler("removechannel", cmd_removechannel_start)],
        states={
            WAITING_REMOVE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_removechannel_receive)
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("listchannels", cmd_listchannels))
    app.add_handler(add_conv)
    app.add_handler(remove_conv)

    # General text search (only when not in a conversation)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot ishga tushmoqda...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

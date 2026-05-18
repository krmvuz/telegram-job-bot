import asyncio
import logging
from datetime import datetime

from fuzzywuzzy import fuzz
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Channel

from synonyms import DISTRICTS, SYNONYMS

logger = logging.getLogger(__name__)


def parse_query(query: str) -> tuple[str | None, list[str]]:
    """
    Parse user query into (district, job_words).
    Checks if any word or phrase matches a known district.
    Returns (district_found, remaining_job_words).
    """
    query_lower = query.lower().strip()
    words = query_lower.split()

    found_district = None

    # Check multi-word districts first (e.g. "mirzo ulugbek")
    for district in sorted(DISTRICTS, key=len, reverse=True):
        if district in query_lower:
            found_district = district
            query_lower = query_lower.replace(district, "").strip()
            break

    job_words = [w for w in query_lower.split() if w] if found_district else words
    return found_district, job_words


def build_keywords(job_words: list[str]) -> list[str]:
    """
    Expand job words with synonyms from the SYNONYMS dictionary.
    Returns a de-duplicated list of all keywords to search for.
    """
    keywords = list(job_words)
    for word in job_words:
        if word in SYNONYMS:
            keywords.extend(SYNONYMS[word])
    # De-duplicate while preserving order
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            unique_keywords.append(kw)
    return unique_keywords


def message_matches(text: str, keywords: list[str]) -> bool:
    """
    Check if a message text matches any keyword.
    Uses exact substring match (case-insensitive) or fuzzywuzzy partial_ratio >= 75.
    """
    text_lower = text.lower()
    for keyword in keywords:
        keyword_lower = keyword.lower()
        # Exact substring match
        if keyword_lower in text_lower:
            return True
        # Fuzzy match
        if fuzz.partial_ratio(keyword_lower, text_lower) >= 75:
            return True
    return False


def remove_duplicates(results: list[dict]) -> list[dict]:
    """
    Remove near-duplicate messages using token_sort_ratio > 85.
    Among duplicates, keep the newest message.
    """
    # Sort by date descending so we always keep the newest
    sorted_results = sorted(results, key=lambda x: x["date"], reverse=True)
    unique: list[dict] = []

    for candidate in sorted_results:
        is_dup = False
        for existing in unique:
            similarity = fuzz.token_sort_ratio(
                candidate["text"][:500], existing["text"][:500]
            )
            if similarity > 85:
                is_dup = True
                break
        if not is_dup:
            unique.append(candidate)

    return unique


async def fetch_channel_messages(
    client: TelegramClient,
    channel: str,
    limit: int = 500,
) -> list:
    """
    Fetch up to `limit` messages from a Telegram channel.
    Returns a list of Telethon Message objects.
    Handles FloodWaitError by waiting and retrying.
    """
    try:
        entity = await client.get_entity(channel)
        messages = await client.get_messages(entity, limit=limit)
        return messages
    except FloodWaitError as e:
        logger.warning("FloodWaitError for %s — waiting %s seconds", channel, e.seconds)
        await asyncio.sleep(e.seconds)
        entity = await client.get_entity(channel)
        messages = await client.get_messages(entity, limit=limit)
        return messages
    except Exception as e:
        logger.error("Error fetching messages from %s: %s", channel, e)
        return []


async def search_jobs(
    client: TelegramClient,
    channels: list[str],
    query: str,
    max_results: int = 10,
) -> tuple[list[dict], str | None]:
    """
    Main search function.
    Returns (results, district) where results is a list of dicts:
      {
        "text": str,
        "channel": str,
        "message_id": int,
        "date": datetime,
      }
    """
    district, job_words = parse_query(query)
    keywords = build_keywords(job_words)

    logger.info("Searching for keywords: %s | district: %s", keywords, district)

    all_matches: list[dict] = []

    for channel in channels:
        messages = await fetch_channel_messages(client, channel)
        for msg in messages:
            if not msg.text:
                continue
            if message_matches(msg.text, keywords):
                # Filter by district if specified
                if district and district.lower() not in msg.text.lower():
                    continue
                all_matches.append(
                    {
                        "text": msg.text,
                        "channel": channel.lstrip("@"),
                        "message_id": msg.id,
                        "date": msg.date,
                    }
                )
        # Small delay to avoid flood
        await asyncio.sleep(0.5)

    # Remove duplicates
    unique_matches = remove_duplicates(all_matches)

    # Sort by date descending and limit results
    unique_matches.sort(key=lambda x: x["date"], reverse=True)
    return unique_matches[:max_results], district


def format_result(result: dict, query: str, district: str | None) -> str:
    """
    Format a single search result for sending to the user.
    """
    date_str = result["date"].strftime("%d.%m.%Y")
    channel = result["channel"]
    message_id = result["message_id"]
    text_preview = result["text"][:300]
    district_display = district if district else "-"

    return (
        "━━━━━━━━━━━━━━━\n"
        f"📍 Hudud: {district_display}\n"
        f"💼 Qidiruv: {query}\n"
        f"📢 Kanal: @{channel}\n"
        f"📅 {date_str}\n"
        "━━━━━━━━━━━━━━━\n"
        f"{text_preview}\n"
        f"🔗 t.me/{channel}/{message_id}\n"
        "━━━━━━━━━━━━━━━"
    )

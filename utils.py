import random
import asyncio
from typing import List, Optional
from aiogram.types import Message

# Keywords that trigger Kai's interest in MEDIUM mode
KAI_KEYWORDS = {
    "кай", "kai", "viperr", "viperr", "виперр", "9mice", "димайс", "димаис",
    "трек", "трека", "треков", "музыка", "музыку", "альбом", "альбома", "клип",
    "дроп", "дропнуть", "сниппет", "snippet", "vibe", "вайб", "swag", "свэг",
    "мода", "моде", "fashion", "chrome hearts", "chrome", "париж", "paris",
    "лос-анджелес", "l.a.", "la", "мелроуз", "melrose", "силенсио", "silencio",
    "секта", "sekta", "lipstick", "heavy metal", "angel may cry", "jennifer's body",
    "depeche mode", "metallica", "deftones", "ethel cain", "dean blunt",
    "twin peaks", "pharaoh", "фараон", "oliver sykes", "bring me the horizon",
    "тату", "татуировка", "tattoo", "концерт", "тур", "show", "выступление",
    "goth", "гот", "готика", "vamp", "вампир", "rock", "рок", "trap", "трэп",
    "рэп", "rap", "hip-hop", "хип-хоп", "hyperpop", "хайперпоп", "rage",
}


def is_directly_addressed(message: Message, bot_username: str, bot_id: int = 0) -> bool:
    """Check if message directly calls Kai or tags the bot."""
    text = (message.text or message.caption or "").lower()

    # Reply to our bot's message specifically
    if message.reply_to_message and message.reply_to_message.from_user:
        replied_user = message.reply_to_message.from_user
        if replied_user.is_bot and (replied_user.username or "").lower() == bot_username.lower():
            return True
        if bot_id and replied_user.id == bot_id:
            return True

    # Username tag
    if f"@{bot_username.lower()}" in text:
        return True

    # Name references
    name_triggers = ["кай англ", "кай"]
    for trigger in name_triggers:
        if trigger in text:
            return True

    return False


def is_username_tagged(message: Message, bot_username: str) -> bool:
    """Check if only username is tagged (for OFF mode)."""
    text = (message.text or message.caption or "").lower()
    return f"@{bot_username.lower()}" in text


def has_kai_keywords(message: Message) -> bool:
    """Check if message contains topics Kai cares about."""
    text = (message.text or message.caption or "").lower()
    words = set(text.split())
    return bool(words & KAI_KEYWORDS)


def should_trigger_in_medium(message: Message, bot_username: str, bot_id: int = 0) -> bool:
    """MEDIUM mode: respond if directly addressed OR topic matches Kai's interests."""
    if is_directly_addressed(message, bot_username, bot_id):
        return True
    if has_kai_keywords(message):
        return True
    return False


def split_response(text: str) -> List[str]:
    """Split LLM response into rapid-fire messages."""
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    # Filter out skip markers
    lines = [line for line in lines if line.lower() not in ("<skip>", "skip")]
    return lines


async def send_rapid_fire_messages(message: Message, texts: List[str]):
    """Send multiple short messages with human-like delays."""
    for i, text in enumerate(texts):
        if i > 0:
            delay = random.uniform(0.6, 1.4)
            await asyncio.sleep(delay)
        await message.answer(text)

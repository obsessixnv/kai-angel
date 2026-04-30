import random
import asyncio
from typing import List, Optional, Dict, Any
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


def clean_llm_output(text: str) -> str:
    """Strip accidental timestamp/username prefixes that LLM sometimes mimics."""
    import re
    # Remove patterns like: [2026-04-30T13:27:31.256844] @Kai Angel: yo brat
    text = re.sub(
        r'^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\]\s*@[^:]+:\s*',
        '',
        text,
        flags=re.MULTILINE
    )
    return text.strip()


def split_response(text: str) -> List[str]:
    """Split LLM response into rapid-fire messages."""
    text = clean_llm_output(text)
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


LOOK_RATING_KEYWORDS = {
    "оцени", "оценка", "лук", "fit", "фит", "аутфит", "outfit", "look",
    "одежда", "look check", "fit check", "rate my", "rate", "аутфит чек",
    "как выгляжу", "что скажешь про", "how do i look", "fit review",
}

ASK_ABOUT_PHOTO_KEYWORDS = {
    "что думаешь", "как тебе", "что скажешь", "опиши", "что это",
    "что на фото", "что на пикче", "реакция", "что ты видишь",
    "how is it", "what do you think", "thoughts", "opinion",
    "что за", "покажи", "расскажи про", "как тебе",
}


def is_look_rating_request(text: str) -> bool:
    """Check if message is asking Kai to rate their outfit/look."""
    text_lower = text.lower()
    return bool(LOOK_RATING_KEYWORDS & set(text_lower.split()))


def is_ask_about_photo(text: str) -> bool:
    """Check if message is asking Kai about a photo."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in ASK_ABOUT_PHOTO_KEYWORDS)


def build_people_context(profiles: List[Dict[str, Any]],
                         memories_map: Dict[int, List[Dict[str, Any]]]) -> str:
    """Build a 'PEOPLE IN THIS CHAT' section for the system prompt."""
    if not profiles:
        return ""

    lines = ["\nPEOPLE IN THIS CHAT YOU REMEMBER:\n"]
    for p in profiles:
        username = p.get("username") or p.get("display_name") or "чел"
        relationship = p.get("relationship") or "знакомый"
        notes = p.get("notes") or ""

        user_memories = memories_map.get(p.get("user_id", 0), [])
        memory_texts = [m["memory_text"] for m in user_memories[:2]]
        memories_str = " | ".join(memory_texts) if memory_texts else ""

        line = f"@{username} — {relationship}"
        if notes:
            line += f". {notes}"
        if memories_str:
            line += f". ты помнишь: {memories_str}"
        lines.append(line)

    return "\n".join(lines)

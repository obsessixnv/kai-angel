from dotenv import load_dotenv
load_dotenv()

import os
import random
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ChatType
from aiogram.filters import Command

import database as db
import llm_client
from prompts import SYSTEM_PROMPT, ACTIVITY_INSTRUCTIONS, SKIP_RESPONSE, PROACTIVE_MESSAGES
from utils import (
    is_directly_addressed,
    is_username_tagged,
    should_trigger_in_medium,
    split_response,
    send_rapid_fire_messages,
    build_people_context,
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
dp = Dispatcher()
router = Router()

# Store bot info after startup
_bot_username: str = ""
_bot_id: int = 0


async def get_bot_info():
    global _bot_username, _bot_id
    if not _bot_username:
        me = await bot.get_me()
        _bot_username = me.username or ""
        _bot_id = me.id


async def get_bot_username() -> str:
    await get_bot_info()
    return _bot_username


async def _analyze_user_background(chat_id: int, user_id: int, username: str, profile: dict):
    """Background task: analyze user vibe and update profile."""
    try:
        recent_msgs = db.get_user_recent_messages(chat_id, user_id, limit=15)
        current_profile_str = (
            f"vibe: {profile.get('vibe_score', 0)}, "
            f"relationship: {profile.get('relationship', 'знакомый')}, "
            f"notes: {profile.get('notes', '')}"
        )

        analysis = await llm_client.analyze_user_profile(
            username=username,
            current_profile=current_profile_str,
            recent_messages=[m["message_text"] for m in recent_msgs],
        )

        if not analysis:
            return

        db.update_user_profile(
            chat_id=chat_id,
            user_id=user_id,
            vibe_score=float(analysis.get("vibe_score", profile.get("vibe_score", 0))),
            relationship=str(analysis.get("relationship", profile.get("relationship", "знакомый"))),
            notes=str(analysis.get("notes", profile.get("notes", ""))),
        )

        for mem in analysis.get("new_memories", []):
            if mem and isinstance(mem, str) and len(mem.strip()) > 3:
                db.add_user_memory(chat_id, user_id, mem.strip())

    except Exception as e:
        logger.error(f"Background analysis error for user {user_id}: {e}")


async def _build_system_prompt_with_people(chat_id: int, base_system: str) -> str:
    """Inject people context into the system prompt."""
    recent_user_ids = db.get_recent_speaker_ids(chat_id, limit_messages=20)

    if not recent_user_ids:
        return base_system

    profiles = db.get_recent_speaker_profiles(chat_id, recent_user_ids)
    if not profiles:
        return base_system

    memories_map = {}
    for p in profiles:
        uid = p.get("user_id", 0)
        if uid:
            memories_map[uid] = db.get_user_memories(chat_id, uid, limit=2)

    people_ctx = build_people_context(profiles, memories_map)
    return base_system + people_ctx


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.chat.type == ChatType.PRIVATE:
        await message.answer("привет 🍸\nдобавь меня в чат и выбери режим через /mode")
    else:
        await message.answer("я в чате 🍸\n/mode — выбрать активность")


@router.message(Command("mode"))
async def cmd_mode(message: types.Message):
    chat_id = message.chat.id
    current = db.get_chat_mode(chat_id)

    args = message.text.lower().split() if message.text else []
    if len(args) < 2:
        await message.answer(
            f"сейчас режим: {current}\n"
            f"чтобы поменять: /mode off | small | medium | high\n\n"
            f"off — молчу пока не тегнут\n"
            f"small — отвечаю только если позвали\n"
            f"medium — отвечаю на темы по мне или если позвали\n"
            f"high — я тут постоянно 🍸"
        )
        return

    new_mode = args[1]
    if new_mode not in ACTIVITY_INSTRUCTIONS:
        await message.answer("не знаю такой режим блять\nварианты: off, small, medium, high")
        return

    chat_type = message.chat.type.value if message.chat else None
    db.set_chat_mode(chat_id, new_mode, chat_type)

    # Schedule first proactive message for group chats (1-3 hours from now)
    if chat_type in ("group", "supergroup") and new_mode != "off":
        db.schedule_next_proactive(chat_id, datetime.utcnow(), hours=random.uniform(1, 3))

    await message.answer(f"режим: {new_mode} 🍸")


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    """Clear chat history (owner only)."""
    if OWNER_USERNAME and message.from_user and message.from_user.username != OWNER_USERNAME:
        return
    await message.answer("история очищена 🍸")


@router.message(Command("whoami"))
async def cmd_whoami(message: types.Message):
    """Show what Kai thinks of you."""
    if not message.from_user:
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    profile = db.get_or_create_user_profile(
        chat_id, user_id,
        message.from_user.username,
        message.from_user.first_name
    )

    memories = db.get_user_memories(chat_id, user_id, limit=3)
    mem_text = "\n".join(f"- {m['memory_text']}" for m in memories) if memories else "пока ничего не помню 🍸"

    vibe = profile.get("vibe_score", 0)
    rel = profile.get("relationship", "знакомый")
    notes = profile.get("notes", "")

    await message.answer(
        f"ты для меня: {rel}\n"
        f"vibe: {vibe}/10\n"
        f"{notes}\n\n"
        f"помню:\n{mem_text}"
    )


@router.message(F.chat.type == ChatType.PRIVATE)
async def handle_private_message(message: types.Message):
    """Handle private DMs — every message is directed at Kai."""
    if not message.text and not message.caption:
        return

    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return

    username = user.username or user.first_name
    text = message.text or message.caption or ""

    # Save incoming message
    db.save_message(
        chat_id=chat_id,
        user_id=user.id,
        username=username,
        message_text=text,
        timestamp=datetime.utcnow(),
        is_bot=False,
    )

    # Track user profile
    profile = db.get_or_create_user_profile(chat_id, user.id, username, user.first_name)
    db.increment_interaction_count(chat_id, user.id)

    # Analyze every 5 messages (fire and forget)
    if profile.get("interaction_count", 0) % 5 == 0:
        asyncio.create_task(_analyze_user_background(chat_id, user.id, username, profile))

    # Build system prompt with people context
    base_system = SYSTEM_PROMPT + "\nYou are chatting 1-on-1 in private messages. Be natural."
    full_system = await _build_system_prompt_with_people(chat_id, base_system)

    history = db.get_chat_history(chat_id, limit=500)

    await bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        response_text = await llm_client.generate_response(
            system_prompt=full_system,
            history=history,
        )
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return

    if not response_text:
        return

    stripped = response_text.strip().lower()
    cleaned = stripped.replace("<", "").replace(">", "").strip()
    if cleaned == "skip":
        return

    messages_to_send = split_response(response_text)
    if not messages_to_send:
        return

    await send_rapid_fire_messages(message, messages_to_send)

    for msg_text in messages_to_send:
        db.save_message(
            chat_id=chat_id,
            user_id=0,
            username="Kai Angel",
            message_text=msg_text,
            timestamp=datetime.utcnow(),
            is_bot=True,
        )


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def handle_group_message(message: types.Message):
    if not message.text and not message.caption:
        return

    bot_username = await get_bot_username()
    chat_id = message.chat.id
    user = message.from_user
    if not user:
        return

    username = user.username or user.first_name
    text = message.text or message.caption or ""

    # Save incoming message
    db.save_message(
        chat_id=chat_id,
        user_id=user.id,
        username=username,
        message_text=text,
        timestamp=datetime.utcnow(),
        is_bot=False,
    )

    # Track user profile
    profile = db.get_or_create_user_profile(chat_id, user.id, username, user.first_name)
    db.increment_interaction_count(chat_id, user.id)

    # Analyze every 5 messages (fire and forget)
    if profile.get("interaction_count", 0) % 5 == 0:
        asyncio.create_task(_analyze_user_background(chat_id, user.id, username, profile))

    # Get current mode
    mode = db.get_chat_mode(chat_id)

    # Decide if we should respond
    should_respond = False
    if mode == "off":
        should_respond = is_username_tagged(message, bot_username)
    elif mode == "small":
        should_respond = is_directly_addressed(message, bot_username, _bot_id)
    elif mode == "medium":
        should_respond = should_trigger_in_medium(message, bot_username, _bot_id)
    elif mode == "high":
        should_respond = True

    if not should_respond:
        return

    # Build full system prompt with activity instruction + people context
    activity_instruction = ACTIVITY_INSTRUCTIONS.get(mode, "")
    base_system = SYSTEM_PROMPT + "\n" + activity_instruction
    full_system = await _build_system_prompt_with_people(chat_id, base_system)

    # Get conversation history
    history = db.get_chat_history(chat_id, limit=500)

    # Typing indicator
    await bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        response_text = await llm_client.generate_response(
            system_prompt=full_system,
            history=history,
        )
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return

    if not response_text:
        return

    # Check for skip
    stripped = response_text.strip().lower()
    if stripped in ("<skip>", "skip", "<skip>"):
        return
    cleaned = stripped.replace("<", "").replace(">", "").strip()
    if cleaned == "skip":
        return

    # Split into rapid-fire messages
    messages_to_send = split_response(response_text)
    if not messages_to_send:
        return

    # Send with delays
    await send_rapid_fire_messages(message, messages_to_send)

    # Save bot messages to history
    for msg_text in messages_to_send:
        db.save_message(
            chat_id=chat_id,
            user_id=0,
            username="Kai Angel",
            message_text=msg_text,
            timestamp=datetime.utcnow(),
            is_bot=True,
        )


async def proactive_messaging_loop():
    """Background task: randomly send proactive messages to active group chats."""
    await asyncio.sleep(30)  # Wait for bot to fully start

    while True:
        try:
            now = datetime.utcnow()
            chats = db.get_chats_due_for_proactive(now)

            for chat in chats:
                chat_id = chat["chat_id"]
                mode = chat.get("activity_mode", "small")

                # Skip if mode is off
                if mode == "off":
                    db.schedule_next_proactive(chat_id, now, hours=random.uniform(24, 48))
                    continue

                # Pick random message
                text = random.choice(PROACTIVE_MESSAGES)

                # Send with small delay for natural feel
                await bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(random.uniform(1.0, 2.5))
                await bot.send_message(chat_id=chat_id, text=text)

                # Save to history
                db.save_message(
                    chat_id=chat_id,
                    user_id=0,
                    username="Kai Angel",
                    message_text=text,
                    timestamp=now,
                    is_bot=True,
                )

                # Schedule next (1-2 days)
                db.schedule_next_proactive(chat_id, now, hours=random.uniform(24, 48))
                logger.info(f"Proactive message sent to chat {chat_id}: {text}")

        except Exception as e:
            logger.error(f"Proactive messaging error: {e}")

        # Check every 10 minutes
        await asyncio.sleep(600)


async def main():
    db.init_db()
    dp.include_router(router)

    # Start background proactive messaging task
    asyncio.create_task(proactive_messaging_loop())

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

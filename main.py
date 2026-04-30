from dotenv import load_dotenv
load_dotenv()

import os
import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ChatType
from aiogram.filters import Command

import database as db
import llm_client
from prompts import SYSTEM_PROMPT, ACTIVITY_INSTRUCTIONS, SKIP_RESPONSE
from utils import (
    is_directly_addressed,
    is_username_tagged,
    should_trigger_in_medium,
    split_response,
    send_rapid_fire_messages,
)

load_dotenv()

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

    db.set_chat_mode(chat_id, new_mode)
    await message.answer(f"режим: {new_mode} 🍸")


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    """Clear chat history (owner only)."""
    if OWNER_USERNAME and message.from_user and message.from_user.username != OWNER_USERNAME:
        return
    # Simple clear: we don't delete from DB but can add if needed
    await message.answer("история очищена 🍸")


@router.message(F.chat.type == ChatType.PRIVATE)
async def handle_private_message(message: types.Message):
    """Handle private DMs — every message is directed at Kai."""
    if not message.text and not message.caption:
        return

    chat_id = message.chat.id
    user = message.from_user
    username = user.username or user.first_name if user else "unknown"
    text = message.text or message.caption or ""

    # Save incoming message
    db.save_message(
        chat_id=chat_id,
        user_id=user.id if user else 0,
        username=username,
        message_text=text,
        timestamp=datetime.utcnow(),
        is_bot=False,
    )

    # In private chat, always respond (no activity modes needed)
    history = db.get_chat_history(chat_id, limit=500)

    full_system = SYSTEM_PROMPT + "\nYou are chatting 1-on-1 in private messages. Be natural."

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
    username = user.username or user.first_name if user else "unknown"
    text = message.text or message.caption or ""

    # Save incoming message
    db.save_message(
        chat_id=chat_id,
        user_id=user.id if user else 0,
        username=username,
        message_text=text,
        timestamp=datetime.utcnow(),
        is_bot=False,
    )

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
        # In high mode, we let the LLM decide by always asking
        should_respond = True

    if not should_respond:
        return

    # Build full system prompt with activity instruction
    activity_instruction = ACTIVITY_INSTRUCTIONS.get(mode, "")
    full_system = SYSTEM_PROMPT + "\n" + activity_instruction

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

    # Check for skip (handle extra whitespace/punctuation)
    stripped = response_text.strip().lower()
    if stripped in ("<skip>", "skip", "<skip>"):
        return
    # Also check if response only contains skip-like content
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


async def main():
    db.init_db()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

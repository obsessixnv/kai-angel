# Kai Angel — Telegram Bot

AI-powered Telegram bot that roleplays as **Kai Angel** (Дмитрий Итсков) — Russian rap/hyperpop artist, producer, and one half of VIPERR.

## Features

- **4 Activity Modes** (per chat):
  - `OFF` — silent unless tagged by `@bot_username`
  - `SMALL` — responds only when called by name or replied to
  - `MEDIUM` — responds when called + on topics Kai cares about (music, fashion, VIPERR, etc.)
  - `HIGH` — active participant with full 500-message context + timestamps

- **Rapid-fire messaging** — splits LLM output into short messages with human-like delays (0.6–1.4s), just like the real Kai Angel on Telegram

- **Full conversation memory** — stores last 500 messages per chat with timestamps so Kai understands context and flow

- **OpenRouter API** — uses `google/gemini-3-flash-preview` (or any model you prefer)

## Setup

### 1. Create bot with @BotFather
- Open Telegram, find `@BotFather`
- Send `/newbot`, follow instructions
- Copy the **HTTP API token**
- Set `Privacy Mode` to **Disabled** (so bot can read all group messages)

### 2. Configure environment
```bash
cp .env .env.local
```
Edit `.env.local`:
```
TELEGRAM_BOT_TOKEN=your_token_from_botfather
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL=google/gemini-3-flash-preview
OWNER_USERNAME=your_telegram_username
```

### 3. Install & run
```bash
# Create venv (recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install deps
pip install -r requirements.txt

# Run
python main.py
```

### 4. Add to group chat
- Add the bot to any group
- Make sure it has permission to read messages
- Set activity mode: `/mode high`

## Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/mode` | Show current activity mode |
| `/mode off\|small\|medium\|high` | Change activity mode |
| `/clear` | Clear chat history (owner only) |

## Activity Modes Explained

- **OFF** — Bot is completely silent. Only responds if someone writes `@bot_username`
- **SMALL** — Bot only talks when directly addressed (`кай`, `кай англ`, `@bot_username`, or reply to bot)
- **MEDIUM** — Bot talks when addressed OR when the conversation is about music, fashion, VIPERR, L.A., Paris, etc.
- **HIGH** — Bot is always "online", reads full context, and naturally jumps into conversations. Uses LLM to decide whether to speak each time.

## Project Structure

```
.
├── main.py           # aiogram bot handlers & entry point
├── database.py       # SQLite (messages + chat settings)
├── llm_client.py     # OpenRouter API client
├── utils.py          # Mention detection, message splitting, delays
├── prompts.py        # System prompt + activity mode instructions
├── requirements.txt
├── .env
└── README.md
```

import os
import json
import re
import aiohttp
from typing import List, Dict, Any, Optional

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _get_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. "
            "Make sure your .env file contains GEMINI_API_KEY=your_key "
            "and you restarted the bot after editing it."
        )
    return key


async def generate_response(
    system_prompt: str,
    history: List[Dict[str, Any]],
    temperature: float = 0.9,
    presence_penalty: float = 0.4,
) -> Optional[str]:
    """Call Google Gemini API directly via REST."""

    api_key = _get_api_key()

    # Build alternating user/model contents from history
    contents = []
    current_role = None
    current_lines = []

    for msg in history:
        role = "model" if msg.get("is_bot") else "user"
        name = msg.get("username") or "user"
        ts = msg.get("timestamp", "")
        text = msg.get("message_text", "")
        line = f"[{ts}] @{name}: {text}"

        if role == current_role:
            current_lines.append(line)
        else:
            if current_lines:
                contents.append({
                    "role": current_role,
                    "parts": [{"text": "\n".join(current_lines)}]
                })
            current_role = role
            current_lines = [line]

    if current_lines:
        contents.append({
            "role": current_role,
            "parts": [{"text": "\n".join(current_lines)}]
        })

    payload: Dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 800,
        }
    }

    # Some models don't support systemInstruction; prepend to first user msg if needed
    try:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
    except Exception:
        # Fallback: prepend system prompt to first user message
        if contents:
            contents[0]["parts"][0]["text"] = f"{system_prompt}\n\n{contents[0]['parts'][0]['text']}"

    params = {"key": api_key}
    headers = {"Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(GEMINI_URL, json=payload, params=params, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Gemini API error {resp.status}: {text}")

            data = await resp.json()

            # Extract text from response
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return None

            return parts[0].get("text")


async def analyze_user_profile(
    username: str,
    current_profile: str,
    recent_messages: List[str],
) -> Optional[Dict[str, Any]]:
    """Analyze a user's vibe and update their profile. Returns parsed JSON or None."""
    from prompts import USER_ANALYSIS_PROMPT

    messages_text = "\n".join(f"- {m}" for m in recent_messages)

    prompt = USER_ANALYSIS_PROMPT.format(
        username=username,
        current_profile=current_profile,
        recent_messages=messages_text,
    )

    api_key = _get_api_key()

    payload = {
        "contents": [{
            "role": "user",
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 400,
        }
    }

    params = {"key": api_key}
    headers = {"Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(GEMINI_URL, json=payload, params=params, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Gemini API error {resp.status}: {text}")

            data = await resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return None

            text = parts[0].get("text", "")
            return _extract_json(text)


async def analyze_look(
    image_b64: str,
    mime_type: str,
    user_prompt: str,
    system_prompt: str,
) -> Optional[str]:
    """Analyze an outfit photo using Gemini vision."""
    api_key = _get_api_key()

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": system_prompt + "\n\nUser's message: " + user_prompt},
                {"inline_data": {"mime_type": mime_type, "data": image_b64}}
            ]
        }],
        "generationConfig": {
            "temperature": 0.95,
            "maxOutputTokens": 500,
        }
    }

    params = {"key": api_key}
    headers = {"Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.post(GEMINI_URL, json=payload, params=params, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"Gemini API error {resp.status}: {text}")

            data = await resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                return None

            return parts[0].get("text")


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Try to extract JSON from LLM response."""
    text = text.strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r'```(?:json)?\s*(.*?)```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding the first { and last }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None

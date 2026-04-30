import os
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

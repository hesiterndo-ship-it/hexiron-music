"""
AI integration service layer.

Provides a configurable interface for AI-powered features such as:
  - Natural-language music search
  - Music recommendations
  - Smart playlist generation
  - User assistance

The actual AI provider is configured via environment variables:
  AI_PROVIDER  — "openai", "gemini", or "" (disabled)
  AI_API_KEY   — API key for the chosen provider
  AI_MODEL     — Model name (optional, has defaults per provider)
  AI_BASE_URL  — Custom base URL (optional)

If no AI provider is configured, all functions return None/empty results
gracefully — the bot continues to work without AI features.
"""

import logging
from typing import Optional

from config import AI_PROVIDER, AI_API_KEY, AI_MODEL, AI_BASE_URL

logger = logging.getLogger("hexiron.ai")

# ── Provider availability ──────────────────────────────────────────


def is_available() -> bool:
    """Check if an AI provider is configured and usable."""
    return bool(AI_PROVIDER and AI_API_KEY)


# ── Suggestion / recommendation ────────────────────────────────────


async def suggest_music(user_message: str) -> Optional[str]:
    """
    Given a natural-language user message like "play something relaxing"
    or "I want upbeat workout music", return a suggested search query.

    Returns None if AI is not available or the request fails.
    """
    if not is_available():
        return None

    prompt = (
        f"A user wants to listen to music. "
        f"Their request: \"{user_message}\"\n\n"
        f"Respond with ONLY a short YouTube search query "
        f"(3-6 words, no quotes, no explanation). "
        f"For example: \"relaxing piano music\" or \"upbeat workout mix\""
    )

    try:
        if AI_PROVIDER == "openai":
            return await _openai_chat(prompt)
        elif AI_PROVIDER == "gemini":
            return await _gemini_chat(prompt)
        else:
            logger.warning("Unknown AI provider: %s", AI_PROVIDER)
            return None
    except Exception:
        logger.exception("AI suggestion failed")
        return None


# ── OpenAI ──────────────────────────────────────────────────────────


async def _openai_chat(prompt: str) -> Optional[str]:
    """Call OpenAI API for a chat completion."""
    try:
        import httpx

        model = AI_MODEL or "gpt-3.5-turbo"
        base_url = AI_BASE_URL or "https://api.openai.com/v1"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 60,
                    "temperature": 0.7,
                },
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("OpenAI API call failed")
        return None


# ── Gemini ──────────────────────────────────────────────────────────


async def _gemini_chat(prompt: str) -> Optional[str]:
    """Call Google Gemini API for a chat completion."""
    try:
        import httpx

        model = AI_MODEL or "gemini-pro"
        base_url = AI_BASE_URL or "https://generativelanguage.googleapis.com/v1beta"

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{base_url}/models/{model}:generateContent?key={AI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        logger.exception("Gemini API call failed")
        return None

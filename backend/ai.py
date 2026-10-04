"""AI layer: multi-provider streaming + MOCK_AI mode for UI testing without spend.

Providers (AI_PROVIDER env):
  - anthropic : Anthropic API (paid). Needs ANTHROPIC_API_KEY.
  - gemini    : Google AI Studio free tier. Needs GEMINI_API_KEY.
                Get one free at https://aistudio.google.com/apikey (no card).
  - mock      : MOCK_AI=true — canned responses, zero API spend.

If AI_PROVIDER is unset, auto-picks gemini when GEMINI_API_KEY is set,
else anthropic when ANTHROPIC_API_KEY is set.
"""
import os
import json

import httpx

MOCK = os.environ.get("MOCK_AI", "").lower() in ("1", "true", "yes")

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_provider = os.environ.get("AI_PROVIDER", "").lower().strip()
if not _provider and not MOCK:
    if GEMINI_KEY:
        _provider = "gemini"
    elif ANTHROPIC_KEY:
        _provider = "anthropic"
    else:
        _provider = "none"

_anthropic_client = None


def _anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic

        if not ANTHROPIC_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (or set MOCK_AI=true for testing)")
        _anthropic_client = Anthropic(api_key=ANTHROPIC_KEY)
    return _anthropic_client


def is_mock() -> bool:
    return MOCK


def provider_name() -> str:
    return "mock" if MOCK else _provider


def _mock_chunks(text: str):
    # Yield word-by-word so SSE streaming looks plausible in the UI.
    for word in text.split(" "):
        yield word + " "


# ---------------------------------------------------------------- Gemini helpers
def _gemini_contents(messages: list) -> list:
    """Convert OpenAI-style messages to Gemini contents.

    Gemini wants roles user/model, alternating, starting with user.
    """
    out = []
    for m in messages:
        role = "model" if m.get("role") == "assistant" else "user"
        text = m.get("content", "")
        if out and out[-1]["role"] == role:
            out[-1]["parts"][0]["text"] += "\n" + text
        else:
            out.append({"role": role, "parts": [{"text": text}]})
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "parts": [{"text": "(conversation start)"}]})
    return out


def _gemini_body(system: str, messages: list, max_tokens: int) -> dict:
    return {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": _gemini_contents(messages),
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.9},
    }


def _gemini_headers() -> dict:
    if not GEMINI_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set (or set MOCK_AI=true for testing)")
    return {"x-goog-api-key": GEMINI_KEY, "Content-Type": "application/json"}


def _gemini_text_from_chunk(data: dict) -> str:
    parts = []
    for cand in data.get("candidates", []):
        content = cand.get("content", {})
        for part in content.get("parts", []):
            text = part.get("text")
            if text:
                parts.append(text)
    return "".join(parts)


def _gemini_stream(system: str, messages: list, max_tokens: int):
    url = f"{GEMINI_BASE}/{GEMINI_MODEL}:streamGenerateContent?alt=sse"
    with httpx.stream(
        "POST", url, headers=_gemini_headers(),
        json=_gemini_body(system, messages, max_tokens), timeout=120.0,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                text = _gemini_text_from_chunk(json.loads(payload))
            except json.JSONDecodeError:
                continue
            if text:
                yield text


def _gemini_complete(system: str, messages: list, max_tokens: int) -> str:
    url = f"{GEMINI_BASE}/{GEMINI_MODEL}:generateContent"
    resp = httpx.post(
        url, headers=_gemini_headers(),
        json=_gemini_body(system, messages, max_tokens), timeout=120.0,
    )
    resp.raise_for_status()
    return _gemini_text_from_chunk(resp.json())


# ---------------------------------------------------------------- public API
def stream(system: str, messages: list, mock_text: str, max_tokens: int = 1024):
    """Yield text chunks. In MOCK mode yields from mock_text, no API call."""
    if MOCK:
        yield from _mock_chunks(mock_text)
        return
    if _provider == "gemini":
        yield from _gemini_stream(system, messages, max_tokens)
        return
    if _provider == "anthropic":
        resp = _anthropic().messages.create(
            model=ANTHROPIC_MODEL, max_tokens=max_tokens,
            system=system, messages=messages, stream=True,
        )
        for event in resp:
            if event.type == "content_block_delta":
                text = getattr(event.delta, "text", None)
                if text:
                    yield text
        return
    raise RuntimeError(
        "No AI provider configured. Set GEMINI_API_KEY (free, https://aistudio.google.com/apikey) "
        "or ANTHROPIC_API_KEY, or MOCK_AI=true for testing."
    )


def complete(system: str, messages: list, mock_text: str, max_tokens: int = 1024) -> str:
    """Non-streaming completion. In MOCK mode returns mock_text."""
    if MOCK:
        return mock_text
    if _provider == "gemini":
        return _gemini_complete(system, messages, max_tokens)
    if _provider == "anthropic":
        resp = _anthropic().messages.create(
            model=ANTHROPIC_MODEL, max_tokens=max_tokens, system=system, messages=messages
        )
        parts = []
        for block in resp.content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
        return "".join(parts)
    raise RuntimeError(
        "No AI provider configured. Set GEMINI_API_KEY (free, https://aistudio.google.com/apikey) "
        "or ANTHROPIC_API_KEY, or MOCK_AI=true for testing."
    )

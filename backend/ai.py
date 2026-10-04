"""AI layer: multi-provider streaming + MOCK_AI mode for UI testing without spend.

Providers (AI_PROVIDER env):
  - groq      : Groq free tier (recommended). Needs GROQ_API_KEY.
                Get one free at https://console.groq.com (no card).
                ~1,000+ requests/day. Model auto-picks from the live catalog
                unless GROQ_MODEL is set.
  - gemini    : Google AI Studio free tier. Needs GEMINI_API_KEY.
                Get one free at https://aistudio.google.com/apikey (no card).
                Note: current free models are capped at ~20 requests/day.
  - anthropic : Anthropic API (paid). Needs ANTHROPIC_API_KEY.
  - mock      : MOCK_AI=true — canned responses, zero API spend.

If AI_PROVIDER is unset, auto-picks groq when GROQ_API_KEY is set,
else gemini when GEMINI_API_KEY is set, else anthropic when ANTHROPIC_API_KEY.

Providers chain: if the primary fails, the next configured provider is tried
before falling back to mock text — the caller always gets *something* usable.
"""
import os
import json

import httpx

MOCK = os.environ.get("MOCK_AI", "").lower() in ("1", "true", "yes")

GROQ_KEY = (os.environ.get("GROQ_API_KEY") or "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "").strip()  # empty = auto-pick from catalog
GROQ_BASE = "https://api.groq.com/openai/v1"

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

GEMINI_KEY = (os.environ.get("GEMINI_API_KEY") or "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

_provider = os.environ.get("AI_PROVIDER", "").lower().strip()
if not _provider and not MOCK:
    if GROQ_KEY:
        _provider = "groq"
    elif GEMINI_KEY:
        _provider = "gemini"
    elif ANTHROPIC_KEY:
        _provider = "anthropic"
    else:
        _provider = "none"


def _chain():
    """Ordered provider ladder: primary first, then any other configured one."""
    order = []
    for p, key in (("groq", GROQ_KEY), ("gemini", GEMINI_KEY), ("anthropic", ANTHROPIC_KEY)):
        if key:
            order.append(p)
    if _provider in order:
        order.remove(_provider)
        order.insert(0, _provider)
    return order


print(f"[ai] provider={_provider} chain={_chain()}", flush=True)

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
        if resp.status_code >= 400:
            body = resp.read().decode(errors="replace")[:500]
            raise RuntimeError(f"Gemini API error {resp.status_code}: {body}")
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
    if resp.status_code >= 400:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:500]}")
    return _gemini_text_from_chunk(resp.json())


# ---------------------------------------------------------------- Groq helpers (OpenAI-compatible)
_groq_model = None


def _groq_headers() -> dict:
    if not GROQ_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")
    return {"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"}


def _groq_pick_model() -> str:
    """Model to use: explicit GROQ_MODEL wins, else auto-pick from the live catalog.

    Groq retires/renames models regularly; auto-picking from /models keeps the
    app working without code changes when that happens.
    """
    global _groq_model
    if _groq_model:
        return _groq_model
    if GROQ_MODEL:
        _groq_model = GROQ_MODEL
        return _groq_model
    try:
        resp = httpx.get(f"{GROQ_BASE}/models", headers=_groq_headers(), timeout=30.0)
        resp.raise_for_status()
        ids = [m.get("id", "") for m in resp.json().get("data", []) if m.get("id")]
        for prefer in ("qwen", "gpt-oss", "llama", "gemma", "mixtral", "deepseek"):
            for mid in ids:
                low = mid.lower()
                if prefer in low and "whisper" not in low and "tts" not in low:
                    _groq_model = mid
                    print(f"[ai] groq auto-picked model={mid}", flush=True)
                    return _groq_model
        if ids:
            _groq_model = ids[0]
            print(f"[ai] groq auto-picked model={_groq_model} (first available)", flush=True)
            return _groq_model
    except Exception as e:
        print(f"[ai] groq model auto-pick failed: {e}", flush=True)
    _groq_model = "qwen/qwen3.6-27b"  # last-resort default
    return _groq_model


def _groq_messages(system: str, messages: list) -> list:
    out = [{"role": "system", "content": system}]
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            role = "user"
        out.append({"role": role, "content": m.get("content", "")})
    return out


def _groq_stream(system: str, messages: list, max_tokens: int):
    body = {
        "model": _groq_pick_model(),
        "messages": _groq_messages(system, messages),
        "max_tokens": max_tokens, "temperature": 0.9, "stream": True,
    }
    with httpx.stream(
        "POST", f"{GROQ_BASE}/chat/completions", headers=_groq_headers(),
        json=body, timeout=120.0,
    ) as resp:
        if resp.status_code >= 400:
            err = resp.read().decode(errors="replace")[:500]
            raise RuntimeError(f"Groq API error {resp.status_code}: {err}")
        for line in resp.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for choice in data.get("choices", []):
                text = (choice.get("delta") or {}).get("content")
                if text:
                    yield text


def _groq_complete(system: str, messages: list, max_tokens: int) -> str:
    body = {
        "model": _groq_pick_model(),
        "messages": _groq_messages(system, messages),
        "max_tokens": max_tokens, "temperature": 0.9,
    }
    resp = httpx.post(
        f"{GROQ_BASE}/chat/completions", headers=_groq_headers(),
        json=body, timeout=120.0,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Groq API error {resp.status_code}: {resp.text[:500]}")
    parts = []
    for choice in resp.json().get("choices", []):
        text = (choice.get("message") or {}).get("content")
        if text:
            parts.append(text)
    return "".join(parts)


def _anthropic_complete(system: str, messages: list, max_tokens: int) -> str:
    resp = _anthropic().messages.create(
        model=ANTHROPIC_MODEL, max_tokens=max_tokens, system=system, messages=messages
    )
    parts = []
    for block in resp.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)


def _anthropic_stream(system: str, messages: list, max_tokens: int):
    resp = _anthropic().messages.create(
        model=ANTHROPIC_MODEL, max_tokens=max_tokens,
        system=system, messages=messages, stream=True,
    )
    for event in resp:
        if event.type == "content_block_delta":
            text = getattr(event.delta, "text", None)
            if text:
                yield text


# ---------------------------------------------------------------- public API
def _stream_with(provider: str, system: str, messages: list, max_tokens: int):
    if provider == "groq":
        yield from _groq_stream(system, messages, max_tokens)
    elif provider == "gemini":
        yield from _gemini_stream(system, messages, max_tokens)
    elif provider == "anthropic":
        yield from _anthropic_stream(system, messages, max_tokens)
    else:
        raise RuntimeError(f"Unknown provider: {provider}")


def _complete_with(provider: str, system: str, messages: list, max_tokens: int) -> str:
    if provider == "groq":
        return _groq_complete(system, messages, max_tokens)
    if provider == "gemini":
        return _gemini_complete(system, messages, max_tokens)
    if provider == "anthropic":
        return _anthropic_complete(system, messages, max_tokens)
    raise RuntimeError(f"Unknown provider: {provider}")


def stream(system: str, messages: list, mock_text: str, max_tokens: int = 1024):
    """Yield text chunks. In MOCK mode yields from mock_text, no API call.

    Walks the provider chain (primary, then any other configured provider);
    falls back to the mock text only when every provider fails. Raises only
    when no provider is configured at all.
    """
    if MOCK:
        yield from _mock_chunks(mock_text)
        return
    chain = _chain()
    if not chain:
        raise RuntimeError(
            "No AI provider configured. Set GROQ_API_KEY (free, https://console.groq.com) "
            "or GEMINI_API_KEY (free, https://aistudio.google.com/apikey), "
            "or ANTHROPIC_API_KEY, or MOCK_AI=true for testing."
        )
    yielded = False
    for provider in chain:
        try:
            for chunk in _stream_with(provider, system, messages, max_tokens):
                yielded = True
                yield chunk
            if yielded:
                return
            print(f"[ai] stream returned empty ({provider}), trying next", flush=True)
        except Exception as e:
            print(f"[ai] stream failed ({provider}), trying next: {e}", flush=True)
    if not yielded:
        yield from _mock_chunks(mock_text)


def complete(system: str, messages: list, mock_text: str, max_tokens: int = 1024) -> str:
    """Non-streaming completion. In MOCK mode returns mock_text.

    Walks the provider chain; falls back to mock_text only when every
    provider fails. Raises only when no provider is configured at all.
    """
    if MOCK:
        return mock_text
    chain = _chain()
    if not chain:
        raise RuntimeError(
            "No AI provider configured. Set GROQ_API_KEY (free, https://console.groq.com) "
            "or GEMINI_API_KEY (free, https://aistudio.google.com/apikey), "
            "or ANTHROPIC_API_KEY, or MOCK_AI=true for testing."
        )
    for provider in chain:
        try:
            text = _complete_with(provider, system, messages, max_tokens)
            if text and text.strip():
                return text
            print(f"[ai] complete returned empty ({provider}), trying next", flush=True)
        except Exception as e:
            print(f"[ai] complete failed ({provider}), trying next: {e}", flush=True)
    print("[ai] all providers failed, falling back to mock", flush=True)
    return mock_text

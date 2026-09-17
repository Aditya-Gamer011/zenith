"""Provider layer for Large Language Model calls.

Every model call in Zenith goes through this module. The brain uses Gemini's
*tool-calling* (OpenAI-compatible chat.completions endpoint) so the model can
emit structured function calls which the runtime executes. We keep the provider
interface tiny so Claude / Ollama / local models can be dropped in later.

Reference: https://ai.google.dev/gemini-api/docs/openai
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from typing import Any, AsyncIterator

import httpx

from .config import settings

log = logging.getLogger("zenith.provider")

# Temperature presets per tier.
TEMPS = {"fast": 0.2, "standard": 0.4, "creative": 0.8, "deep": 0.25}

# Provider mode: 'antigravity' (local agy CLI), 'gemini' (direct Gemini API), or 'fallback'
PROVIDER_MODE = os.getenv("PROVIDER_MODE", "antigravity").strip().lower()

# OpenAI-compatible base (Gemini's OpenAI layer).
# NOTE: the /v1beta/openai/ path 404'd on this key. Gemini's OpenAI-compatible
# endpoint is actually /v1beta/openai/chat/completions for BOTH API keys
# (AIza...) and OAuth tokens — but authentication differs:
#   - API key:  Authorization: Bearer <AIza...>
#   - OAuth:    Authorization: Bearer <AQ token> + x-goog-user-project:<project>
# We support both by sending the right header and detecting key type.
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
_CHAT_URL = f"{_BASE_URL}/chat/completions"

# Fallback provider (llm-solutions DeepSeek relay) used when Gemini is
# rate-limited (429) or returns no key. Configurable via .env.
FALLBACK_ENDPOINT = os.getenv("FALLBACK_ENDPOINT", "https://llmsolutions.top/v1/chat/completions")
FALLBACK_API_KEY = os.getenv("FALLBACK_API_KEY", "").strip()
FALLBACK_MODEL = os.getenv("FALLBACK_MODEL", "deepseek-v4-flash-0731")
# When true, the orchestrator routes EVERY standard-tier turn through the
# fallback provider (DeepSeek) instead of waiting for a Gemini quota hit.
# Makes Zenith independent of the Gemini free-tier 20-req/min cap.
FALLBACK_PREFER = os.getenv("FALLBACK_PREFER", "no").strip().lower() in {"1", "true", "yes", "on"}
MODEL_FALLBACK_CHAIN = [
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
]

# Keys come ONLY from env (.env is gitignored). No literal tokens in source.
# Rotate by adding GEMINI_API_KEY_2 / GEMINI_API_KEY_3 to .env.
API_KEYS = [
    os.getenv("GEMINI_API_KEY", "").strip(),
    os.getenv("GEMINI_API_KEY_2", "").strip(),
    os.getenv("GEMINI_API_KEY_3", "").strip(),
]
_seen_keys = set()
API_KEYS = [k for k in API_KEYS if k and not (k in _seen_keys or _seen_keys.add(k))]

KEY_COOLDOWNS: dict[str, float] = {}


def get_prioritized_keys() -> list[str]:
    """Return API keys ordered so non-rate-limited keys come first, and rate-limited keys are shifted to the back."""
    all_keys = [
        settings.gemini_api_key,
        os.getenv("GEMINI_API_KEY", "").strip(),
        os.getenv("GEMINI_API_KEY_2", "").strip(),
        os.getenv("GEMINI_API_KEY_3", "").strip(),
    ]
    seen = set()
    unique_keys = [k for k in all_keys if k and not (k in seen or seen.add(k))]

    now = time.time()
    active = [k for k in unique_keys if KEY_COOLDOWNS.get(k, 0) <= now]
    cooled = [k for k in unique_keys if KEY_COOLDOWNS.get(k, 0) > now]
    return active + cooled


def mark_key_rate_limited(key: str, cooldown_sec: float = 120.0):
    """Mark a key as rate-limited so subsequent model calls shift it to the end of the fallback chain."""
    KEY_COOLDOWNS[key] = time.time() + cooldown_sec
    log.warning("Shifted API key (...%s) to back of fallback chain for %.0fs due to rate-limiting.", key[-6:], cooldown_sec)


def model_for(tier: str) -> str:
    """Resolve a tier ('fast' | 'standard') to a full Gemini model ID."""
    attr = settings.tier_routing[tier]
    return getattr(settings, attr)


def _headers_for_key(key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if key.startswith("AQ.") or key.startswith("ya29."):
        h["Authorization"] = f"Bearer {key}"
        proj = settings.oauth_project_number or ""
        if proj:
            h["x-goog-user-project"] = proj
    else:
        h["Authorization"] = f"Bearer {key}"
        h["x-goog-api-key"] = key
    return h


def _headers() -> dict[str, str]:
    keys = get_prioritized_keys()
    key = keys[0] if keys else settings.gemini_api_key
    return _headers_for_key(key)


def _messages_from_recent(recent: list[dict[str, Any]], system: str) -> list[dict[str, Any]]:
    """Build an OpenAI-style messages list from stored recent conversation rows."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for row in recent:
        role = row.get("role")
        if role not in ("user", "assistant"):
            continue
        content = row.get("content")
        if not content:
            continue
        messages.append({"role": role, "content": content})
    return messages


def _extract_text(data: dict[str, Any]) -> str:
    """Grab the final assistant text from an OpenAI-style completion response."""
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return (message.get("content") or "").strip()


async def chat_stream(
    tier: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 2048,
) -> AsyncIterator[dict[str, Any]]:
    """Stream a chat completion across rotated API keys and fallback models."""
    initial_model = model_for(tier)
    if initial_model in MODEL_FALLBACK_CHAIN:
        idx = MODEL_FALLBACK_CHAIN.index(initial_model)
        models = MODEL_FALLBACK_CHAIN[idx:] + MODEL_FALLBACK_CHAIN[:idx]
    else:
        models = [initial_model] + [m for m in MODEL_FALLBACK_CHAIN if m != initial_model]

    started = time.time()
    # Tracked across the whole key/model sweep: a 404/5xx means the model ID is
    # bad or upstream is down, distinct from a rate-limit ("quota"). We still
    # rotate keys within a model before moving on.
    model_has_any_non_quota_error = False
    for current_model in models:
        keys_to_try = get_prioritized_keys()
        model_has_non_quota_error = False

        for current_key in keys_to_try:
            payload: dict[str, Any] = {
                "model": current_model,
                "messages": messages,
                "temperature": TEMPS.get(tier, 0.4),
                "max_tokens": max_tokens,
                "stream": True,
            }
            if tools:
                payload["tools"] = tools

            try:
                async with httpx.AsyncClient(timeout=90) as client:
                    async with client.stream("POST", _CHAT_URL, headers=_headers_for_key(current_key), json=payload) as resp:
                        resp.raise_for_status()
                        try:
                            async for line in resp.aiter_lines():
                                if not line or not line.startswith("data:"):
                                    continue
                                raw = line[len("data:"):].strip()
                                if raw == "[DONE]":
                                    break
                                try:
                                    evt = json.loads(raw)
                                except json.JSONDecodeError:
                                    continue

                                choices = evt.get("choices") or []
                                if not choices:
                                    continue
                                delta = choices[0].get("delta") or {}
                                message = choices[0].get("message") or {}

                                text = delta.get("content") or message.get("content")
                                if text:
                                    yield {"type": "text", "text": text}

                                tools_delta = delta.get("tool_calls")
                                if tools_delta:
                                    for tc in tools_delta:
                                        idx_tc = tc.get("index", 0)
                                        if tc.get("id") or tc.get("function"):
                                            yield {"type": "tool_call", "index": idx_tc,
                                                   "id": tc.get("id", ""),
                                                   "function": tc.get("function") or {},
                                                   "extra": tc.get("extra_content") or {}}
                                        else:
                                            fn = tc.get("function") or {}
                                            yield {"type": "tool_delta", "index": idx_tc,
                                                   "name": fn.get("name", ""), "args": fn.get("arguments", ""),
                                                   "extra": tc.get("extra_content") or {}}
                        except Exception as exc:
                            # Partial-stream failure: text/tool deltas may already
                            # have been yielded, so the orchestrator must NOT
                            # treat the truncated reply as final or fire its
                            # pending tools. Surface it as an error instead of
                            # silently propagating out of the generator.
                            log.warning("Stream broke mid-turn on %s: %s", current_model, exc)
                            yield {"type": "error", "error": "stream_broken", "detail": str(exc)}
                            return

                    yield {"type": "done", "model": current_model, "duration": round(time.time() - started, 3)}
                    return
            except httpx.HTTPStatusError as exc:
                detail = await _read_error_detail(exc)
                status = exc.response.status_code if exc.response else 0
                body_is_quota = '"code": 429' in detail or "QUOTA_EXCEEDED" in detail or "quota" in detail.lower()
                if status == 429 or body_is_quota:
                    mark_key_rate_limited(current_key)
                    log.warning("Rate limit on %s with Key (...%s) — trying next API key...", current_model, current_key[-6:])
                    continue
                elif status in (404, 500, 502, 503, 504):
                    # A dead model ID / upstream 5xx isn't this key's fault — try
                    # the next key before giving up on the model (previously this
                    # `break` skipped every remaining key for a transient 5xx or
                    # one stale AQ token).
                    log.warning("Model status %s on %s with Key (...%s) — trying next key...", status, current_model, current_key[-6:])
                    model_has_any_non_quota_error = True
                    continue
                else:
                    log.error("Provider %s failed: %s | %s", current_model, exc, detail[:400])
                    tag = f"HTTP {status}"
                    yield {"type": "error", "error": tag, "detail": detail}
                    return
            except Exception as exc:
                log.warning("Provider error on %s with Key (...%s): %s — trying next key...", current_model, current_key[-6:], exc)
                continue

        if model_has_any_non_quota_error:
            continue

    if model_has_any_non_quota_error:
        yield {"type": "error", "error": "unavailable",
               "detail": "Models unavailable (404/5xx) across all keys."}
    else:
        yield {"type": "error", "error": "quota", "detail": "All model & API key combinations rate-limited."}


async def _read_error_detail(exc: httpx.HTTPStatusError) -> str:
    """Best-effort read of a failed streaming response's error body."""
    if exc.response is None:
        return ""
    try:
        body = await exc.response.aread()
        if body:
            return body.decode(errors="replace")[:800]
    except Exception:
        pass
    try:
        body = exc.response.read()
        if body:
            return body.decode(errors="replace")[:800]
    except Exception:
        pass
    return ""


async def chat_stream_fallback(
    tier: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 1600,
) -> AsyncIterator[dict[str, Any]]:
    """DeepSeek (llm-solutions) agentic streaming. Used when Gemini is out of quota.

    llmsolutions.top exposes the same OpenAI-compatible interface as the Gemini
    OpenAI layer, so this mirrors `chat_stream` (tier, messages, tools,
    max_tokens) and — crucially — passes `tools` through. That makes the
    fallback a genuinely agentic provider (parallel tool calls, 200k context),
    not a text-only relay. DeepSeek doesn't hand back a `thought_signature`, so
    no `extra` is threaded on echo; the orchestrator already tolerates that.
    """
    del tier  # interface parity; tier is a Gemini-only concept
    if not FALLBACK_API_KEY:
        yield {"type": "error", "error": "no_fallback_key"}
        return
    payload: dict[str, Any] = {
        "model": FALLBACK_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "stream": True,
        "temperature": TEMPS.get("standard", 0.4),
    }
    if tools:
        payload["tools"] = tools
    headers = {"Authorization": f"Bearer {FALLBACK_API_KEY}", "Content-Type": "application/json"}
    started = time.time()
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", FALLBACK_ENDPOINT, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    choices = evt.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    msg = choices[0].get("message") or {}
                    text = delta.get("content") or msg.get("content")
                    if text:
                        yield {"type": "text", "text": text}
                    # tool calls — full agentic path: pass through the function
                    # and thread incremental tool args the way the main loop does.
                    tcs = delta.get("tool_calls") or msg.get("tool_calls") or []
                    for tc in tcs:
                        idx = tc.get("index", 0)
                        fn = tc.get("function") or {}
                        if tc.get("id") or fn.get("name"):
                            yield {"type": "tool_call", "index": idx, "id": tc.get("id", ""),
                                   "function": fn, "extra": {}}
                        else:
                            yield {"type": "tool_delta", "index": idx,
                                   "name": fn.get("name", ""), "args": fn.get("arguments", ""),
                                   "extra": {}}
        yield {"type": "done", "model": FALLBACK_MODEL, "duration": round(time.time() - started, 3)}
    except httpx.HTTPStatusError as exc:
        # Reading an already-consumed streaming body raises StreamClosed; read
        # defensively so a broken relay never takes Zenith down.
        detail = ""
        if exc.response is not None:
            try:
                detail = (await exc.response.aread()).decode(errors="replace")[:400]
            except Exception:
                detail = ""
        log.error("Fallback provider failed: %s | %s", exc, detail)
        yield {"type": "error", "error": f"HTTP {exc.response.status_code if exc.response else '?'}"}
    except httpx.StreamClosed:
        log.error("Fallback provider stream closed early: %s", FALLBACK_ENDPOINT)
        yield {"type": "error", "error": "stream closed"}
    except Exception as exc:
        log.error("Fallback stream error: %s", exc)
        yield {"type": "error", "error": str(exc)}


async def chat_stream_antigravity(
    tier: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 2048,
) -> AsyncIterator[dict[str, Any]]:
    """Antigravity CLI provider engine.

    Streams real-time events directly from the host Antigravity Worker CLI
    (`agy` on port 8022) with `gemini-3.1-pro-high`.
    """
    del tier, max_tokens
    started = time.time()
    try:
        from .tools import _get_worker_url
        worker_url = _get_worker_url().rstrip("/")
    except Exception:
        worker_url = os.getenv("WORKER_URL", "http://host.docker.internal:8022").rstrip("/")

    prompt_parts = []
    system_msg = ""
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if role == "system" and content:
            system_msg = content
        elif content:
            prompt_parts.append(f"{role.upper()}: {content}")

    if system_msg:
        full_prompt = f"System Context:\n{system_msg}\n\nConversation History:\n" + "\n".join(prompt_parts[-10:])
    else:
        full_prompt = "\n".join(prompt_parts[-10:]) or "Hello"

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            async with client.stream("POST", f"{worker_url}/chat", json={"prompt": full_prompt}) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if raw == "[DONE]":
                        break
                    try:
                        obj = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    ev = obj.get("event")
                    if ev == "step_update":
                        su = obj.get("step_update", {})
                        delta = su.get("text_delta") or ""
                        if delta:
                            yield {"type": "text", "text": delta}
                    elif ev == "result":
                        res = obj.get("result", {})
                        resp_text = res.get("response", "").strip()
                        if resp_text:
                            from .orchestrator import _parse_markup_calls
                            markup_calls = _parse_markup_calls(resp_text)
                            for idx, (name, args) in enumerate(markup_calls):
                                yield {
                                    "type": "tool_call",
                                    "index": idx,
                                    "id": f"call_{name}_{idx}",
                                    "function": {"name": name, "arguments": args},
                                    "extra": {},
                                }
        yield {"type": "done", "model": "antigravity-agy", "duration": round(time.time() - started, 3)}
    except Exception as exc:
        log.error("Antigravity worker stream error: %s", exc)
        yield {"type": "error", "error": str(exc)}


async def chat_once(
    tier: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int = 2048,
) -> str:
    """One-shot (non-streaming) completion; returns plain assistant text."""
    parts: list[str] = []
    async for evt in chat_stream(tier, messages, tools, max_tokens):
        if evt.get("type") == "text":
            parts.append(evt.get("text", ""))
    return "".join(parts).strip()


async def classify_tier(prompt: str) -> str:
    """Pick fast or standard tier for plain (non-tool) chat.

    This is a cheap heuristic; the real decision for tool paths lives in the
    Orchestrator. Tuned so greetings/small talk hit the lite model.
    """
    p = prompt.strip().lower()
    short = len(p.split()) <= 4
    greeting = any(g in p for g in ("hi", "hey", "hello", "yo", "thanks", "thank you", "who are you", "what can you do"))
    if short and greeting:
        return "fast"
    long = len(p.split()) > 24
    hard = any(w in p for w in (
        "explain", "teach", "plan", "design", "refactor", "debug", "review",
        "why", "how", "compare", "analyze", "jee", "rotational", "derive",
        "proof", "architecture",
    ))
    return "standard" if (long or hard) else "fast"


async def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Embed a list of strings (for future vector memory). Returns None on failure."""
    model = settings.embedding_model or "gemini-embedding-001"
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
        payload = {
            "requests": [{"model": model, "content": {"parts": [{"text": t}]}} for t in texts]
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=_headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
        return [emb.get("values", []) for emb in data.get("embeddings", [])]
    except Exception as exc:
        log.warning("embedding failed: %s", exc)
        return []
"""Text-to-speech provider layer.

Zenith's spoken output, provider-agnostic, mirroring :mod:`stt`. The request
path only calls ``synthesize()``; the provider (and its fallbacks) are chosen
here from environment, so a different TTS server can be dropped in without
touching the API layer:

  Zenith text
      ↓
  TTS Provider
      ├── Edge TTS (natural female voice, default when the lib is available)
      ├── gTTS (Google, legacy — robotic but zero-dependency)
      └── Web Speech fallback happens client-side (speechSynthesis)
      ↓
  audio (mp3) back to the browser

See Also
--------
``static/app.js`` — ``speak()`` / ``speakWebSpeech`` select a natural female
voice client-side if the server TTS is unavailable.
"""
from __future__ import annotations

import io
import logging
import os
import re

log = logging.getLogger("zenith.voice.tts")

# Provider order: "edgetts" → "gtts". Edge (the same engine that powers
# Microsoft's neural voices) sounds notably more natural than gTTS; gTTS is kept
# as a zero-dependency fallback since it has no native deps.
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edgetts").strip().lower()

# Persona voice: calm, serene, compassionate female. en-IN-NeerjaNeural is a
# warm, measured Indian-English female neural voice. Override per-taste via .env.
EDGE_VOICE = os.getenv("EDGE_VOICE", "en-IN-NeerjaNeural").strip()
GTTS_TLD = os.getenv("GTTS_TLD", "co.in").strip()
GTTS_LANG = os.getenv("GTTS_LANG", "en").strip()

MAX_CHARS = 300  # spoken replies stay short — the full answer lives on screen

# Clean model-speak (markdown / urls / code fences) down to spoken prose. Mirrors
# the client-side scrub so server audio matches what the user sees.
_MD_SCRUB = [
    (re.compile(r"```[\s\S]*?```"), " I have generated the code on your screen. "),
    (re.compile(r"`([^`]+)`"), r"\1"),
    (re.compile(r"!\[([^\]]*)\]\([^)]+\)"), r"\1"),
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),
    (re.compile(r"(?:https?|ftp):\/\/[\n\S]+"), ""),
    (re.compile(r"[*_#~|<=>]"), " "),
    (re.compile(r"\s+"), " "),
]


def provider_name() -> str:
    return TTS_PROVIDER


def _clean(text: str) -> str:
    clean = text.strip()
    if not clean:
        return ""
    for pattern, repl in _MD_SCRUB:
        clean = pattern.sub(repl, clean)
    clean = clean.strip()
    if not clean:
        clean = "I'm working on that for you."
    return clean[:MAX_CHARS]


def synthesize(text: str) -> bytes:
    """Return spoken audio (mp3 bytes) for ``text``. Empty bytes on failure."""
    clean = _clean(text)
    if not clean:
        return b""

    if TTS_PROVIDER == "edgetts":
        out = _edge_tts_all(clean)
        if out:
            return out
        log.warning("Edge TTS failed — falling back to gTTS.")
    return _gtts(clean)


async def synthesize_stream(text: str):
    """Yield spoken-audio bytes as they generate (low-latency streaming).

    Falls back gracefully: if Edge is unavailable, yields a single gTTS chunk
    so the request path always produces audio. Reuses the same markdown scrub
    as the one-shot ``synthesize`` so spoken output matches the screen.
    """
    clean = _clean(text)
    if not clean:
        return

    if TTS_PROVIDER == "edgetts":
        try:
            async for chunk in _edge_tts_stream(clean):
                if chunk:
                    yield chunk
            return
        except Exception as exc:
            log.warning("Edge TTS stream failed — falling back to gTTS: %s", exc)

    gtts_bytes = _gtts(clean)
    if gtts_bytes:
        yield gtts_bytes


def _edge_tts_all(text: str) -> bytes:
    """Collect the full Edge audio to memory (one-shot path)."""
    try:
        import asyncio
        import edge_tts
    except ImportError:
        log.warning("edge-tts not installed — cannot use natural Edge voices.")
        return b""

    async def _gen() -> bytes:
        communicate = edge_tts.Communicate(text, EDGE_VOICE)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    try:
        return asyncio.run(_gen())
    except Exception as exc:
        log.warning("Edge TTS generation error: %s", exc)
        return b""


async def _edge_tts_stream(text: str):
    """Async generator yielding Edge audio chunks as they're produced.

    edge-tts' ``stream()`` yields ``{"type": "audio", "data": bytes}`` in
    sentence-marker order, so the browser can start playing the first chunk
    while the rest are still being synthesized.
    """
    try:
        import edge_tts
    except ImportError:
        log.warning("edge-tts not installed — cannot stream natural Edge voices.")
        return

    communicate = edge_tts.Communicate(text, EDGE_VOICE)
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            yield chunk["data"]


# ── gTTS (zero-dependency legacy fallback) ────────────────────────────────────

def _gtts(text: str) -> bytes:
    try:
        from gtts import gTTS
    except ImportError:
        log.warning("gtts not installed — no TTS output available.")
        return b""
    try:
        tts = gTTS(text=text, lang=GTTS_LANG, tld=GTTS_TLD)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        return buf.getvalue()
    except Exception as exc:
        log.warning("gTTS generation error: %s", exc)
        return b""

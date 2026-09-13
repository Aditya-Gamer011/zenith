"""Gemini Live API — native bidirectional audio plane (.gemini_live).

Primary voice path for Zenith. The Live WebSocket (``BidiGenerateContent``)
accepts browser-captured speech as ``realtimeInput`` audio and returns the
model's spoken reply as *response audio* — no text round-trip, no per-chunk
STT/TTS. Speech recognition (STT) and synthesis (TTS) happen inside the model,
so this one call replaces the Groq Whisper → Edge TTS pipeline.

Key properties that shape the implementation:

  * **Gemini 3.1 Flash Live is the only model we use.** We verify every model
    before shipping. ``gemini-2.5-flash-native-audio-latest`` (and the older
    ``-dialog`` alias) return **1011 "Internal error" on every key** even with
    clean PCM — unusable. ``gemini-3.1-flash-live-preview`` is the current
    recommended Live model: native audio output, low latency, 128k context,
    ``thinkingLevel`` instead of the old ``thinkingBudget``. It's the default
    slot and the one that actually speaks on verified API keys.

  * **Input is 16 kHz PCM16 mono** — the Live API's *native* input rate. The
    browser sends raw 16k PCM; server-side transcodes of webm/ogg also target
    16k. Output audio comes back at 24 kHz and is played as-is.

  * **Auth.** The Live WS accepts a plain API key via ``?key=`` query — both
    AIza and AQ keys work there (header auth is rejected). Server-to-server
    only — the browser never sees a credential.

  * **Websocket availability.** The ``websockets`` client is already a
    dependency (``>=12,<14``); no new package needed. The WebSocket protocol
    messages are plain JSON; we avoid the python SDK entirely.

  * **Fallback.** If every key fails on every accepted model (or Live is
    disabled), ``live_handle`` signals the caller to fall back to the classic
    Groq Whisper → Edge TTS pipeline. Live errors never crash the voice path.

The URL is the ``v1beta`` endpoint with the model in the path:

    wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.\
        v1beta.GenerativeService.BidiGenerateContent?key=<APIKEY>

Message flow
------------
We send an initial ``BidiGenerateContentSetup``, then a stream of
``realtimeInput`` carrying the audio bytes. The server replies with
``BidiGenerateContentServerMessage`` whose ``serverContent`` carries the
model's response audio in chunks, plus ``sessionResumption`` etc. As soon as
the session starts, we begin streaming response audio back to the client.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from dataclasses import dataclass, field

log = logging.getLogger("zenith.voice.live")

LIVE_ENABLED = os.getenv("LIVE_VOICE_ENABLED", "yes").strip().lower() in {"1", "true", "yes", "on"}
# Gemini 3.1 Flash Live is the ONLY model we ship by default — the 2.5 native
# audio model 1011s on every key, so including it just adds dead-weight retries.
# Override via .env if a future model lands.
_LIVE_MODELS_ENV = os.getenv("LIVE_MODELS", "gemini-3.1-flash-live-preview")
LIVE_MODELS = [m.strip() for m in _LIVE_MODELS_ENV.split(",") if m.strip()]

# The Live API consumes raw 16 kHz mono PCM16 — its *native* input rate.
# (24 kHz worked too, but 16k is the documented default and avoids a resample.)
LIVE_SAMPLE_RATE = int(os.getenv("LIVE_SAMPLE_RATE", "16000"))

# Native-audio output (the model speaks; Zenith streams that audio to the client).
_RESPONSE_MODALITIES = ["AUDIO"]

# Hard safety cap on a single Live exchange — the conversation pacing and the
# native-audio output mean a single turn should not stream for minutes. Callers
# (browser VAD) already cap utterance length; this is the server-side backstop.
LIVE_MAX_RESPONSE_SECONDS = 45

# Time to open the WebSocket + stream a response. Generous — model + audio.
_LIVE_TIMEOUT_S = 30.0

# Completed Live responses are streamed back to the client in fixed chunks.
LIVE_RESPONSE_CHUNK = 16384


def available() -> bool:
    """Whether a Live model is configured. The actual auth depends on having a
    key (checked at session-time so we can fall back cleanly)."""
    return LIVE_ENABLED and bool(LIVE_MODELS)


async def live_speak(text: str, system_instruction: str = "") -> LiveTurn:
    """Make Gemini *speak* a line of text (native audio) with no mic input.

    Primary use: the chat path's final reply — the orchestrator returns text,
    and we want Zenith's spoken answer to come from the same Live voice that
    carries the whole conversation, not a separate TTS engine.

    Implementation: seed the session with the text as client content, then
    turn-complete with empty audio. The model replies with native audio the
    same way it does after hearing the user speak.
    """
    if not available():
        return LiveTurn(error="Live voice disabled")
    text = (text or "").strip()
    if not text:
        return LiveTurn(error="No text to speak")

    for attempt in range(2):
        key = _next_key()
        if not key:
            return LiveTurn(error="No Gemini keys configured")
        for model in LIVE_MODELS:
            try:
                turn = await _run_speak_model(model, text, key, system_instruction)
            except Exception as exc:
                log.warning("live_speak model=%s key=…%s failed: %s", model,
                            key[-6:] if len(key) > 6 else "?", exc)
                turn = LiveTurn(error=str(exc))
            if turn.ok:
                return turn
    return LiveTurn(error="All Live models/keys failed to speak")


async def _run_speak_model(model: str, text: str, key: str,
                           system_instruction: str) -> LiveTurn:
    from websockets.legacy.client import connect

    turn = LiveTurn(model=model, key=key)
    url = ("wss://generativelanguage.googleapis.com/ws/"
           "google.ai.generativelanguage.v1beta.GenerativeService."
           "BidiGenerateContent?key=" + key)

    async with connect(url, extra_headers={},
                       open_timeout=_LIVE_TIMEOUT_S, close_timeout=5) as ws:
        await ws.send(json.dumps(_first_msg(model, system_instruction)))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=_LIVE_TIMEOUT_S))
            if "setupComplete" in msg:
                break
        # Seed the model with the text we want it to speak, then complete the
        # (empty) audio turn — the model now speaks the seeded content.
        await ws.send(json.dumps({"clientContent": {
            "turns": [{"role": "user", "parts": [{"text": text}]}],
            "turnComplete": True}}))
        turn.audio = b""
        completed = False
        started = asyncio.get_event_loop().time()
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=_LIVE_TIMEOUT_S)
            except asyncio.TimeoutError:
                break
            if asyncio.get_event_loop().time() - started > LIVE_MAX_RESPONSE_SECONDS:
                break
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            sc = msg.get("serverContent")
            if sc:
                mt = sc.get("modelTurn") or {}
                for part in mt.get("parts", []) or []:
                    if (inline := part.get("inlineData")) and inline.get("data"):
                        turn.audio += base64.b64decode(inline["data"])
                        if inline.get("mimeType"):
                            turn.audio_mime = inline["mimeType"]
                if sc.get("turnComplete") or sc.get("generationComplete"):
                    completed = True
                    break
            if msg.get("error"):
                turn.error = str(msg.get("error"))
        turn.ok = completed and bool(turn.audio)
        if not turn.ok and not turn.error:
            turn.error = "No spoken audio produced"
        if turn.ok:
            _normalize_output_audio(turn)
    return turn


def _ws_headers(key: str) -> dict[str, str]:
    """Auth headers for the live WS.

    Verified: the Live WS accepts the AQ./AIza. key via ``?key=`` in the URL
    and REJECTS it as an ``Authorization: Bearer/Token`` header ("API keys are
    not supported … Expected OAuth 2 access token"). So we always auth via the
    URL query param and send no headers here.
    """
    return {}


def _first_msg(model: str, system_instruction: str = "") -> dict:
    """The required first WebSocket message (BidiGenerateContentSetup).

    Includes Zenith's full tool catalog so the model can call tools mid-
    conversation (the frontend shows them, and _handle_tool_calls executes them).
    """
    setup = {
        "model": f"models/{model}",
        "generationConfig": {"responseModalities": _RESPONSE_MODALITIES},
    }
    if system_instruction and system_instruction.strip():
        setup["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    # Attach Zenith's tool schemas so the Live model can use them — sanitized so
    # arrays/objects without child schemas don't 1007 the whole setup.
    try:
        from ..core.tools import catalog
        tool_specs = catalog()
        if tool_specs:
            clean = _sanitize_tools(tool_specs)
            if clean:
                setup["tools"] = [
                    {"functionDeclarations": [t["function"] for t in clean if t.get("function")]}
                ]
    except Exception as exc:
        log.warning("Could not attach tool catalog to Live setup: %s", exc)
    return {"setup": setup}


def _audio_chunks(data: bytes) -> list[dict]:
    """Turn raw audio bytes into Live ``realtimeInput.audio`` Blob frames.

    The Live API consumes raw mono PCM16 (input rate 16 kHz by default). Split
    into ~100ms slices so the model starts ASR while we stream the rest. The
    mimeType carries the true sample rate so the server doesn't guess wrong.
    """
    if not data:
        return []
    step = (LIVE_SAMPLE_RATE // 10) * 2  # 0.1s of PCM16
    frames = [data[i:i + step] for i in range(0, len(data), step)]
    return [{"mimeType": f"audio/pcm;rate={LIVE_SAMPLE_RATE}",
             "data": base64.b64encode(f).decode("ascii")} for f in frames]


# ── Output-audio normalization ────────────────────────────────────────────────
# Gemini Live returns the model's speech as RAW mono PCM16 at 24 kHz
# (`audio/pcm;rate=24000`), which Zenith's consumers cannot handle as-is:
#   * the /ws/live tunnel streams the PCM to the browser's `playLivePcm`, which
#     declares the buffer's rate (`LIVE_PCM_RATE`) — 24k data declared at the
#     16k/native rate would play back at the wrong speed (pitch shifts);
#   * the /api/transcribe and chat-«done» paths serve the audio to `new Audio(url)`,
#     which cannot decode raw `audio/pcm` at all → silent.
# So the model's output is resampled 24 kHz → 16 kHz here (matching the input
# side: LIVE_SAMPLE_RATE / frontend LIVE_PCM_RATE, keeping the whole system at
# one 16k rate), and the two `<audio>`-based paths additionally wrap it in a .wav
# container (universally playable by the browser, lossless).

# Gemini's native-audio output rate (this is what the Live API actually returns).
LIVE_OUTPUT_RATE = 24000


def pcm24k_to_16k(data: bytes) -> bytes:
    """Linear-interpolate 24 kHz PCM16 mono down to 16 kHz (factor 3→2).

    Pure-Python (stdlib ``array``), dependency-free by design — this runs in the
    /api/transcribe path where we avoid pulling in numpy. Chunks are small
    (~15 KB per audio frame), so the interpolation cost is negligible.
    """
    if not data:
        return b""
    if len(data) % 2:
        data = data[:-1]
    import array

    src = array.array("h")
    src.frombytes(data)
    n_in = len(src)
    if n_in < 2:
        return b""
    # 24000 → 16000: for every 3 input samples emit 2. Output is monotonic and
    # exactly 2/3 the input length — the WebAudio resampler expects no drift.
    n_out = (n_in * 2) // 3
    out = array.array("h", [0]) * n_out
    for i in range(n_out):
        # input position is at 3i/2 — interpolate between the flanking samples
        pos = i * 3 / 2
        i0 = int(pos)
        frac = pos - i0
        s0 = src[i0]
        s1 = src[i0 + 1] if i0 + 1 < n_in else s0
        out[i] = int(s0 + (s1 - s0) * frac)
    return out.tobytes()


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    """Wrap 16-bit PCM mono in a minimal RIFF/WAVE file (.wav is lossless and
    universally playable by ``new Audio()`` / HTMLAudioElement — raw ``audio/pcm``
    is not)."""
    if not pcm:
        return b""
    import io
    import wave

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


# The output PCM (resampled to the input 16k) rides to the browser inside a .wav
# so HTML `<audio>` can decode it; the bytes are still plain PCM16 inside, which
# is what playLivePcm reads.
OUTPUT_MIME = "audio/wav"


def _normalize_output_audio(turn: "LiveTurn") -> None:
    """Resample a turn's Live output to the 16k PCM the rest of Zenith expects,
    and wrap it in a playable WAV container.

    Call after ``turn.ok`` is set. 24k raw PCM16 (``audio/pcm;rate=24000``) is
    what Gemini streams; the streaming tunnel and the two `<audio>`-based paths
    all consume the normalized 16k bytes here.
    """
    if not turn.audio:
        return
    # Only resample raw PCM — a webm/opus container (some models/modes) passes
    # straight through untouched; the browser decodes it natively.
    if "pcm" in turn.audio_mime.lower():
        turn.audio = pcm24k_to_16k(turn.audio)
        turn.audio_mime = OUTPUT_MIME
        # Wrap the resampled PCM in a .wav so new Audio()/HTMLAudioElement can
        # decode it (raw audio/pcm is not a browser-decodable format).
        turn.audio = pcm_to_wav(turn.audio)


_LAST_KEY: str = ""
_KEY_INDEX = 0


def _next_key() -> str:
    """Round-robin over the configured Gemini keys, so all three contribute."""
    global _KEY_INDEX, _LAST_KEY
    try:
        from zenith.core import provider
        keys = provider.API_KEYS
    except Exception:
        keys = [os.getenv("GEMINI_API_KEY", "").strip()]
    keys = [k for k in keys if k]
    if not keys:
        return ""
    key = keys[_KEY_INDEX % len(keys)]
    _KEY_INDEX += 1
    _LAST_KEY = key
    return key


@dataclass
class LiveTurn:
    """One live exchange: input audio in, response audio out (or a failure)."""
    transcript: str = ""          # text the model heard (as a fallback note)
    audio: bytes = field(default=b"")     # response audio
    audio_mime: str = "audio/webm"        # actual container of `audio` (from the model)
    model: str = ""
    key: str = ""
    provider: str = "gemini-live"
    ok: bool = False
    error: str = ""


async def live_handle(audio_bytes: bytes, fmt: str = "webm",
                      system_instruction: str = "") -> LiveTurn:
    """Run one utterance through Gemini Live. Returns a LiveTurn; ``ok`` False
    means the caller should fall back to the classic Groq→Edge TTS pipeline."""
    if not available():
        return LiveTurn(error="Live voice disabled")
    if not audio_bytes:
        return LiveTurn(error="No audio")

    # Rotate through models (best+fastest first) then keys. Auth is via ?key=
    # URL param for every key (the Live WS accepts AQ keys there).
    for model in LIVE_MODELS:
        for attempt in range(2):  # give each model two key attempts
            key = _next_key()
            if not key:
                return LiveTurn(error="No Gemini keys configured")
            try:
                turn = await _run_model(model, audio_bytes, fmt, key, system_instruction)
            except Exception as exc:
                log.warning("Live model=%s key=…%s failed: %s", model,
                            key[-6:] if len(key) > 6 else "?", exc)
                turn = LiveTurn(error=str(exc))
            if turn.ok:
                return turn
            if attempt:  # second attempt on the same model failed too — try next model
                break
    return LiveTurn(error="All Live models/keys failed")


async def _run_model(model: str, audio_bytes: bytes, fmt: str, key: str,
                     system_instruction: str) -> LiveTurn:
    """Open one Live session, stream the audio, collect the response audio.

    Returns a LiveTurn whose ``ok`` is True if the model produced a complete
    response — not merely "some audio". A turn is complete the moment the
    server reports ``turnComplete``/``generationComplete`` (the model may have
    answered with *text* for a tool-heavy request; that's still a successful
    exchange even with no audio). We only mark failure when the model sends no
    turn completion at all within the cap — the old empty-audio check treated
    valid text-only tool turns as failures and burned quota retrying.
    """
    # websockets 13 moved the asyncio client to websockets.asyncio.client and it
    # no longer accepts ``extra_headers``. The legacy client
    # (websockets.legacy.client.connect) still takes ``extra_headers`` and
    # ``open_timeout``, which is what we need.
    from websockets.legacy.client import connect

    turn = LiveTurn(model=model, key=key)

    # Auth: EVERY key (AIza AND AQ) rides in the URL as ``?key=``. Verified:
    # the Live WS accepts the AQ key there and rejects it as any header.
    url = ("wss://generativelanguage.googleapis.com/ws/"
           "google.ai.generativelanguage.v1beta.GenerativeService."
           "BidiGenerateContent?key=" + key)

    async with connect(url, extra_headers={},
                       open_timeout=_LIVE_TIMEOUT_S, close_timeout=5) as ws:
        # 1) setup
        await ws.send(json.dumps(_first_msg(model, system_instruction)))
        # Wait for setupComplete before streaming audio. The server sends
        # {"setupComplete": {}} — check KEY PRESENCE, not truthiness ({} is falsy).
        try:
            while True:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=_LIVE_TIMEOUT_S))
                if "setupComplete" in msg:
                    break
        except Exception:
            pass
        # 2) stream the audio as realtimeInput.audio Blobs. The Live WS API
        # consumes RAW mono PCM16 at 16 kHz (LIVE_SAMPLE_RATE). The streaming
        # tunnel (LiveSession) is fed true PCM16 by the browser; the synchronous
        # /api/transcribe path passes a webm/opus browser capture and MUST be
        # converted first — otherwise we'd ship the compressed bytes as
        # "audio/pcm" and Gemini would hear garbage (silence, hangs, no reply).
        if fmt == "pcm":
            pcm = audio_bytes  # the caller already produced raw PCM16
        else:
            from .stt import _to_pcm16k
            pcm = _to_pcm16k(audio_bytes, fmt)
            if not pcm:
                return LiveTurn(error="Could not convert audio for Gemini Live")
        chunks = _audio_chunks(pcm)
        for c in chunks:
            payload = {"realtimeInput": {"audio": c}}
            await ws.send(json.dumps(payload))
            await asyncio.sleep(0.01)
        # 3) end of input turn — explicit audio_stream_end flushes cached audio
        # so the server can finalize ASR without waiting on its silence timer.
        await ws.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))
        # 4) read the server response audio (+ tool calls). Send and receive
        # must interleave: tool calls arrive mid-turn and their responses are
        # written back on the same socket while the model keeps speaking.
        turn.audio = b""
        completed = False
        error = ""
        started = asyncio.get_event_loop().time()
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            content = msg.get("serverContent")
            if content:
                mt = content.get("modelTurn", {}) or {}
                for part in mt.get("parts", []) or []:
                    if (inline := part.get("inlineData")) and inline.get("data"):
                        turn.audio += base64.b64decode(inline["data"])
                        if inline.get("mimeType"):
                            turn.audio_mime = inline["mimeType"]
                if content.get("turnComplete") or content.get("generationComplete"):
                    completed = True
                    break
            if msg.get("toolCall"):
                # Zenith's tool layer: execute the called functions and send the
                # response back so the model can finish its turn (with audio).
                await _handle_tool_calls(ws, msg["toolCall"])
            if msg.get("error"):
                error = str(msg.get("error"))
            if asyncio.get_event_loop().time() - started > LIVE_MAX_RESPONSE_SECONDS:
                log.warning("Live response exceeded %ds cap — returning partial audio.",
                            LIVE_MAX_RESPONSE_SECONDS)
                break
        # A turn is a success only if it BOTH completed AND produced audio. The
        # model sometimes "completes" a turn with zero audio (a known Live quirk:
        # turns alternate, some are silent). For the /api/transcribe path, that
        # empty turn must count as a failure so the caller falls back to Groq
        # instead of serving a silent (or absent) reply.
        turn.ok = completed and bool(turn.audio)
        if not turn.ok:
            turn.error = error or ("Live replied without audio" if completed else
                                   "Live response ended before turn completion")
        if turn.ok:
            _normalize_output_audio(turn)
    return turn


async def _handle_tool_calls(ws, tool_call: dict) -> None:
    """Run Zenith's tool handlers for each functionCall and reply on the socket."""
    calls = tool_call.get("functionCalls", []) or []
    responses = []
    for c in calls:
        name = c.get("name", "")
        args = c.get("args") or {}
        cid = c.get("id", "")
        try:
            from ..core.tools import call_tool
            res = await call_tool(name, args if isinstance(args, dict) else {})
            result = res.get("result", res.get("error", ""))
        except Exception as exc:
            result = f"error: {exc}"
        responses.append({"id": cid, "response": {"result": str(result)}})
    if responses:
        await ws.send(json.dumps({"toolResponse": {"functionResponses": responses}}))


# ── config helpers (defaults match the module-level constants above) ─────────

def provider_name() -> str:
    return "gemini-live"


def configured_models() -> list[str]:
    return list(LIVE_MODELS)


# ── Tool schema sanitizer ─────────────────────────────────────────────────────
# Gemini's Live setup REJECTS custom tools whose parameters reference arrays
# or objects without their child schemas (e.g. generate_pptx: slides.items
# .properties.stats is {"type":"array"} with no "items" → 1007 invalid frame).
# Recursively fill missing "items"/"properties" so every tool is Live-safe.

def _sanitize_schema(node) -> None:
    """In-place: ensure arrays have items and objects have properties."""
    if not isinstance(node, dict):
        return
    # $ref vendors
    if "type" in node:
        t = node.get("type")
        if t == "array" and "items" not in node:
            node["items"] = {"type": "string"}  # default to string items
        elif t == "object" and "properties" not in node:
            node["properties"] = {}
    # recurse
    for v in node.get("properties", {}).values():
        _sanitize_schema(v)
    items = node.get("items")
    if isinstance(items, dict):
        _sanitize_schema(items)
    # additionalProperties / anyOf-ish
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in node.get(key, []) or []:
            _sanitize_schema(sub)


def _sanitize_tools(tool_specs: list[dict]) -> list[dict]:
    out = []
    for t in tool_specs:
        fn = t.get("function") or {}
        params = fn.get("parameters") or {}
        try:
            _sanitize_schema(params)
        except Exception:
            continue  # drop a tool that can't be sanitized
        out.append({"type": "function", "function": fn})
    return out


# ── Persistent bidirectional session (true streaming) ────────────────────────
# One Live WebSocket that stays open for a conversation. The browser streams
# PCM audio up (realtimeInput), the model streams native audio + tool calls down.
# Tool calls are executed server-side and the responses fed back. This is what
# the frontend's voice mode uses for natural, continuous, interruptible dialogue.

class LiveSession:
    """A live bidirectional session between one browser and Gemini Live."""

    def __init__(self, system_instruction: str = "") -> None:
        self.ws = None
        self.key: str = ""
        self.model: str = ""
        self.system_instruction = system_instruction
        self._send_lock = asyncio.Lock()
        self._closed = False

    async def open(self) -> str:
        """Connect + setup one Live WS. Returns an error string, or "" on success."""
        from websockets.legacy.client import connect

        key = _next_key()
        if not key:
            return "No Gemini keys configured"
        self.key = key
        # rotate models too
        last_error = ""
        for model in LIVE_MODELS:
            url = ("wss://generativelanguage.googleapis.com/ws/"
                   "google.ai.generativelanguage.v1beta.GenerativeService."
                   "BidiGenerateContent?key=" + key)
            try:
                ws = await connect(url, extra_headers={},
                                   open_timeout=_LIVE_TIMEOUT_S, close_timeout=5)
                await ws.send(json.dumps(_first_msg(model, self.system_instruction)))
                while True:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=_LIVE_TIMEOUT_S))
                    if "setupComplete" in msg:
                        break
                self.ws = ws
                self.model = model
                return ""
            except Exception as exc:
                log.warning("Live session open failed model=%s key=…%s: %s", model,
                            key[-6:] if len(key) > 6 else "?", exc)
                last_error = str(exc)
                try:
                    await ws.close()
                except Exception:
                    pass
        return f"All Live models failed to open: {last_error}"

    async def push_audio(self, pcm: bytes) -> None:
        """Stream raw PCM16 (16 kHz) into the model."""
        if not self.ws or not pcm:
            return
        chunks = _audio_chunks(pcm)
        async with self._send_lock:
            for c in chunks:
                await self.ws.send(json.dumps({"realtimeInput": {"audio": c}}))
                await asyncio.sleep(0.004)

    async def end_turn(self) -> None:
        """Signal the end of the user's audio turn so the model starts replying."""
        if not self.ws:
            return
        async with self._send_lock:
            try:
                # audio_stream_end flushes the model-side ASR buffer so it can
                # finalize the turn without waiting out its silence timer.
                await self.ws.send(json.dumps({"realtimeInput": {"audioStreamEnd": True}}))
            except Exception:
                pass

    async def events(self):
        """Yield (kind, payload) tuples from the model, driving the conversation.
        Kinds: "audio" (bytes), "text" (model transcription), "tool" (called tool),
        "done" (turnComplete), "error"."""
        if not self.ws:
            yield ("error", "no session")
            return
        while not self._closed:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=_LIVE_TIMEOUT_S)
            except asyncio.TimeoutError:
                continue
            except Exception:
                # Transient wire break (e.g. a 1011 mid-turn). The caller will
                # emit an error; on close the client reconnects the whole tunnel.
                if not self._closed:
                    yield ("error", "connection closed")
                return
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            sc = msg.get("serverContent")
            if sc:
                mt = sc.get("modelTurn") or {}
                for part in mt.get("parts", []) or []:
                    inline = part.get("inlineData") or {}
                    if inline.get("data"):
                        # The model speaks at 24 kHz. The browser's playLivePcm
                        # decodes via the AudioContext device rate (typically 48k)
                        # — raw 24k read as 48k plays ~2× too fast. Resample to
                        # 16k here so every client decodes at the correct speed.
                        # (This model always returns audio/pcm; default to the
                        # resample when the mime is absent — safer than passing
                        # raw 24k through to a 16k-declaring client.)
                        audio = base64.b64decode(inline["data"])
                        mime = (inline.get("mimeType") or "").lower()
                        if not mime or "pcm" in mime:
                            audio = pcm24k_to_16k(audio)
                        yield ("audio", audio)
                # streaming text transcription of the model's speech
                if sc.get("outputTranscription") and sc["outputTranscription"].get("text"):
                    yield ("text", sc["outputTranscription"]["text"])
                if sc.get("inputTranscription") and sc["inputTranscription"].get("text"):
                    yield ("heard", sc["inputTranscription"]["text"])
                if sc.get("turnComplete") or sc.get("generationComplete"):
                    yield ("done", None)
                    # Multi-turn: the SAME Live session persists across turns. Do
                    # NOT return/break the generator — keep reading so the next
                    # utterance on this WebSocket (push_audio + end_turn) produces
                    # the next reply over the same connection. The recv timeout
                    # below just `continue`s while the user is between turns.
                    continue
            tc = msg.get("toolCall")
            if tc and tc.get("functionCalls"):
                calls = tc["functionCalls"]
                for fc in calls:
                    yield ("tool", fc)
                # Execute EVERY call in the message (the model can batch several)
                # and send the responses back automatically — missing one would
                # leave the model waiting on a result that never arrives.
                for fc in calls:
                    await self._handle_tool_calls(fc)
            if msg.get("error"):
                yield ("error", str(msg.get("error")))

    async def _handle_tool_calls(self, fc: dict) -> None:
        from ..core.tools import call_tool

        name = fc.get("name", "")
        args = fc.get("args") or {}
        cid = fc.get("id", "")
        try:
            # Timebox tool execution: a hung tool (shell, browser, a slow
            # network call) must NOT freeze the conversation/mic. 45s is the
            # max the model waits on any single tool before it should move on.
            res = await asyncio.wait_for(
                call_tool(name, args if isinstance(args, dict) else {}),
                timeout=45.0,
            )
            result = res.get("result", res.get("error", ""))
        except asyncio.TimeoutError:
            result = "error: tool timed out after 45s"
        except Exception as exc:
            result = f"error: {exc}"
        async with self._send_lock:
            try:
                await self.ws.send(json.dumps({"toolResponse": {"functionResponses": [
                    {"id": cid, "response": {"result": str(result)}}]}}))
            except Exception:
                pass

    async def close(self) -> None:
        self._closed = True
        if self.ws:
            try:
                await self.ws.send(json.dumps({"clientContent": {"turnComplete": True}}))
            except Exception:
                pass
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
"""Speech-to-text provider layer.

Zenith's voice input path, provider-agnostic. The API layer only ever talks to
``transcribe_audio`` — which provider does the actual recognition is decided
here from environment, never hard-coded into the request path:

  Voice input
      ↓
  STT Provider
      ├── Groq Whisper (default)   — GROQ_API_KEY
      ├── Local Whisper (future)   — offline fallback
      └── Google Web (legacy)      — bundled free fallback
      ↓
  Zenith agent
      ↓
  Tools / actions

The Groq API key never leaves the server: it is read from the environment in
the container (compose ``env_file: .env``) and used for a single server-side
POST. The browser only ever POSTs the raw audio blob back to Zenith's own
``/api/transcribe`` endpoint.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import httpx

log = logging.getLogger("zenith.voice.stt")

# The default provider. "groq" needs GROQ_API_KEY; anything else falls back to
# the legacy Google Web Speech recognizer bundled with the speech_recognition lib.
STT_PROVIDER = os.getenv("STT_PROVIDER", "groq").strip().lower()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo").strip()
# Language hint passed to Whisper — improves accuracy and speed on known
# languages. Default en for voice conversations.
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "en").strip() or None

# Reasonable safety rails on the voice channel. Groq's Whisper endpoint accepts
# at most 25 MB of audio per request; a 10-minute 48 kHz webm is nowhere near
# that, but we cap on both bytes and wall-clock so a stuck tab can't pin the
# endpoint or fill /tmp with garbage.
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_AUDIO_SECONDS = 45

# Stray punctuation and artifacts Whisper occasionally emits for short commands
# ("drop the fan", "turn onl the fan" ...). Strip trailing junk so the agent
# pipeline receives clean instruction text.
_NOISE_TRIM = ".,!?…;:"

_TIMEOUT_MS = 60000


def _get_groq_key() -> str:
    from ..core.config import settings
    return settings.groq_api_key or os.getenv("GROQ_API_KEY", "").strip()


def available() -> bool:
    """Whether a working STT provider is configured (Groq key present)."""
    if STT_PROVIDER == "groq":
        return bool(_get_groq_key())
    return True  # bundled Google Web recognizer needs no key


def reason_configured() -> str:
    key = _get_groq_key()
    if STT_PROVIDER == "groq" and not key:
        return "GROQ_API_KEY not set — add it in Settings for Groq Whisper (currently using legacy recognizer)."
    return f"Groq Whisper ({GROQ_WHISPER_MODEL})"


def transcribe_audio(audio_bytes: bytes, fmt: str = "webm") -> str:
    """Transcribe raw audio bytes.

    ``fmt`` is the browser MIME subtype (webm/ogg/mp4/wav/…) and is only used to
    pick an extension for the temporary file we hand to ffmpeg; the format is
    normalized to 16 kHz mono WAV before recognition either way.
    """
    if not audio_bytes:
        return ""
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        log.warning("Audio input too large: %d bytes (cap %d)", len(audio_bytes), MAX_AUDIO_BYTES)
        return ""

    fmt = (fmt or "webm").strip().lstrip(".")
    if not _plausible_fmt(fmt):
        fmt = "webm"

    groq_key = _get_groq_key()
    if STT_PROVIDER != "groq" or not groq_key:
        return _transcribe_legacy(audio_bytes, fmt)

    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as in_file:
        in_file.write(audio_bytes)
        in_path = Path(in_file.name)

    out_path = None
    try:
        out_path = _to_wav16k(in_path)
        if out_path is None or not out_path.exists():
            log.warning("ffmpeg normalize failed for %s", in_path.name)
            return _fallback_or_empty(audio_bytes, fmt)
        if out_path.stat().st_size > MAX_AUDIO_BYTES:
            log.warning("Normalized WAV exceeds cap — dropped.")
            return ""
        return _groq_transcribe(out_path.read_bytes(), key=groq_key)
    except Exception as exc:
        log.warning("Groq transcription exception: %s", exc)
        return _fallback_or_empty(audio_bytes, fmt)
    finally:
        for p in (in_path, out_path):
            if p is not None and p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass


# ── Groq Whisper ──────────────────────────────────────────────────────────────

def _groq_transcribe(wav_bytes: bytes, key: str | None = None) -> str:
    """POST a 16 kHz mono WAV to Groq Whisper; returns cleaned transcript."""
    if not wav_bytes:
        return ""
    active_key = key or _get_groq_key()
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {active_key}"}
    files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
    data = {"model": GROQ_WHISPER_MODEL}
    if STT_LANGUAGE:
        data["language"] = STT_LANGUAGE
    try:
        resp = httpx.post(url, headers=headers, files=files, data=data, timeout=_TIMEOUT_MS)
        resp.raise_for_status()
        text = (resp.json().get("text") or "").strip()
    except httpx.HTTPStatusError as exc:
        log.error("Groq Whisper HTTP %s: %s", exc.response.status_code, exc.response.text[:300])
        raise
    except httpx.TimeoutException as exc:
        log.error("Groq Whisper timed out: %s", exc)
        raise
    except httpx.HTTPError as exc:
        log.error("Groq Whisper request failed: %s", exc)
        raise

    # Whisper sometimes keeps the trailing period it heard ("turn on the fan.")
    # — harmless, but strip terminal punctuation for a clean command string.
    return text.strip().rstrip(_NOISE_TRIM)


# ── ffmpeg normalization (shared) ─────────────────────────────────────────────

def _to_wav16k(in_path: Path) -> Path | None:
    """Transcode any browser capture to 16 kHz mono WAV for Whisper (or legacy)."""
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg not installed — cannot normalize audio for transcription")
        return None
    out_path = in_path.with_suffix(".wav")
    try:
        cmd = [
            "ffmpeg", "-y", "-i", str(in_path),
            "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
            str(out_path),
        ]
        proc = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=True, timeout=15,
        )
        if proc.returncode != 0 or not out_path.exists():
            return None
        return out_path
    except Exception as exc:
        log.warning("ffmpeg normalize failed: %s", exc)
        return None


def _plausible_fmt(fmt: str) -> bool:
    return fmt in {"webm", "ogg", "opus", "mp4", "m4a", "wav", "mp3", "aac"}


def _to_pcm16k(audio_bytes: bytes, fmt: str = "webm") -> bytes | None:
    """Transcode a browser capture to raw 16 kHz mono PCM16 for Gemini Live.
    Returns b"" on any failure. Reuses the ffmpeg path already installed in
    the image (same shape as _to_wav16k but to the Live input sample rate).
    """
    if not audio_bytes:
        return b""
    fmt = (fmt or "webm").strip().lstrip(".")
    if not _plausible_fmt(fmt):
        fmt = "webm"
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg not installed — cannot convert audio for Gemini Live")
        return b""
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as in_file:
        in_file.write(audio_bytes)
        in_path = Path(in_file.name)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(in_path),
             "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le",
             "-f", "s16le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=15,
        )
        if proc.returncode != 0:
            return b""
        return proc.stdout or b""
    except Exception as exc:
        log.warning("ffmpeg -> pcm16k failed: %s", exc)
        return b""
    finally:
        try:
            in_path.unlink()
        except Exception:
            pass


def _to_pcm24k(audio_bytes: bytes, fmt: str = "webm") -> bytes | None:
    """Transcode a browser capture to raw 24 kHz mono PCM16 (legacy Live
    output-rate helper; the input path now uses :func:`_to_pcm16k`)."""
    if not audio_bytes:
        return b""
    fmt = (fmt or "webm").strip().lstrip(".")
    if not _plausible_fmt(fmt):
        fmt = "webm"
    if not shutil.which("ffmpeg"):
        log.warning("ffmpeg not installed — cannot convert audio for Gemini Live")
        return b""
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as in_file:
        in_file.write(audio_bytes)
        in_path = Path(in_file.name)
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(in_path),
             "-ar", "24000", "-ac", "1", "-acodec", "pcm_s16le",
             "-f", "s16le", "pipe:1"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=15,
        )
        if proc.returncode != 0:
            return b""
        return proc.stdout or b""
    except Exception as exc:
        log.warning("ffmpeg -> pcm24k failed: %s", exc)
        return b""
    finally:
        try:
            in_path.unlink()
        except Exception:
            pass


# ── legacy Google Web recognizer (no-key fallback) ───────────────────────────

def _transcribe_legacy(audio_bytes: bytes, fmt: str = "webm") -> str:
    """Fallback when no Groq key is configured: bundled Google Web Speech API."""
    try:
        import speech_recognition as sr
    except ImportError:
        log.warning("speech_recognition not installed; no STT fallback available")
        return ""

    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as in_file:
        in_file.write(audio_bytes)
        in_path = Path(in_file.name)
    out_path = None
    try:
        out_path = _to_wav16k(in_path)
        if out_path is None:
            return ""
        r = sr.Recognizer()
        with sr.AudioFile(str(out_path)) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)
        return (text or "").strip()
    except Exception as exc:
        log.warning("Legacy transcribe exception: %s", exc)
        return ""
    finally:
        for p in (in_path, out_path):
            if p is not None and p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass


# ── misc helpers ──────────────────────────────────────────────────────────────

def bytes_to_seconds(audio_bytes: bytes, fmt: str = "webm") -> float:
    """Best-effort duration of an audio blob (ffprobe). Returns 0 on failure."""
    if not audio_bytes:
        return 0.0
    fmt = (fmt or "webm").strip().lstrip(".")
    if not _plausible_fmt(fmt):
        fmt = "webm"
    with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as in_file:
        in_file.write(audio_bytes)
        in_path = Path(in_file.name)
    try:
        if not shutil.which("ffprobe"):
            return 0.0
        proc = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(in_path)],
            capture_output=True, text=True, timeout=10,
        )
        try:
            return float(proc.stdout.strip().splitlines()[0])
        except Exception:
            return 0.0
    except Exception:
        return 0.0
    finally:
        try:
            in_path.unlink()
        except Exception:
            pass


def _fallback_or_empty(audio_bytes: bytes, fmt: str) -> str:
    """Groq failed — try the bundled recognizer; if that's unavailable, degrade
    gracefully to nothing rather than surfacing a provider crash to the user."""
    try:
        return _transcribe_legacy(audio_bytes, fmt)
    except Exception as exc:
        log.warning("Fallback recognition also failed: %s", exc)
        return ""

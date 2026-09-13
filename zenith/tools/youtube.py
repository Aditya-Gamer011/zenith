"""YouTube transcript → clean text for summarization.

Primary: youtube_transcript_api (extracts captions directly, no video download).
Fallback: yt-dlp's --skip-download + --write-auto-sub when captions are missing.
Both run off the event loop (network I/O) with hard timeouts.
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys

log = logging.getLogger("zenith.youtube")

_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})"
)


def extract_id(url: str) -> str:
    """Pull the 11-char video id from a YouTube URL, or bail."""
    if not url:
        return ""
    m = _ID_RE.search(url)
    if m:
        return m.group(1)
    # A bare id (already pasted)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url.strip()):
        return url.strip()
    return ""


def _clean(segments: list[str]) -> str:
    """Flatten transcript segments into readable paragraphs."""
    chunks: list[str] = []
    buf: list[str] = []
    for seg in segments:
        buf.append(seg.strip())
        if len(" ".join(buf)) > 420:
            chunks.append(" ".join(buf))
            buf = []
    if buf:
        chunks.append(" ".join(buf))
    return "\n\n".join(chunks)[:6000]


async def _transcript_yt_api(video_id: str) -> str | None:
    """Try youtube_transcript_api (needs SSL + the package)."""
    def _sync() -> str | None:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            # Prefer manual captions; fall back to auto-generated.
            try:
                fetched = api.fetch(video_id)
            except Exception:
                fetched = api.fetch(video_id, languages=["en"])
            text = " ".join(s.text for s in fetched)
            return _clean([t for t in re.split(r"(?<=[.!?])\s", text) if t.strip()]) or None
        except Exception as exc:
            log.debug("youtube_transcript_api failed: %s", exc)
            return None

    try:
        return await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(None, _sync),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        return None


async def _transcript_yt_dlp(video_id: str) -> str | None:
    """Fallback: yt-dlp --skip-download --write-auto-sub to stdout JSON."""
    def _sync() -> str | None:
        try:
            import json as _json
            from pathlib import Path

            out_path = Path("/tmp") / f"yt_{video_id}.json"
            cmd = [
                sys.executable, "-m", "yt_dlp",
                "--skip-download", "--write-auto-sub",
                "--write-subs", "--sub-format", "json3",
                "--sub-langs", "en.*",
                "--print", "after_move:filepath",
                "--no-warnings", "-o", str(out_path),
                f"https://www.youtube.com/watch?v={video_id}",
            ]
            proc = subprocess_run(cmd, timeout=120)
            if proc.returncode != 0 or not out_path.exists():
                return None
            data = _json.loads(out_path.read_text(errors="replace"))
            # json3 shape: {"events":[{"segs":[{"utf8":"..."}]}]}
            segs = []
            for ev in data.get("events", []):
                for s in (ev.get("segs") or []):
                    segs.append(s.get("utf8", ""))
            out_path.unlink(missing_ok=True)
            text = "".join(segs)
            if not text.strip() or "transcript" not in text.lower() and len(text) < 40:
                return None
            return _clean([t for t in text.split("\n") if t.strip()]) or None
        except Exception as exc:
            log.debug("yt-dlp fallback failed: %s", exc)
            return None

    try:
        return await asyncio.wait_for(
            asyncio.get_running_loop().run_in_executor(None, _sync),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        return None


# Thin wrapper so the executor path is obvious + testable.
def subprocess_run(cmd, timeout: int = 120):
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


async def youtube_transcript(url: str = "") -> str:
    """Fetch a YouTube video's transcript (captions) as clean text.

    Returns a short summary header + the transcript (trimmed to ~6k chars),
    or a clear error. Uses captions only — never downloads the video.
    """
    video_id = extract_id(url)
    if not video_id:
        return ("[youtube] Couldn't find a video id in that URL. "
                "Pass a full youtube.com/watch?v=… / youtu.be/… / shorts link.")

    transcript = await _transcript_yt_api(video_id)
    if not transcript:
        transcript = await _transcript_yt_dlp(video_id)
    if not transcript:
        return ("[youtube] No transcript available for that video (no captions "
                "and auto-subs weren't fetchable). Try another video.")

    # Short intro so the model knows what it's looking at.
    return (f"Transcript for YouTube video {video_id}:\n\n{transcript}")


async def youtube_search(query: str = "") -> str:
    """Snippet-only YouTube search for titles/URLs (no key required)."""
    import urllib.parse
    import urllib.request
    import json

    if not query.strip():
        return "[youtube] Provide a query."
    try:
        url = ("https://www.youtube.com/results?search_query="
               + urllib.parse.quote(query))
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ZenithBot/1.0)",
        })
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode(errors="replace")
        # videoRenderer keys carry the watch url + title; extract best-effort.
        items = []
        for m in re.finditer(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"[^}]*?"title":\{"runs":\[\{"text":"([^"]{0,80})', html):
            vid, title = m.group(1), m.group(2)
            items.append(f"https://youtu.be/{vid} — {title}")
            if len(items) >= 6:
                break
        return "\n".join(items) if items else "[youtube] No results parsed."
    except Exception as exc:
        return f"[youtube] search failed: {exc}"
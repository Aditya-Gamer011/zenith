"""Zenith Media Studio — professional multimedia processing, audio/video editing,
speech synthesis, YouTube/web media ingestion, image collages, memes, and color palettes.

Equips Zenith's Creative & Media Studio agent with high-performance studio tools:
1. Audio/Video Editing (FFmpeg & FFprobe):
   - Transcode/convert formats (mp4, mkv, webm, avi, mp3, wav, flac, aac, ogg, gif).
   - Trim/cut media clips with millisecond precision.
   - Extract audio from video streams.
   - Extract high-resolution video frames/thumbnails.
   - Merge audio soundtracks/voiceovers with video.
   - Smart media compression for size limits (Discord, email, web).
2. Audio & Neural Speech Synthesis (Edge TTS):
   - Realistic multi-voice studio speech synthesis across global accents.
   - Speed/rate control and instant web playback URLs.
3. Web & YouTube Media Ingestion (yt-dlp):
   - Fast extraction of clean MP3 audio from YouTube, SoundCloud, Twitter/X, and web URLs.
   - Video downloading with resolution capping.
   - Remote media metadata extraction (title, channel, duration, chapters, views).
4. Visual Design & Image Studio (Pillow):
   - Aesthetic photo collage and grid generation.
   - Meme generator with classic outlined Impact typography.
   - Dominant color palette extraction with visual hex swatches.
   - Animated GIF generator from image sequences.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import settings

log = logging.getLogger("zenith.media_studio")

_UPLOADS_DIR = settings.static_dir / "uploads"
_TMP_DIR = Path("/tmp/zenith-files")


def _ensure_media_dirs() -> None:
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _TMP_DIR.mkdir(parents=True, exist_ok=True)


def _resolve_input_path(file_path: str) -> Path:
    """Resolve input media file from absolute, workspace, or uploads paths."""
    _ensure_media_dirs()
    p = Path(file_path).expanduser()
    if p.is_file():
        return p.resolve()

    # Check relative to active workspace
    if settings.workspace_dir and (settings.workspace_dir / p).is_file():
        return (settings.workspace_dir / p).resolve()

    # Check uploads directory
    if (_UPLOADS_DIR / p.name).is_file():
        return (_UPLOADS_DIR / p.name).resolve()

    # Check tmp directory
    if (_TMP_DIR / p.name).is_file():
        return (_TMP_DIR / p.name).resolve()

    return p.resolve()


def _get_web_url(path: Path) -> str:
    """Convert an output file path to a relative URL for frontend rendering."""
    try:
        rel = path.relative_to(settings.static_dir)
        return f"/static/{rel.as_posix()}"
    except Exception:
        if "uploads" in str(path):
            return f"/static/uploads/{path.name}"
        return f"/static/uploads/{path.name}"


# ─── 1. FFprobe & Media Metadata Inspection ──────────────────────────────────
async def media_info(file_path: str) -> str:
    """Inspect comprehensive audio, video, or image metadata using ffprobe.
    
    Returns duration, resolution, codecs, bitrates, sample rates, channels, and tags.
    """
    p = _resolve_input_path(file_path)
    if not p.is_file():
        return f"[media_info] File not found: {file_path}"

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # Fallback to file size and extension
        size_mb = p.stat().st_size / (1024 * 1024)
        return f"📁 **File**: `{p.name}`\n  - Size: {size_mb:.2f} MB\n  - Path: `{p}`\n  *(ffprobe not available)*"

    cmd = [
        ffprobe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(p),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        data = json.loads(stdout.decode(errors="replace"))
    except Exception as exc:
        return f"[media_info error]: {exc}"

    fmt = data.get("format", {})
    streams = data.get("streams", [])

    duration_sec = float(fmt.get("duration", 0))
    size_bytes = int(fmt.get("size", p.stat().st_size))
    size_mb = size_bytes / (1024 * 1024)
    bitrate_kbps = int(fmt.get("bit_rate", 0)) // 1000 if fmt.get("bit_rate") else 0
    fmt_name = fmt.get("format_long_name", fmt.get("format_name", p.suffix.lstrip(".").upper()))

    mins, secs = divmod(int(duration_sec), 60)
    hours, mins = divmod(mins, 60)
    dur_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

    lines = [
        f"🎬 **Media Metadata**: `{p.name}`",
        f"  - **Container**: {fmt_name}",
        f"  - **Duration**: {dur_str} ({duration_sec:.2f}s)",
        f"  - **File Size**: {size_mb:.2f} MB ({size_bytes:,} bytes)",
    ]
    if bitrate_kbps:
        lines.append(f"  - **Overall Bitrate**: {bitrate_kbps} kbps")

    for idx, s in enumerate(streams):
        stype = s.get("codec_type", "unknown")
        codec = s.get("codec_long_name", s.get("codec_name", "unknown"))
        if stype == "video":
            w = s.get("width", 0)
            h = s.get("height", 0)
            fps_str = s.get("r_frame_rate", "0/0")
            fps = eval(fps_str) if "/" in fps_str and not fps_str.startswith("0/") else 0
            lines.append(
                f"  - **Stream {idx} (Video)**: {codec}\n"
                f"    Resolution: {w}x{h} | FPS: {fps:.2f} | PixFmt: {s.get('pix_fmt', 'unknown')}"
            )
        elif stype == "audio":
            sr = s.get("sample_rate", "unknown")
            ch = s.get("channels", "unknown")
            ch_layout = s.get("channel_layout", "stereo")
            lines.append(
                f"  - **Stream {idx} (Audio)**: {codec}\n"
                f"    Sample Rate: {sr} Hz | Channels: {ch} ({ch_layout})"
            )

    return "\n".join(lines)


# ─── 2. Audio/Video Editing & Transcoding (FFmpeg) ───────────────────────────
async def convert_media(
    input_path: str,
    output_format: str = "mp3",
    quality: str = "high",
    output_filename: str = "",
) -> str:
    """Convert/transcode audio or video between formats (mp4, mp3, wav, aac, flac, webm, mkv, gif)."""
    _ensure_media_dirs()
    src = _resolve_input_path(input_path)
    if not src.is_file():
        return f"[convert_media] Input file not found: {input_path}"

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "[convert_media] ffmpeg binary is not installed on the host system."

    ext = output_format.lower().lstrip(".")
    ts = int(time.time())
    out_name = output_filename or f"conv_{src.stem}_{ts}.{ext}"
    out_path = _UPLOADS_DIR / out_name

    cmd = [ffmpeg, "-y", "-i", str(src)]

    # Preset configurations
    if ext == "mp3":
        b = "320k" if quality == "high" else "192k" if quality == "medium" else "128k"
        cmd.extend(["-vn", "-acodec", "libmp3lame", "-b:a", b])
    elif ext == "wav":
        cmd.extend(["-vn", "-acodec", "pcm_s16le"])
    elif ext == "aac":
        cmd.extend(["-vn", "-acodec", "aac", "-b:a", "256k"])
    elif ext == "flac":
        cmd.extend(["-vn", "-acodec", "flac"])
    elif ext == "mp4":
        crf = "18" if quality == "high" else "23" if quality == "medium" else "28"
        cmd.extend(["-c:v", "libx264", "-crf", crf, "-preset", "fast", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"])
    elif ext == "webm":
        cmd.extend(["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus"])
    elif ext == "gif":
        cmd.extend(["-vf", "fps=15,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse", "-loop", "0"])

    cmd.append(str(out_path))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            return f"[convert_media error]: FFmpeg exited with code {proc.returncode}:\n{stderr.decode(errors='replace')[-500:]}"

        web_url = _get_web_url(out_path)
        size_kb = out_path.stat().st_size / 1024
        return (
            f"✅ **Media Converted Successfully**:\n"
            f"  - **Output**: `{out_path.name}` ({size_kb:.1f} KB)\n"
            f"  - **Format**: `{ext.upper()}`\n"
            f"  - **Path**: `{out_path}`\n"
            f"  - **Web URL**: [{out_path.name}]({web_url})"
        )
    except Exception as exc:
        return f"[convert_media error]: {exc}"


async def trim_media(
    input_path: str,
    start_time: str,
    duration: str = "",
    end_time: str = "",
    output_filename: str = "",
) -> str:
    """Trim an audio or video clip with exact start time and duration/end time.
    
    Times can be specified in seconds (e.g. "45") or HH:MM:SS format (e.g. "00:01:30").
    """
    _ensure_media_dirs()
    src = _resolve_input_path(input_path)
    if not src.is_file():
        return f"[trim_media] Input file not found: {input_path}"

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "[trim_media] ffmpeg binary is not installed on the host system."

    ext = src.suffix.lstrip(".").lower() or "mp4"
    ts = int(time.time())
    out_name = output_filename or f"trimmed_{src.stem}_{ts}.{ext}"
    out_path = _UPLOADS_DIR / out_name

    cmd = [ffmpeg, "-y", "-ss", str(start_time), "-i", str(src)]

    if duration:
        cmd.extend(["-t", str(duration)])
    elif end_time:
        cmd.extend(["-to", str(end_time)])

    # Use re-encode for frame-accurate cuts
    cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-avoid_negative_ts", "1", str(out_path)])

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            # Fallback to copy codec
            fallback_cmd = [ffmpeg, "-y", "-ss", str(start_time), "-i", str(src)]
            if duration: fallback_cmd.extend(["-t", str(duration)])
            elif end_time: fallback_cmd.extend(["-to", str(end_time)])
            fallback_cmd.extend(["-c", "copy", str(out_path)])
            fb_proc = await asyncio.create_subprocess_exec(*fallback_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await fb_proc.communicate()
            if fb_proc.returncode != 0:
                return f"[trim_media error]: {stderr.decode(errors='replace')[-400:]}"

        web_url = _get_web_url(out_path)
        size_kb = out_path.stat().st_size / 1024
        return (
            f"✂️ **Media Trimmed Successfully**:\n"
            f"  - **Output**: `{out_path.name}` ({size_kb:.1f} KB)\n"
            f"  - **Trim Range**: Start at `{start_time}` (Duration: `{duration or end_time}`)\n"
            f"  - **Web URL**: [{out_path.name}]({web_url})"
        )
    except Exception as exc:
        return f"[trim_media error]: {exc}"


async def extract_frames(
    video_path: str,
    timestamp: str = "00:00:01",
    count: int = 1,
    output_format: str = "jpg",
) -> str:
    """Extract one or more high-resolution snapshot frames from a video at given timestamp."""
    _ensure_media_dirs()
    src = _resolve_input_path(video_path)
    if not src.is_file():
        return f"[extract_frames] Video file not found: {video_path}"

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "[extract_frames] ffmpeg binary is not installed on the host system."

    ext = output_format.lower().lstrip(".")
    ts = int(time.time())
    out_name = f"frame_{src.stem}_{ts}.{ext}"
    out_path = _UPLOADS_DIR / out_name

    cmd = [
        ffmpeg, "-y",
        "-ss", str(timestamp),
        "-i", str(src),
        "-frames:v", str(count),
        "-q:v", "2",
        str(out_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode != 0 or not out_path.is_file():
            return f"[extract_frames error]: Could not extract frame at {timestamp}."

        web_url = _get_web_url(out_path)
        return (
            f"📸 **Video Frame Captured** (`{timestamp}`):\n"
            f"  - **Image**: `{out_path.name}`\n"
            f"  - **Preview**:\n"
            f"  ![Captured Frame]({web_url})"
        )
    except Exception as exc:
        return f"[extract_frames error]: {exc}"


async def merge_audio_video(
    video_path: str,
    audio_path: str,
    output_filename: str = "",
    replace_audio: bool = True,
) -> str:
    """Merge an audio track (e.g. voiceover, background music) into a video file."""
    _ensure_media_dirs()
    v_src = _resolve_input_path(video_path)
    a_src = _resolve_input_path(audio_path)

    if not v_src.is_file():
        return f"[merge_audio_video] Video file not found: {video_path}"
    if not a_src.is_file():
        return f"[merge_audio_video] Audio file not found: {audio_path}"

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "[merge_audio_video] ffmpeg binary is not installed."

    ts = int(time.time())
    out_name = output_filename or f"merged_{v_src.stem}_{ts}.mp4"
    out_path = _UPLOADS_DIR / out_name

    if replace_audio:
        cmd = [
            ffmpeg, "-y",
            "-i", str(v_src),
            "-i", str(a_src),
            "-c:v", "copy",
            "-c:a", "aac",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(out_path),
        ]
    else:
        # Mix original audio + new audio
        cmd = [
            ffmpeg, "-y",
            "-i", str(v_src),
            "-i", str(a_src),
            "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest[a]",
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            str(out_path),
        ]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()
        if proc.returncode != 0:
            return f"[merge_audio_video error]: Failed to merge audio and video."

        web_url = _get_web_url(out_path)
        return (
            f"🎬 **Audio & Video Merged Successfully**:\n"
            f"  - **Video Output**: `{out_path.name}`\n"
            f"  - **Web Link**: [{out_path.name}]({web_url})"
        )
    except Exception as exc:
        return f"[merge_audio_video error]: {exc}"


async def compress_media(
    input_path: str,
    target_size_mb: float = 10.0,
    output_filename: str = "",
) -> str:
    """Smart compress video or audio to fit under target size limit (e.g. for Discord 25MB or email)."""
    _ensure_media_dirs()
    src = _resolve_input_path(input_path)
    if not src.is_file():
        return f"[compress_media] File not found: {input_path}"

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return "[compress_media] ffmpeg / ffprobe binaries are required."

    # Get duration
    try:
        probe_proc = await asyncio.create_subprocess_exec(
            ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(src),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await probe_proc.communicate()
        duration = float(stdout.decode().strip() or 10.0)
    except Exception:
        duration = 10.0

    # Calculate target bitrate
    target_total_bits = target_size_mb * 8 * 1024 * 1024 * 0.9  # 10% safety margin
    total_bitrate = int(target_total_bits / max(duration, 1.0))
    audio_bitrate = min(128_000, int(total_bitrate * 0.15))
    video_bitrate = max(100_000, total_bitrate - audio_bitrate)

    ext = src.suffix.lstrip(".").lower() or "mp4"
    ts = int(time.time())
    out_name = output_filename or f"compressed_{src.stem}_{ts}.{ext}"
    out_path = _UPLOADS_DIR / out_name

    cmd = [
        ffmpeg, "-y",
        "-i", str(src),
        "-b:v", f"{video_bitrate // 1000}k",
        "-b:a", f"{audio_bitrate // 1000}k",
        "-preset", "medium",
        str(out_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.communicate()
        if proc.returncode != 0:
            return f"[compress_media error]: Compression failed."

        orig_mb = src.stat().st_size / (1024 * 1024)
        comp_mb = out_path.stat().st_size / (1024 * 1024)
        savings = (1 - (comp_mb / orig_mb)) * 100 if orig_mb > 0 else 0
        web_url = _get_web_url(out_path)

        return (
            f"🗜️ **Media Compressed Successfully**:\n"
            f"  - **Original Size**: {orig_mb:.2f} MB $\to$ **New Size**: {comp_mb:.2f} MB ({savings:.1f}% reduction)\n"
            f"  - **Web Link**: [{out_path.name}]({web_url})"
        )
    except Exception as exc:
        return f"[compress_media error]: {exc}"


# ─── 3. Audio & Neural Speech Synthesis (Edge TTS) ───────────────────────────
VOICE_MAP = {
    "female_us": "en-US-JennyNeural",
    "male_us": "en-US-GuyNeural",
    "female_in": "en-IN-NeerjaNeural",
    "male_in": "en-IN-PrabhatNeural",
    "female_uk": "en-GB-SoniaNeural",
    "male_uk": "en-GB-RyanNeural",
    "female_au": "en-AU-NatNeural",
    "spanish": "es-ES-ElviraNeural",
    "french": "fr-FR-DeniseNeural",
    "german": "de-DE-KatjaNeural",
    "japanese": "ja-JP-NanamiNeural",
}


async def text_to_speech(
    text: str,
    voice: str = "en-US-JennyNeural",
    speed: str = "+0%",
    output_filename: str = "",
) -> str:
    """Generate human-quality neural speech audio (MP3) from text using Edge TTS.
    
    Supports natural voices (Jenny, Guy, Neerja, Sonia, Ryan) and speed adjustments (e.g. '+10%', '-15%').
    """
    if not text or not text.strip():
        return "[text_to_speech] Text cannot be empty."

    _ensure_media_dirs()
    selected_voice = VOICE_MAP.get(voice.lower().strip(), voice)

    ts = int(time.time())
    out_name = output_filename or f"speech_{ts}.mp3"
    if not out_name.endswith(".mp3"):
        out_name += ".mp3"
    out_path = _UPLOADS_DIR / out_name

    try:
        import edge_tts

        communicate = edge_tts.Communicate(text.strip(), selected_voice, rate=speed)
        await communicate.save(str(out_path))

        size_kb = out_path.stat().st_size / 1024
        web_url = _get_web_url(out_path)

        return (
            f"🎙️ **Neural Speech Audio Generated**:\n"
            f"  - **File**: `{out_path.name}` ({size_kb:.1f} KB)\n"
            f"  - **Voice**: `{selected_voice}` (Rate: `{speed}`)\n"
            f"  - **Player Link**: [Listen / Download ({out_path.name})]({web_url})\n"
            f"  - **Path**: `{out_path}`"
        )
    except Exception as exc:
        return f"[text_to_speech error]: {exc}"


# ─── 4. Web & YouTube Media Ingestion (yt-dlp) ───────────────────────────────
async def download_web_audio(url: str, output_filename: str = "") -> str:
    """Download clean MP3 audio stream from YouTube, SoundCloud, Twitter/X, or any web video URL."""
    if not url or not url.strip():
        return "[download_web_audio] URL required."

    _ensure_media_dirs()
    ts = int(time.time())

    def _sync_dl() -> dict[str, Any]:
        import yt_dlp

        out_template = str(_UPLOADS_DIR / (output_filename or f"audio_{ts}_%(id)s.%(ext)s"))
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url.strip(), download=True)
            return info

    try:
        info = await asyncio.to_thread(_sync_dl)
        title = info.get("title", "Audio Track")
        uploader = info.get("uploader", "Unknown Artist")
        duration = info.get("duration", 0)
        mins, secs = divmod(int(duration), 60)

        # Find downloaded file
        mp3_files = sorted(_UPLOADS_DIR.glob(f"*{info.get('id', ts)}*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
        if mp3_files:
            target_file = mp3_files[0]
            web_url = _get_web_url(target_file)
            size_mb = target_file.stat().st_size / (1024 * 1024)
            return (
                f"🎵 **Audio Downloaded Successfully**:\n"
                f"  - **Title**: {title}\n"
                f"  - **Artist/Channel**: {uploader}\n"
                f"  - **Duration**: {mins:02d}:{secs:02d} | **Size**: {size_mb:.2f} MB\n"
                f"  - **Audio Link**: [{target_file.name}]({web_url})\n"
                f"  - **Local Path**: `{target_file}`"
            )
        return f"✅ Audio downloaded from {url}."
    except Exception as exc:
        return f"[download_web_audio error]: {exc}"


async def download_web_video(
    url: str,
    max_resolution: str = "1080",
    output_filename: str = "",
) -> str:
    """Download video from YouTube or supported web platforms capped at target resolution (e.g. 720, 1080)."""
    if not url or not url.strip():
        return "[download_web_video] URL required."

    _ensure_media_dirs()
    ts = int(time.time())

    def _sync_dl() -> dict[str, Any]:
        import yt_dlp

        out_template = str(_UPLOADS_DIR / (output_filename or f"video_{ts}_%(id)s.%(ext)s"))
        ydl_opts = {
            "format": f"bestvideo[height<={max_resolution}]+bestaudio/best[height<={max_resolution}]/best",
            "outtmpl": out_template,
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url.strip(), download=True)
            return info

    try:
        info = await asyncio.to_thread(_sync_dl)
        title = info.get("title", "Video")
        duration = info.get("duration", 0)
        mins, secs = divmod(int(duration), 60)

        vid_files = sorted(_UPLOADS_DIR.glob(f"*{info.get('id', ts)}*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        if vid_files:
            target_file = vid_files[0]
            web_url = _get_web_url(target_file)
            size_mb = target_file.stat().st_size / (1024 * 1024)
            return (
                f"🎥 **Video Downloaded Successfully**:\n"
                f"  - **Title**: {title}\n"
                f"  - **Duration**: {mins:02d}:{secs:02d} | **Size**: {size_mb:.2f} MB\n"
                f"  - **Video Link**: [{target_file.name}]({web_url})\n"
                f"  - **Local Path**: `{target_file}`"
            )
        return f"✅ Video downloaded from {url}."
    except Exception as exc:
        return f"[download_web_video error]: {exc}"


async def web_media_info(url: str) -> str:
    """Inspect web video/audio metadata (title, uploader, views, duration, chapters) without downloading."""
    if not url or not url.strip():
        return "[web_media_info] URL required."

    def _sync_probe() -> dict[str, Any]:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": False}) as ydl:
            return ydl.extract_info(url.strip(), download=False)

    try:
        info = await asyncio.to_thread(_sync_probe)
        title = info.get("title", "Unknown Title")
        uploader = info.get("uploader", "Unknown")
        views = info.get("view_count", 0)
        duration = info.get("duration", 0)
        upload_date = info.get("upload_date", "")
        desc = info.get("description", "")[:400]
        thumbnail = info.get("thumbnail", "")

        mins, secs = divmod(int(duration), 60)
        hours, mins = divmod(mins, 60)
        dur_str = f"{hours:02d}:{mins:02d}:{secs:02d}" if hours else f"{mins:02d}:{secs:02d}"

        out = [
            f"📺 **Media Information**: [{title}]({url})",
            f"  - **Channel / Creator**: {uploader}",
            f"  - **Duration**: {dur_str}",
            f"  - **View Count**: {views:,}" if views else "",
            f"  - **Upload Date**: {upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}" if len(upload_date) == 8 else "",
        ]
        if thumbnail:
            out.append(f"\n![Thumbnail]({thumbnail})")
        if desc:
            out.append(f"\n**Description Snippet**:\n> {desc.replace(chr(10), ' ')}")

        return "\n".join(l for l in out if l)
    except Exception as exc:
        return f"[web_media_info error]: {exc}"


# ─── 5. Advanced Visual Design, Collages & Memes (Pillow) ────────────────────
async def create_collage(
    image_paths: list[str],
    layout: str = "auto",
    spacing: int = 12,
    bg_color: str = "#181825",
    output_filename: str = "",
) -> str:
    """Combine 2 to 9 images into an aesthetic photo grid / collage with spacing and clean borders."""
    if not image_paths or len(image_paths) < 2:
        return "[create_collage] At least 2 image paths required."

    _ensure_media_dirs()

    def _sync_make() -> Path:
        from PIL import Image, ImageOps

        resolved: list[Image.Image] = []
        for ip in image_paths[:9]:
            rp = _resolve_input_path(ip)
            if rp.is_file():
                try:
                    img = Image.open(rp).convert("RGB")
                    resolved.append(img)
                except Exception:
                    pass

        if len(resolved) < 2:
            raise ValueError("Could not load at least 2 valid images.")

        n = len(resolved)
        # Determine grid cols and rows
        if layout == "1x2" or (layout == "auto" and n == 2):
            cols, rows = 2, 1
        elif layout == "1x3" or (layout == "auto" and n == 3):
            cols, rows = 3, 1
        elif layout == "2x2" or (layout == "auto" and n == 4):
            cols, rows = 2, 2
        elif n in (5, 6):
            cols, rows = 3, 2
        else:
            cols, rows = 3, 3

        cell_w, cell_h = 600, 600
        canvas_w = (cell_w * cols) + (spacing * (cols + 1))
        canvas_h = (cell_h * rows) + (spacing * (rows + 1))

        # Parse bg color
        canvas = Image.new("RGB", (canvas_w, canvas_h), bg_color)

        for idx, img in enumerate(resolved[:cols * rows]):
            r = idx // cols
            c = idx % cols
            x = spacing + c * (cell_w + spacing)
            y = spacing + r * (cell_h + spacing)

            fitted = ImageOps.fit(img, (cell_w, cell_h), Image.Resampling.LANCZOS)
            canvas.paste(fitted, (x, y))

        ts = int(time.time())
        out_name = output_filename or f"collage_{ts}.jpg"
        out_path = _UPLOADS_DIR / out_name
        canvas.save(out_path, quality=92)
        return out_path

    try:
        out_path = await asyncio.to_thread(_sync_make)
        web_url = _get_web_url(out_path)
        return (
            f"🖼️ **Photo Collage Created**:\n"
            f"  - **Saved**: `{out_path.name}` ({out_path.stat().st_size / 1024:.1f} KB)\n"
            f"  - **Preview**:\n"
            f"  ![Collage: {out_path.name}]({web_url})"
        )
    except Exception as exc:
        return f"[create_collage error]: {exc}"


async def generate_meme(
    image_path: str,
    top_text: str = "",
    bottom_text: str = "",
    style: str = "impact",
    output_filename: str = "",
) -> str:
    """Generate a meme with bold outlined text (Impact style) over an image."""
    src = _resolve_input_path(image_path)
    if not src.is_file():
        return f"[generate_meme] Image file not found: {image_path}"

    _ensure_media_dirs()

    def _sync_meme() -> Path:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(src).convert("RGB")
        w, h = img.size

        # Fit image within reasonable bounds (e.g. max 1200px)
        if w > 1200 or h > 1200:
            img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)
            w, h = img.size

        draw = ImageDraw.Draw(img)

        # Estimate font size
        font_size = max(24, int(w / 14))
        try:
            # Try system fonts
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except Exception:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()

        def _draw_text_with_outline(text: str, y_pos: int):
            if not text: return
            text = text.upper()
            bbox = draw.textbbox((0, 0), text, font=font)
            text_w = bbox[2] - bbox[0]
            x_pos = (w - text_w) // 2

            # Black outline
            thickness = max(2, font_size // 15)
            for dx in range(-thickness, thickness + 1):
                for dy in range(-thickness, thickness + 1):
                    draw.text((x_pos + dx, y_pos + dy), text, font=font, fill="black")
            # White text
            draw.text((x_pos, y_pos), text, font=font, fill="white")

        if top_text:
            _draw_text_with_outline(top_text, int(h * 0.04))

        if bottom_text:
            bbox = draw.textbbox((0, 0), bottom_text.upper(), font=font)
            text_h = bbox[3] - bbox[1]
            _draw_text_with_outline(bottom_text, int(h - text_h - h * 0.06))

        ts = int(time.time())
        out_name = output_filename or f"meme_{ts}.jpg"
        out_path = _UPLOADS_DIR / out_name
        img.save(out_path, quality=90)
        return out_path

    try:
        out_path = await asyncio.to_thread(_sync_meme)
        web_url = _get_web_url(out_path)
        return (
            f"🎭 **Meme Generated**:\n"
            f"  - **File**: `{out_path.name}`\n"
            f"  - **Preview**:\n"
            f"  ![Meme]({web_url})"
        )
    except Exception as exc:
        return f"[generate_meme error]: {exc}"


async def extract_palette(image_path: str, num_colors: int = 5) -> str:
    """Extract dominant color palette from an image and format as visual hex swatches."""
    src = _resolve_input_path(image_path)
    if not src.is_file():
        return f"[extract_palette] Image file not found: {image_path}"

    def _sync_palette() -> list[tuple[str, tuple[int, int, int]]]:
        from PIL import Image

        img = Image.open(src).convert("RGB")
        img.thumbnail((200, 200))
        quantized = img.quantize(colors=max(2, min(num_colors, 10)))
        palette = quantized.getpalette()[:num_colors * 3]

        colors = []
        for i in range(0, len(palette), 3):
            r, g, b = palette[i], palette[i + 1], palette[i + 2]
            hex_code = f"#{r:02x}{g:02x}{b:02x}".upper()
            colors.append((hex_code, (r, g, b)))
        return colors

    try:
        colors = await asyncio.to_thread(_sync_palette)
        lines = [
            f"🎨 **Extracted Color Palette**: `{src.name}`",
            "| Swatch | Hex Code | RGB Values |",
            "| :---: | :--- | :--- |",
        ]
        for hex_code, (r, g, b) in colors:
            swatch = f"`{hex_code}`"
            lines.append(f"| █ | **{hex_code}** | `rgb({r}, {g}, {b})` |")

        return "\n".join(lines)
    except Exception as exc:
        return f"[extract_palette error]: {exc}"


async def create_animated_gif(
    image_paths: list[str],
    duration_ms: int = 400,
    loop: int = 0,
    output_filename: str = "",
) -> str:
    """Create an animated GIF from a sequence of images."""
    if not image_paths or len(image_paths) < 2:
        return "[create_animated_gif] At least 2 images required."

    _ensure_media_dirs()

    def _sync_gif() -> Path:
        from PIL import Image

        frames: list[Image.Image] = []
        for p in image_paths:
            rp = _resolve_input_path(p)
            if rp.is_file():
                frames.append(Image.open(rp).convert("RGBA"))

        if len(frames) < 2:
            raise ValueError("Could not load at least 2 frames.")

        base_size = frames[0].size
        norm_frames = [f.resize(base_size, Image.Resampling.LANCZOS) for f in frames]

        ts = int(time.time())
        out_name = output_filename or f"animated_{ts}.gif"
        out_path = _UPLOADS_DIR / out_name

        norm_frames[0].save(
            out_path,
            save_all=True,
            append_images=norm_frames[1:],
            duration=duration_ms,
            loop=loop,
            optimize=True,
        )
        return out_path

    try:
        out_path = await asyncio.to_thread(_sync_gif)
        web_url = _get_web_url(out_path)
        return (
            f"🎞️ **Animated GIF Created**:\n"
            f"  - **File**: `{out_path.name}` ({out_path.stat().st_size / 1024:.1f} KB)\n"
            f"  - **Duration**: {duration_ms}ms per frame ({len(image_paths)} frames)\n"
            f"  - **Preview**:\n"
            f"  ![Animated GIF]({web_url})"
        )
    except Exception as exc:
        return f"[create_animated_gif error]: {exc}"


def _get_font(size: int):
    """Attempt to load a crisp TrueType system font, falling back to default."""
    from PIL import ImageFont
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for c in candidates:
        if Path(c).is_file():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


# ─── 5. Advanced Multimedia Engineering & Production Depth ───────────────────
async def create_audiogram(
    audio_path: str,
    background_image: str = "",
    title: str = "",
    artist_or_host: str = "",
    wave_color: str = "#00f0ff",
    style: str = "wave",
    output_filename: str = "",
) -> str:
    """Generate an MP4 video audiogram with an animated waveform visualizer from an audio file.

    Parameters:
    - audio_path: Input audio file (.mp3, .wav, .m4a, .aac, .ogg, .flac).
    - background_image: Optional background image path. If not provided, a sleek studio gradient is generated.
    - title: Optional title text displayed on the audiogram card.
    - artist_or_host: Optional host/speaker or episode subtitle text.
    - wave_color: Waveform color in hex format (e.g. '#00f0ff', '#38bdf8', '#10b981', '#f43f5e').
    - style: Waveform visualization mode: 'wave' (smooth line), 'p2p' (point-to-point / bars), or 'cline' (centered line).
    - output_filename: Optional custom output mp4 filename.
    """
    _ensure_media_dirs()
    src = _resolve_input_path(audio_path)
    if not src.is_file():
        return f"[create_audiogram] Audio file not found: {audio_path}"

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "[create_audiogram] FFmpeg is not installed on the system."

    def _sync_audiogram_bg() -> Path:
        from PIL import Image, ImageDraw, ImageOps
        w, h = 1280, 720
        bg_card_path = _TMP_DIR / f"audiogram_bg_{uuid.uuid4().hex[:8]}.png"

        if background_image:
            bg_in = _resolve_input_path(background_image)
            if bg_in.is_file():
                try:
                    img = Image.open(bg_in).convert("RGBA")
                    img = ImageOps.fit(img, (w, h), method=Image.Resampling.LANCZOS)
                    # Add dark translucent scrim
                    scrim = Image.new("RGBA", (w, h), (10, 15, 26, 190))
                    canvas = Image.alpha_composite(img, scrim).convert("RGB")
                except Exception:
                    canvas = Image.new("RGB", (w, h), (15, 23, 42))
            else:
                canvas = Image.new("RGB", (w, h), (15, 23, 42))
        else:
            canvas = Image.new("RGB", (w, h), (11, 15, 25))
            draw = ImageDraw.Draw(canvas)
            # Modern high-tech studio container
            draw.rectangle([24, 24, w - 24, h - 24], outline=(30, 41, 59), width=2)
            draw.rectangle([48, 48, w - 48, h - 48], fill=(19, 26, 42), outline=(51, 65, 85), width=2)

        draw = ImageDraw.Draw(canvas)
        font_title = _get_font(38)
        font_sub = _get_font(22)
        font_badge = _get_font(18)

        # Header badge
        draw.rounded_rectangle([72, 70, 310, 105], radius=6, fill=(30, 41, 59))
        draw.text((86, 77), "🎙️ ZENITH AUDIO STUDIO", fill=(56, 189, 248), font=font_badge)

        # Title
        disp_title = title or src.stem.replace("_", " ").title()
        if len(disp_title) > 55:
            disp_title = disp_title[:52] + "..."
        draw.text((72, 130), disp_title, fill=(248, 250, 252), font=font_title)

        # Subtitle / Artist
        disp_artist = artist_or_host or "Official Audio Stream • High Fidelity Studio Output"
        draw.text((72, 185), disp_artist, fill=(148, 163, 184), font=font_sub)

        # Waveform container box
        draw.rounded_rectangle([68, 430, w - 68, 630], radius=12, fill=(10, 15, 26), outline=(30, 41, 59), width=2)
        # Decorative audio channel tags
        draw.text((88, 445), "STEREO L/R • 44.1kHz • 24-BIT MASTER", fill=(100, 116, 139), font=font_badge)

        canvas.save(bg_card_path, format="PNG")
        return bg_card_path

    try:
        bg_path = await asyncio.to_thread(_sync_audiogram_bg)

        # Map style to showwaves mode
        mode_map = {
            "wave": "line",
            "p2p": "p2p",
            "cline": "cline",
        }
        mode = mode_map.get(style.lower(), "line")

        # Convert hex color e.g. #00f0ff -> 0x00f0ff
        clean_color = wave_color.strip()
        if clean_color.startswith("#"):
            clean_color = "0x" + clean_color[1:]
        elif not clean_color.startswith("0x"):
            clean_color = "0x" + clean_color

        ts = int(time.time())
        out_name = output_filename or f"audiogram_{src.stem}_{ts}.mp4"
        if not out_name.endswith(".mp4"):
            out_name += ".mp4"
        out_path = _UPLOADS_DIR / out_name

        cmd = [
            ffmpeg, "-y",
            "-loop", "1",
            "-framerate", "25",
            "-i", str(bg_path),
            "-i", str(src),
            "-filter_complex",
            f"[1:a]showwaves=s=1100x140:mode={mode}:colors={clean_color}:rate=25,format=rgba[wave];[0:v][wave]overlay=(W-w)/2:470:shortest=1[outv]",
            "-map", "[outv]",
            "-map", "1:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(out_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        # Cleanup temporary background
        try:
            bg_path.unlink(missing_ok=True)
        except Exception:
            pass

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[-500:]
            return f"[create_audiogram error]: FFmpeg failed (code {proc.returncode}):\n{err}"

        web_url = _get_web_url(out_path)
        size_mb = out_path.stat().st_size / (1024 * 1024)

        return (
            f"🎬 **Audiogram Video Generated Successfully**:\n"
            f"  - **Title**: {title or src.stem}\n"
            f"  - **Audio Source**: `{src.name}`\n"
            f"  - **Waveform Style**: `{style}` ({wave_color})\n"
            f"  - **Video Specs**: 1280x720 H.264 / AAC 192k ({size_mb:.2f} MB)\n"
            f"  - **Direct Video URL**: [{out_path.name}]({web_url})\n\n"
            f'<video controls width="640" src="{web_url}"></video>'
        )
    except Exception as exc:
        return f"[create_audiogram error]: {exc}"


async def create_slideshow(
    image_paths: list[str],
    audio_path: str = "",
    duration_per_slide: float = 3.0,
    resolution: str = "1280x720",
    output_filename: str = "",
) -> str:
    """Compile a sequence of images into a high-definition MP4 video slideshow with optional audio.

    Parameters:
    - image_paths: List of image file paths (minimum 2 images).
    - audio_path: Optional background music or voiceover narration file.
    - duration_per_slide: Duration in seconds for each slide (default: 3.0).
    - resolution: Video dimensions, e.g. '1280x720' (horizontal) or '1080x1920' (vertical reel/shorts).
    - output_filename: Optional output mp4 filename.
    """
    if not image_paths or len(image_paths) < 2:
        return "[create_slideshow] At least 2 images required to build a slideshow."

    _ensure_media_dirs()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "[create_slideshow] FFmpeg is not installed on the system."

    try:
        rw, rh = map(int, resolution.lower().split("x"))
    except Exception:
        rw, rh = 1280, 720

    uid = uuid.uuid4().hex[:8]
    temp_frames: list[Path] = []

    def _prepare_frames() -> list[Path]:
        from PIL import Image, ImageOps
        prepared = []
        for i, p in enumerate(image_paths):
            rp = _resolve_input_path(p)
            if rp.is_file():
                try:
                    img = Image.open(rp).convert("RGB")
                    norm = ImageOps.fit(img, (rw, rh), method=Image.Resampling.LANCZOS)
                    frame_path = _TMP_DIR / f"slide_{uid}_{i:03d}.png"
                    norm.save(frame_path, format="PNG")
                    prepared.append(frame_path)
                except Exception as e:
                    log.warning(f"Could not load slide image {p}: {e}")
        return prepared

    try:
        temp_frames = await asyncio.to_thread(_prepare_frames)
        if len(temp_frames) < 2:
            return "[create_slideshow] Failed to process at least 2 valid slide images."

        # Write concat list
        concat_file = _TMP_DIR / f"slides_concat_{uid}.txt"
        lines = []
        for frame in temp_frames:
            lines.append(f"file '{frame.resolve().as_posix()}'")
            lines.append(f"duration {duration_per_slide:.2f}")
        # Repeat last slide to ensure final slide is rendered for full duration
        lines.append(f"file '{temp_frames[-1].resolve().as_posix()}'")
        concat_file.write_text("\n".join(lines), encoding="utf-8")

        ts = int(time.time())
        out_name = output_filename or f"slideshow_{ts}.mp4"
        if not out_name.endswith(".mp4"):
            out_name += ".mp4"
        out_path = _UPLOADS_DIR / out_name

        cmd = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
        ]

        has_audio = False
        if audio_path:
            audio_src = _resolve_input_path(audio_path)
            if audio_src.is_file():
                cmd.extend(["-i", str(audio_src)])
                has_audio = True

        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-r", "25",
        ])

        if has_audio:
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
            ])

        cmd.append(str(out_path))

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        # Clean up frames
        for f in temp_frames:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            concat_file.unlink(missing_ok=True)
        except Exception:
            pass

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[-500:]
            return f"[create_slideshow error]: FFmpeg failed (code {proc.returncode}):\n{err}"

        total_duration = len(temp_frames) * duration_per_slide
        size_mb = out_path.stat().st_size / (1024 * 1024)
        web_url = _get_web_url(out_path)

        return (
            f"🎞️ **Slideshow Video Created Successfully**:\n"
            f"  - **Slides**: {len(temp_frames)} images\n"
            f"  - **Resolution**: {rw}x{rh}\n"
            f"  - **Total Duration**: ~{total_duration:.1f}s ({duration_per_slide}s/slide)\n"
            f"  - **Audio Track**: {'Included' if has_audio else 'None (Silent)'}\n"
            f"  - **File**: `{out_path.name}` ({size_mb:.2f} MB)\n"
            f"  - **Direct Video URL**: [{out_path.name}]({web_url})\n\n"
            f'<video controls width="640" src="{web_url}"></video>'
        )
    except Exception as exc:
        return f"[create_slideshow error]: {exc}"


async def normalize_audio(
    input_path: str,
    target_lufs: float = -14.0,
    output_filename: str = "",
) -> str:
    """Standardize audio loudness to broadcast / streaming standards using FFmpeg EBU R128 loudnorm.

    Standards:
    - YouTube / Spotify / Podcasts: -14.0 LUFS
    - Apple Podcasts: -16.0 LUFS
    - Broadcast / EBU R128: -23.0 LUFS

    Parameters:
    - input_path: Input audio or video file.
    - target_lufs: Integrated loudness target in LUFS (default: -14.0).
    - output_filename: Optional output filename.
    """
    _ensure_media_dirs()
    src = _resolve_input_path(input_path)
    if not src.is_file():
        return f"[normalize_audio] File not found: {input_path}"

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "[normalize_audio] FFmpeg is not installed on the system."

    ts = int(time.time())
    ext = src.suffix.lower()
    is_video = ext in {".mp4", ".mkv", ".webm", ".mov", ".avi"}

    if output_filename:
        out_name = output_filename
    else:
        out_ext = ext if ext in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".mp4", ".mkv"} else ".mp3"
        out_name = f"{src.stem}_norm{out_ext}"

    out_path = _UPLOADS_DIR / out_name

    filter_str = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json"

    cmd = [ffmpeg, "-y", "-i", str(src)]
    if is_video:
        cmd.extend(["-c:v", "copy", "-af", filter_str, "-c:a", "aac", "-b:a", "192k"])
    else:
        cmd.extend(["-af", filter_str])
        if out_path.suffix.lower() == ".mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "256k"])

    cmd.append(str(out_path))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode(errors="replace")[-500:]
        return f"[normalize_audio error]: FFmpeg failed:\n{err}"

    stderr_str = stderr.decode(errors="replace")
    stats_match = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", stderr_str, re.DOTALL)
    stats: dict[str, str] = {}
    if stats_match:
        try:
            stats = json.loads(stats_match.group(0))
        except Exception:
            pass

    size_mb = out_path.stat().st_size / (1024 * 1024)
    web_url = _get_web_url(out_path)

    out = [
        f"🔊 **Audio Loudness Normalized (EBU R128)**:",
        f"  - **Input File**: `{src.name}`",
        f"  - **Target Loudness**: `{target_lufs} LUFS`",
        f"  - **Output File**: `{out_path.name}` ({size_mb:.2f} MB)",
        f"  - **Playback URL**: [{out_path.name}]({web_url})",
    ]

    if stats:
        out.extend([
            "  - **Loudness Analysis**:",
            f"    • Input Integrated Loudness: `{stats.get('input_i', 'N/A')} LUFS`",
            f"    • Output Integrated Loudness: `{stats.get('output_i', 'N/A')} LUFS`",
            f"    • Input True Peak: `{stats.get('input_tp', 'N/A')} dBFS`",
            f"    • Output True Peak: `{stats.get('output_tp', 'N/A')} dBFS`",
            f"    • Target Offset: `{stats.get('target_offset', 'N/A')} dB`",
        ])

    if not is_video:
        out.append(f'\n<audio controls src="{web_url}"></audio>')
    else:
        out.append(f'\n<video controls width="640" src="{web_url}"></video>')

    return "\n".join(out)


async def overlay_media(
    base_media_path: str,
    overlay_path: str,
    position: str = "bottom_right",
    scale: float = 0.2,
    margin: int = 24,
    output_filename: str = "",
) -> str:
    """Overlay a watermark logo, badge, or picture-in-picture media on top of a video or image.

    Parameters:
    - base_media_path: Primary video (.mp4, .mkv, .mov) or image (.png, .jpg) file.
    - overlay_path: Watermark logo or overlay image/video file.
    - position: 'bottom_right', 'bottom_left', 'top_right', 'top_left', or 'center'.
    - scale: Scale of overlay relative to base media width (e.g. 0.2 = 20% width).
    - margin: Margin in pixels from frame border (default: 24).
    - output_filename: Optional output filename.
    """
    _ensure_media_dirs()
    base = _resolve_input_path(base_media_path)
    ovrl = _resolve_input_path(overlay_path)

    if not base.is_file():
        return f"[overlay_media] Base media file not found: {base_media_path}"
    if not ovrl.is_file():
        return f"[overlay_media] Overlay file not found: {overlay_path}"

    ffmpeg = shutil.which("ffmpeg")
    ts = int(time.time())
    is_base_video = base.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".avi"}

    # Handle image-on-image using Pillow
    if not is_base_video and base.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        def _sync_overlay_img() -> Path:
            from PIL import Image
            b_img = Image.open(base).convert("RGBA")
            o_img = Image.open(ovrl).convert("RGBA")

            target_w = max(20, int(b_img.width * scale))
            target_h = max(20, int(o_img.height * (target_w / o_img.width)))
            o_img = o_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            pos = position.lower()
            if pos == "bottom_right":
                xy = (b_img.width - target_w - margin, b_img.height - target_h - margin)
            elif pos == "bottom_left":
                xy = (margin, b_img.height - target_h - margin)
            elif pos == "top_right":
                xy = (b_img.width - target_w - margin, margin)
            elif pos == "top_left":
                xy = (margin, margin)
            else:  # center
                xy = ((b_img.width - target_w) // 2, (b_img.height - target_h) // 2)

            b_img.alpha_composite(o_img, xy)
            out_ext = ".png" if base.suffix.lower() == ".png" else ".jpg"
            out_name = output_filename or f"{base.stem}_watermarked_{ts}{out_ext}"
            out_p = _UPLOADS_DIR / out_name
            if out_ext == ".png":
                b_img.save(out_p, format="PNG")
            else:
                b_img.convert("RGB").save(out_p, format="JPEG", quality=95)
            return out_p

        try:
            out_path = await asyncio.to_thread(_sync_overlay_img)
            web_url = _get_web_url(out_path)
            return (
                f"🖼️ **Image Watermark / Overlay Complete**:\n"
                f"  - **Base Image**: `{base.name}`\n"
                f"  - **Overlay**: `{ovrl.name}` ({int(scale * 100)}% scale, {position})\n"
                f"  - **Result**: [{out_path.name}]({web_url})\n\n"
                f"  ![Watermarked Image]({web_url})"
            )
        except Exception as exc:
            return f"[overlay_media image error]: {exc}"

    # Handle Video Overlay via FFmpeg
    if not ffmpeg:
        return "[overlay_media] FFmpeg is required for video overlay."

    pos = position.lower()
    if pos == "bottom_right":
        overlay_coord = f"W-w-{margin}:H-h-{margin}"
    elif pos == "bottom_left":
        overlay_coord = f"{margin}:H-h-{margin}"
    elif pos == "top_right":
        overlay_coord = f"W-w-{margin}:{margin}"
    elif pos == "top_left":
        overlay_coord = f"{margin}:{margin}"
    else:  # center
        overlay_coord = "(W-w)/2:(H-h)/2"

    out_name = output_filename or f"{base.stem}_overlaid_{ts}.mp4"
    if not out_name.endswith(".mp4"):
        out_name += ".mp4"
    out_path = _UPLOADS_DIR / out_name

    filter_complex = f"[1:v]scale=iw*{scale}:-1[ovrl];[0:v][ovrl]overlay={overlay_coord}[outv]"

    cmd = [
        ffmpeg, "-y",
        "-i", str(base),
        "-i", str(ovrl),
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        str(out_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[-500:]
            return f"[overlay_media video error]: FFmpeg failed:\n{err}"

        web_url = _get_web_url(out_path)
        size_mb = out_path.stat().st_size / (1024 * 1024)

        return (
            f"🎬 **Video Overlay Applied Successfully**:\n"
            f"  - **Base Video**: `{base.name}`\n"
            f"  - **Overlay Element**: `{ovrl.name}` ({position}, {int(scale * 100)}% width)\n"
            f"  - **Output File**: `{out_path.name}` ({size_mb:.2f} MB)\n"
            f"  - **Direct Video URL**: [{out_path.name}]({web_url})\n\n"
            f'<video controls width="640" src="{web_url}"></video>'
        )
    except Exception as exc:
        return f"[overlay_media video error]: {exc}"


async def apply_image_filter(
    image_path: str,
    filter_name: str = "cinematic",
    intensity: float = 1.0,
    output_filename: str = "",
) -> str:
    """Apply professional color grading and photographic aesthetic filters to images.

    Filter presets:
    - 'cinematic': Hollywood teal-and-orange grade with cool shadows and warm highlights.
    - 'vintage': Nostalgic warm 70s film aesthetic with soft sepia contrast.
    - 'noir': High-contrast black & white with dramatic shadows.
    - 'cyberpunk': Electric neon magenta and cyan futuristic palette.
    - 'vibrant': Rich saturation boost with crisp contrast and pop.
    - 'dramatic': Punchy contrast with deep rich blacks and vibrant highlights.

    Parameters:
    - image_path: Input image file (.jpg, .png, .webp).
    - filter_name: Preset filter name.
    - intensity: Filter intensity multiplier (0.2 to 2.0, default: 1.0).
    - output_filename: Optional output filename.
    """
    _ensure_media_dirs()
    src = _resolve_input_path(image_path)
    if not src.is_file():
        return f"[apply_image_filter] Image file not found: {image_path}"

    intensity = max(0.2, min(intensity, 2.0))

    def _sync_filter() -> Path:
        import numpy as np
        from PIL import Image, ImageEnhance, ImageOps

        img = Image.open(src).convert("RGB")
        arr = np.array(img, dtype=np.float32)

        r = arr[:, :, 0]
        g = arr[:, :, 1]
        b = arr[:, :, 2]
        lum = (r * 0.299 + g * 0.587 + b * 0.114) / 255.0
        shadow_mask = 1.0 - lum
        highlight_mask = lum

        fn = filter_name.lower().strip()

        if fn == "cinematic":
            r = r + (highlight_mask * 30.0 - shadow_mask * 20.0) * intensity
            g = g + (highlight_mask * 10.0 + shadow_mask * 15.0) * intensity
            b = b + (shadow_mask * 35.0 - highlight_mask * 25.0) * intensity
            out_arr = np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.uint8)
            res = Image.fromarray(out_arr)
            res = ImageEnhance.Contrast(res).enhance(1.0 + 0.25 * intensity)

        elif fn in {"vintage", "sepia", "film"}:
            r = r + (35.0 * intensity)
            g = g + (15.0 * intensity)
            b = b - (20.0 * intensity)
            out_arr = np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.uint8)
            res = Image.fromarray(out_arr)
            res = ImageEnhance.Color(res).enhance(max(0.4, 1.0 - 0.3 * intensity))
            res = ImageEnhance.Contrast(res).enhance(0.95)

        elif fn in {"noir", "bw", "monochrome"}:
            bw = ImageOps.grayscale(img)
            res = ImageEnhance.Contrast(bw).enhance(1.0 + 0.6 * intensity).convert("RGB")

        elif fn == "cyberpunk":
            r = r + (highlight_mask * 45.0 - shadow_mask * 20.0) * intensity
            g = g + (shadow_mask * 25.0 - highlight_mask * 15.0) * intensity
            b = b + (highlight_mask * 35.0 + shadow_mask * 40.0) * intensity
            out_arr = np.clip(np.stack([r, g, b], axis=-1), 0, 255).astype(np.uint8)
            res = Image.fromarray(out_arr)
            res = ImageEnhance.Color(res).enhance(1.0 + 0.5 * intensity)
            res = ImageEnhance.Contrast(res).enhance(1.0 + 0.3 * intensity)

        elif fn == "vibrant":
            res = ImageEnhance.Color(img).enhance(1.0 + 0.6 * intensity)
            res = ImageEnhance.Contrast(res).enhance(1.0 + 0.2 * intensity)

        elif fn == "dramatic":
            res = ImageEnhance.Contrast(img).enhance(1.0 + 0.5 * intensity)
            res = ImageEnhance.Color(res).enhance(1.0 + 0.15 * intensity)
            res = ImageEnhance.Brightness(res).enhance(0.95)

        else:
            res = ImageEnhance.Contrast(img).enhance(1.1)

        ts = int(time.time())
        ext = src.suffix.lower() if src.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} else ".jpg"
        out_name = output_filename or f"{src.stem}_{fn}_{ts}{ext}"
        out_p = _UPLOADS_DIR / out_name

        if ext == ".png":
            res.save(out_p, format="PNG")
        else:
            res.save(out_p, format="JPEG", quality=95)
        return out_p

    try:
        out_path = await asyncio.to_thread(_sync_filter)
        web_url = _get_web_url(out_path)
        return (
            f"🎨 **Photo Aesthetic Filter Applied**:\n"
            f"  - **Input Image**: `{src.name}`\n"
            f"  - **Preset**: `{filter_name}` (Intensity: `{intensity:.1f}x`)\n"
            f"  - **Output File**: `{out_path.name}` ({out_path.stat().st_size / 1024:.1f} KB)\n"
            f"  - **Result Preview**:\n"
            f"  ![Filtered Image]({web_url})"
        )
    except Exception as exc:
        return f"[apply_image_filter error]: {exc}"


async def burn_subtitles(
    video_path: str,
    subtitles_srt_or_path: str,
    font_size: int = 22,
    primary_color: str = "&H00FFFFFF",
    output_filename: str = "",
) -> str:
    """Burn hardcoded subtitles into a video file for social media reels, TikTok, Shorts, and presentations.

    Parameters:
    - video_path: Input video file (.mp4, .mkv, .mov).
    - subtitles_srt_or_path: Path to an .srt file OR raw SRT formatted text.
    - font_size: Subtitle font size (default: 22).
    - primary_color: Subtitle text color in ASS hex format (default: '&H00FFFFFF' for white, '&H0000FFFF' for yellow).
    - output_filename: Optional output mp4 filename.
    """
    _ensure_media_dirs()
    src = _resolve_input_path(video_path)
    if not src.is_file():
        return f"[burn_subtitles] Video file not found: {video_path}"

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "[burn_subtitles] FFmpeg is not installed on the system."

    is_raw_text = "-->" in subtitles_srt_or_path
    uid = uuid.uuid4().hex[:8]
    temp_srt: Optional[Path] = None

    if is_raw_text:
        temp_srt = _TMP_DIR / f"subtitles_{uid}.srt"
        temp_srt.write_text(subtitles_srt_or_path.strip(), encoding="utf-8")
        srt_file = temp_srt
    else:
        srt_file = _resolve_input_path(subtitles_srt_or_path)
        if not srt_file.is_file():
            return f"[burn_subtitles] Subtitle file not found: {subtitles_srt_or_path}"

    ts = int(time.time())
    out_name = output_filename or f"{src.stem}_subbed_{ts}.mp4"
    if not out_name.endswith(".mp4"):
        out_name += ".mp4"
    out_path = _UPLOADS_DIR / out_name

    sub_path_escaped = str(srt_file.resolve()).replace(":", "\\:").replace("'", "\\'")

    style = f"FontSize={font_size},PrimaryColour={primary_color},OutlineColour=&H00000000,BorderStyle=1,Outline=2"
    filter_arg = f"subtitles={sub_path_escaped}:force_style='{style}'"

    cmd = [
        ffmpeg, "-y",
        "-i", str(src),
        "-vf", filter_arg,
        "-c:a", "copy",
        str(out_path),
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if temp_srt:
            try:
                temp_srt.unlink(missing_ok=True)
            except Exception:
                pass

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[-500:]
            return f"[burn_subtitles error]: FFmpeg failed:\n{err}"

        size_mb = out_path.stat().st_size / (1024 * 1024)
        web_url = _get_web_url(out_path)

        return (
            f"📝 **Subtitles Burned into Video Successfully**:\n"
            f"  - **Input Video**: `{src.name}`\n"
            f"  - **Subtitles**: `{srt_file.name}` (Font Size: {font_size})\n"
            f"  - **Output Video**: `{out_path.name}` ({size_mb:.2f} MB)\n"
            f"  - **Direct Video URL**: [{out_path.name}]({web_url})\n\n"
            f'<video controls width="640" src="{web_url}"></video>'
        )
    except Exception as exc:
        return f"[burn_subtitles error]: {exc}"


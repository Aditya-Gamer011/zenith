"""Tests for Zenith Media Studio — audio/video editing, speech synthesis,
YouTube/web media downloads, collages, memes, and color palettes.
"""
import asyncio
from pathlib import Path
import pytest
import tempfile
from PIL import Image

from zenith.core import tools as tool_reg
from zenith.agents.agent_service import AgentService, DEPARTMENTS
from zenith.tools.media_studio import (
    media_info,
    convert_media,
    trim_media,
    extract_frames,
    merge_audio_video,
    compress_media,
    text_to_speech,
    download_web_audio,
    web_media_info,
    create_collage,
    generate_meme,
    extract_palette,
    create_animated_gif,
    create_audiogram,
    create_slideshow,
    normalize_audio,
    overlay_media,
    apply_image_filter,
    burn_subtitles,
)


# ── 1. Neural Speech Synthesis ───────────────────────────────────────────────
@pytest.mark.anyio
async def test_text_to_speech():
    res = await text_to_speech(
        text="Zenith Media Studio neural voice synthesis active.",
        voice="en-US-JennyNeural",
        output_filename="test_speech.mp3",
    )
    assert "Neural Speech Audio Generated" in res
    assert "test_speech.mp3" in res
    assert "/static/uploads/" in res


# ── 2. FFprobe & Media Metadata ──────────────────────────────────────────────
@pytest.mark.anyio
async def test_media_info_and_ffprobe():
    # Generate a small audio file first
    tts_res = await text_to_speech("Audio test metadata", output_filename="info_test.mp3")
    assert "🎙️" in tts_res

    # Test media_info on generated file
    info = await media_info("info_test.mp3")
    assert "Media Metadata" in info or "Container" in info
    assert "Duration" in info


# ── 3. Media Transcoding & Trimming ──────────────────────────────────────────
@pytest.mark.anyio
async def test_convert_and_trim_media():
    # 1. Generate base audio
    await text_to_speech("Convert test audio sample", output_filename="base_audio.mp3")

    # 2. Transcode MP3 to WAV
    conv_res = await convert_media("base_audio.mp3", output_format="wav")
    assert "Media Converted Successfully" in conv_res
    assert "WAV" in conv_res or ".wav" in conv_res.lower()

    # 3. Trim audio
    trim_res = await trim_media("base_audio.mp3", start_time="0", duration="1")
    assert "Media Trimmed Successfully" in trim_res


# ── 4. Visual Studio: Collages, Memes & Palettes ─────────────────────────────
@pytest.mark.anyio
async def test_visual_design_tools():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        p1 = tmp_p / "img1.png"
        p2 = tmp_p / "img2.png"

        Image.new("RGB", (200, 200), "#3498db").save(p1)
        Image.new("RGB", (200, 200), "#e74c3c").save(p2)

        # 1. Test Collage
        col_res = await create_collage([str(p1), str(p2)], layout="1x2")
        assert "Photo Collage Created" in col_res
        assert "/static/uploads/" in col_res

        # 2. Test Meme
        meme_res = await generate_meme(str(p1), top_text="ZENITH", bottom_text="ONLINE")
        assert "Meme Generated" in meme_res
        assert "/static/uploads/" in meme_res

        # 3. Test Palette
        pal_res = await extract_palette(str(p1), num_colors=3)
        assert "Extracted Color Palette" in pal_res
        assert "#3498DB" in pal_res.upper() or "3498DB" in pal_res.upper()

        # 4. Test Animated GIF
        gif_res = await create_animated_gif([str(p1), str(p2)], duration_ms=200)
        assert "Animated GIF Created" in gif_res
        assert ".gif" in gif_res


# ── 5. Media Compression ─────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_compress_media():
    await text_to_speech("Compression test payload audio content", output_filename="comp_test.mp3")
    res = await compress_media("comp_test.mp3", target_size_mb=1.0)
    assert "Media Compressed Successfully" in res or "Web Link" in res


# ── 6. Advanced Audiograms & Animated Waveforms ──────────────────────────────
@pytest.mark.anyio
async def test_create_audiogram():
    # Generate short audio speech sample
    await text_to_speech("Welcome to the Zenith Podcast Episode One.", output_filename="podcast_sample.mp3")
    res = await create_audiogram(
        audio_path="podcast_sample.mp3",
        title="Zenith Multi-Agent Architecture",
        artist_or_host="Episode 1 • Zenith Labs",
        wave_color="#00f0ff",
        style="wave",
        output_filename="test_audiogram.mp4",
    )
    assert "Audiogram Video Generated Successfully" in res
    assert "test_audiogram.mp4" in res
    assert "/static/uploads/" in res


# ── 7. Slideshow Video Creation ──────────────────────────────────────────────
@pytest.mark.anyio
async def test_create_slideshow():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        s1 = tmp_p / "slide1.png"
        s2 = tmp_p / "slide2.png"
        Image.new("RGB", (640, 360), "#2c3e50").save(s1)
        Image.new("RGB", (640, 360), "#8e44ad").save(s2)

        res = await create_slideshow(
            image_paths=[str(s1), str(s2)],
            duration_per_slide=1.5,
            resolution="640x360",
            output_filename="test_slideshow.mp4",
        )
        assert "Slideshow Video Created Successfully" in res
        assert "test_slideshow.mp4" in res
        assert "2 images" in res


# ── 8. Audio Loudness Normalization (EBU R128) ────────────────────────────────
@pytest.mark.anyio
async def test_normalize_audio():
    await text_to_speech("Testing loudness normalization target.", output_filename="norm_sample.mp3")
    res = await normalize_audio("norm_sample.mp3", target_lufs=-14.0, output_filename="norm_out.mp3")
    assert "Audio Loudness Normalized" in res
    assert "norm_out.mp3" in res
    assert "LUFS" in res


# ── 9. Watermarking & Media Overlay ──────────────────────────────────────────
@pytest.mark.anyio
async def test_overlay_media():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        base = tmp_p / "base.png"
        logo = tmp_p / "logo.png"
        Image.new("RGB", (500, 300), "#34495e").save(base)
        Image.new("RGBA", (80, 80), (231, 76, 60, 200)).save(logo)

        res = await overlay_media(str(base), str(logo), position="bottom_right", scale=0.2)
        assert "Image Watermark / Overlay Complete" in res
        assert "/static/uploads/" in res


# ── 10. Photo Aesthetic Filters & Cinematic Grading ──────────────────────────
@pytest.mark.anyio
async def test_apply_image_filter():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_p = Path(tmp_dir)
        sample_img = tmp_p / "photo.png"
        Image.new("RGB", (300, 300), "#7f8c8d").save(sample_img)

        res = await apply_image_filter(str(sample_img), filter_name="cinematic", intensity=1.2)
        assert "Photo Aesthetic Filter Applied" in res
        assert "cinematic" in res


# ── 11. Subtitle Burning ─────────────────────────────────────────────────────
@pytest.mark.anyio
async def test_burn_subtitles():
    # Use the generated audiogram video
    srt = (
        "1\n"
        "00:00:00,000 --> 00:00:01,500\n"
        "Testing Subtitle Engine\n"
    )
    res = await burn_subtitles("test_audiogram.mp4", subtitles_srt_or_path=srt, font_size=20)
    assert "Subtitles Burned into Video Successfully" in res
    assert ".mp4" in res


# ── 12. Tool Registry & Creative / Media Department ──────────────────────────
def test_media_tools_registered_and_in_catalog():
    all_tools = set(tool_reg.TOOLS)
    expected = {
        "media_info", "convert_media", "trim_media", "extract_frames",
        "merge_audio_video", "compress_media", "text_to_speech",
        "download_web_audio", "download_web_video", "web_media_info",
        "create_collage", "generate_meme", "extract_palette",
        "create_animated_gif", "create_audiogram", "create_slideshow",
        "normalize_audio", "overlay_media", "apply_image_filter", "burn_subtitles",
    }
    for t in expected:
        assert t in all_tools, f"Missing tool: {t}"

    # Verify Creative/Media department catalog
    svc = AgentService()
    cat = svc.get_catalog("creative")
    cat_names = {t["function"]["name"] for t in cat}
    for t in expected:
        assert t in cat_names, f"Missing tool in creative department: {t}"

    # Verify 'media' alias resolves to creative
    assert svc.resolve_agent_key("media") == "creative"
    media_cat = svc.get_catalog("media")
    media_names = {t["function"]["name"] for t in media_cat}
    assert "text_to_speech" in media_names
    assert "convert_media" in media_names
    assert "create_audiogram" in media_names
    assert "normalize_audio" in media_names


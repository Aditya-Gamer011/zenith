"""PowerPoint Presentation (.pptx) Visual Engine for Zenith.

Implements a multi-primitive presentation generation architecture with Web Photo Integration:
  - Downloads and embeds real high-resolution web photos (Unsplash / Pexels / Pixabay / Wikimedia)
  - Generates matplotlib charts as embedded images for data visualization
  - Supports 10+ visual layout primitives (photo_hero, photo_story, hero_title, cards_grid,
    stat_hero, timeline, split_hero, comparison, quote, chapter_divider)
  - Executive Dark Mode color palette (#0B0F19 background, #1E293B cards, #8B5CF6 / #06B6D4 accents)
  - High-hierarchy typography, generous whitespace, rounded container shapes
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, List, Dict, Optional

import tempfile

log = logging.getLogger("zenith.tools.presentation")

OUT_DIR = Path(tempfile.gettempdir()) / "zenith-files"
OUT_DIR.mkdir(parents=True, exist_ok=True)
IMG_DIR = OUT_DIR / "images"
IMG_DIR.mkdir(parents=True, exist_ok=True)


# ── Color Palette Catalog ──────────────────────────────────────────────────
COLOR_PALETTES = {
    "dark": {
        "bg": (11, 15, 25),       # #0B0F19
        "card": (30, 41, 59),      # #1E293B
        "border": (51, 65, 85),   # #334155
        "title": (248, 250, 252), # #F8FAFC
        "muted": (148, 163, 184), # #94A3B8
        "accent1": (139, 92, 246),# #8B5CF6 (Purple)
        "accent2": (6, 182, 212),  # #06B6D4 (Cyan)
    },
    "cyberpunk_neon": {
        "bg": (8, 9, 12),         # #08090C
        "card": (18, 20, 28),     # #12141C
        "border": (42, 47, 69),   # #2A2F45
        "title": (255, 255, 255), # #FFFFFF
        "muted": (138, 149, 165), # #8A95A5
        "accent1": (0, 243, 255),  # #00F3FF (Neon Cyan)
        "accent2": (255, 0, 127), # #FF007F (Magenta)
    },
    "corporate_light": {
        "bg": (248, 250, 252),    # #F8FAFC
        "card": (255, 255, 255),  # #FFFFFF
        "border": (226, 232, 240),# #E2E8F0
        "title": (15, 23, 42),    # #0F172A
        "muted": (100, 116, 139), # #64748B
        "accent1": (30, 64, 175),  # #1E40AF (Royal Sapphire)
        "accent2": (2, 132, 199),  # #0284C7 (Sky Blue)
    },
    "emerald_forest": {
        "bg": (4, 30, 25),        # #041E19
        "card": (15, 52, 44),      # #0F342C
        "border": (30, 83, 71),   # #1E5347
        "title": (236, 253, 245), # #ECFDF5
        "muted": (167, 243, 208), # #A7F3D0
        "accent1": (16, 185, 129),# #10B981 (Emerald)
        "accent2": (20, 184, 166),# #14B8A6 (Teal)
    },
    "sunset_warm": {
        "bg": (28, 25, 23),       # #1C1917
        "card": (41, 37, 36),      # #292524
        "border": (68, 64, 60),   # #44403C
        "title": (250, 250, 249), # #FAFAF9
        "muted": (214, 211, 209), # #D6D3D1
        "accent1": (245, 158, 11),# #F59E0B (Amber Gold)
        "accent2": (225, 29, 72), # #E11D48 (Crimson Rose)
    },
    "midnight_violet": {
        "bg": (15, 12, 27),       # #0F0C1B
        "card": (29, 23, 53),      # #1D1735
        "border": (53, 43, 94),   # #352B5E
        "title": (245, 243, 255), # #F5F3FF
        "muted": (196, 181, 253), # #C4B5FD
        "accent1": (168, 85, 247),# #A855F7 (Bright Purple)
        "accent2": (236, 72, 153),# #EC4899 (Hot Pink)
    }
}
COLOR_PALETTES["executive_dark"] = COLOR_PALETTES["dark"]
COLOR_PALETTES["light"] = COLOR_PALETTES["corporate_light"]


PRESET_TEMPLATES = {
    "pitch_deck": [
        {"title": "The Executive Opportunity & Vision", "layout": "split_hero", "subtitle": "Addressing Unmet Industry Demand & Scale"},
        {"title": "Market Pain Points & Current Friction", "layout": "photo_hero", "image_query": "Global Business Corporate Meeting Executive", "bullets": ["Legacy infrastructure bottlenecking growth", "High operational overhead and compliance costs", "Fragmented user experience across legacy tools"]},
        {"title": "Core Solution & Key Platform Advantages", "layout": "cards_grid", "cards": [{"title": "Proprietary Tech", "points": ["AI-native automation", "Sub-millisecond processing"]}, {"title": "Scalable Model", "points": ["Zero-friction onboarding", "Enterprise security integration"]}]},
        {"title": "Financial Revenue Trajectory & ARR Scale", "layout": "chart_hero", "chart_type": "column", "labels": ["2023", "2024", "2025", "2026 (Est)"], "values": [12.5, 28.4, 55.0, 110.2], "series_name": "ARR Revenue ($M)", "bullets": ["110% YoY revenue acceleration", "Expanding net dollar retention across enterprise clients", "High-margin SaaS recurring subscription model"]},
        {"title": "Market Scale & Financial Projections", "layout": "stat_hero", "stats": [{"number": "$12.5B", "label": "TAM", "sub": "Total Addressable Market"}, {"number": "48%", "label": "YoY Growth", "sub": "Annual Expansion Rate"}, {"number": "85%", "label": "Gross Margin", "sub": "SaaS Unit Economics"}, {"number": "120%", "label": "NDR", "sub": "Net Dollar Retention"}]},
        {"title": "Product Architecture & Differentiation", "layout": "cards_grid", "cards": [{"title": "High Performance", "points": ["Distributed microservices", "Real-time sync engine"]}, {"title": "Enterprise Trust", "points": ["SOC2 Type II certified", "End-to-end encryption"]}]},
        {"title": "Strategic Execution Roadmap", "layout": "timeline", "steps": [{"title": "Q1 2026", "desc": "Platform v2.0 Release & Beta Rollout"}, {"title": "Q2 2026", "desc": "Enterprise API & Ecosystem Integration"}, {"title": "Q3 2026", "desc": "Global Expansion & North America Entry"}, {"title": "Q4 2026", "desc": "AI Automation Suite & Developer SDK"}]},
        {"title": "Leadership Team & Investment Summary", "layout": "split_hero", "subtitle": "Backed by World-Class Engineering & Domain Experts"}
    ],
    "tech_overview": [
        {"title": "System Architecture & Infrastructure", "layout": "photo_hero", "image_query": "Cloud Data Server Center Architecture", "bullets": ["Multi-region distributed cluster topology", "High-throughput message queues and event streaming", "Automated failover and disaster recovery"]},
        {"title": "Core Performance SLAs & Metrics", "layout": "stat_hero", "stats": [{"number": "99.99%", "label": "Uptime SLA", "sub": "High availability cluster"}, {"number": "< 8ms", "label": "P99 Latency", "sub": "Sub-millisecond API response"}, {"number": "50K+", "label": "RPS", "sub": "Requests Per Second Capacity"}, {"number": "100%", "label": "Data Integrity", "sub": "ACID Compliant Storage"}]},
        {"title": "System Throughput & Auto-Scaling Metrics", "layout": "chart_hero", "chart_type": "area", "labels": ["00:00", "06:00", "12:00", "18:00"], "values": [12000, 35000, 85000, 62000], "series_name": "Requests Per Second (RPS)", "bullets": ["Auto-scaling worker clusters handle traffic spikes effortlessly", "Sub-millisecond query routing across distributed edge nodes"]},
        {"title": "Key Infrastructure Components", "layout": "cards_grid", "cards": [{"title": "Compute Layer", "points": ["Async IO worker pools", "Stateless auto-scaling containers"]}, {"title": "Security & Auth", "points": ["Zero-trust network architecture", "Hardware Security Module (HSM) key management"]}]},
        {"title": "Data Pipeline & Stream Processing", "layout": "cards_grid", "cards": [{"title": "Ingestion Engine", "points": ["Kafka event bus streaming", "Schema validation at edge"]}, {"title": "Analytics Store", "points": ["Columnar database query engine", "Real-time aggregation dashboards"]}]},
        {"title": "CI/CD & Deployment Pipeline", "layout": "timeline", "steps": [{"title": "Commit", "desc": "Automated Linting & Unit Testing"}, {"title": "Build", "desc": "Container Image Scanning & Staging"}, {"title": "Deploy", "desc": "Canary Rollout & Automated Rollback"}, {"title": "Monitor", "desc": "Real-time Telemetry & APM Tracking"}]},
        {"title": "Strategic Technical Roadmap", "layout": "split_hero", "subtitle": "Pioneering Next-Gen Edge Compute & Autonomous Monitoring"}
    ]
}


def _apply_slide_transition(slide, transition_type: str = "fade"):
    """Inject OpenXML transition elements into python-pptx slide."""
    if not transition_type:
        return
    try:
        from pptx.oxml import parse_xml
        t_map = {
            "fade": '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:fade/></p:transition>',
            "push": '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:push dir="u"/></p:transition>',
            "wipe": '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:wipe dir="r"/></p:transition>',
            "zoom": '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:zoom/></p:transition>',
        }
        xml_str = t_map.get(transition_type.lower(), t_map["fade"])
        t_elem = parse_xml(xml_str)
        slide.element.append(t_elem)
    except Exception as exc:
        log.debug("Slide transition injection skipped: %s", exc)


def _ensure_valid_image(path_str: str | None) -> str | None:
    if not path_str or not os.path.exists(path_str):
        return None
    try:
        from PIL import Image
        with Image.open(path_str) as im:
            fmt = im.format
            if fmt in ("JPEG", "PNG", "BMP", "GIF"):
                return path_str
            rgb_im = im.convert("RGB")
            rgb_im.save(path_str, "JPEG")
            return path_str
    except Exception as exc:
        log.debug("Image validation/conversion failed for %s: %s", path_str, exc)
        try:
            os.remove(path_str)
        except Exception:
            pass
        return None


def _create_accent_graphic(query: str, save_path: Path, palette_bg=(11, 15, 25), accent_color=(139, 92, 246)) -> str:
    """Create a high-design 1280x720 abstract geometric graphic image for slides when web photo search is unavailable."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        import random
        img = Image.new("RGB", (1280, 720), color=palette_bg)
        draw = ImageDraw.Draw(img)

        # Background noise / gradient overlay
        for i in range(40):
            x = random.randint(0, 1280)
            y = random.randint(0, 720)
            r = random.randint(40, 200)
            alpha_color = tuple(min(255, c + random.randint(5, 25)) for c in palette_bg)
            draw.ellipse([x-r, y-r, x+r, y+r], fill=alpha_color)

        # Draw decorative glowing accent circles & grid lines
        draw.ellipse([-100, -100, 500, 500], fill=None, outline=accent_color, width=4)
        draw.ellipse([700, 200, 1400, 900], fill=None, outline=(6, 182, 212), width=3)
        draw.ellipse([400, -200, 900, 300], fill=None, outline=tuple(min(255, c+30) for c in accent_color), width=2)
        draw.rectangle([100, 100, 1180, 620], fill=None, outline=(51, 65, 85), width=2)

        # Add decorative accent bar
        draw.rectangle([140, 140, 160, 580], fill=accent_color)

        # Draw topic watermark text
        clean_text = query.replace("_", " ").title()[:35]
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        except Exception:
            font = ImageFont.load_default()
        draw.text((190, 320), clean_text, fill=(248, 250, 252), font=font)

        img.save(save_path, "JPEG", quality=90)
        return str(save_path)
    except Exception as exc:
        log.debug("Graphic generation error for '%s': %s", query, exc)
        return None


def _add_fitted_picture(slide, img_path: str, box_left: float, box_top: float, box_width: float, box_height: float, card_bg=(30, 41, 59), border_color=(51, 65, 85)):
    """Embed an image into a slide scaled & centered inside a target bounding box without distorting aspect ratio."""
    try:
        from pptx.util import Inches
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.dml.color import RGBColor
        from PIL import Image

        # Draw underlying frame card
        frame = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(box_left), Inches(box_top), Inches(box_width), Inches(box_height))
        frame.fill.solid()
        frame.fill.fore_color.rgb = RGBColor(*card_bg)
        frame.line.color.rgb = RGBColor(*border_color)

        with Image.open(img_path) as im:
            w, h = im.size

        if w <= 0 or h <= 0:
            return

        scale = min(box_width / float(w), box_height / float(h))
        render_w = float(w) * scale
        render_h = float(h) * scale

        pos_left = box_left + (box_width - render_w) / 2.0
        pos_top = box_top + (box_height - render_h) / 2.0

        slide.shapes.add_picture(
            img_path,
            Inches(pos_left),
            Inches(pos_top),
            width=Inches(render_w),
            height=Inches(render_h)
        )
    except Exception as exc:
        log.error("Failed to add fitted picture '%s': %s", img_path, exc)


def _generate_chart_image(
    chart_type: str,
    labels: list,
    values: list,
    series_name: str = "Data",
    title: str = "",
    palette_bg=(11, 15, 25),
    accent_color=(139, 92, 246),
    accent2_color=(6, 182, 212),
) -> str | None:
    """Generate a matplotlib chart as a high-DPI PNG image suitable for embedding in slides."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np

        bg_hex = "#{:02x}{:02x}{:02x}".format(*palette_bg)
        card_hex = "#{:02x}{:02x}{:02x}".format(*(min(255, c+20) for c in palette_bg))
        accent_hex = "#{:02x}{:02x}{:02x}".format(*accent_color)
        accent2_hex = "#{:02x}{:02x}{:02x}".format(*accent2_color)
        text_hex = "#F8FAFC"
        muted_hex = "#94A3B8"

        fig, ax = plt.subplots(figsize=(10, 6), dpi=150, facecolor=bg_hex)
        ax.set_facecolor(card_hex)

        clean_vals = []
        for v in values:
            try:
                clean_vals.append(float(v))
            except Exception:
                clean_vals.append(0.0)

        x = np.arange(len(labels))
        ct = chart_type.lower()

        if ct in ("bar", "column"):
            colors = [accent_hex if i % 2 == 0 else accent2_hex for i in range(len(clean_vals))]
            bars = ax.bar(x, clean_vals, color=colors, width=0.6, edgecolor='none', zorder=3)
            for bar, val in zip(bars, clean_vals):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(clean_vals)*0.02,
                        f'{val:g}', ha='center', va='bottom', color=text_hex, fontsize=10, fontweight='bold')
        elif ct == "line":
            ax.plot(x, clean_vals, color=accent_hex, linewidth=3, marker='o', markersize=8,
                    markerfacecolor=accent2_hex, markeredgecolor=accent_hex, zorder=3)
            ax.fill_between(x, clean_vals, alpha=0.15, color=accent_hex, zorder=2)
        elif ct == "area":
            ax.fill_between(x, clean_vals, alpha=0.4, color=accent_hex, zorder=2)
            ax.plot(x, clean_vals, color=accent_hex, linewidth=2.5, zorder=3)
        elif ct in ("pie", "donut"):
            colors = [accent_hex, accent2_hex, '#F59E0B', '#EC4899', '#10B981', '#FF6B80'][:len(clean_vals)]
            wedges, texts, autotexts = ax.pie(clean_vals, labels=[str(l) for l in labels],
                                              colors=colors, autopct='%1.1f%%', startangle=140,
                                              textprops={'color': text_hex, 'fontsize': 10})
            if ct == "donut":
                centre = plt.Circle((0, 0), 0.55, fc=bg_hex)
                ax.add_artist(centre)
        else:
            bars = ax.bar(x, clean_vals, color=accent_hex, width=0.6, zorder=3)

        if ct not in ("pie", "donut"):
            ax.set_xticks(x)
            ax.set_xticklabels([str(l) for l in labels], color=muted_hex, fontsize=10)
            ax.tick_params(axis='y', colors=muted_hex, labelsize=9)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color(muted_hex)
            ax.spines['left'].set_linewidth(0.5)
            ax.spines['bottom'].set_color(muted_hex)
            ax.spines['bottom'].set_linewidth(0.5)
            ax.grid(axis='y', color=muted_hex, alpha=0.15, linewidth=0.5, zorder=0)
            ax.set_ylabel(series_name, color=muted_hex, fontsize=11)

        if title and ct not in ("pie", "donut"):
            ax.set_title(title, color=text_hex, fontsize=14, fontweight='bold', pad=15)

        plt.tight_layout()

        ts = int(time.time() * 1000)
        chart_path = IMG_DIR / f"chart_{ts}.png"
        fig.savefig(chart_path, dpi=150, bbox_inches='tight', facecolor=bg_hex, edgecolor='none')
        plt.close(fig)

        log.info("Generated chart image: %s (%s)", chart_path, ct)
        return str(chart_path)
    except Exception as exc:
        log.error("Chart image generation failed: %s", exc)
        return None


async def fetch_web_image(query: str, index: int = 0) -> Optional[str]:
    """Download a real photo from Unsplash/Pexels/Pixabay/Wikimedia or generate an abstract visual graphic for the requested search query."""
    if not query:
        return None

    safe_q = "".join(c for c in query if c.isalnum() or c == " ").strip().replace(" ", "_").lower()
    local_path = IMG_DIR / f"{safe_q[:35]}_{index}.jpg"
    if local_path.exists() and local_path.stat().st_size > 1000:
        valid = _ensure_valid_image(str(local_path))
        if valid:
            return valid

    # 1. Unsplash Official Search API (High Quality Stock Photos)
    unsplash_key = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
    if unsplash_key:
        try:
            import httpx
            u_url = "https://api.unsplash.com/search/photos"
            u_params = {"query": query, "per_page": 10, "orientation": "landscape"}
            u_headers = {"Authorization": f"Client-ID {unsplash_key}", "User-Agent": "ZenithBot/1.0"}
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                resp = await client.get(u_url, params=u_params, headers=u_headers)
                if resp.status_code == 200:
                    results = resp.json().get("results", [])
                    if results:
                        photo = results[index % len(results)]
                        img_url = photo.get("urls", {}).get("regular") or photo.get("urls", {}).get("full")
                        if img_url:
                            img_resp = await client.get(img_url)
                            if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                                import io
                                from PIL import Image
                                im = Image.open(io.BytesIO(img_resp.content))
                                im = im.convert("RGB")
                                if im.width > 1920:
                                    im.thumbnail((1920, 1080), Image.LANCZOS)
                                im.save(local_path, "JPEG", quality=85)
                                log.info("Downloaded Unsplash photo (idx %d) for '%s': %s", index, query, local_path)
                                return str(local_path)
        except Exception as exc:
            log.debug("Unsplash search error for '%s': %s", query, exc)

    # 2. Pexels Free Stock Photos
    try:
        import httpx
        pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
        if pexels_key:
            pexels_url = f"https://api.pexels.com/v1/search?query={query.replace(' ', '+')}&per_page=10&orientation=landscape"
            pexels_headers = {
                "Authorization": pexels_key,
                "User-Agent": "ZenithBot/1.0",
            }
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                resp = await client.get(pexels_url, headers=pexels_headers)
                if resp.status_code == 200:
                    photos = resp.json().get("photos", [])
                    if photos:
                        photo = photos[index % len(photos)]
                        img_url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("large")
                        if img_url:
                            img_resp = await client.get(img_url)
                            if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                                import io
                                from PIL import Image
                                im = Image.open(io.BytesIO(img_resp.content))
                                im = im.convert("RGB")
                                if im.width > 1920:
                                    im.thumbnail((1920, 1080), Image.LANCZOS)
                                im.save(local_path, "JPEG", quality=85)
                                log.info("Downloaded Pexels photo (idx %d) for '%s': %s", index, query, local_path)
                                return str(local_path)
    except Exception as exc:
        log.debug("Pexels search error for '%s': %s", query, exc)

    # 3. Pixabay Free Stock Photos
    try:
        import httpx
        pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()
        if pixabay_key:
            pixabay_url = f"https://pixabay.com/api/?key={pixabay_key}&q={query.replace(' ', '+')}&image_type=photo&orientation=horizontal&per_page=10&min_width=800"
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
                resp = await client.get(pixabay_url)
                if resp.status_code == 200:
                    hits = resp.json().get("hits", [])
                    if hits:
                        hit = hits[index % len(hits)]
                        img_url = hit.get("largeImageURL") or hit.get("webformatURL")
                        if img_url:
                            img_resp = await client.get(img_url)
                            if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                                import io
                                from PIL import Image
                                im = Image.open(io.BytesIO(img_resp.content))
                                im = im.convert("RGB")
                                if im.width > 1920:
                                    im.thumbnail((1920, 1080), Image.LANCZOS)
                                im.save(local_path, "JPEG", quality=85)
                                log.info("Downloaded Pixabay photo (idx %d) for '%s': %s", index, query, local_path)
                                return str(local_path)
    except Exception as exc:
        log.debug("Pixabay search error for '%s': %s", query, exc)

    # 4. Wikimedia Commons Search
    try:
        import httpx
        url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": 6,
            "gsrlimit": 10,
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "format": "json"
        }
        headers = {"User-Agent": "ZenithAssistant/2.0"}
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                pages = list(data.get("query", {}).get("pages", {}).values())
                valid_urls = []
                for page in pages:
                    info_list = page.get("imageinfo", [])
                    if not info_list:
                        continue
                    info = info_list[0]
                    img_url = info.get("url")
                    mime = info.get("mime", "")
                    size = info.get("size", 0)
                    if img_url and mime in ("image/jpeg", "image/png", "image/webp") and 5000 < size < 15_000_000:
                        valid_urls.append(img_url)
                if valid_urls:
                    target_url = valid_urls[index % len(valid_urls)]
                    img_resp = await client.get(target_url, headers=headers)
                    if img_resp.status_code == 200 and len(img_resp.content) > 5000:
                        import io
                        from PIL import Image
                        im = Image.open(io.BytesIO(img_resp.content))
                        im = im.convert("RGB")
                        if im.width > 1920 or im.height > 1080:
                            im.thumbnail((1920, 1080), Image.LANCZOS)
                        im.save(local_path, "JPEG", quality=85)
                        log.info("Downloaded Wikimedia photo (idx %d) for '%s': %s", index, query, local_path)
                        return str(local_path)
    except Exception as exc:
        log.debug("Wikimedia search error for '%s': %s", query, exc)

    # 5. Fallback Graphic
    return _create_accent_graphic(f"{query}_{index}", local_path)


async def generate_pptx(
    title: str,
    subtitle: str = "",
    slides: list[dict[str, Any]] | str = None,
    author: str = "Zenith User",
    theme: str = "executive_dark",
    template: str = "",
    transition: str = "fade",
) -> str:
    """Generate a high-design .pptx presentation file using visual layout primitives, themes, templates, and real photos."""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        from pptx.enum.shapes import MSO_SHAPE
    except ImportError as e:
        log.error("python-pptx import error: %s", e)
        return f"python-pptx library error: {e}"

    if not slides:
        if template and template.lower() in PRESET_TEMPLATES:
            slides = PRESET_TEMPLATES[template.lower()]
        else:
            try:
                from zenith.presentation.pipeline import generate_topical_slide_structure
                slides = generate_topical_slide_structure(title=title, topic=title, subtitle=subtitle)
            except Exception as e:
                log.debug("Fallback to basic slides structure: %s", e)
                slides = [{"title": title, "layout": "cards_grid", "subtitle": subtitle}]

    if isinstance(slides, str):
        try:
            slides = json.loads(slides)
        except Exception:
            parsed_slides = []
            for line in slides.split("\n"):
                line = line.strip()
                if line.startswith("# ") or line.endswith(":"):
                    parsed_slides.append({"title": line.lstrip("#").rstrip(":").strip(), "layout": "cards_grid", "cards": [{"title": "Key Insight", "points": [line]}]})
            slides = parsed_slides or [{"title": title, "layout": "cards_grid", "subtitle": subtitle}]

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    blank_layout = prs.slide_layouts[6]

    # Resolve Theme Palette from Design System
    from .design_system import resolve_theme
    t_cfg = resolve_theme(theme)
    tc = t_cfg["colors"]
    palette = {
        "bg": tc["bg_rgb"],
        "card": tc["card_rgb"],
        "border": tc["border_rgb"],
        "title": tc["text_rgb"],
        "muted": tc["muted_rgb"],
        "accent1": tc["accent1_rgb"],
        "accent2": tc["accent2_rgb"],
    }
    BG_COLOR = RGBColor(*palette["bg"])
    CARD_BG = RGBColor(*palette["card"])
    BORDER_COLOR = RGBColor(*palette["border"])
    TITLE_COLOR = RGBColor(*palette["title"])
    TEXT_MUTED = RGBColor(*palette["muted"])
    ACCENT_PURPLE = RGBColor(*palette["accent1"])
    ACCENT_CYAN = RGBColor(*palette["accent2"])

    def set_slide_background(slide):
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = BG_COLOR

    # 1. TITLE SLIDE (Hero Title Layout)
    t_slide = prs.slides.add_slide(blank_layout)
    set_slide_background(t_slide)
    _apply_slide_transition(t_slide, transition)

    # Check for title slide image (index 0)
    main_img_path = await fetch_web_image(title, index=0)

    if main_img_path:
        # Title Slide with Real Downloaded Photo (fitted inside 5.4 x 5.1 box without distortion)
        _add_fitted_picture(t_slide, main_img_path, 0.8, 1.2, 5.4, 5.1, palette["card"], palette["border"])

        hero_card = t_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.5), Inches(1.2), Inches(6.0), Inches(5.1))
        hero_card.fill.solid()
        hero_card.fill.fore_color.rgb = CARD_BG
        hero_card.line.color.rgb = BORDER_COLOR

        badge = t_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(7.3), Inches(1.6), Inches(3.2), Inches(0.45))
        badge.fill.solid()
        badge.fill.fore_color.rgb = ACCENT_PURPLE
        badge.line.color.rgb = ACCENT_PURPLE
        btf = badge.text_frame
        btf.paragraphs[0].text = "EXECUTIVE PRESENTATION"
        btf.paragraphs[0].font.size = Pt(11)
        btf.paragraphs[0].font.bold = True
        btf.paragraphs[0].font.color.rgb = TITLE_COLOR
        btf.paragraphs[0].alignment = PP_ALIGN.CENTER

        tb = t_slide.shapes.add_textbox(Inches(7.3), Inches(2.3), Inches(4.8), Inches(3.6))
        tf = tb.text_frame
        tf.word_wrap = True
        p0 = tf.paragraphs[0]
        p0.text = title
        p0.font.size = Pt(36)
        p0.font.bold = True
        p0.font.color.rgb = TITLE_COLOR

        if subtitle:
            p1 = tf.add_paragraph()
            p1.text = subtitle
            p1.font.size = Pt(18)
            p1.font.color.rgb = ACCENT_CYAN
            p1.space_before = Pt(12)

        p2 = tf.add_paragraph()
        p2.text = f"Prepared for {author}  •  Zenith Engine"
        p2.font.size = Pt(13)
        p2.font.color.rgb = TEXT_MUTED
        p2.space_before = Pt(20)
    else:
        hero_card = t_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.0), Inches(1.2), Inches(11.333), Inches(5.1))
        hero_card.fill.solid()
        hero_card.fill.fore_color.rgb = CARD_BG
        hero_card.line.color.rgb = BORDER_COLOR

        badge = t_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(1.7), Inches(3.2), Inches(0.45))
        badge.fill.solid()
        badge.fill.fore_color.rgb = ACCENT_PURPLE
        badge.line.color.rgb = ACCENT_PURPLE
        btf = badge.text_frame
        btf.paragraphs[0].text = "EXECUTIVE PRESENTATION"
        btf.paragraphs[0].font.size = Pt(11)
        btf.paragraphs[0].font.bold = True
        btf.paragraphs[0].font.color.rgb = TITLE_COLOR
        btf.paragraphs[0].alignment = PP_ALIGN.CENTER

        tb = t_slide.shapes.add_textbox(Inches(1.5), Inches(2.4), Inches(10.333), Inches(3.2))
        tf = tb.text_frame
        tf.word_wrap = True

        p0 = tf.paragraphs[0]
        p0.text = title
        p0.font.size = Pt(44)
        p0.font.bold = True
        p0.font.color.rgb = TITLE_COLOR

        if subtitle:
            p1 = tf.add_paragraph()
            p1.text = subtitle
            p1.font.size = Pt(20)
            p1.font.color.rgb = ACCENT_CYAN
            p1.space_before = Pt(14)

        p2 = tf.add_paragraph()
        p2.text = f"Prepared for {author}  •  Zenith Intelligence Engine"
        p2.font.size = Pt(13)
        p2.font.color.rgb = TEXT_MUTED
        p2.space_before = Pt(24)

    # 2. RENDER SLIDES VIA VISUAL PRIMITIVES
    for idx, slide_data in enumerate(slides or []):
        c_slide = prs.slides.add_slide(blank_layout)
        set_slide_background(c_slide)
        _apply_slide_transition(c_slide, transition)

        # Speaker notes injection
        notes_text = str(slide_data.get("notes") or slide_data.get("speaker_notes") or "")
        if notes_text:
            try:
                c_slide.notes_slide.notes_text_frame.text = notes_text
            except Exception:
                pass

        stitle = slide_data.get("title", f"Slide {idx + 1}")
        DEFAULT_LAYOUT_CYCLE = ["photo_hero", "split_hero", "stat_hero", "chart_hero", "cards_grid", "timeline"]
        layout_type = (slide_data.get("layout") or DEFAULT_LAYOUT_CYCLE[idx % len(DEFAULT_LAYOUT_CYCLE)]).lower().replace("-", "_")
        if layout_type in ("cinematic_hero", "hero_title", "hero"):
            layout_type = "split_hero"
        elif layout_type in ("split_screen", "magazine", "editorial"):
            layout_type = "split_hero"
        elif layout_type in ("data_story", "metrics"):
            layout_type = "stat_hero"
        elif layout_type in ("bento", "cards"):
            layout_type = "cards_grid"
        elif layout_type in ("roadmap", "process_steps", "workflow"):
            layout_type = "timeline"
        bullets = slide_data.get("bullets", [])
        items = slide_data.get("items", []) or slide_data.get("cards", [])
        img_query = slide_data.get("image_query") or slide_data.get("query") or slide_data.get("photo") or stitle or title
        # Pass slide index (idx + 1) so each slide gets a unique image from the search results!
        img_index = idx + 1

        # Header Title Area
        header_box = c_slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.733), Inches(0.9))
        htf = header_box.text_frame
        htf.word_wrap = True
        hp0 = htf.paragraphs[0]
        hp0.text = stitle
        hp0.font.size = Pt(28)
        hp0.font.bold = True
        hp0.font.color.rgb = TITLE_COLOR

        # --- PRIMITIVE 0: NATIVE CHART AS EMBEDDED IMAGE ---
        if layout_type in ("chart_hero", "chart", "graph", "bar_chart", "line_chart", "pie_chart") or slide_data.get("chart") or slide_data.get("chart_type"):
            chart_info = slide_data.get("chart") or {}
            c_type_str = (chart_info.get("type") or slide_data.get("chart_type") or "column").lower()
            labels = chart_info.get("labels") or slide_data.get("labels") or ["2023", "2024", "2025", "2026 (Est)"]
            values = chart_info.get("values") or slide_data.get("values") or [35, 60, 95, 140]
            series_name = chart_info.get("series_name") or slide_data.get("series_name") or "Growth Trajectory"

            chart_rendered = False
            try:
                from pptx.chart.data import CategoryChartData
                from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

                chart_data_obj = CategoryChartData()
                chart_data_obj.categories = [str(l) for l in labels]

                clean_vals = []
                for v in values:
                    try:
                        clean_vals.append(float(v))
                    except Exception:
                        clean_vals.append(0.0)

                chart_data_obj.add_series(series_name, clean_vals)

                chart_type_map = {
                    "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
                    "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
                    "line": XL_CHART_TYPE.LINE,
                    "pie": XL_CHART_TYPE.PIE,
                    "donut": XL_CHART_TYPE.DOUGHNUT,
                    "area": XL_CHART_TYPE.AREA,
                }
                xl_type = chart_type_map.get(c_type_str, XL_CHART_TYPE.COLUMN_CLUSTERED)

                chart_shape = c_slide.shapes.add_chart(
                    xl_type, Inches(0.8), Inches(1.6), Inches(6.0), Inches(5.0), chart_data_obj
                )
                chart_obj = chart_shape.chart
                chart_obj.has_legend = True
                chart_obj.legend.position = XL_LEGEND_POSITION.BOTTOM
                chart_rendered = True
            except Exception as chart_err:
                log.warning("Native chart rendering error, falling back to matplotlib: %s", chart_err)

            if not chart_rendered:
                chart_img = _generate_chart_image(
                    c_type_str, labels, values, series_name, stitle,
                    palette["bg"], palette["accent1"], palette["accent2"],
                )
                if chart_img:
                    _add_fitted_picture(c_slide, chart_img, 0.8, 1.6, 6.0, 5.0, palette["card"], palette["border"])
                    chart_rendered = True

            if chart_rendered:
                card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(7.1), Inches(1.6), Inches(5.4), Inches(5.0))
                card.fill.solid()
                card.fill.fore_color.rgb = CARD_BG
                card.line.color.rgb = BORDER_COLOR

                ctb = c_slide.shapes.add_textbox(Inches(7.3), Inches(1.9), Inches(5.0), Inches(4.4))
                ctf = ctb.text_frame
                ctf.word_wrap = True
                cp0 = ctf.paragraphs[0]
                cp0.text = slide_data.get("subtitle") or "Data Insights & Metrics"
                cp0.font.size = Pt(20)
                cp0.font.bold = True
                cp0.font.color.rgb = ACCENT_CYAN

                for j, b in enumerate(bullets[:4]):
                    cp = ctf.add_paragraph()
                    cp.text = f"• {b}"
                    cp.font.size = Pt(13)
                    cp.font.color.rgb = TEXT_MUTED
                    cp.space_before = Pt(10)
            else:
                layout_type = "photo_hero"

        # --- PRIMITIVE 1: PHOTO HERO (Real Web Image + Content Card) ---
        elif layout_type in ("photo_hero", "photo", "image") or (slide_data.get("image_query") and layout_type not in ("chart_hero", "chart", "graph", "bar_chart", "line_chart", "pie_chart", "stat_hero", "stats", "metrics", "timeline", "process", "workflow", "comparison", "vs", "split_hero", "split", "asymmetric", "chapter_divider", "chapter", "divider")):
            img_path = await fetch_web_image(img_query, index=img_index)
            if img_path:
                # Embed Photo on Left (fitted in 5.4 x 5.2 box)
                _add_fitted_picture(c_slide, img_path, 0.8, 1.5, 5.4, 5.2, palette["card"], palette["border"])

                # Executive Content Card on Right
                card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.5), Inches(1.5), Inches(6.0), Inches(5.2))
                card.fill.solid()
                card.fill.fore_color.rgb = CARD_BG
                card.line.color.rgb = BORDER_COLOR

                ctb = c_slide.shapes.add_textbox(Inches(6.8), Inches(1.8), Inches(5.4), Inches(4.6))
                ctf = ctb.text_frame
                ctf.word_wrap = True
                cp0 = ctf.paragraphs[0]
                cp0.text = slide_data.get("subtitle") or "Visual Highlight"
                cp0.font.size = Pt(20)
                cp0.font.bold = True
                cp0.font.color.rgb = ACCENT_CYAN

                for j, b in enumerate(bullets[:4]):
                    cp = ctf.add_paragraph()
                    cp.text = f"• {b}"
                    cp.font.size = Pt(13)
                    cp.font.color.rgb = TEXT_MUTED
                    cp.space_before = Pt(10)
            else:
                layout_type = "split_hero"

        # --- PRIMITIVE 2: STAT HERO (Big Metrics + Embedded Photo) ---
        elif layout_type in ("stat_hero", "stats", "metrics") or slide_data.get("stats"):
            stats_list = slide_data.get("stats") or items or [
                {"number": "100%", "label": "Operational Efficiency", "sub": "Automated workflow"},
                {"number": "24/7", "label": "Continuous Monitoring", "sub": "Real-time alerts"},
                {"number": "< 1s", "label": "Execution Latency", "sub": "Instant feedback"}
            ]
            count = min(len(stats_list), 4)
            img_path = await fetch_web_image(img_query, index=img_index)

            if img_path:
                left_space = 8.0
                card_w = (left_space - (0.25 * (count - 1))) / count
                for i, stat in enumerate(stats_list[:count]):
                    left = 0.8 + i * (card_w + 0.25)
                    card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(1.7), Inches(card_w), Inches(4.8))
                    card.fill.solid()
                    card.fill.fore_color.rgb = CARD_BG
                    card.line.color.rgb = BORDER_COLOR

                    ntb = c_slide.shapes.add_textbox(Inches(left + 0.1), Inches(2.2), Inches(card_w - 0.2), Inches(1.8))
                    ntf = ntb.text_frame
                    ntf.word_wrap = True
                    np = ntf.paragraphs[0]
                    np.text = str(stat.get("number") or stat.get("value") or "0")
                    np.font.size = Pt(36 if count == 4 else 44)
                    np.font.bold = True
                    np.font.color.rgb = ACCENT_CYAN if i % 2 == 0 else ACCENT_PURPLE

                    ltb = c_slide.shapes.add_textbox(Inches(left + 0.1), Inches(4.0), Inches(card_w - 0.2), Inches(2.2))
                    ltf = ltb.text_frame
                    ltf.word_wrap = True
                    lp0 = ltf.paragraphs[0]
                    lp0.text = str(stat.get("label") or stat.get("title") or "")
                    lp0.font.size = Pt(14 if count == 4 else 17)
                    lp0.font.bold = True
                    lp0.font.color.rgb = TITLE_COLOR

                    if stat.get("sub") or stat.get("desc"):
                        lp1 = ltf.add_paragraph()
                        lp1.text = str(stat.get("sub") or stat.get("desc"))
                        lp1.font.size = Pt(11 if count == 4 else 13)
                        lp1.font.color.rgb = TEXT_MUTED
                        lp1.space_before = Pt(6)

                _add_fitted_picture(c_slide, img_path, 9.1, 1.7, 3.4, 4.8, palette["card"], palette["border"])
            else:
                card_width = (11.733 - (0.4 * (count - 1))) / count
                for i, stat in enumerate(stats_list[:count]):
                    left = 0.8 + i * (card_width + 0.4)
                    card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(1.7), Inches(card_width), Inches(4.8))
                    card.fill.solid()
                    card.fill.fore_color.rgb = CARD_BG
                    card.line.color.rgb = BORDER_COLOR

                    ntb = c_slide.shapes.add_textbox(Inches(left + 0.2), Inches(2.2), Inches(card_width - 0.4), Inches(1.8))
                    ntf = ntb.text_frame
                    ntf.word_wrap = True
                    np = ntf.paragraphs[0]
                    np.text = str(stat.get("number") or stat.get("value") or "0")
                    np.font.size = Pt(48)
                    np.font.bold = True
                    np.font.color.rgb = ACCENT_CYAN if i % 2 == 0 else ACCENT_PURPLE

                    ltb = c_slide.shapes.add_textbox(Inches(left + 0.2), Inches(4.0), Inches(card_width - 0.4), Inches(2.2))
                    ltf = ltb.text_frame
                    ltf.word_wrap = True
                    lp0 = ltf.paragraphs[0]
                    lp0.text = str(stat.get("label") or stat.get("title") or "")
                    lp0.font.size = Pt(18)
                    lp0.font.bold = True
                    lp0.font.color.rgb = TITLE_COLOR

                    if stat.get("sub") or stat.get("desc"):
                        lp1 = ltf.add_paragraph()
                        lp1.text = str(stat.get("sub") or stat.get("desc"))
                        lp1.font.size = Pt(13)
                        lp1.font.color.rgb = TEXT_MUTED
                        lp1.space_before = Pt(8)

        # --- PRIMITIVE 3: TIMELINE / PROCESS FLOW WITH EMBEDDED PHOTO ---
        elif layout_type in ("timeline", "process", "workflow") or slide_data.get("steps"):
            steps = slide_data.get("steps") or items or [
                {"title": "Phase 1", "desc": "Initial Setup & Architecture"},
                {"title": "Phase 2", "desc": "Core Implementation"},
                {"title": "Phase 3", "desc": "Testing & Deployment"},
                {"title": "Phase 4", "desc": "Production Release"}
            ]
            count = min(len(steps), 4)
            img_path = await fetch_web_image(img_query, index=img_index)

            if img_path:
                left_space = 8.0
                card_w = (left_space - (0.25 * (count - 1))) / count
                bar = c_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(2.3), Inches(7.6), Inches(0.08))
                bar.fill.solid()
                bar.fill.fore_color.rgb = ACCENT_PURPLE
                bar.line.fill.background()

                for i, step in enumerate(steps[:count]):
                    left = 0.8 + i * (card_w + 0.25)
                    circle = c_slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(left + card_w/2 - 0.35), Inches(1.95), Inches(0.7), Inches(0.7))
                    circle.fill.solid()
                    circle.fill.fore_color.rgb = ACCENT_PURPLE if i % 2 == 0 else ACCENT_CYAN
                    circle.line.color.rgb = TITLE_COLOR
                    ctf = circle.text_frame
                    cp = ctf.paragraphs[0]
                    cp.text = str(i + 1)
                    cp.font.size = Pt(16)
                    cp.font.bold = True
                    cp.font.color.rgb = TITLE_COLOR
                    cp.alignment = PP_ALIGN.CENTER

                    card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(2.9), Inches(card_w), Inches(3.8))
                    card.fill.solid()
                    card.fill.fore_color.rgb = CARD_BG
                    card.line.color.rgb = BORDER_COLOR

                    ctb = c_slide.shapes.add_textbox(Inches(left + 0.1), Inches(3.1), Inches(card_w - 0.2), Inches(3.3))
                    ctf2 = ctb.text_frame
                    ctf2.word_wrap = True
                    stp0 = ctf2.paragraphs[0]
                    stp0.text = str(step.get("title") or f"Step {i+1}")
                    stp0.font.size = Pt(15 if count == 4 else 18)
                    stp0.font.bold = True
                    stp0.font.color.rgb = TITLE_COLOR

                    stp1 = ctf2.add_paragraph()
                    stp1.text = str(step.get("desc") or step.get("text") or "")
                    stp1.font.size = Pt(11 if count == 4 else 13)
                    stp1.font.color.rgb = TEXT_MUTED
                    stp1.space_before = Pt(6)

                _add_fitted_picture(c_slide, img_path, 9.1, 1.7, 3.4, 4.8, palette["card"], palette["border"])
            else:
                card_width = (11.733 - (0.4 * (count - 1))) / count
                bar = c_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(2.3), Inches(11.333), Inches(0.08))
                bar.fill.solid()
                bar.fill.fore_color.rgb = ACCENT_PURPLE
                bar.line.fill.background()

                for i, step in enumerate(steps[:count]):
                    left = 0.8 + i * (card_width + 0.4)
                    circle = c_slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(left + card_width/2 - 0.35), Inches(1.95), Inches(0.7), Inches(0.7))
                    circle.fill.solid()
                    circle.fill.fore_color.rgb = ACCENT_PURPLE if i % 2 == 0 else ACCENT_CYAN
                    circle.line.color.rgb = TITLE_COLOR
                    ctf = circle.text_frame
                    cp = ctf.paragraphs[0]
                    cp.text = str(i + 1)
                    cp.font.size = Pt(16)
                    cp.font.bold = True
                    cp.font.color.rgb = TITLE_COLOR
                    cp.alignment = PP_ALIGN.CENTER

                    card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(2.9), Inches(card_width), Inches(3.8))
                    card.fill.solid()
                    card.fill.fore_color.rgb = CARD_BG
                    card.line.color.rgb = BORDER_COLOR

                    ctb = c_slide.shapes.add_textbox(Inches(left + 0.2), Inches(3.1), Inches(card_width - 0.4), Inches(3.3))
                    ctf2 = ctb.text_frame
                    ctf2.word_wrap = True
                    stp0 = ctf2.paragraphs[0]
                    stp0.text = str(step.get("title") or f"Step {i+1}")
                    stp0.font.size = Pt(18)
                    stp0.font.bold = True
                    stp0.font.color.rgb = TITLE_COLOR

                    stp1 = ctf2.add_paragraph()
                    stp1.text = str(step.get("desc") or step.get("text") or "")
                    stp1.font.size = Pt(13)
                    stp1.font.color.rgb = TEXT_MUTED
                    stp1.space_before = Pt(8)

        # --- PRIMITIVE 4: COMPARISON ---
        elif layout_type in ("comparison", "vs") or slide_data.get("columns"):
            raw_cols = slide_data.get("columns") or [
                {"title": "Option A", "points": bullets[:len(bullets)//2 or 1]},
                {"title": "Option B", "points": bullets[len(bullets)//2 or 1:]}
            ]
            rows_data = slide_data.get("rows") or []
            cols = []
            for i, c in enumerate(raw_cols):
                if isinstance(c, str):
                    c_points = [r[i] for r in rows_data if isinstance(r, (list, tuple)) and len(r) > i]
                    if not c_points and bullets:
                        c_points = [b for j, b in enumerate(bullets) if j % len(raw_cols) == i]
                    cols.append({"title": c, "points": c_points})
                elif isinstance(c, dict):
                    cols.append(c)
                else:
                    cols.append({"title": str(c), "points": []})

            count = min(len(cols), 3)
            card_width = (11.733 - (0.4 * (count - 1))) / count

            for i, col in enumerate(cols[:count]):
                left = 0.8 + i * (card_width + 0.4)
                card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(1.7), Inches(card_width), Inches(4.8))
                card.fill.solid()
                card.fill.fore_color.rgb = CARD_BG
                card.line.color.rgb = ACCENT_PURPLE if i == 0 else ACCENT_CYAN

                hdr = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left + 0.2), Inches(1.9), Inches(card_width - 0.4), Inches(0.6))
                hdr.fill.solid()
                hdr.fill.fore_color.rgb = ACCENT_PURPLE if i == 0 else ACCENT_CYAN
                hdr.line.fill.background()
                htf = hdr.text_frame
                hp = htf.paragraphs[0]
                hp.text = str(col.get("title") or f"Option {i+1}")
                hp.font.size = Pt(16)
                hp.font.bold = True
                hp.font.color.rgb = TITLE_COLOR
                hp.alignment = PP_ALIGN.CENTER

                ctb = c_slide.shapes.add_textbox(Inches(left + 0.3), Inches(2.7), Inches(card_width - 0.6), Inches(3.6))
                ctf = ctb.text_frame
                ctf.word_wrap = True
                for j, pt in enumerate(col.get("points") or []):
                    p = ctf.paragraphs[0] if j == 0 else ctf.add_paragraph()
                    p.text = f"• {pt}"
                    p.font.size = Pt(14)
                    p.font.color.rgb = TEXT_MUTED
                    p.space_before = Pt(8)

        # --- PRIMITIVE 5: SPLIT HERO (2-Column Asymmetric with Embedded Photo) ---
        elif layout_type in ("split_hero", "split", "asymmetric"):
            left_card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.7), Inches(6.5), Inches(4.8))
            left_card.fill.solid()
            left_card.fill.fore_color.rgb = CARD_BG
            left_card.line.color.rgb = BORDER_COLOR

            ltb = c_slide.shapes.add_textbox(Inches(1.1), Inches(2.0), Inches(5.9), Inches(4.2))
            ltf = ltb.text_frame
            ltf.word_wrap = True
            lp0 = ltf.paragraphs[0]
            lp0.text = slide_data.get("subtitle") or slide_data.get("summary") or stitle
            lp0.font.size = Pt(22)
            lp0.font.bold = True
            lp0.font.color.rgb = ACCENT_PURPLE

            for j, b in enumerate(bullets[:4]):
                lp = ltf.add_paragraph()
                lp.text = f"• {b}"
                lp.font.size = Pt(14)
                lp.font.color.rgb = TEXT_MUTED
                lp.space_before = Pt(10)

            img_path = await fetch_web_image(img_query, index=img_index)
            if img_path:
                _add_fitted_picture(c_slide, img_path, 7.7, 1.7, 4.8, 4.8, palette["card"], palette["border"])
            else:
                right_card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(7.7), Inches(1.7), Inches(4.8), Inches(4.8))
                right_card.fill.solid()
                right_card.fill.fore_color.rgb = CARD_BG
                right_card.line.color.rgb = ACCENT_CYAN

        elif layout_type in ("chapter_divider", "chapter", "divider"):
            vbar = c_slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(2.0), Inches(0.15), Inches(3.5))
            vbar.fill.solid()
            vbar.fill.fore_color.rgb = ACCENT_PURPLE
            vbar.line.fill.background()

            dtb = c_slide.shapes.add_textbox(Inches(1.6), Inches(2.0), Inches(10.5), Inches(3.5))
            dtf = dtb.text_frame
            dtf.word_wrap = True
            dp0 = dtf.paragraphs[0]
            dp0.text = f"CHAPTER {idx + 1}"
            dp0.font.size = Pt(14)
            dp0.font.bold = True
            dp0.font.color.rgb = ACCENT_CYAN

            dp1 = dtf.add_paragraph()
            dp1.text = stitle
            dp1.font.size = Pt(40)
            dp1.font.bold = True
            dp1.font.color.rgb = TITLE_COLOR
            dp1.space_before = Pt(8)

            if bullets:
                dp2 = dtf.add_paragraph()
                dp2.text = bullets[0]
                dp2.font.size = Pt(18)
                dp2.font.color.rgb = TEXT_MUTED
                dp2.space_before = Pt(14)

        # --- PRIMITIVE: COMPARISON ---
        elif layout_type in ("comparison", "compare", "vs"):
            cols = slide_data.get("columns") or ["Conventional Standards", f"Modern Advanced {title}"]
            rows = slide_data.get("rows") or []
            c_width = 5.6
            for c_i, col_name in enumerate(cols[:2]):
                c_left = 0.8 + c_i * 6.0
                card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(c_left), Inches(1.7), Inches(c_width), Inches(4.8))
                card.fill.solid()
                card.fill.fore_color.rgb = CARD_BG
                card.line.color.rgb = ACCENT_CYAN if c_i == 1 else BORDER_COLOR

                ctb = c_slide.shapes.add_textbox(Inches(c_left + 0.3), Inches(2.0), Inches(c_width - 0.6), Inches(4.2))
                ctf = ctb.text_frame
                ctf.word_wrap = True
                cp0 = ctf.paragraphs[0]
                cp0.text = str(col_name)
                cp0.font.size = Pt(20)
                cp0.font.bold = True
                cp0.font.color.rgb = ACCENT_PURPLE if c_i == 1 else TITLE_COLOR

                for r_item in rows:
                    cp = ctf.add_paragraph()
                    val = r_item[c_i] if isinstance(r_item, (list, tuple)) and len(r_item) > c_i else str(r_item)
                    cp.text = f"• {val}"
                    cp.font.size = Pt(13)
                    cp.font.color.rgb = TEXT_MUTED
                    cp.space_before = Pt(8)

        # --- PRIMITIVE: CLOSING / SUMMARY ---
        elif layout_type in ("closing", "conclusion", "summary"):
            c_card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(1.8), Inches(10.33), Inches(4.5))
            c_card.fill.solid()
            c_card.fill.fore_color.rgb = CARD_BG
            c_card.line.color.rgb = BORDER_COLOR

            ctb = c_slide.shapes.add_textbox(Inches(2.0), Inches(2.2), Inches(9.33), Inches(3.8))
            ctf = ctb.text_frame
            ctf.word_wrap = True
            cp0 = ctf.paragraphs[0]
            cp0.text = slide_data.get("subtitle") or f"Key Takeaways & Strategic Horizons for {title}"
            cp0.font.size = Pt(22)
            cp0.font.bold = True
            cp0.font.color.rgb = ACCENT_CYAN

            close_points = bullets or [
                f"Sustained mastery and domain advancement in {title}",
                f"Continuous refinement, empirical validation, and standard-setting impact",
                f"Pioneering next-generation paradigms with verifiable outcomes",
            ]
            for p_text in close_points[:4]:
                cp = ctf.add_paragraph()
                cp.text = f"✔  {p_text}"
                cp.font.size = Pt(14)
                cp.font.color.rgb = TITLE_COLOR
                cp.space_before = Pt(12)

        # --- PRIMITIVE: QUOTE CALLOUT ---
        elif layout_type in ("quote_callout", "quote"):
            q_card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1.5), Inches(1.8), Inches(10.33), Inches(4.5))
            q_card.fill.solid()
            q_card.fill.fore_color.rgb = CARD_BG
            q_card.line.color.rgb = BORDER_COLOR

            qtb = c_slide.shapes.add_textbox(Inches(2.0), Inches(2.3), Inches(9.33), Inches(3.5))
            qtf = qtb.text_frame
            qtf.word_wrap = True
            qp0 = qtf.paragraphs[0]
            qp0.text = f"“{slide_data.get('quote') or slide_data.get('text') or stitle}”"
            qp0.font.size = Pt(24)
            qp0.font.italic = True
            qp0.font.bold = True
            qp0.font.color.rgb = TITLE_COLOR
            qp0.alignment = PP_ALIGN.CENTER

            qp1 = qtf.add_paragraph()
            qp1.text = f"— {slide_data.get('author') or slide_data.get('subtitle') or 'Executive Perspective'}"
            qp1.font.size = Pt(14)
            qp1.font.color.rgb = ACCENT_PURPLE
            qp1.alignment = PP_ALIGN.CENTER
            qp1.space_before = Pt(16)

        # --- PRIMITIVE 7: CARDS GRID (Default with Embedded Photo) ---
        else:
            raw_cards = items or []
            card_items = []
            for c in raw_cards:
                if isinstance(c, str):
                    card_items.append({"title": c, "points": []})
                elif isinstance(c, dict):
                    card_items.append(c)
                else:
                    card_items.append({"title": str(c), "points": []})

            if not card_items and bullets:
                chunk_size = max(1, (len(bullets) + 2) // 3)
                for c_idx in range(0, len(bullets), chunk_size):
                    chunk = bullets[c_idx:c_idx + chunk_size]
                    card_items.append({"title": f"Key Focus {len(card_items)+1}", "points": chunk})

            if not card_items:
                card_items = [{"title": "Overview", "points": ["Key presentation takeaway point."]}]

            count = min(len(card_items), 4)
            img_path = await fetch_web_image(img_query, index=img_index)

            if img_path and count <= 2:
                for i, card_data in enumerate(card_items[:2]):
                    left = 0.8 + i * 3.5
                    card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(1.7), Inches(3.3), Inches(4.8))
                    card.fill.solid()
                    card.fill.fore_color.rgb = CARD_BG
                    card.line.color.rgb = BORDER_COLOR

                    apill = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left + 0.3), Inches(1.95), Inches(0.6), Inches(0.08))
                    apill.fill.solid()
                    apill.fill.fore_color.rgb = ACCENT_PURPLE if i % 2 == 0 else ACCENT_CYAN
                    apill.line.fill.background()

                    ctb = c_slide.shapes.add_textbox(Inches(left + 0.3), Inches(2.2), Inches(2.7), Inches(4.1))
                    ctf = ctb.text_frame
                    ctf.word_wrap = True

                    cp0 = ctf.paragraphs[0]
                    cp0.text = str(card_data.get("title") or f"Insight {i+1}")
                    cp0.font.size = Pt(18)
                    cp0.font.bold = True
                    cp0.font.color.rgb = TITLE_COLOR

                    pts = card_data.get("points") or card_data.get("bullets") or []
                    if isinstance(pts, str):
                        pts = [pts]

                    for pt in pts:
                        cp = ctf.add_paragraph()
                        cp.text = f"• {pt}"
                        cp.font.size = Pt(13)
                        cp.font.color.rgb = TEXT_MUTED
                        cp.space_before = Pt(8)

                _add_fitted_picture(c_slide, img_path, 7.8, 1.7, 4.7, 4.8, palette["card"], palette["border"])
            else:
                card_width = (11.733 - (0.4 * (count - 1))) / count
                for i, card_data in enumerate(card_items[:count]):
                    left = 0.8 + i * (card_width + 0.4)
                    card = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(1.7), Inches(card_width), Inches(4.8))
                    card.fill.solid()
                    card.fill.fore_color.rgb = CARD_BG
                    card.line.color.rgb = BORDER_COLOR

                    apill = c_slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left + 0.3), Inches(1.95), Inches(0.6), Inches(0.08))
                    apill.fill.solid()
                    apill.fill.fore_color.rgb = ACCENT_PURPLE if i % 2 == 0 else ACCENT_CYAN
                    apill.line.fill.background()

                    ctb = c_slide.shapes.add_textbox(Inches(left + 0.3), Inches(2.2), Inches(card_width - 0.6), Inches(4.1))
                    ctf = ctb.text_frame
                    ctf.word_wrap = True

                    cp0 = ctf.paragraphs[0]
                    cp0.text = str(card_data.get("title") or f"Insight {i+1}")
                    cp0.font.size = Pt(18)
                    cp0.font.bold = True
                    cp0.font.color.rgb = TITLE_COLOR

                    pts = card_data.get("points") or card_data.get("bullets") or []
                    if isinstance(pts, str):
                        pts = [pts]

                    for j, pt in enumerate(pts[:4]):
                        cp = ctf.add_paragraph()
                        cp.text = f"• {pt}"
                        cp.font.size = Pt(13)
                        cp.font.color.rgb = TEXT_MUTED
                        cp.space_before = Pt(8)

    ts = int(time.time())
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")[:30]
    filename = f"presentation_{safe_title}_{ts}.pptx"
    out_path = OUT_DIR / filename
    prs.save(out_path)

    try:
        gen_dir = Path("static/generated")
        gen_dir.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy(out_path, gen_dir / filename)
    except Exception as exc:
        log.debug("Could not copy PPTX to static/generated: %s", exc)

    deck_id = f"deck_{safe_title}_{ts}"
    try:
        from ..memory import store
        store.save_artifact(
            artifact_id=deck_id,
            artifact_type="presentation",
            title=title,
            theme=theme,
            data_json={
                "title": title,
                "subtitle": subtitle,
                "author": author,
                "theme": theme,
                "slides": slides if isinstance(slides, list) else [],
                "file_path": str(out_path),
            },
            file_path=str(out_path),
            web_url=f"/api/files/download?filename={filename}",
        )
        store.set_last_generated_artifact(deck_id)
        log.info("Registered presentation artifact %s in store: %s", deck_id, out_path)
    except Exception as exc:
        log.debug("Could not save presentation artifact in store: %s", exc)

    log.info("Generated Executive PPTX with Visual Primitives & Web Photos: %s", out_path)
    return str(out_path)

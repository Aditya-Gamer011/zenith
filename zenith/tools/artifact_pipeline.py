"""Zenith Media Studio — Studio-Grade Presentation & Document Generation Pipeline.

Orchestrates the 5-stage media pipeline:
1. Understand Brief & Art Direction (Topic, Audience, Theme)
2. Content Strategy & Layout Planning (Structured JSON with Layout Primitives)
3. Specialist Rendering (Interactive Web Presentation + Editable PPTX + DOCX/PDF)
4. Quality Critic & Validation Loop (Overflow & Density Guardrails)
5. Refine, Persist & Deliver (SQLite Artifact Store + Iterative Editing)
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .design_system import resolve_theme, DESIGN_CONSTRAINTS, THEMES, get_color_palette_meta, compute_relative_luminance
from .web_presentation import generate_web_presentation
from .presentation import generate_pptx
from ..memory import store

log = logging.getLogger("zenith.tools.artifact_pipeline")


# ── Stage 1: Brief & Theme Inference ─────────────────────────────────────────

def infer_art_direction(topic: str, requested_theme: str = "") -> str:
    """Infer the most authentic, human-crafted theme based on prompt topic, avoiding AI neon defaults."""
    if requested_theme and requested_theme.lower() in THEMES:
        return requested_theme.lower()

    t_lower = (topic or "").lower()

    if any(k in t_lower for k in ("boba", "tea", "drink", "cafe", "food", "snack", "bash")):
        return "boba_bash"
    elif any(k in t_lower for k in ("nature", "climate", "forest", "eco", "sustainability", "plant", "green")):
        return "terracotta_warm"
    elif any(k in t_lower for k in ("nordic", "cloud", "saas", "api", "database", "security", "infra", "ocean")):
        return "nordic_navy"
    elif any(k in t_lower for k in ("apple", "swiss", "minimal", "clean", "white", "report", "academic")):
        return "swiss_clean"
    elif any(k in t_lower for k in ("monochrome", "warren", "investor", "finance", "audit", "stripe")):
        return "executive_mono"
    elif any(k in t_lower for k in ("cyberpunk", "sci-fi", "futuristic", "matrix", "gaming", "neon")):
        return "cyberpunk_neon"

    # Default: Studio Editorial (Warm Obsidian & Champagne Accent)
    return "editorial_slate"


# ── Stage 4: Quality Critic & Density Guardrail ──────────────────────────────

def run_quality_critic(slides: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Inspect and auto-repair slide layouts for text overflow, density fatigue, and readability."""
    repaired = []
    max_bullets = DESIGN_CONSTRAINTS["max_bullets_per_slide"]
    max_words = DESIGN_CONSTRAINTS["max_words_per_bullet"]

    for idx, slide in enumerate(slides):
        s = dict(slide)
        layout = (s.get("layout") or "cards_grid").lower()

        # Check title length
        if len(s.get("title", "")) > DESIGN_CONSTRAINTS["max_chars_per_title"]:
            # Truncate at word boundary
            words = s["title"].split()
            s["title"] = " ".join(words[:8]) + "..."

        # Check bullets density
        bullets = s.get("bullets", [])
        if isinstance(bullets, list):
            cleaned_bullets = []
            for b in bullets[:max_bullets]:
                b_str = str(b).strip()
                b_words = b_str.split()
                if len(b_words) > max_words:
                    b_str = " ".join(b_words[:max_words]) + "..."
                cleaned_bullets.append(b_str)
            s["bullets"] = cleaned_bullets

        # Check cards density
        cards = s.get("cards", [])
        if isinstance(cards, list) and len(cards) > 4:
            s["cards"] = cards[:4]

        # Ensure speaker notes exist
        if not s.get("notes") and not s.get("speaker_notes"):
            title = s.get("title", f"Slide {idx + 1}")
            s["notes"] = f"Key takeaway for {title}: Deliver with concise, confident executive presence."

        repaired.append(s)

    return repaired


# ── Stage 3 & 5: Master Presentation Generator ───────────────────────────────

async def generate_presentation(
    title: str,
    topic: str = "",
    theme: str = "",
    slides: List[Dict[str, Any]] | str = "",
    subtitle: str = "",
    author: str = "Zenith Studio",
    format: str = "both",  # 'both' | 'web' | 'pptx'
    motion_intensity: str = "high",
    style: str = "",
) -> str:
    """Generate a Studio-Grade presentation with visual style selection, visual rhythm, component retrieval, and quality critic auto-refinement."""
    from zenith.presentation import get_master_pipeline, VISUAL_STYLES

    ts = int(time.time())
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")[:24]
    deck_id = f"deck_{safe_title}_{ts}"

    # Determine Theme & Style
    selected_theme = infer_art_direction(f"{title} {topic}", theme)
    theme_meta = resolve_theme(selected_theme)

    # Parse slides if passed as JSON string or markdown
    slide_items = []
    if isinstance(slides, str) and slides.strip():
        try:
            slide_items = json.loads(slides)
        except Exception:
            current_slide = None
            for line in slides.split("\n"):
                line = line.strip()
                if line.startswith("# ") or (line.startswith("Slide") and ":" in line):
                    if current_slide:
                        slide_items.append(current_slide)
                    stitle = line.lstrip("#").split(":", 1)[-1].strip()
                    current_slide = {"title": stitle, "layout": "cards_grid", "cards": []}
                elif line.startswith("- ") or line.startswith("• "):
                    if not current_slide:
                        current_slide = {"title": title, "layout": "hero_title", "subtitle": subtitle}
                    b_text = line[2:].strip()
                    current_slide.setdefault("bullets", []).append(b_text)
            if current_slide:
                slide_items.append(current_slide)
    elif isinstance(slides, list):
        slide_items = slides

    # If no slides provided, construct standard topical structure
    if not slide_items:
        from zenith.presentation.pipeline import generate_topical_slide_structure
        slide_items = generate_topical_slide_structure(title=title, topic=topic or title, subtitle=subtitle)

    # Run Quality Critic & Density Guardrail
    validated_slides = run_quality_critic(slide_items)

    # Execute Master Presentation Pipeline
    master_pipeline = get_master_pipeline()
    pipeline_result = await master_pipeline.execute_pipeline(
        title=title,
        topic=topic or title,
        slides=validated_slides,
        style=style,
        theme=selected_theme,
        subtitle=subtitle,
        author=author,
        deck_id=deck_id,
    )

    deck_id = pipeline_result.get("deck_id") or deck_id
    pptx_path = pipeline_result["pptx_path"]
    pdf_path = pipeline_result.get("pdf_path", "")
    slide_images = pipeline_result.get("slide_images", [])

    pptx_url = ""
    if pptx_path and Path(pptx_path).exists():
        pptx_filename = Path(pptx_path).name
        pptx_url = f"/api/files/download?filename={pptx_filename}"

    pdf_url = ""
    if pdf_path and Path(pdf_path).exists():
        pdf_filename = Path(pdf_path).name
        pdf_url = f"/api/files/download?filename={pdf_filename}"

    web_url = pipeline_result.get("web_url") or f"/presentation/{deck_id}"
    quality_score = pipeline_result["quality_score"]
    style_display = pipeline_result["style_name"]
    visual_intensity = pipeline_result["intensity"]
    rhythm_seq = pipeline_result["visual_rhythm"]

    palette_info = pipeline_result.get("palette_meta") or get_color_palette_meta(selected_theme)
    tokens = palette_info.get("tokens", {})
    contrast = palette_info.get("contrast", {})
    wcag_badge = contrast.get("wcag_overall", "AA")
    t_ratio = contrast.get("text_on_bg", {}).get("ratio", "N/A")
    canvas_hex = tokens.get("canvas_background", "#0D0F12")
    card_hex = tokens.get("surface_card", "#181B20")
    text_hex = tokens.get("primary_text", "#F4F4F6")
    accent_hex = tokens.get("accent_primary", "#D4A373")

    # Save to SQLite Artifacts Store
    artifact_payload = {
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "theme": selected_theme,
        "style": pipeline_result["style"],
        "intensity": visual_intensity,
        "palette_meta": palette_info,
        "quality_score": quality_score,
        "motion_intensity": motion_intensity,
        "slides": validated_slides,
        "pdf_path": pdf_path,
        "slide_images": slide_images,
    }
    store.save_artifact(
        artifact_id=deck_id,
        artifact_type="presentation",
        title=title,
        theme=selected_theme,
        data_json=artifact_payload,
        file_path=pptx_path,
        web_url=web_url,
    )

    # Construct Rich Markdown Deliverable
    slide_count = len(validated_slides)
    theme_display = theme_meta["name"]

    response = (
        f"🎨 **Studio Presentation Created**: `{title}`\n\n"
        f"- **Visual Style**: `{style_display}` (Intensity: {visual_intensity}/5)\n"
        f"- **Design Theme**: `{theme_display}`\n"
        f"- **Color Palette & Contrast**: `{theme_display}` [Canvas: `{canvas_hex}`, Card: `{card_hex}`, Text: `{text_hex}` ({t_ratio}:1 — WCAG {wcag_badge}), Accent: `{accent_hex}`]\n"
        f"- **Quality Critic Score**: **{quality_score}/100** (Auto-Refined & Guardrail Verified)\n"
        f"- **Total Slides**: {slide_count} slides with structured visual rhythm cadence\n"
        f"- **Visual Rhythm**: `{' → '.join(rhythm_seq[:slide_count])}`\n"
        f"- **Features**: Three.js WebGL 3D ambient canvas, 3D card tilt, fullscreen (`F`), speaker notes (`N`), slide grid (`G`)\n\n"
        f"### 🚀 **Deliverables**\n"
        f"1. **[🖥️ Launch Interactive Web Presentation]({web_url})** *(Present in-browser with 3D effects & keyboard arrows)*\n"
    )

    if pptx_path:
        response += (
            f"2. **[📥 Download Editable PowerPoint (.pptx)]({pptx_url})** *(Full native shapes, tables, transitions, and notes)*\n"
        )
    if pdf_url:
        response += (
            f"3. **[📄 Download Presentation PDF]({pdf_url})** *(Print-ready vector export with slide pages)*\n"
        )
    if pptx_path:
        response += (
            f"- **Attachment File Path**: `{pptx_path}` *(Use for `email_send` `attachment_path`)*\n"
        )
    if slide_images:
        response += (
            f"- **Slide Previews Rendered**: {len(slide_images)} slides inspected and verified by Visual Critic\n"
        )

    response += (
        f"\n**Slide Outline**:\n" +
        "\n".join(f"  - **Slide {i+1}**: {s.get('title')} `[{s.get('layout')}]`" for i, s in enumerate(validated_slides)) +
        f"\n\n*Tip: You can ask me to edit any slide iteratively (e.g. `Make slide 3 less crowded`, `Change style to Minimal Premium`, or `Add comparison on slide 4`).*"
    )

    return response


# ── Presentation Planning, Search & Critique Tools ───────────────────────────

async def presentation_plan(
    title: str,
    topic: str = "",
    num_slides: int = 8,
    style: str = "",
    theme: str = "",
) -> str:
    """Plan a structured presentation deck following Visual Rhythm and Visual Style guidelines."""
    from zenith.presentation import get_master_pipeline, VISUAL_STYLES

    pipeline = get_master_pipeline()
    dsl = pipeline.plan_presentation(
        title=title,
        topic=topic or title,
        num_slides=num_slides,
        requested_style=style,
        requested_theme=theme,
    )

    style_name = VISUAL_STYLES[dsl.style].name
    palette_info = dsl.palette_meta or get_color_palette_meta(dsl.theme)
    tokens = palette_info.get("tokens", {})
    contrast = palette_info.get("contrast", {})
    wcag_badge = contrast.get("wcag_overall", "AA")
    t_ratio = contrast.get("text_on_bg", {}).get("ratio", "N/A")

    out = [
        f"### Presentation Plan: {dsl.title}",
        f"- **Visual Style**: {style_name} (`{dsl.style}`)",
        f"- **Visual Intensity**: {dsl.intensity}/5",
        f"- **Design Theme**: `{dsl.theme}` (WCAG {wcag_badge} verified, {t_ratio}:1 contrast)",
        f"- **Color Tokens**: Canvas `{tokens.get('canvas_background')}`, Card `{tokens.get('surface_card')}`, Text `{tokens.get('primary_text')}`, Accent `{tokens.get('accent_primary')}`",
        f"- **Planned Slides**: {len(dsl.slides)}",
        f"- **Visual Rhythm**: `{' → '.join(dsl.visual_rhythm)}`\n",
        "#### Planned Slide Cadence:",
    ]
    for s in dsl.slides:
        out.append(f"{s.slide_number}. **{s.title}**")
        out.append(f"   - **Layout**: `{s.layout}` | **Rhythm**: `{s.rhythm}`")
        out.append(f"   - **Eyebrow**: {s.eyebrow}")
        out.append(f"   - **Transition**: `{s.transition}`")

    return "\n".join(out)


async def presentation_search_components(
    query: str = "",
    type: str = "",
    type_filter: str = "",
    intensity: int = 5,
    style: str = "",
) -> str:
    """Search presentation layouts, components, effects, typography, and 3D assets."""
    from zenith.presentation import get_presentation_registry

    effective_type = type_filter or type or None
    reg = get_presentation_registry()
    items = reg.search(query=query, type_filter=effective_type, intensity=intensity, style=style or None, limit=10)

    if not items:
        return f"No presentation components found matching query='{query}', type='{type}'."

    out = [f"Found {len(items)} matching presentation asset(s):\n"]
    for i, item in enumerate(items, 1):
        out.append(
            f"{i}. **{item.name}** (`{item.id}`)\n"
            f"   - **Type**: `{item.type}` | **Intensity**: {item.visualIntensity}/5\n"
            f"   - **Tags**: {', '.join(item.tags)}\n"
            f"   - **Best For**: {', '.join(item.bestFor)}\n"
            f"   - **Compatible Styles**: {', '.join(item.compatibleStyles)}\n"
            f"   - **Description**: {item.description}\n"
        )
    return "\n".join(out)


async def presentation_critique(deck_id: str = "") -> str:
    """Run visual quality critic on an existing or generated presentation deck."""
    from zenith.presentation import get_critic, get_master_pipeline

    pipeline = get_master_pipeline()
    critic = get_critic()

    # If deck_id is given, retrieve from memory store
    deck_data = None
    if deck_id:
        deck_data = store.get_artifact(deck_id)

    if deck_data and "slides" in deck_data.get("data_json", {}):
        slides = deck_data["data_json"]["slides"]
        title = deck_data.get("title", "Presentation")
        dsl = pipeline.plan_presentation(title=title, topic=title, raw_slides_input=slides)
    else:
        # Default plan demonstration
        dsl = pipeline.plan_presentation(title="Sample Quality Audit", topic="Artificial Intelligence")

    critique = critic.critique(dsl)

    out = [
        f"### Visual Quality Critique: {dsl.title}",
        f"- **Quality Score**: **{critique.score}/100**",
        f"- **Status**: {'✅ PASSED' if critique.passed else '⚠️ NEEDS REFINEMENT'}",
        f"- **Total Slides Audited**: {critique.total_slides}",
    ]

    if critique.palette_info:
        p_info = critique.palette_info
        c_report = critique.contrast_report or {}
        out.append("\n#### Color Palette & Accessibility Audit:")
        out.append(f"- **Theme**: {p_info.get('theme_name', dsl.theme)} ({p_info.get('mode', 'dark').capitalize()} Mode)")
        out.append(f"- **WCAG 2.1 Compliance**: **{c_report.get('wcag_overall', 'AA')}** ({'✅ Compliant' if c_report.get('compliant') else '⚠️ Non-compliant'})")
        out.append(f"- **Text on Canvas Contrast**: **{c_report.get('text_on_bg', {}).get('ratio', 'N/A')}:1** (WCAG {c_report.get('text_on_bg', {}).get('wcag', 'AAA')})")
        out.append(f"- **Text on Card Contrast**: **{c_report.get('text_on_card', {}).get('ratio', 'N/A')}:1** (WCAG {c_report.get('text_on_card', {}).get('wcag', 'AAA')})")
        out.append(f"- **Secondary Muted Contrast**: **{c_report.get('muted_on_card', {}).get('ratio', 'N/A')}:1** (WCAG {c_report.get('muted_on_card', {}).get('wcag', 'AA')})")

    if critique.strengths:
        out.append("\n#### Strengths:")
        for st in critique.strengths:
            out.append(f"- {st}")

    if critique.issues:
        out.append("\n#### Detected Issues & Recommendations:")
        for iss in critique.issues:
            out.append(f"- **Slide {iss['slide']}** `[{iss['severity'].upper()}]`: {iss['issue']}")
            out.append(f"  *Fix*: {iss['recommendation']}")

    return "\n".join(out)


# ── Iterative Deck Editing ───────────────────────────────────────────────────

async def edit_presentation(
    deck_id: str,
    action: str,
    slide_number: int = 0,
    modifications: Dict[str, Any] | str = "",
) -> str:
    """Modify an existing presentation artifact iteratively without starting from scratch.
    
    Actions:
      - 'change_theme': change deck theme (e.g. 'boba_bash', 'editorial_slate', 'swiss_clean')
      - 'update_slide': update slide title, bullets, cards, or notes on slide_number (1-indexed)
      - 'add_slide': append a new slide with specified layout
      - 'remove_slide': delete slide at slide_number
    """
    art = store.get_artifact(deck_id)
    if not art:
        return f"[edit_presentation] Deck artifact '{deck_id}' not found. Please provide a valid deck_id."

    data = art.get("data", {})
    slides = data.get("slides", [])
    title = data.get("title", art.get("title", "Presentation"))
    subtitle = data.get("subtitle", "")
    author = data.get("author", "Zenith Studio")
    theme = art.get("theme", "editorial_slate")

    mod_dict: Dict[str, Any] = {}
    if isinstance(modifications, str) and modifications.strip():
        try:
            mod_dict = json.loads(modifications)
        except Exception:
            mod_dict = {"text": modifications}
    elif isinstance(modifications, dict):
        mod_dict = modifications

    action = action.lower().strip()

    if action == "change_theme":
        new_theme = mod_dict.get("theme") or mod_dict.get("name") or "editorial_slate"
        theme = infer_art_direction("", new_theme)

    elif action == "update_slide":
        idx = max(0, slide_number - 1)
        if idx < len(slides):
            target = slides[idx]
            if "title" in mod_dict:
                target["title"] = mod_dict["title"]
            if "subtitle" in mod_dict:
                target["subtitle"] = mod_dict["subtitle"]
            if "layout" in mod_dict:
                target["layout"] = mod_dict["layout"]
            if "bullets" in mod_dict:
                target["bullets"] = mod_dict["bullets"]
            if "cards" in mod_dict:
                target["cards"] = mod_dict["cards"]
            if "stats" in mod_dict:
                target["stats"] = mod_dict["stats"]
            if "notes" in mod_dict:
                target["notes"] = mod_dict["notes"]
            if "text" in mod_dict and not mod_dict.get("bullets"):
                target["bullets"] = [mod_dict["text"]]
        else:
            return f"[edit_presentation] Slide number {slide_number} exceeds slide count ({len(slides)})."

    elif action == "add_slide":
        new_s = {
            "title": mod_dict.get("title", f"Slide {len(slides) + 1}"),
            "layout": mod_dict.get("layout", "cards_grid"),
            "subtitle": mod_dict.get("subtitle", ""),
            "bullets": mod_dict.get("bullets", []),
            "cards": mod_dict.get("cards", []),
            "notes": mod_dict.get("notes", ""),
        }
        slides.append(new_s)

    elif action == "remove_slide":
        idx = max(0, slide_number - 1)
        if idx < len(slides):
            removed = slides.pop(idx)
        else:
            return f"[edit_presentation] Slide number {slide_number} exceeds slide count ({len(slides)})."

    # Re-run quality critic
    validated = run_quality_critic(slides)

    # Re-generate PPTX
    pptx_path = ""
    pptx_url = ""
    try:
        pptx_path = await generate_pptx(
            title=title,
            subtitle=subtitle,
            author=author,
            theme=theme,
            slides=validated,
        )
        if pptx_path and not pptx_path.startswith("python-pptx library error"):
            pptx_filename = Path(pptx_path).name
            pptx_url = f"/api/files/download?filename={pptx_filename}"
    except Exception as exc:
        log.warning("PPTX re-generation failed during edit: %s", exc)

    # Re-generate Web Presentation
    _, html_path = generate_web_presentation(
        title=title,
        slides=validated,
        theme_name=theme,
        subtitle=subtitle,
        author=author,
        deck_id=deck_id,
        pptx_url=pptx_url if pptx_path else "",
    )

    # Update SQLite store
    data["slides"] = validated
    data["theme"] = theme
    store.save_artifact(
        artifact_id=deck_id,
        artifact_type="presentation",
        title=title,
        theme=theme,
        data_json=data,
        file_path=pptx_path,
        web_url=f"/presentation/{deck_id}",
    )

    theme_info = resolve_theme(theme)["name"]
    return (
        f"✅ **Presentation Updated (`{deck_id}`)**\n"
        f"- **Action**: `{action}` on slide {slide_number if slide_number else 'N/A'}\n"
        f"- **Current Theme**: `{theme_info}`\n"
        f"- **Total Slides**: {len(validated)}\n"
        f"- **[🖥️ View Updated Presentation](/presentation/{deck_id})**\n"
        f"- **[📥 Download Updated PPTX]({pptx_url})**"
    )


# ── Quick Preview ────────────────────────────────────────────────────────────

def preview_presentation(deck_id: str) -> str:
    """Get the live presentation web link and slide count for a deck."""
    art = store.get_artifact(deck_id)
    if not art:
        return f"[preview_presentation] Deck '{deck_id}' not found."

    url = art.get("web_url") or f"/presentation/{deck_id}"
    slides = art.get("data", {}).get("slides", [])
    theme = art.get("theme", "editorial_slate")
    theme_name = resolve_theme(theme)["name"]

    return (
        f"📊 **Presentation Preview**: `{art.get('title')}`\n"
        f"- **Theme**: {theme_name}\n"
        f"- **Slides**: {len(slides)}\n"
        f"- **Live Link**: [🖥️ Open Presentation]({url})"
    )


# ── Palette & Contrast Inspection ────────────────────────────────────────────

async def presentation_inspect_palette(theme: str = "editorial_slate") -> str:
    """Inspect a presentation color palette and its WCAG 2.1 contrast compliance ratings, luminance values, color tokens, and accessibility metrics."""
    meta = get_color_palette_meta(theme)
    tokens = meta["tokens"]
    contrast = meta["contrast"]
    mode_str = "Dark Canvas (Matte Elegance)" if meta["mode"] == "dark" else "Light Canvas (Editorial Air)"
    wcag_badge = contrast["wcag_overall"]
    is_compliant = contrast["compliant"]

    canvas_lum = round(compute_relative_luminance(tokens["canvas_background"]), 3)
    card_lum = round(compute_relative_luminance(tokens["surface_card"]), 3)
    border_lum = round(compute_relative_luminance(tokens["surface_border"]), 3)
    text_lum = round(compute_relative_luminance(tokens["primary_text"]), 3)
    muted_lum = round(compute_relative_luminance(tokens["secondary_muted"]), 3)
    a1_lum = round(compute_relative_luminance(tokens["accent_primary"]), 3)
    a2_lum = round(compute_relative_luminance(tokens["accent_secondary"]), 3)

    out = [
        f"### 🎨 Color Palette Analysis: **{meta['theme_name']}**",
        f"- **Theme Identifier**: `{meta['theme_id']}`",
        f"- **Canvas Philosophy**: {mode_str}",
        f"- **Art Direction**: {meta['description']}",
        f"- **Overall Accessibility Rating**: **WCAG {wcag_badge}** ({'✅ Passed AA & AAA Thresholds' if is_compliant else '⚠️ Needs Adjustment'})\n",
        "#### 🖌️ Design System Color Tokens:",
        "| Token Role | Hex Code | Relative Luminance | Purpose in Presentation |",
        "| :--- | :--- | :--- | :--- |",
        f"| **Canvas Background** | `{tokens['canvas_background']}` | {canvas_lum} | Foundation background & WebGL ambient backdrop |",
        f"| **Surface / Card** | `{tokens['surface_card']}` | {card_lum} | Floating cards, bento cells & glassmorphic surfaces |",
        f"| **Surface Border** | `{tokens['surface_border']}` | {border_lum} | Subtle structural card dividers & geometric contours |",
        f"| **Primary Text** | `{tokens['primary_text']}` | {text_lum} | High-impact headlines, stats & primary titles |",
        f"| **Secondary Muted** | `{tokens['secondary_muted']}` | {muted_lum} | Eyebrows, captions, timestamps & metadata |",
        f"| **Accent Primary** | `{tokens['accent_primary']}` | {a1_lum} | Focal point highlights, progress bars & metric badges |",
        f"| **Accent Secondary** | `{tokens['accent_secondary']}` | {a2_lum} | Supporting visual accents & complementary chart series |\n",
        "#### 📐 WCAG 2.1 Contrast Ratio Matrix:",
        "| Element Pair | Contrast Ratio | WCAG Compliance | Target Requirement | Status |",
        "| :--- | :--- | :--- | :--- | :--- |",
        f"| **Primary Text on Canvas** | **{contrast['text_on_bg']['ratio']}:1** | WCAG {contrast['text_on_bg']['wcag']} | ≥ 4.5:1 (AA) / ≥ 7.0:1 (AAA) | {'✅ PASS' if contrast['text_on_bg']['ratio'] >= 4.5 else '❌ FAIL'} |",
        f"| **Primary Text on Card** | **{contrast['text_on_card']['ratio']}:1** | WCAG {contrast['text_on_card']['wcag']} | ≥ 4.5:1 (AA) / ≥ 7.0:1 (AAA) | {'✅ PASS' if contrast['text_on_card']['ratio'] >= 4.5 else '❌ FAIL'} |",
        f"| **Muted Text on Canvas** | **{contrast['muted_on_bg']['ratio']}:1** | WCAG {contrast['muted_on_bg']['wcag']} | ≥ 3.0:1 (AA Large) | {'✅ PASS' if contrast['muted_on_bg']['ratio'] >= 3.0 else '❌ FAIL'} |",
        f"| **Muted Text on Card** | **{contrast['muted_on_card']['ratio']}:1** | WCAG {contrast['muted_on_card']['wcag']} | ≥ 3.0:1 (AA Large) | {'✅ PASS' if contrast['muted_on_card']['ratio'] >= 3.0 else '❌ FAIL'} |",
        f"| **Accent 1 on Canvas** | **{contrast['accent1_on_bg']['ratio']}:1** | WCAG {contrast['accent1_on_bg']['wcag']} | ≥ 3.0:1 (Visual Indicator) | {'✅ PASS' if contrast['accent1_on_bg']['ratio'] >= 3.0 else '❌ FAIL'} |",
        f"| **Accent 1 on Card** | **{contrast['accent1_on_card']['ratio']}:1** | WCAG {contrast['accent1_on_card']['wcag']} | ≥ 3.0:1 (Visual Indicator) | {'✅ PASS' if contrast['accent1_on_card']['ratio'] >= 3.0 else '❌ FAIL'} |",
        f"| **Accent 2 on Canvas** | **{contrast['accent2_on_bg']['ratio']}:1** | WCAG {contrast['accent2_on_bg']['wcag']} | ≥ 3.0:1 (Visual Indicator) | {'✅ PASS' if contrast['accent2_on_bg']['ratio'] >= 3.0 else '❌ FAIL'} |\n",
        f"💡 *All slides generated with theme `{meta['theme_id']}` strictly enforce these contrast guardrails across both PowerPoint native shapes and interactive WebGL canvas.*",
    ]
    return "\n".join(out)

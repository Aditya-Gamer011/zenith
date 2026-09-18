"""Zenith Visual Design System & Component Registry.

Provides human-crafted, studio-grade design constraints, named themes, typography scales,
layout primitives, and visual component presets for presentations and documents.
Designed to feel human-directed, editorial, and sophisticated—NEVER generic AI neon/purple slop.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

THEMES: Dict[str, Dict[str, Any]] = {
    # ── 1. STUDIO EDITORIAL (Default) ─────────────────────────────────────────
    # Inspired by Pentagram, Linear, and modern luxury editorial publications.
    # Restrained, elegant, warm slate/charcoal with brushed amber or cobalt hairline accents.
    "editorial_slate": {
        "name": "Studio Editorial",
        "description": "Restrained, human-crafted editorial aesthetic. Deep warm charcoal, crisp typography, and subtle brushed champagne accents.",
        "font_heading": "'Plus Jakarta Sans', 'Inter', -apple-system, sans-serif",
        "font_body": "'Inter', -apple-system, sans-serif",
        "font_mono": "'JetBrains Mono', monospace",
        "colors": {
            "bg": "#0D0F12",          # Warm obsidian slate
            "bg_rgb": (13, 15, 18),
            "card": "#181B20",        # Matte slate surface
            "card_rgb": (24, 27, 32),
            "card_glass": "rgba(24, 27, 32, 0.78)",
            "border": "#2A2E37",      # Subtle 1px hairline border
            "border_rgb": (42, 46, 55),
            "text": "#F4F4F6",        # Crisp off-white (no eye strain)
            "text_rgb": (244, 244, 246),
            "muted": "#8E95A2",       # Sophisticated stone muted
            "muted_rgb": (142, 149, 162),
            "accent1": "#D4A373",     # Brushed Champagne / Warm Amber
            "accent1_rgb": (212, 163, 115),
            "accent2": "#3B82F6",     # Clear Cobalt
            "accent2_rgb": (59, 130, 246),
            "glow": "rgba(212, 163, 115, 0.15)",  # Very subtle, refined ambient glow
        },
        "canvas_effect": "ambient_particles",  # Subtle floating stardust, not lasers
    },

    # ── 2. BOBA BASH BRAND ────────────────────────────────────────────────────
    # Bespoke brand aesthetic: creamy milk tea, roasted brown sugar pearls, matcha green.
    "boba_bash": {
        "name": "Boba Bash Brand",
        "description": "Playful, tactile beverage brand with creamy milk tea, roasted brown sugar pearls, matcha green, and warm cream.",
        "font_heading": "'Plus Jakarta Sans', 'Outfit', sans-serif",
        "font_body": "'Outfit', 'Inter', sans-serif",
        "font_mono": "'JetBrains Mono', monospace",
        "colors": {
            "bg": "#14110F",          # Roasted brown sugar dark background
            "bg_rgb": (20, 17, 15),
            "card": "#241D19",        # Warm milk tea dark card
            "card_rgb": (36, 29, 25),
            "card_glass": "rgba(36, 29, 25, 0.82)",
            "border": "#42352D",
            "border_rgb": (66, 53, 45),
            "text": "#FDFBF7",        # Creamy foam white
            "text_rgb": (253, 251, 247),
            "muted": "#C2B29F",       # Oat milk muted
            "muted_rgb": (194, 178, 159),
            "accent1": "#DDA15E",     # Warm Amber Boba Pearl
            "accent1_rgb": (221, 161, 94),
            "accent2": "#606C38",     # Ceremonial Matcha Green
            "accent2_rgb": (96, 108, 56),
            "glow": "rgba(221, 161, 94, 0.2)",
        },
        "canvas_effect": "floating_pearls",
    },

    # ── 3. SWISS CLEAN / APPLE KEYNOTE ────────────────────────────────────────
    # Pure architectural daylight. Crisp white, charcoal text, international accent.
    "swiss_clean": {
        "name": "Swiss Modern Clean",
        "description": "Inspired by Swiss graphic design and Apple keynotes. Crisp white paper, high contrast typography, and architectural precision.",
        "font_heading": "'Inter', -apple-system, sans-serif",
        "font_body": "'Inter', -apple-system, sans-serif",
        "font_mono": "'JetBrains Mono', monospace",
        "colors": {
            "bg": "#F8FAFC",          # Daylight white
            "bg_rgb": (248, 250, 252),
            "card": "#FFFFFF",        # Pure crisp card
            "card_rgb": (255, 255, 255),
            "card_glass": "rgba(255, 255, 255, 0.92)",
            "border": "#E2E8F0",      # Clean minimal border
            "border_rgb": (226, 232, 240),
            "text": "#0F172A",        # Deep ink slate
            "text_rgb": (15, 23, 42),
            "muted": "#64748B",       # Architectural slate
            "muted_rgb": (100, 116, 139),
            "accent1": "#0284C7",     # Precision Sky Blue
            "accent1_rgb": (2, 132, 199),
            "accent2": "#EA580C",     # International Orange / Vermillion
            "accent2_rgb": (234, 88, 12),
            "glow": "rgba(2, 132, 199, 0.08)",
        },
        "canvas_effect": "subtle_lines",
    },

    # ── 4. TERRACOTTA & SAGE ──────────────────────────────────────────────────
    # Earthy, human, magazine-like warmth.
    "terracotta_warm": {
        "name": "Terracotta & Sage",
        "description": "Warm, tactile, human aesthetic with baked terracotta, rich charcoal, and calm sage green accents.",
        "font_heading": "'Playfair Display', Georgia, serif",
        "font_body": "'Plus Jakarta Sans', sans-serif",
        "font_mono": "'JetBrains Mono', monospace",
        "colors": {
            "bg": "#181412",
            "bg_rgb": (24, 20, 18),
            "card": "#26201D",
            "card_rgb": (38, 32, 29),
            "card_glass": "rgba(38, 32, 29, 0.82)",
            "border": "#3D342E",
            "border_rgb": (61, 52, 46),
            "text": "#FDFBF7",
            "text_rgb": (253, 251, 247),
            "muted": "#B5A79E",
            "muted_rgb": (181, 167, 158),
            "accent1": "#E07A5F",     # Terracotta Clay
            "accent1_rgb": (224, 122, 95),
            "accent2": "#81B29A",     # Muted Sage
            "accent2_rgb": (129, 178, 154),
            "glow": "rgba(224, 122, 95, 0.18)",
        },
        "canvas_effect": "ambient_particles",
    },

    # ── 5. NORDIC FJORD NAVY ──────────────────────────────────────────────────
    # Deep maritime navy, crisp ice white, and clear northern sky blue.
    "nordic_navy": {
        "name": "Nordic Navy",
        "description": "Scandinavian depth with midnight oceanic navy, crisp iceberg typography, and calm cobalt accents.",
        "font_heading": "'Inter', -apple-system, sans-serif",
        "font_body": "'Inter', sans-serif",
        "font_mono": "'JetBrains Mono', monospace",
        "colors": {
            "bg": "#09111E",          # Deep fjord navy
            "bg_rgb": (9, 17, 30),
            "card": "#132034",        # Maritime slate card
            "card_rgb": (19, 32, 52),
            "card_glass": "rgba(19, 32, 52, 0.8)",
            "border": "#1E3452",
            "border_rgb": (30, 52, 82),
            "text": "#F8FAFC",
            "text_rgb": (248, 250, 252),
            "muted": "#8BA0BA",
            "muted_rgb": (139, 160, 186),
            "accent1": "#38BDF8",     # Ice Sky Blue
            "accent1_rgb": (56, 189, 248),
            "accent2": "#818CF8",     # Indigo Dawn
            "accent2_rgb": (129, 140, 248),
            "glow": "rgba(56, 189, 248, 0.18)",
        },
        "canvas_effect": "ambient_particles",
    },

    # ── 6. EXECUTIVE MONOCHROME ───────────────────────────────────────────────
    # High-contrast black & white executive deck (Warren Buffett / Stripe Press vibe).
    "executive_mono": {
        "name": "Executive Monochrome",
        "description": "Timeless, confident black and titanium white. Zero distractions, pure typography and structural clarity.",
        "font_heading": "'Inter', -apple-system, sans-serif",
        "font_body": "'Inter', sans-serif",
        "font_mono": "'JetBrains Mono', monospace",
        "colors": {
            "bg": "#0A0A0A",
            "bg_rgb": (10, 10, 10),
            "card": "#161616",
            "card_rgb": (22, 22, 22),
            "card_glass": "rgba(22, 22, 22, 0.85)",
            "border": "#282828",
            "border_rgb": (40, 40, 40),
            "text": "#FFFFFF",
            "text_rgb": (255, 255, 255),
            "muted": "#888888",
            "muted_rgb": (136, 136, 136),
            "accent1": "#E5E5E5",     # Titanium Silver
            "accent1_rgb": (229, 229, 229),
            "accent2": "#737373",     # Neutral Steel
            "accent2_rgb": (115, 115, 115),
            "glow": "rgba(255, 255, 255, 0.08)",
        },
        "canvas_effect": "subtle_lines",
    },

    # ── 7. OPTIONAL: CYBERPUNK NEON (Available on explicit request, never default) ─
    "cyberpunk_neon": {
        "name": "Cyberpunk Neon (Sci-Fi Keynote)",
        "description": "Explicit high-energy futuristic keynote with pitch-black void, neon cyan, and magenta HUD lines.",
        "font_heading": "'Syne', 'Inter', sans-serif",
        "font_body": "'Inter', sans-serif",
        "font_mono": "'JetBrains Mono', monospace",
        "colors": {
            "bg": "#08090C",
            "bg_rgb": (8, 9, 12),
            "card": "#12141C",
            "card_rgb": (18, 20, 28),
            "card_glass": "rgba(18, 20, 28, 0.82)",
            "border": "#2A2F45",
            "border_rgb": (42, 47, 69),
            "text": "#FFFFFF",
            "text_rgb": (255, 255, 255),
            "muted": "#8A95A5",
            "muted_rgb": (138, 149, 165),
            "accent1": "#00F3FF",
            "accent1_rgb": (0, 243, 255),
            "accent2": "#FF007F",
            "accent2_rgb": (255, 0, 127),
            "glow": "rgba(0, 243, 255, 0.28)",
        },
        "canvas_effect": "matrix_grid",
    },
}

# Aliases and backward compatibility
THEMES["default"] = THEMES["editorial_slate"]
THEMES["executive_dark"] = THEMES["editorial_slate"]
THEMES["dark"] = THEMES["editorial_slate"]
THEMES["light"] = THEMES["swiss_clean"]
THEMES["corporate_light"] = THEMES["swiss_clean"]
THEMES["minimal_mono"] = THEMES["executive_mono"]


# ── Design Constraints & Rules ───────────────────────────────────────────────
DESIGN_CONSTRAINTS = {
    "max_bullets_per_slide": 4,
    "max_words_per_bullet": 15,
    "max_chars_per_title": 65,
    "max_cards_per_grid": 4,
    "max_stats_per_row": 4,
    "min_contrast_ratio": 4.5,
    "default_motion_intensity": "high",  # 'subtle' | 'high' | 'extreme'
    "default_theme": "editorial_slate",  # NEVER neon AI slop
}


# ── Layout Primitives Catalog ────────────────────────────────────────────────
LAYOUT_PRIMITIVES = [
    "hero_title",      # Opening statement, bold typography, optional photo or 3D hero
    "split_hero",      # 50/50 split: key takeaway on left, visual/photo on right
    "cards_grid",      # 2, 3, or 4 clean matte cards with micro-labels
    "stat_hero",       # 3 or 4 oversized KPI metric counters with subtext
    "comparison",      # Side-by-side comparison (Before vs After, Legacy vs Modern)
    "timeline",        # Milestone roadmap with clean connected nodes
    "process_steps",   # Sequenced steps or architectural workflow
    "chart_hero",      # Embedded chart visualization with bullet takeaways
    "quote_callout",   # Elegant editorial quote with attribution
    "case_study",      # Challenge, Solution, Impact 3-part layout
    "chapter_divider", # Bold transitional slide separating sections
    "photo_story",     # Visual-first slide with photography and concise caption
]


def resolve_theme(theme_name: str | None) -> Dict[str, Any]:
    """Resolve theme configuration with graceful fallback to human-crafted editorial_slate."""
    if not theme_name:
        return THEMES["editorial_slate"]
    key = str(theme_name).lower().strip().replace("-", "_").replace(" ", "_")
    return THEMES.get(key, THEMES.get(key.split("_")[0], THEMES["editorial_slate"]))


def list_theme_summaries() -> List[Dict[str, str]]:
    """List available themes with description and primary color accents."""
    return [
        {
            "id": key,
            "name": t["name"],
            "description": t["description"],
            "accent1": t["colors"]["accent1"],
            "accent2": t["colors"]["accent2"],
            "bg": t["colors"]["bg"],
        }
        for key, t in THEMES.items()
        if key not in ("dark", "light", "corporate_light", "minimal_mono", "default", "executive_dark")
    ]


# ── Color Awareness & Contrast Calculations (WCAG 2.1) ───────────────────────

def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
    """Convert hex string '#RRGGBB' to (R, G, B) tuple."""
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        return (255, 255, 255)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Convert (R, G, B) tuple to hex string '#RRGGBB'."""
    r, g, b = [max(0, min(255, int(v))) for v in rgb]
    return f"#{r:02X}{g:02X}{b:02X}"


def compute_relative_luminance(rgb_or_hex: Tuple[int, int, int] | str) -> float:
    """Calculate relative luminance according to WCAG 2.1 specifications."""
    if isinstance(rgb_or_hex, str):
        rgb = hex_to_rgb(rgb_or_hex)
    else:
        rgb = rgb_or_hex

    r, g, b = [x / 255.0 for x in rgb]

    def _adjust(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _adjust(r) + 0.7152 * _adjust(g) + 0.0722 * _adjust(b)


def compute_contrast_ratio(c1: Tuple[int, int, int] | str, c2: Tuple[int, int, int] | str) -> float:
    """Calculate WCAG contrast ratio between two colors (range: 1.0 to 21.0)."""
    l1 = compute_relative_luminance(c1)
    l2 = compute_relative_luminance(c2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def get_wcag_rating(ratio: float, is_large_text: bool = False) -> str:
    """Return WCAG 2.1 compliance rating for a given contrast ratio."""
    if is_large_text:
        if ratio >= 4.5:
            return "AAA"
        elif ratio >= 3.0:
            return "AA"
        return "Fail"
    else:
        if ratio >= 7.0:
            return "AAA"
        elif ratio >= 4.5:
            return "AA"
        elif ratio >= 3.0:
            return "AA-Large"
        return "Fail"


def auto_adjust_contrast(
    fg: Tuple[int, int, int] | str,
    bg: Tuple[int, int, int] | str,
    min_ratio: float = 4.5,
) -> Tuple[int, int, int]:
    """Automatically adjust foreground color to guarantee minimum WCAG contrast ratio against background."""
    fg_rgb = hex_to_rgb(fg) if isinstance(fg, str) else tuple(fg)
    bg_rgb = hex_to_rgb(bg) if isinstance(bg, str) else tuple(bg)

    current_ratio = compute_contrast_ratio(fg_rgb, bg_rgb)
    if current_ratio >= min_ratio:
        return fg_rgb

    bg_lum = compute_relative_luminance(bg_rgb)
    should_lighten = bg_lum < 0.5

    r, g, b = fg_rgb
    for step in range(1, 100):
        factor = step / 100.0
        if should_lighten:
            nr = int(r + (255 - r) * factor)
            ng = int(g + (255 - g) * factor)
            nb = int(b + (255 - b) * factor)
        else:
            nr = int(r * (1 - factor))
            ng = int(g * (1 - factor))
            nb = int(b * (1 - factor))

        candidate = (nr, ng, nb)
        if compute_contrast_ratio(candidate, bg_rgb) >= min_ratio:
            return candidate

    return (255, 255, 255) if should_lighten else (15, 23, 42)


def evaluate_palette_contrast(colors: Dict[str, Any]) -> Dict[str, Any]:
    """Comprehensive accessibility and contrast audit for a color palette."""
    bg = colors.get("bg", "#000000")
    card = colors.get("card", "#111111")
    text = colors.get("text", "#FFFFFF")
    muted = colors.get("muted", "#888888")
    accent1 = colors.get("accent1", "#3B82F6")
    accent2 = colors.get("accent2", "#10B981")

    t_bg_ratio = compute_contrast_ratio(text, bg)
    t_card_ratio = compute_contrast_ratio(text, card)
    m_bg_ratio = compute_contrast_ratio(muted, bg)
    m_card_ratio = compute_contrast_ratio(muted, card)
    a1_bg_ratio = compute_contrast_ratio(accent1, bg)
    a1_card_ratio = compute_contrast_ratio(accent1, card)
    a2_bg_ratio = compute_contrast_ratio(accent2, bg)

    is_dark = compute_relative_luminance(bg) < 0.5
    overall_compliant = t_bg_ratio >= 4.5 and t_card_ratio >= 4.5 and m_bg_ratio >= 3.0

    return {
        "is_dark_canvas": is_dark,
        "text_on_bg": {"ratio": t_bg_ratio, "wcag": get_wcag_rating(t_bg_ratio)},
        "text_on_card": {"ratio": t_card_ratio, "wcag": get_wcag_rating(t_card_ratio)},
        "muted_on_bg": {"ratio": m_bg_ratio, "wcag": get_wcag_rating(m_bg_ratio, is_large_text=True)},
        "muted_on_card": {"ratio": m_card_ratio, "wcag": get_wcag_rating(m_card_ratio, is_large_text=True)},
        "accent1_on_bg": {"ratio": a1_bg_ratio, "wcag": get_wcag_rating(a1_bg_ratio, is_large_text=True)},
        "accent1_on_card": {"ratio": a1_card_ratio, "wcag": get_wcag_rating(a1_card_ratio, is_large_text=True)},
        "accent2_on_bg": {"ratio": a2_bg_ratio, "wcag": get_wcag_rating(a2_bg_ratio, is_large_text=True)},
        "wcag_overall": "AAA" if (t_bg_ratio >= 7.0 and t_card_ratio >= 7.0 and m_card_ratio >= 4.5) else ("AA" if overall_compliant else "Fail"),
        "compliant": overall_compliant,
    }


def get_color_palette_meta(theme_name: str | None = None) -> Dict[str, Any]:
    """Retrieve full color tokens, semantics, and WCAG contrast evaluations for a theme."""
    theme = resolve_theme(theme_name)
    colors = theme["colors"]
    contrast_eval = evaluate_palette_contrast(colors)

    return {
        "theme_id": theme_name or "editorial_slate",
        "theme_name": theme["name"],
        "description": theme["description"],
        "mode": "dark" if contrast_eval["is_dark_canvas"] else "light",
        "tokens": {
            "canvas_background": colors["bg"],
            "surface_card": colors["card"],
            "surface_border": colors["border"],
            "primary_text": colors["text"],
            "secondary_muted": colors["muted"],
            "accent_primary": colors["accent1"],
            "accent_secondary": colors["accent2"],
        },
        "contrast": contrast_eval,
    }

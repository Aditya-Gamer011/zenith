"""Zenith Visual Style System, Visual Intensity & Rhythm Architecture.

Implements the 5 named visual styles, 1-5 visual intensity scale, and the
visualRhythm sequencing engine to ensure presentations alternate cadence and
prevent visual fatigue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── 1. The 5 Named Visual Styles ─────────────────────────────────────────────

@dataclass
class VisualStyle:
    id: str
    name: str
    description: str
    default_theme: str
    font_heading: str
    font_body: str
    font_mono: str
    typography_traits: List[str]
    layout_preferences: List[str]
    motion_traits: List[str]
    intensity_default: int
    characteristics: List[str]


VISUAL_STYLES: Dict[str, VisualStyle] = {
    "cinematic-futuristic": VisualStyle(
        id="cinematic-futuristic",
        name="Cinematic Futuristic",
        description="Dark void backgrounds, oversized kinetic typography, luminous accents, 3D floating meshes, dramatic depth, particles, and light beams.",
        default_theme="cyberpunk_neon",
        font_heading="Syne",
        font_body="Inter",
        font_mono="JetBrains Mono",
        typography_traits=["oversized headlines", "all-caps eyebrows", "gradient highlights", "letter-spacing tracking"],
        layout_preferences=["cinematic-hero", "split-screen", "bento", "data-story"],
        motion_traits=["stagger-reveal", "zoom", "morph", "continuous-float"],
        intensity_default=5,
        characteristics=["particles", "light-beam", "3d-orb", "glow", "high-contrast"],
    ),
    "premium-editorial": VisualStyle(
        id="premium-editorial",
        name="Premium Editorial",
        description="Asymmetric editorial grids, giant serif/sans typography, sophisticated whitespace, crisp photographic crops, and restrained champagne/cobalt hairline accents.",
        default_theme="editorial_slate",
        font_heading="Plus Jakarta Sans",
        font_body="Inter",
        font_mono="JetBrains Mono",
        typography_traits=["giant editorial titles", "small refined captions", "split headlines", "deliberate italics"],
        layout_preferences=["editorial", "statement", "case-study", "bento", "split-screen"],
        motion_traits=["fade", "slide-up", "gentle-reveal"],
        intensity_default=3,
        characteristics=["grain", "glass", "asymmetry", "generous-whitespace", "curated-palette"],
    ),
    "experimental-creative": VisualStyle(
        id="experimental-creative",
        name="Experimental / Creative",
        description="Unconventional compositions, typography treated as large graphic art, overlapping geometric elements, extreme scale contrasts, and bold visual dynamism.",
        default_theme="terracotta_warm",
        font_heading="Playfair Display",
        font_body="Plus Jakarta Sans",
        font_mono="JetBrains Mono",
        typography_traits=["extreme scale differences", "overlapping text", "vertical typography", "kinetic numbers"],
        layout_preferences=["statement", "image-bleed", "comparison", "bento"],
        motion_traits=["morph", "scale", "stagger-reveal"],
        intensity_default=4,
        characteristics=["abstract-shapes", "overlapping-cards", "high-energy", "distinctive-grids"],
    ),
    "playful-youthful": VisualStyle(
        id="playful-youthful",
        name="Playful / Youthful",
        description="Tactile, vibrant, warm brand aesthetic with rounded containers, energetic accents, illustrative pills, and bouncy expressive typography.",
        default_theme="boba_bash",
        font_heading="Outfit",
        font_body="Inter",
        font_mono="JetBrains Mono",
        typography_traits=["rounded geometric headings", "badge pills", "friendly weights"],
        layout_preferences=["cards-grid", "process", "timeline", "split-screen"],
        motion_traits=["spring", "bounce", "zoom"],
        intensity_default=3,
        characteristics=["rounded-pills", "warm-tones", "friendly-icons", "tactile-cards"],
    ),
    "minimal-premium": VisualStyle(
        id="minimal-premium",
        name="Minimal Premium (Swiss Clean)",
        description="Inspired by Swiss international graphic design and Apple keynotes. Crisp white paper or jet black, architectural precision, vast whitespace, and pure structural clarity.",
        default_theme="swiss_clean",
        font_heading="Inter",
        font_body="Inter",
        font_mono="JetBrains Mono",
        typography_traits=["monolithic sans-serif", "single bold focal points", "exact alignment"],
        layout_preferences=["statement", "editorial", "split-screen", "data-story"],
        motion_traits=["fade", "slide-up"],
        intensity_default=2,
        characteristics=["vast-whitespace", "razor-thin-borders", "zero-noise", "editorial-clarity"],
    ),
}


# ── 2. Visual Intensity Constraints ──────────────────────────────────────────

INTENSITY_CONSTRAINTS: Dict[int, Dict[str, Any]] = {
    1: {
        "label": "Minimal",
        "max_effects_per_slide": 0,
        "use_3d": False,
        "max_cards_per_grid": 2,
        "whitespace_ratio": "extreme",
        "description": "Pure typography and whitespace. Zero decorative noise.",
    },
    2: {
        "label": "Clean",
        "max_effects_per_slide": 1,
        "use_3d": False,
        "max_cards_per_grid": 3,
        "whitespace_ratio": "generous",
        "description": "Structured cards, crisp hairline borders, subtle single accents.",
    },
    3: {
        "label": "Modern",
        "max_effects_per_slide": 2,
        "use_3d": True,
        "max_cards_per_grid": 4,
        "whitespace_ratio": "balanced",
        "description": "Glass cards, subtle glow badges, light gradient accents.",
    },
    4: {
        "label": "Highly Art Directed",
        "max_effects_per_slide": 3,
        "use_3d": True,
        "max_cards_per_grid": 4,
        "whitespace_ratio": "dynamic",
        "description": "Bento grid, 3D accents, directional light beams, layered cards.",
    },
    5: {
        "label": "Cinematic / Experimental",
        "max_effects_per_slide": 4,
        "use_3d": True,
        "max_cards_per_grid": 4,
        "whitespace_ratio": "cinematic",
        "description": "3D floating geometries, particle fields, kinetic typography, spotlights, dramatic depth.",
    },
}


# ── 3. Visual Rhythm Sequences ───────────────────────────────────────────────

STANDARD_RHYTHM_PATTERNS: Dict[str, List[str]] = {
    "pitch_deck": [
        "high-impact",     # Slide 1: Opening Hero statement
        "breathing-room",  # Slide 2: The Big Opportunity (Breathing room)
        "data-story",      # Slide 3: Market Size & KPI traction
        "bento-grid",      # Slide 4: Core Solution & Key pillars
        "process-flow",    # Slide 5: How It Works / Product Flow
        "cinematic",       # Slide 6: Moat & Technology Engine
        "case-study",      # Slide 7: Customer Impact & Validation
        "giant-stat",      # Slide 8: Revenue Scale & Projections
        "summary",         # Slide 9: Strategic Roadmap & Execution
        "final-hero",      # Slide 10: The Ask / Visionary Closing
    ],
    "tech_overview": [
        "high-impact",     # Slide 1: System Title & Vision
        "bento-grid",      # Slide 2: Architectural Overview & Tiers
        "data-story",      # Slide 3: Performance SLAs & Latency Metrics
        "process-flow",    # Slide 4: Ingestion & Transaction Pipeline
        "breathing-room",  # Slide 5: Core Engineering Principles
        "cinematic",       # Slide 6: Distributed Consensus & Sandbox
        "comparison",      # Slide 7: Legacy vs Sovereign Architecture
        "summary",         # Slide 8: Observability & Production Vitals
    ],
    "general": [
        "high-impact",
        "breathing-room",
        "bento-grid",
        "data-story",
        "process-flow",
        "summary",
        "final-hero",
    ],
}


def infer_visual_style(topic: str, requested_style: str = "") -> Tuple[str, int]:
    """Select the optimal visual style and intensity based on topic brief."""
    if requested_style:
        key = requested_style.lower().strip().replace(" ", "-").replace("_", "-")
        if key in VISUAL_STYLES:
            return key, VISUAL_STYLES[key].intensity_default

    t = (topic or "").lower()

    if any(w in t for w in ("ai", "cyber", "future", "autonomous", "matrix", "agent", "gpu", "neural", "sci-fi")):
        return "cinematic-futuristic", 5
    elif any(w in t for w in ("apple", "clean", "swiss", "minimal", "report", "academic", "white")):
        return "minimal-premium", 2
    elif any(w in t for w in ("tea", "boba", "food", "snack", "youth", "fun", "game", "social", "community")):
        return "playful-youthful", 3
    elif any(w in t for w in ("art", "creative", "experimental", "music", "fashion", "film", "studio")):
        return "experimental-creative", 4

    # Default: Premium Editorial
    return "premium-editorial", 4


def generate_visual_rhythm(num_slides: int, deck_type: str = "general") -> List[str]:
    """Generate a balanced visual rhythm cadence alternating high-impact and breathing room."""
    pattern = STANDARD_RHYTHM_PATTERNS.get(deck_type, STANDARD_RHYTHM_PATTERNS["general"])

    if num_slides <= len(pattern):
        # Trim but always ensure last slide is a closing hero
        seq = pattern[:num_slides - 1] + [pattern[-1]]
        return seq

    # If more slides, repeat the alternating middle sequence
    middle_pool = ["breathing-room", "data-story", "bento-grid", "process-flow", "case-study", "cinematic"]
    seq = [pattern[0]]
    for i in range(1, num_slides - 1):
        seq.append(middle_pool[(i - 1) % len(middle_pool)])
    seq.append(pattern[-1])
    return seq

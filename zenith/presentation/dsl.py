"""Zenith Presentation DSL (Domain Specific Language).

Defines the intermediate declarative schema between the LLM / Presentation Planner
and the native PowerPoint renderer. Enables structured composition of layouts,
components, effects, 3D assets, typography treatments, and animations.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AnimationSpec:
    """Animation and motion transition descriptor for PPTX elements."""
    animation: str = "fade"  # fade, reveal, stagger-reveal, zoom, slide-up, scale, morph
    duration: float = 0.5    # seconds
    delay: float = 0.0       # seconds
    direction: str = "up"    # up, down, left, right
    easing: str = "easeOut"  # easeOut, easeInOut, linear


@dataclass
class PositionSpec:
    """Position and dimension coordinates in inches (16:9 widescreen: 13.333 x 7.5)."""
    left: float
    top: float
    width: float
    height: float


@dataclass
class SlideElement:
    """A single visual component or visual primitive on a slide."""
    type: str  # typography, card, stat, chart, 3d, process, timeline, comparison, mockup, effect
    variant: str = ""  # kinetic-title, giant-number, glass-card, chrome-orb, etc.
    text: str = ""
    eyebrow: str = ""
    subtitle: str = ""
    highlight_words: List[str] = field(default_factory=list)
    position: Optional[Dict[str, float]] = None  # {"left": x, "top": y, "width": w, "height": h}
    style: Dict[str, Any] = field(default_factory=dict)
    data: Dict[str, Any] = field(default_factory=dict)  # stats, cards, steps, chart series
    animation: Optional[Dict[str, Any]] = None
    asset: str = ""  # e.g. "chrome-orb", "glass-sphere", "network-grid"
    scale: float = 1.0


@dataclass
class SlideDSL:
    """Declarative specification for a single presentation slide."""
    slide_number: int
    layout: str  # cinematic-hero, editorial, split-screen, bento, statement, timeline, process, etc.
    style: str = "cinematic-futuristic"  # cinematic-futuristic, premium-editorial, minimal-premium, etc.
    intensity: int = 4  # 1 to 5
    rhythm: str = "high-impact"  # high-impact, breathing-room, data-story, bento-grid, process-flow, etc.
    title: str = ""
    eyebrow: str = ""
    subtitle: str = ""
    tag: str = ""
    elements: List[SlideElement] = field(default_factory=list)
    transition: str = "fade"  # fade, morph, push, wipe, zoom
    speaker_notes: str = ""
    background_override: Optional[str] = None  # custom color or gradient


@dataclass
class PresentationDSL:
    """Complete declarative presentation specification."""
    title: str
    topic: str
    style: str = "cinematic-futuristic"
    theme: str = "editorial_slate"
    intensity: int = 4
    author: str = "Zenith Creative Director"
    subtitle: str = ""
    visual_rhythm: List[str] = field(default_factory=list)
    slides: List[SlideDSL] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    palette_meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert DSL instance to JSON-serializable dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert DSL instance to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PresentationDSL:
        """Parse PresentationDSL from dictionary."""
        slides_data = data.get("slides", [])
        slides = []
        for s in slides_data:
            elements_data = s.get("elements", [])
            elements = [SlideElement(**e) if isinstance(e, dict) else e for e in elements_data]
            s_copy = dict(s)
            s_copy["elements"] = elements
            slides.append(SlideDSL(**s_copy))

        p_data = dict(data)
        p_data["slides"] = slides
        return cls(**p_data)

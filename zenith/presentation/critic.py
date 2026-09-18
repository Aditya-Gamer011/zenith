"""Zenith Visual Quality Critic & Auto-Refinement Engine.

Inspects PresentationDSL for:
- Text overflow and excessive word density
- Slide bounds clipping (13.333 x 7.5 inches widescreen)
- Visual hierarchy and "One Big Idea" focus
- Visual rhythm pacing (alternation between high density and breathing room)
- Theme contrast consistency

Automatically refines and repairs presentation specifications before rendering.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from zenith.tools.design_system import (
    DESIGN_CONSTRAINTS,
    resolve_theme,
    evaluate_palette_contrast,
    get_color_palette_meta,
    compute_contrast_ratio,
    auto_adjust_contrast,
)
from .dsl import PresentationDSL, SlideDSL, SlideElement
from .styles import INTENSITY_CONSTRAINTS

log = logging.getLogger("zenith.presentation.critic")


@dataclass
class CriticIssue:
    slide: int
    severity: str  # high, medium, low
    category: str  # overflow, density, rhythm, bounds, hierarchy, contrast
    issue: str
    recommendation: str


@dataclass
class CritiqueResult:
    score: int  # 0 to 100
    passed: bool
    total_slides: int
    issues: List[Dict[str, Any]]
    strengths: List[str]
    contrast_report: Dict[str, Any] = field(default_factory=dict)
    palette_info: Dict[str, Any] = field(default_factory=dict)


class VisualQualityCritic:
    """Evaluates slide composition quality, readability, pacing, and WCAG color contrast."""

    def __init__(self, passing_score: int = 85) -> None:
        self.passing_score = passing_score

    def critique(self, dsl: PresentationDSL) -> CritiqueResult:
        """Run multi-tier deterministic, design, and color contrast critique on PresentationDSL."""
        issues: List[CriticIssue] = []
        strengths: List[str] = []
        deductions = 0

        # Check color palette and WCAG contrast
        theme_cfg = resolve_theme(dsl.theme)
        colors = theme_cfg["colors"]
        palette_meta = get_color_palette_meta(dsl.theme)
        contrast_eval = palette_meta["contrast"]

        t_bg_ratio = contrast_eval["text_on_bg"]["ratio"]
        t_card_ratio = contrast_eval["text_on_card"]["ratio"]
        m_card_ratio = contrast_eval["muted_on_card"]["ratio"]

        if t_bg_ratio < DESIGN_CONSTRAINTS["min_contrast_ratio"]:
            deductions += 15
            issues.append(CriticIssue(
                slide=0,
                severity="high",
                category="contrast",
                issue=f"Primary text contrast ({t_bg_ratio}:1) on canvas fails WCAG AA (minimum {DESIGN_CONSTRAINTS['min_contrast_ratio']}:1).",
                recommendation="Increase contrast between primary text and slide background.",
            ))

        if t_card_ratio < DESIGN_CONSTRAINTS["min_contrast_ratio"]:
            deductions += 10
            issues.append(CriticIssue(
                slide=0,
                severity="high",
                category="contrast",
                issue=f"Primary text contrast ({t_card_ratio}:1) on card surface fails WCAG AA.",
                recommendation="Adjust card surface or text luminance for comfortable reading.",
            ))

        if m_card_ratio < 3.0:
            deductions += 5
            issues.append(CriticIssue(
                slide=0,
                severity="medium",
                category="contrast",
                issue=f"Secondary muted text contrast ({m_card_ratio}:1) is below 3.0:1 threshold.",
                recommendation="Boost secondary text luminance for improved legibility.",
            ))

        if contrast_eval["compliant"]:
            wcag_badge = contrast_eval["wcag_overall"]
            strengths.append(
                f"Color Palette verified: '{theme_cfg['name']}' achieves WCAG {wcag_badge} compliance "
                f"({t_bg_ratio}:1 text/canvas, {t_card_ratio}:1 text/card, {m_card_ratio}:1 muted/card)."
            )

        # Check total slide count
        num_slides = len(dsl.slides)
        if num_slides < 3:
            deductions += 15
            issues.append(CriticIssue(
                slide=0,
                severity="high",
                category="density",
                issue="Presentation has fewer than 3 slides",
                recommendation="Expand deck with opening hero, core capability pillars, and a closing synthesis.",
            ))
        else:
            strengths.append(f"Substantial presentation deck with {num_slides} planned slides.")

        # Check visual rhythm cadence
        rhythm_seq = [s.rhythm for s in dsl.slides]
        consecutive_heavy = 0
        for i, s in enumerate(dsl.slides, 1):
            if s.rhythm in ("high-impact", "bento-grid", "data-story"):
                consecutive_heavy += 1
                if consecutive_heavy >= 3:
                    deductions += 10
                    issues.append(CriticIssue(
                        slide=i,
                        severity="medium",
                        category="rhythm",
                        issue=f"Three consecutive high-density slides around slide {i}",
                        recommendation="Insert a 'breathing-room' statement slide to prevent audience visual fatigue.",
                    ))
            else:
                consecutive_heavy = 0

        # Slide-by-slide checks
        for s in dsl.slides:
            s_num = s.slide_number

            # 1. Title length check
            title_chars = len(s.title or "")
            if title_chars > DESIGN_CONSTRAINTS["max_chars_per_title"]:
                deductions += 6
                issues.append(CriticIssue(
                    slide=s_num,
                    severity="medium",
                    category="overflow",
                    issue=f"Slide title is {title_chars} characters (max recommended: {DESIGN_CONSTRAINTS['max_chars_per_title']})",
                    recommendation="Shorten headline to a punchy takeaway and move supporting detail to subtitle.",
                ))

            # 2. Elements checks
            for elem in s.elements:
                cards = elem.data.get("cards", [])
                if isinstance(cards, list) and len(cards) > DESIGN_CONSTRAINTS["max_cards_per_grid"]:
                    deductions += 8
                    issues.append(CriticIssue(
                        slide=s_num,
                        severity="high",
                        category="density",
                        issue=f"Card grid contains {len(cards)} cards (max: {DESIGN_CONSTRAINTS['max_cards_per_grid']})",
                        recommendation="Cap grid at 4 cards to maintain comfortable whitespace and legible type size.",
                    ))

                bullets = elem.data.get("bullets", [])
                if isinstance(bullets, list):
                    if len(bullets) > DESIGN_CONSTRAINTS["max_bullets_per_slide"]:
                        deductions += 8
                        issues.append(CriticIssue(
                            slide=s_num,
                            severity="high",
                            category="density",
                            issue=f"Slide contains {len(bullets)} bullets (max: {DESIGN_CONSTRAINTS['max_bullets_per_slide']})",
                            recommendation="Limit to 4 key takeaways. Treat typography as visual punchlines.",
                        ))
                    for b in bullets:
                        words = len(str(b).split())
                        if words > DESIGN_CONSTRAINTS["max_words_per_bullet"]:
                            deductions += 4
                            issues.append(CriticIssue(
                                slide=s_num,
                                severity="low",
                                category="overflow",
                                issue=f"Bullet item contains {words} words (max recommended: {DESIGN_CONSTRAINTS['max_words_per_bullet']})",
                                recommendation="Condense bullet into a crisp, active sentence.",
                            ))

            # 3. Speaker notes presence
            if not s.speaker_notes:
                deductions += 2
                issues.append(CriticIssue(
                    slide=s_num,
                    severity="low",
                    category="hierarchy",
                    issue="Missing executive speaker notes",
                    recommendation="Provide 1-2 sentences of key speaker talking points.",
                ))

            # 4. Slide background override contrast check
            if s.background_override:
                try:
                    override_ratio = compute_contrast_ratio(colors["text"], s.background_override)
                    if override_ratio < DESIGN_CONSTRAINTS["min_contrast_ratio"]:
                        deductions += 8
                        issues.append(CriticIssue(
                            slide=s_num,
                            severity="high",
                            category="contrast",
                            issue=f"Custom background '{s.background_override}' provides low contrast ({override_ratio}:1) with text.",
                            recommendation="Adjust background shade to guarantee minimum 4.5:1 contrast.",
                        ))
                except Exception:
                    pass

        # Compute final score
        final_score = max(35, min(100, 100 - deductions))
        passed = final_score >= self.passing_score

        if passed and not [i for i in issues if i.severity == "high"]:
            strengths.append("Masterful visual hierarchy, verified WCAG contrast, and clean cadence.")

        return CritiqueResult(
            score=final_score,
            passed=passed,
            total_slides=num_slides,
            issues=[asdict(i) for i in issues],
            strengths=strengths,
            contrast_report=contrast_eval,
            palette_info=palette_meta,
        )

    def auto_refine(self, dsl: PresentationDSL, min_score: int = 85, max_iterations: int = 3) -> Tuple[PresentationDSL, CritiqueResult]:
        """Automatically repair detected flaws in PresentationDSL until passing criteria are met."""
        current_dsl = dsl
        latest_critique = self.critique(current_dsl)

        for iteration in range(max_iterations):
            if latest_critique.score >= min_score:
                break

            log.info("Refining presentation (Iteration %d, Score: %d)...", iteration + 1, latest_critique.score)

            # Repair slides
            theme_cfg = resolve_theme(current_dsl.theme)
            colors = theme_cfg["colors"]
            repaired_slides = []
            for s in current_dsl.slides:
                repaired = SlideDSL(
                    slide_number=s.slide_number,
                    layout=s.layout,
                    style=s.style,
                    intensity=s.intensity,
                    rhythm=s.rhythm,
                    title=s.title,
                    eyebrow=s.eyebrow,
                    subtitle=s.subtitle,
                    tag=s.tag,
                    elements=[],
                    transition=s.transition,
                    speaker_notes=s.speaker_notes or f"Deliver key takeaways for {s.title} with executive confidence.",
                    background_override=s.background_override,
                )

                # Fix title overflow
                if len(repaired.title) > DESIGN_CONSTRAINTS["max_chars_per_title"]:
                    words = repaired.title.split()
                    repaired.title = " ".join(words[:8]) + "..."

                # Fix background contrast if failing
                if repaired.background_override:
                    try:
                        bg_ratio = compute_contrast_ratio(colors["text"], repaired.background_override)
                        if bg_ratio < DESIGN_CONSTRAINTS["min_contrast_ratio"]:
                            adjusted_rgb = auto_adjust_contrast(repaired.background_override, colors["text"], min_ratio=4.5)
                            repaired.background_override = f"#{adjusted_rgb[0]:02X}{adjusted_rgb[1]:02X}{adjusted_rgb[2]:02X}"
                    except Exception:
                        repaired.background_override = None

                # Fix elements
                for elem in s.elements:
                    e_copy = SlideElement(
                        type=elem.type,
                        variant=elem.variant,
                        text=elem.text,
                        eyebrow=elem.eyebrow,
                        subtitle=elem.subtitle,
                        highlight_words=elem.highlight_words,
                        position=elem.position,
                        style=dict(elem.style),
                        data=dict(elem.data),
                        animation=elem.animation,
                        asset=elem.asset,
                        scale=elem.scale,
                    )
                    # Cap cards at 4
                    if "cards" in e_copy.data and isinstance(e_copy.data["cards"], list):
                        e_copy.data["cards"] = e_copy.data["cards"][:4]

                    # Cap bullets at 4, max 15 words
                    if "bullets" in e_copy.data and isinstance(e_copy.data["bullets"], list):
                        cleaned = []
                        for b in e_copy.data["bullets"][:4]:
                            b_words = str(b).split()
                            if len(b_words) > 15:
                                b = " ".join(b_words[:15]) + "..."
                            cleaned.append(b)
                        e_copy.data["bullets"] = cleaned

                    repaired.elements.append(e_copy)

                repaired_slides.append(repaired)

            current_dsl.slides = repaired_slides
            latest_critique = self.critique(current_dsl)

        return current_dsl, latest_critique


_CRITIC_INSTANCE: Optional[VisualQualityCritic] = None


def get_critic() -> VisualQualityCritic:
    """Get or instantiate singleton VisualQualityCritic."""
    global _CRITIC_INSTANCE
    if _CRITIC_INSTANCE is None:
        _CRITIC_INSTANCE = VisualQualityCritic()
    return _CRITIC_INSTANCE

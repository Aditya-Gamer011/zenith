"""Zenith Presentation Engine Package."""
from __future__ import annotations

from .dsl import PresentationDSL, SlideDSL, SlideElement
from .styles import VISUAL_STYLES, infer_visual_style, generate_visual_rhythm
from .registry import get_presentation_registry, PresentationComponentRegistry
from .renderer import get_renderer, PPTXRenderer
from .critic import get_critic, VisualQualityCritic
from .pipeline import get_master_pipeline, MasterPresentationPipeline

__all__ = [
    "PresentationDSL",
    "SlideDSL",
    "SlideElement",
    "VISUAL_STYLES",
    "infer_visual_style",
    "generate_visual_rhythm",
    "get_presentation_registry",
    "PresentationComponentRegistry",
    "get_renderer",
    "PPTXRenderer",
    "get_critic",
    "VisualQualityCritic",
    "get_master_pipeline",
    "MasterPresentationPipeline",
]

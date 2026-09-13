"""Zenith Services — Modular Capabilities & Sensory Operating Layer."""

from .privacy_guard import privacy_guard, PrivacyGuard
from .activity_watch import activity_watch, ActivityWatchService
from .screen_awareness import clippy_vision, ClippyVisionService
from .memory_layer import memory_layer, Mem0MemoryService
from .browser_unified import browser_unified, UnifiedBrowserService
from .vision_engine import vision_engine, VisionEngine
from .context_engine import context_engine, UnifiedContextEngine

__all__ = [
    "privacy_guard",
    "PrivacyGuard",
    "activity_watch",
    "ActivityWatchService",
    "clippy_vision",
    "ClippyVisionService",
    "memory_layer",
    "Mem0MemoryService",
    "browser_unified",
    "UnifiedBrowserService",
    "vision_engine",
    "VisionEngine",
    "context_engine",
    "UnifiedContextEngine",
]

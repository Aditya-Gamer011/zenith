"""Holds the shared service singletons (agent service, browser engine, etc.)."""
from __future__ import annotations

from . import provider

# Lazily populated by main.py at startup.
_agent_service = None
_browser_engine = None


def get_agent_service():
    global _agent_service
    if _agent_service is None:
        from ..agents.agent_service import AgentService

        _agent_service = AgentService()
    return _agent_service


def get_browser_engine():
    global _browser_engine
    if _browser_engine is None:
        from ..tools.browser import BrowserEngine

        _browser_engine = BrowserEngine()
    return _browser_engine


__all__ = ["get_agent_service", "get_browser_engine", "provider"]
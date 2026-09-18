"""Tests for Zenith Visual Vocabulary Component Registry and Creative Director Tools."""
import os
import pytest
from pathlib import Path

from zenith.components.registry import ComponentRegistry, get_registry
from zenith.components.composer import VisualComposer, get_composer
from zenith.tools.design_components import (
    component_catalog_summary,
    component_search,
    component_get,
    component_adapt,
    component_compose_page,
)
from zenith.agents.agent_service import AgentService
from zenith.core.tools import TOOLS


def test_component_registry_load():
    registry = get_registry()
    assert registry is not None
    summary = registry.catalog_summary()
    assert summary["total_curated_components"] >= 15
    assert summary["total_indexed_galaxy_components"] >= 3000
    assert "button" in summary["curated_by_category"] or "buttons" in summary["curated_by_category"]
    assert "zenith" in summary["curated_by_source"]
    assert "magicui" in summary["curated_by_source"]


def test_component_search_curated():
    registry = get_registry()
    # Search for neon CTA
    results = registry.search(query="neon", min_intensity=4)
    assert len(results) > 0
    cids = [r["id"] for r in results]
    assert "magnetic-neon-button" in cids or "neon-button" in cids


def test_component_search_galaxy():
    registry = get_registry()
    # Search galaxy components
    results = registry.search(query="button", include_galaxy=True, limit=5)
    assert len(results) == 5


def test_component_get():
    registry = get_registry()
    comp = registry.get("magnetic-neon-button")
    assert comp is not None
    assert comp["name"] == "Magnetic Neon Button"
    assert comp["intensity"] == 5
    assert "tsx" in comp["code"]
    assert "css" in comp["code"]


def test_component_adapt_to_theme():
    registry = get_registry()
    adapted = registry.adapt_component_to_theme("magnetic-neon-button", theme_name="boba_bash")
    assert adapted["theme_name"] == "boba_bash"
    assert "accent_1" in adapted["colors_applied"]
    assert adapted["colors_applied"]["accent_1"] == "#DDA15E"
    assert "--accent-1: #DDA15E" in adapted["theme_scope_css"]
    assert "<button" in adapted["raw_html"]
    assert "<!DOCTYPE html>" in adapted["preview_html"]


def test_visual_composer_page():
    composer = get_composer()
    result = composer.compose_page(
        title="Test Sovereign AI",
        theme_name="cyberpunk_neon",
        brief="Autonomous testing suite for visual vocabulary",
        hero_cta_text="Launch Test Matrix",
    )
    assert result["site_id"].startswith("site_")
    assert result["url"].startswith("/static/sites/")
    file_path = Path(result["file_path"])
    assert file_path.exists()
    content = file_path.read_text(encoding="utf-8")
    assert "Test Sovereign AI" in content
    assert "Launch Test Matrix" in content
    assert "three-viewport" in content
    assert "particle-canvas" in content


@pytest.mark.anyio
async def test_tool_handlers():
    summary_txt = await component_catalog_summary()
    assert "Visual Vocabulary Catalog Summary" in summary_txt

    search_txt = await component_search(query="cta", min_intensity=3)
    assert "matching visual component" in search_txt

    get_txt = await component_get("glass-card")
    assert "Sovereign Glassmorphism Card" in get_txt

    adapt_txt = await component_adapt("glass-card", theme="swiss_clean")
    assert "Swiss Modern Clean" in adapt_txt

    compose_txt = await component_compose_page(
        title="Automated Test Landing",
        theme="nordic_navy",
        brief="Test brief",
    )
    assert "Generated Interactive Landing Page" in compose_txt
    assert "Automated Test Landing" in compose_txt


def test_creative_agent_department():
    service = AgentService()
    dept = service.get_agent_profile("creative")
    assert dept is not None
    tools = dept["tools"]
    assert "component_search" in tools
    assert "component_get" in tools
    assert "component_adapt" in tools
    assert "component_compose_page" in tools
    assert "component_catalog_summary" in tools
    assert "visual vocabulary" in dept["system"].lower()



def test_tool_registry_registration():
    tool_names = list(TOOLS.keys())
    assert "component_search" in tool_names
    assert "component_get" in tool_names
    assert "component_adapt" in tool_names
    assert "component_compose_page" in tool_names
    assert "component_catalog_summary" in tool_names

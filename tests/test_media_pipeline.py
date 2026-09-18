"""Tests for Studio-Grade Presentation & Document Generation Pipeline."""
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from zenith.tools.design_system import THEMES, resolve_theme, DESIGN_CONSTRAINTS
from zenith.tools.artifact_pipeline import (
    infer_art_direction,
    run_quality_critic,
    generate_presentation,
    edit_presentation,
    preview_presentation,
)
from zenith.tools.web_presentation import generate_web_presentation
from zenith.tools.filegen import generate_pdf, generate_docx
from zenith.memory import store
from zenith.core.tools import TOOLS
from zenith.main import app


def test_design_system_themes():
    """Verify built-in themes are human-crafted and avoid neon AI slop defaults."""
    assert "editorial_slate" in THEMES
    assert "boba_bash" in THEMES
    assert "swiss_clean" in THEMES
    assert "terracotta_warm" in THEMES
    assert "nordic_navy" in THEMES
    assert "executive_mono" in THEMES

    # Default should be editorial slate (warm obsidian & brushed champagne)
    default_theme = resolve_theme("editorial_slate")
    assert "#0d0f12" in default_theme["colors"]["bg"].lower()
    assert "#d4a373" in default_theme["colors"]["accent1"].lower()

    # Boba bash theme
    boba = resolve_theme("boba_bash")
    assert "Boba" in boba["name"]


def test_infer_art_direction():
    """Verify intelligent, context-aware theme inference."""
    assert infer_art_direction("Boba Tea & Milkshake Shop Pitch") == "boba_bash"
    assert infer_art_direction("Apple Swiss Minimal Architecture Report") == "swiss_clean"
    assert infer_art_direction("Cloud Infrastructure and Database Scaling") == "nordic_navy"
    assert infer_art_direction("Forest Sustainability and Climate Strategy") == "terracotta_warm"
    assert infer_art_direction("Wall Street Financial Audit Monochrome") == "executive_mono"
    # General topics default to editorial slate
    assert infer_art_direction("Artificial Intelligence Strategy in Q3") == "editorial_slate"
    # Explicit user choice overrides inference
    assert infer_art_direction("Any topic", requested_theme="boba_bash") == "boba_bash"


def test_quality_critic_guardrails():
    """Verify quality critic enforces density and readability guardrails."""
    noisy_slides = [
        {
            "title": "A Very Extremely Excessively Long Title That Would Definitely Overflow The Header Box On Most Displays",
            "layout": "cards_grid",
            "bullets": [
                "Point 1: " + "word " * 30,  # Exceeds max_words_per_bullet
                "Point 2",
                "Point 3",
                "Point 4",
                "Point 5 should be pruned",   # Exceeds max_bullets_per_slide
                "Point 6 should be pruned",
            ],
            "cards": [{"title": f"Card {i}"} for i in range(10)],  # Exceeds max 4 cards
        }
    ]

    repaired = run_quality_critic(noisy_slides)
    s0 = repaired[0]

    # Title was safely truncated
    assert len(s0["title"]) <= DESIGN_CONSTRAINTS["max_chars_per_title"] + 5
    assert s0["title"].endswith("...")

    # Bullets capped to 4
    assert len(s0["bullets"]) <= DESIGN_CONSTRAINTS["max_bullets_per_slide"]
    # Overly verbose bullet was trimmed
    assert s0["bullets"][0].endswith("...")

    # Cards capped to 4
    assert len(s0["cards"]) <= 4

    # Default speaker notes injected
    assert "notes" in s0 and len(s0["notes"]) > 0


def test_web_presentation_generator(tmp_path: Path):
    """Verify standalone HTML generation with Three.js WebGL and glassmorphic cards."""
    slides = [
        {"title": "Executive Overview", "layout": "hero_title", "subtitle": "Q4 Performance", "tag": "INTRO"},
        {"title": "Key Capabilities", "layout": "cards_grid", "cards": [{"title": "Fast", "points": ["Sub-millisecond latency"]}]},
    ]
    deck_id, file_path = generate_web_presentation(
        title="Test Executive Brief",
        slides=slides,
        theme_name="editorial_slate",
        deck_id="deck_test_123",
    )

    assert deck_id == "deck_test_123"
    assert Path(file_path).exists()
    content = Path(file_path).read_text(encoding="utf-8")

    assert "Test Executive Brief" in content
    assert "three.min.js" in content
    assert "initWebGLBackground" in content
    assert "Executive Overview" in content
    assert "Key Capabilities" in content


@pytest.mark.anyio
async def test_generate_and_edit_presentation_pipeline():
    """Verify end-to-end presentation generation, SQLite artifact persistence, and iterative edits."""
    store.init_db()

    # 1. Generate presentation
    result = await generate_presentation(
        title="Autonomous Agent Architecture",
        topic="Cloud AI Systems",
        theme="editorial_slate",
        subtitle="Foundations of Self-Directing Intelligence",
    )

    assert "Studio Presentation Created" in result
    assert "Launch Interactive Web Presentation" in result
    assert "Download Editable PowerPoint" in result

    # Extract deck_id from output
    import re
    m = re.search(r"/presentation/(deck_[a-zA-Z0-9_\-]+)", result)
    assert m is not None, f"Could not find presentation deck_id in {result}"
    deck_id = m.group(1)

    # 2. Check artifact in SQLite store
    art = store.get_artifact(deck_id)
    assert art is not None
    assert art["title"] == "Autonomous Agent Architecture"
    assert art["theme"] == "editorial_slate"
    assert len(art["data"]["slides"]) >= 4

    # 3. Edit presentation: change theme
    edit_res = await edit_presentation(
        deck_id=deck_id,
        action="change_theme",
        modifications={"theme": "boba_bash"},
    )
    assert "Presentation Updated" in edit_res
    updated_art = store.get_artifact(deck_id)
    assert updated_art["theme"] == "boba_bash"

    # 4. Edit presentation: update slide 1
    edit_res2 = await edit_presentation(
        deck_id=deck_id,
        action="update_slide",
        slide_number=1,
        modifications={"title": "Updated Agent Vision 2026", "subtitle": "Next Generation"},
    )
    assert "Presentation Updated" in edit_res2
    updated_art2 = store.get_artifact(deck_id)
    assert updated_art2["data"]["slides"][0]["title"] == "Updated Agent Vision 2026"

    # 5. Preview presentation
    preview = preview_presentation(deck_id)
    assert "Autonomous Agent Architecture" in preview
    assert f"/presentation/{deck_id}" in preview


@pytest.mark.anyio
async def test_substantial_documents_generation(tmp_path: Path):
    """Verify PDF and DOCX generation with executive cover pages and section hierarchy."""
    doc_content = """# Executive Strategic Audit 2026

## Section 1: Macro Environment Analysis
The current technological frontier is experiencing an unprecedented inflection point driven by agentic multi-model orchestration.
Autonomous systems must reconcile low-latency responsiveness with verifiable safety boundaries.

## Section 2: Systems Architecture
Modern infrastructure mandates unified persistent memory graphs coupled with isolated sandboxed execution tiers.
This approach eliminates single points of failure while maintaining high-throughput coordination.

## Section 3: Projections & Milestones
- Phase 1: Core Engine Stabilization
- Phase 2: Autonomous Fleet Orchestration
- Phase 3: Global Distributed Verification
"""
    pdf_path = await generate_pdf("executive_audit_report.pdf", doc_content, title="Executive Strategic Audit 2026")
    assert Path(pdf_path).exists()
    assert Path(pdf_path).stat().st_size > 1000

    docx_path = await generate_docx("executive_audit_report.docx", doc_content, title="Executive Strategic Audit 2026")
    assert Path(docx_path).exists()
    assert Path(docx_path).stat().st_size > 1000


def test_tool_registry_presentation_tools():
    """Verify new presentation tools are properly registered in core tool registry."""
    assert "generate_presentation" in TOOLS
    assert "edit_presentation" in TOOLS
    assert "preview_presentation" in TOOLS
    assert "list_design_themes" in TOOLS


def test_fastapi_presentation_routes():
    """Verify FastAPI routes for /presentation/{deck_id}, /api/presentations/{deck_id}, and /api/files/download."""
    client = TestClient(app)

    # 1. Test 404 for nonexistent presentation
    resp = client.get("/presentation/nonexistent_deck_999")
    assert resp.status_code == 404

    # 2. Test 404 for nonexistent artifact api
    resp_art = client.get("/api/presentations/nonexistent_deck_999")
    assert resp_art.status_code == 404

    # 3. Create dummy presentation HTML and test serving
    test_html_dir = Path("static/presentations")
    test_html_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_html_dir / "test_deck_live.html"
    test_file.write_text("<!DOCTYPE html><html><body><h1>Live Deck Test</h1></body></html>")

    try:
        resp_view = client.get("/presentation/test_deck_live")
        assert resp_view.status_code == 200
        assert "Live Deck Test" in resp_view.text

        # Test download endpoint
        dl_resp = client.get(f"/api/files/download?path={test_file}")
        assert dl_resp.status_code == 200
        assert "Live Deck Test" in dl_resp.text
        assert "attachment" in dl_resp.headers.get("content-disposition", "")

    finally:
        if test_file.exists():
            test_file.unlink()

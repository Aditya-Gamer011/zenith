"""Zenith Component Registry & Visual Vocabulary Engine.

Manages curated multi-library component catalog (Uiverse, Aceternity UI,
Magic UI, Three.js, GSAP, and Zenith Proprietary) and 3,800+ indexed Uiverse
Galaxy elements. Provides search, inspection, brand theming adaptation,
and developer code export.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from zenith.tools.design_system import resolve_theme, THEMES

log = logging.getLogger("zenith.components.registry")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_AGENT_DIR = ROOT_DIR / "media-agent"
COMPONENTS_DIR = MEDIA_AGENT_DIR / "components"
GALAXY_DB_PATH = COMPONENTS_DIR / "uiverse_galaxy.db"


class ComponentRegistry:
    """Multi-Library Visual Vocabulary Registry for Zenith Media Agent."""

    def __init__(self, components_dir: Optional[Path] = None) -> None:
        self.components_dir = Path(components_dir) if components_dir else COMPONENTS_DIR
        self._curated_cache: Dict[str, Dict[str, Any]] = {}
        self._categories: set[str] = set()
        self._sources: set[str] = {"uiverse", "aceternity", "magicui", "threejs", "gsap", "zenith"}
        self._load_curated_cache()

    def _load_curated_cache(self) -> None:
        """Scan components_dir for metadata.json in each component folder."""
        self._curated_cache.clear()
        self._categories.clear()

        if not self.components_dir.exists():
            log.warning("Components directory not found at %s", self.components_dir)
            return

        for meta_file in self.components_dir.glob("*/*/metadata.json"):
            try:
                data = json.loads(meta_file.read_text(encoding="utf-8"))
                cid = data.get("id") or meta_file.parent.name
                category = data.get("category", meta_file.parent.parent.name).lower()
                data["id"] = cid
                data["category"] = category
                data["local_path"] = str(meta_file.parent.relative_to(ROOT_DIR))

                self._curated_cache[cid] = data
                self._categories.add(category)
                if "source" in data:
                    self._sources.add(data["source"].lower())
            except Exception as e:
                log.warning("Failed parsing %s: %s", meta_file, e)

        log.info("Loaded %d curated components across %d categories", len(self._curated_cache), len(self._categories))

    def reload(self) -> None:
        """Reload the registry cache from disk."""
        self._load_curated_cache()

    def search(
        self,
        query: str = "",
        category: Optional[str] = None,
        source: Optional[str] = None,
        motion: Optional[str] = None,
        min_intensity: int = 0,
        max_intensity: int = 5,
        tags: Optional[List[str]] = None,
        limit: int = 15,
        include_galaxy: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search across curated libraries and indexed Uiverse Galaxy elements."""
        results: List[Dict[str, Any]] = []
        q = (query or "").strip().lower()
        target_cat = category.strip().lower() if category else None
        target_source = source.strip().lower() if source else None
        target_motion = motion.strip().lower() if motion else None
        target_tags = [t.lower().strip() for t in tags] if tags else []

        # 1. Search in-memory curated components
        for cid, comp in self._curated_cache.items():
            # Category filter
            if target_cat and comp.get("category") != target_cat:
                # check if category partial matches (e.g., 'button' in 'buttons')
                if not (target_cat in comp.get("category", "") or comp.get("category", "") in target_cat):
                    continue

            # Source filter
            if target_source and comp.get("source", "").lower() != target_source:
                continue

            # Motion filter
            if target_motion and target_motion not in comp.get("motion", "").lower():
                continue

            # Intensity filter
            intensity = int(comp.get("intensity", 3))
            if not (min_intensity <= intensity <= max_intensity):
                continue

            # Tag filter
            comp_tags = [t.lower() for t in comp.get("tags", [])]
            if target_tags and not any(t in comp_tags for t in target_tags):
                continue

            # Text query match (name, description, tags, id)
            score = 0
            if q:
                if q in cid:
                    score += 5
                if q in comp.get("name", "").lower():
                    score += 4
                if any(q in t for t in comp_tags):
                    score += 3
                if q in comp.get("description", "").lower():
                    score += 2
                if score == 0:
                    continue
            else:
                score = 1

            item = dict(comp)
            item["match_score"] = score
            item["is_curated"] = True
            results.append(item)

        # Sort curated results by match score desc, intensity desc
        results.sort(key=lambda x: (x.get("match_score", 0), x.get("intensity", 0)), reverse=True)

        # 2. If limit not reached and include_galaxy enabled, query Uiverse Galaxy SQLite
        remaining = limit - len(results)
        if remaining > 0 and include_galaxy and GALAXY_DB_PATH.exists():
            galaxy_items = self._search_galaxy(
                query=q,
                category=target_cat,
                min_intensity=min_intensity,
                max_intensity=max_intensity,
                limit=remaining,
            )
            results.extend(galaxy_items)

        return results[:limit]

    def _search_galaxy(
        self,
        query: str,
        category: Optional[str] = None,
        min_intensity: int = 0,
        max_intensity: int = 5,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Query SQLite Uiverse Galaxy database with FTS5 or LIKE search."""
        galaxy_results: List[Dict[str, Any]] = []
        try:
            conn = sqlite3.connect(str(GALAXY_DB_PATH))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()

            conditions = ["intensity >= ? AND intensity <= ?"]
            params: List[Any] = [min_intensity, max_intensity]

            if category:
                # normalize plural/singular
                cat_clean = category.rstrip("s")
                conditions.append("(category LIKE ? OR category LIKE ?)")
                params.extend([f"%{cat_clean}%", f"%{category}%"])

            if query:
                # Attempt FTS match, fallback to LIKE
                try:
                    # Clean query for FTS5 syntax
                    safe_q = re.sub(r"[^\w\s]", "", query).strip()
                    if safe_q:
                        cur.execute(f"""
                        SELECT u.id, u.name, u.category, u.author, u.tags, u.motion, u.intensity, u.framework, u.file_path
                        FROM uiverse_components u
                        JOIN uiverse_fts f ON u.id = f.id
                        WHERE uiverse_fts MATCH ? AND {' AND '.join(conditions)}
                        LIMIT ?
                        """, [safe_q] + params + [limit])
                        rows = cur.fetchall()
                    else:
                        rows = []
                except Exception:
                    rows = []

                if not rows:
                    like_cond = f"(name LIKE ? OR tags LIKE ? OR id LIKE ?)"
                    params_like = [f"%{query}%", f"%{query}%", f"%{query}%"]
                    cur.execute(f"""
                    SELECT id, name, category, author, tags, motion, intensity, framework, file_path
                    FROM uiverse_components
                    WHERE {' AND '.join(conditions)} AND {like_cond}
                    LIMIT ?
                    """, params + params_like + [limit])
                    rows = cur.fetchall()
            else:
                cur.execute(f"""
                SELECT id, name, category, author, tags, motion, intensity, framework, file_path
                FROM uiverse_components
                WHERE {' AND '.join(conditions)}
                ORDER BY intensity DESC
                LIMIT ?
                """, params + [limit])
                rows = cur.fetchall()

            for r in rows:
                tags_list = [t.strip() for t in (r["tags"] or "").split(",") if t.strip()]
                galaxy_results.append({
                    "id": r["id"],
                    "name": r["name"],
                    "category": r["category"],
                    "source": "uiverse",
                    "author": r["author"],
                    "tags": tags_list,
                    "motion": r["motion"],
                    "intensity": r["intensity"],
                    "framework": r["framework"],
                    "local_path": r["file_path"],
                    "is_curated": False,
                    "best_for": ["uiverse-community", r["category"]],
                    "description": f"Uiverse Galaxy {r['category']} component by {r['author']}.",
                })
            conn.close()
        except Exception as e:
            log.warning("Galaxy search error: %s", e)

        return galaxy_results

    def get(self, component_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve complete component by ID, including code and CSS."""
        # Check curated cache first
        if component_id in self._curated_cache:
            return dict(self._curated_cache[component_id])

        # Lookup in curated by alias / loose match
        cid_clean = component_id.strip().lower()
        for cid, comp in self._curated_cache.items():
            if cid.lower() == cid_clean or comp.get("name", "").lower() == cid_clean:
                return dict(comp)

        # Lookup in SQLite Uiverse Galaxy
        if GALAXY_DB_PATH.exists():
            try:
                conn = sqlite3.connect(str(GALAXY_DB_PATH))
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT * FROM uiverse_components WHERE id = ? LIMIT 1", (component_id,))
                row = cur.fetchone()
                conn.close()

                if row:
                    tags_list = [t.strip() for t in (row["tags"] or "").split(",") if t.strip()]
                    return {
                        "id": row["id"],
                        "name": row["name"],
                        "category": row["category"],
                        "source": "uiverse",
                        "author": row["author"],
                        "tags": tags_list,
                        "motion": row["motion"],
                        "intensity": row["intensity"],
                        "framework": row["framework"],
                        "local_path": row["file_path"],
                        "is_curated": False,
                        "description": f"Uiverse Galaxy {row['category']} element by {row['author']}.",
                        "best_for": [row["category"], "web"],
                        "code": {
                            "html": row["html"],
                            "css": row["css"],
                            "tsx": f"// Uiverse Galaxy Component: {row['name']}\nimport React from 'react';\n\nexport const {row['name'].replace(' ', '')} = () => (\n  <div dangerouslySetInnerHTML={{{{ __html: `{row['html']}` }}}} />\n);",
                        },
                        "theme_adaptable_vars": {
                            "accent_1": "--accent-1",
                            "bg_color": "--bg-color",
                            "card_bg": "--card-bg",
                            "text_color": "--text-color",
                        },
                    }
            except Exception as e:
                log.warning("Galaxy lookup error for %s: %s", component_id, e)

        return None

    def adapt_component_to_theme(
        self,
        component_id: str,
        theme_name: str = "editorial_slate",
        custom_overrides: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Adapt a component's styles and colors to match a Zenith brand theme.

        Replaces hardcoded hex codes and injects appropriate CSS variables:
        --bg-color, --card-bg, --accent-1, --accent-2, --glow-color, --text-color,
        --border-color, --font-heading, --font-body.
        """
        comp = self.get(component_id)
        if not comp:
            raise ValueError(f"Component '{component_id}' not found in registry.")

        theme = resolve_theme(theme_name)
        colors = dict(theme["colors"])
        if custom_overrides:
            colors.update(custom_overrides)

        raw_css = comp.get("code", {}).get("css", "")
        raw_html = comp.get("code", {}).get("html", "")
        raw_tsx = comp.get("code", {}).get("tsx", "")

        # 1. Replace hardcoded common vibrant hex codes with theme CSS variables
        # Map common hardcoded colors to semantic theme tokens
        color_subs = [
            (r"#00f3ff|#38bdf8|#552da8|#2563eb|#4f46e5|#3b82f6|#6366f1", "var(--accent-1)"),
            (r"#ff007f|#818cf8|#a855f7|#ec4899|#f43f5e", "var(--accent-2)"),
            (r"#0d0f12|#08090c|#0f172a|#0b0f19|#12141c|#000000", "var(--bg-color)"),
            (r"#181b20|#1e293b|#242938|#1f2937|#14171f", "var(--card-bg)"),
            (r"#2a2e37|#334155|#374151|#27272a", "var(--border-color)"),
            (r"#f4f4f6|#f8fafc|#ffffff", "var(--text-color)"),
            (r"#8e95a2|#94a3b8|#9ca3af|#a1a1aa", "var(--muted-color)"),
        ]

        adapted_css = raw_css
        for pattern, replacement in color_subs:
            adapted_css = re.sub(pattern, replacement, adapted_css, flags=re.IGNORECASE)

        # Inset theme wrapper styles
        theme_scope_css = f"""/* Adapted for Theme: {theme['name']} */
:root, .theme-scope-{theme_name} {{
  --bg-color: {colors.get("bg", "#0d0f12")};
  --card-bg: {colors.get("card", "#181b20")};
  --card-glass: {colors.get("card_glass", "rgba(24, 27, 32, 0.8)")};
  --border-color: {colors.get("border", "#2a2e37")};
  --text-color: {colors.get("text", "#f4f4f6")};
  --muted-color: {colors.get("muted", "#8e95a2")};
  --accent-1: {colors.get("accent1", "#d4a373")};
  --accent-2: {colors.get("accent2", "#3b82f6")};
  --glow-color: {colors.get("glow", "rgba(212, 163, 115, 0.2)")};
  --font-heading: {theme.get("font_heading", "'Inter', sans-serif")};
  --font-body: {theme.get("font_body", "'Inter', sans-serif")};
}}

{adapted_css}
"""

        # Self-contained preview HTML
        preview_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{comp['name']} — {theme['name']} Preview</title>
  <style>
    {theme_scope_css}
    body {{
      margin: 0;
      padding: 60px 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      background-color: var(--bg-color);
      color: var(--text-color);
      font-family: var(--font-body);
      box-sizing: border-box;
    }}
  </style>
</head>
<body class="theme-scope-{theme_name}">
  {raw_html}
</body>
</html>
"""

        return {
            "component_id": comp["id"],
            "component_name": comp["name"],
            "category": comp["category"],
            "source": comp["source"],
            "theme_name": theme_name,
            "theme_title": theme["name"],
            "colors_applied": {
                "accent_1": colors.get("accent1"),
                "accent_2": colors.get("accent2"),
                "bg": colors.get("bg"),
                "card": colors.get("card"),
                "glow": colors.get("glow"),
            },
            "adapted_css": adapted_css,
            "theme_scope_css": theme_scope_css,
            "raw_html": raw_html,
            "raw_tsx": raw_tsx,
            "preview_html": preview_html,
        }

    def catalog_summary(self) -> Dict[str, Any]:
        """Provide real-time statistics of visual vocabulary catalog."""
        curated_by_source: Dict[str, int] = {}
        curated_by_category: Dict[str, int] = {}

        for comp in self._curated_cache.values():
            src = comp.get("source", "zenith").lower()
            cat = comp.get("category", "other").lower()
            curated_by_source[src] = curated_by_source.get(src, 0) + 1
            curated_by_category[cat] = curated_by_category.get(cat, 0) + 1

        galaxy_count = 0
        galaxy_categories: Dict[str, int] = {}
        if GALAXY_DB_PATH.exists():
            try:
                conn = sqlite3.connect(str(GALAXY_DB_PATH))
                cur = conn.cursor()
                cur.execute("SELECT count(*) FROM uiverse_components")
                galaxy_count = cur.fetchone()[0]

                cur.execute("SELECT category, count(*) FROM uiverse_components GROUP BY category")
                for row in cur.fetchall():
                    galaxy_categories[row[0]] = row[1]
                conn.close()
            except Exception as e:
                log.warning("Galaxy count error: %s", e)

        return {
            "total_curated_components": len(self._curated_cache),
            "total_indexed_galaxy_components": galaxy_count,
            "total_visual_vocabulary_assets": len(self._curated_cache) + galaxy_count,
            "curated_by_source": curated_by_source,
            "curated_by_category": curated_by_category,
            "galaxy_by_category": galaxy_categories,
            "supported_themes": list(THEMES.keys()),
            "library_hierarchy": [
                "UIVERSE (3,800+ community elements)",
                "Aceternity UI (Bento Grids, 3D Cards, Spotlight, Aurora)",
                "Magic UI (Shimmer, Border Beam, Particles, Marquee, Safari)",
                "Three.js / WebGL (Floating 3D Meshes, Starfields, Terrains)",
                "GSAP Primitives (ScrollTrigger, Parallax, Timelines)",
                "Zenith Proprietary (Studio Editorial, Sovereign HUD, Audiograms)",
            ],
        }


# Singleton registry accessor
_REGISTRY_INSTANCE: Optional[ComponentRegistry] = None


def get_registry() -> ComponentRegistry:
    """Get or instantiate global ComponentRegistry singleton."""
    global _REGISTRY_INSTANCE
    if _REGISTRY_INSTANCE is None:
        _REGISTRY_INSTANCE = ComponentRegistry()
    return _REGISTRY_INSTANCE

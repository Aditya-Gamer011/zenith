"""Zenith Visual Vocabulary & Component Registry Tools.

Provides high-performance search, inspection, theme adaptation, and complete page
composition across Uiverse Galaxy, Aceternity UI, Magic UI, Three.js, GSAP, and
Zenith proprietary component libraries.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from zenith.components.registry import get_registry
from zenith.components.composer import get_composer

log = logging.getLogger("zenith.tools.design_components")


async def component_search(
    query: str = "",
    category: str = "",
    source: str = "",
    motion: str = "",
    min_intensity: int = 0,
    max_intensity: int = 5,
    limit: int = 10,
) -> str:
    """Search visual vocabulary across Uiverse, Aceternity UI, Magic UI, Three.js, GSAP, and Zenith.
    
    Args:
        query: Search term (e.g. 'cta', 'neon', 'tilt', 'particles', 'aurora', 'bento').
        category: Category filter ('button', 'card', 'background', 'text', 'effects', 'mockup', 'three_r3f', 'gsap').
        source: Library source ('uiverse', 'aceternity', 'magicui', 'threejs', 'gsap', 'zenith').
        motion: Motion type ('hover', 'magnetic', '3d', 'particles', 'shimmer', 'glitch').
        min_intensity: Minimum visual intensity (1 to 5).
        max_intensity: Maximum visual intensity (1 to 5).
        limit: Max results to return (default 10).
    """
    registry = get_registry()
    results = registry.search(
        query=query,
        category=category or None,
        source=source or None,
        motion=motion or None,
        min_intensity=min_intensity,
        max_intensity=max_intensity,
        limit=limit,
    )

    if not results:
        return f"No visual components found matching query='{query}', category='{category}', source='{source}'."

    out = [f"Found {len(results)} matching visual component(s):\n"]
    for i, c in enumerate(results, 1):
        tags_str = ", ".join(c.get("tags", []))
        curated_tag = " [Curated Signature]" if c.get("is_curated") else f" [Uiverse Galaxy: {c.get('author', 'community')}]"
        out.append(
            f"{i}. **{c.get('name')}** (`{c.get('id')}`){curated_tag}\n"
            f"   - **Source**: {c.get('source', 'uiverse').upper()} | **Category**: {c.get('category')} | **Intensity**: {c.get('intensity')}/5\n"
            f"   - **Motion**: {c.get('motion')} | **Framework**: {c.get('framework')}\n"
            f"   - **Tags**: {tags_str}\n"
            f"   - **Best For**: {', '.join(c.get('best_for', []))}\n"
            f"   - **Description**: {c.get('description', 'Visual UI component.')}\n"
        )
    return "\n".join(out)


async def component_get(component_id: str) -> str:
    """Retrieve full component details, metadata, TSX, CSS, and HTML code.
    
    Args:
        component_id: Unique component ID (e.g. 'magnetic-neon-button', 'glass-card', 'aurora-background', '3d-card').
    """
    registry = get_registry()
    comp = registry.get(component_id)
    if not comp:
        return f"Component '{component_id}' not found in registry."

    code = comp.get("code", {})
    tsx_snippet = code.get("tsx", "")[:600] if code.get("tsx") else "N/A"
    css_snippet = code.get("css", "")[:400] if code.get("css") else "N/A"
    html_snippet = code.get("html", "")[:400] if code.get("html") else "N/A"

    return f"""### Component: {comp.get('name')} (`{comp.get('id')}`)
- **Library Source**: {comp.get('source', 'uiverse').upper()}
- **Category**: {comp.get('category')}
- **Motion**: {comp.get('motion')} | **Intensity**: {comp.get('intensity')}/5
- **Framework**: {comp.get('framework')}
- **Tags**: {', '.join(comp.get('tags', []))}
- **Best For**: {', '.join(comp.get('best_for', []))}
- **Path**: `{comp.get('local_path', '')}`

#### Description
{comp.get('description', '')}

#### HTML Template Snippet
```html
{html_snippet}
```

#### CSS Styling Snippet
```css
{css_snippet}
```

#### React TSX Snippet
```tsx
{tsx_snippet}
```
"""


async def component_adapt(
    component_id: str,
    theme: str = "editorial_slate",
    custom_colors: str = "",
) -> str:
    """Adapt a component to a brand design theme with automatic semantic CSS variable mapping.
    
    Args:
        component_id: Unique component ID (e.g. 'magnetic-neon-button', 'glass-card', '3d-card').
        theme: Zenith design theme ('editorial_slate', 'boba_bash', 'swiss_clean', 'terracotta_warm', 'nordic_navy', 'executive_mono', 'cyberpunk_neon').
        custom_colors: Optional JSON dictionary of color overrides (e.g. '{"accent1": "#ff007f"}').
    """
    registry = get_registry()
    overrides = None
    if custom_colors:
        try:
            overrides = json.loads(custom_colors)
        except Exception:
            pass

    try:
        adapted = registry.adapt_component_to_theme(component_id, theme_name=theme, custom_overrides=overrides)
    except Exception as e:
        return f"Failed adapting component '{component_id}': {e}"

    return f"""### Theme Adaptation: {adapted['component_name']} &rarr; {adapted['theme_title']}
- **Component ID**: `{adapted['component_id']}`
- **Theme**: `{adapted['theme_name']}` ({adapted['theme_title']})
- **Accent 1**: `{adapted['colors_applied']['accent_1']}`
- **Accent 2**: `{adapted['colors_applied']['accent_2']}`
- **Background**: `{adapted['colors_applied']['bg']}` | **Card**: `{adapted['colors_applied']['card']}`

#### Adapted Theme Scope CSS
```css
{adapted['theme_scope_css'][:800]}
```

#### Ready-to-Use Markup
```html
{adapted['raw_html']}
```
"""


async def component_compose_page(
    title: str = "Zenith Sovereign Intelligence",
    theme: str = "editorial_slate",
    brief: str = "",
    hero_cta: str = "Launch Sovereign Environment",
    hero_bg: str = "aurora-background",
) -> str:
    """Synthesize an entire interactive HTML5 landing page composed of visual vocabulary primitives.
    
    Composes:
    - Hero: Aurora background + Particle field + 3D WebGL Torus + Kinetic headline + Glass card + Magnetic CTA
    - Features: 3D tilt cards + Bento grid + Spotlight hover + Scroll reveal
    - Product Section: macOS Safari mockup + Terminal + Interactive cursor
    - Footer: Animated gradient mesh + Brand badges
    
    Args:
        title: Page headline and branding title.
        theme: Design theme ('editorial_slate', 'boba_bash', 'swiss_clean', 'terracotta_warm', 'nordic_navy', 'executive_mono', 'cyberpunk_neon').
        brief: Visual and conceptual brief describing the landing page goal.
        hero_cta: Text for the primary magnetic neon CTA button.
        hero_bg: Primary background primitive ('aurora-background', 'interactive-particles', 'retro-grid').
    """
    composer = get_composer()
    components_map = {}
    if hero_bg:
        components_map["hero_bg"] = hero_bg

    try:
        result = composer.compose_page(
            title=title,
            theme_name=theme,
            brief=brief,
            hero_cta_text=hero_cta,
            components_map=components_map,
        )
        return (
            f"### Generated Interactive Landing Page\n"
            f"- **Title**: {result['title']}\n"
            f"- **Theme**: {result['theme_name']} (`{result['theme']}`)\n"
            f"- **Components Composed**: {result['component_count']} primitives\n"
            f"- **Live Preview URL**: [{result['title']} Preview]({result['url']})\n"
            f"- **Local File**: `{result['file_path']}`\n\n"
            f"The site is fully responsive, interactive, and self-contained with Three.js WebGL 3D, "
            f"3D card tilt physics, smooth cursor follower, and particle constellation."
        )
    except Exception as e:
        return f"Failed synthesizing landing page: {e}"


async def component_catalog_summary() -> str:
    """Get live statistics of the visual vocabulary library across all sources and categories."""
    registry = get_registry()
    summary = registry.catalog_summary()

    curated_sources = ", ".join(f"{k.upper()}: {v}" for k, v in summary["curated_by_source"].items())
    curated_cats = ", ".join(f"{k}: {v}" for k, v in summary["curated_by_category"].items())

    return f"""### Visual Vocabulary Catalog Summary
- **Total Curated Signature Components**: {summary['total_curated_components']}
- **Total Indexed Uiverse Galaxy Elements**: {summary['total_indexed_galaxy_components']}
- **Total Visual Assets**: {summary['total_visual_vocabulary_assets']:,}

#### Curated Components by Library Source
{curated_sources}

#### Curated Components by Category
{curated_cats}

#### Integrated Library Hierarchy
1. **UIVERSE GALAXY** (3,800+ community elements: buttons, cards, loaders, forms, inputs)
2. **Aceternity UI** (3D cards, Bento grids, Spotlight illumination, Aurora waves)
3. **Magic UI** (Shimmer button, Border beam, Particle constellation, Safari mockup)
4. **Three.js / WebGL / R3F** (Interactive 3D geometry, Torus knot, Starfields)
5. **GSAP Animation Primitives** (ScrollTrigger, Parallax, Timeline orchestration)
6. **Zenith Proprietary** (Sovereign glassmorphism, Kinetic typography, Tactical HUD)

#### Supported Design Themes
{', '.join(summary['supported_themes'])}
"""

"""Zenith Presentation Component Library Registry.

Houses the structured, reusable presentation primitives:
- Layouts (cinematic-hero, editorial, split-screen, bento, statement, etc.)
- Components (glass-card, giant-stat, quote, comparison-table, process-flow, etc.)
- Effects (glow, grain, gradient-mesh, light-beam, particles, spotlight, etc.)
- Typography (kinetic-title, giant-number, outlined-title, highlighted-word, etc.)
- Data (bar-chart, line-chart, donut-chart, metric-counter, comparison-chart)
- 3D Assets (chrome, glass, metallic, abstract, technology)
- Animations (fade, reveal, stagger, zoom, morph, slide, scale, parallax)
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("zenith.presentation.registry")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MEDIA_AGENT_PRES_DIR = ROOT_DIR / "media-agent" / "presentation"


@dataclass
class PresentationComponentMeta:
    """Metadata schema for all presentation library assets."""
    id: str
    name: str
    type: str  # layout, component, effect, typography, data, 3d, animation
    tags: List[str]
    visualIntensity: int  # 1 to 5
    bestFor: List[str]
    compatibleStyles: List[str]
    description: str
    components: List[str] = field(default_factory=list)
    motion: List[str] = field(default_factory=list)
    default_props: Dict[str, Any] = field(default_factory=dict)


# ── Curated Presentation Library Catalog ─────────────────────────────────────

CURATED_PRESENTATION_LIBRARY: List[PresentationComponentMeta] = [
    # ── LAYOUTS ───────────────────────────────────────────────────────────────
    PresentationComponentMeta(
        id="cinematic-hero",
        name="Cinematic Hero Layout",
        type="layout",
        tags=["cinematic", "futuristic", "hero", "opening", "3d", "light-beam"],
        visualIntensity=5,
        bestFor=["opening", "section-divider", "closing", "keynote"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative"],
        description="High-contrast opening hero featuring kinetic typography, 3D floating object, dramatic directional light beam, and particle depth.",
        components=["kinetic-title", "3d-hero-object", "light-beam", "eyebrow-pill"],
        motion=["stagger-reveal", "slow-zoom", "morph"],
    ),
    PresentationComponentMeta(
        id="editorial",
        name="Asymmetric Editorial Layout",
        type="layout",
        tags=["editorial", "magazine", "whitespace", "sophisticated", "asymmetric"],
        visualIntensity=3,
        bestFor=["thesis", "concept", "product-reveal", "brand"],
        compatibleStyles=["premium-editorial", "minimal-premium"],
        description="Swiss & Pentagram-inspired editorial layout with large headline typography, asymmetric margins, and refined metadata caption blocks.",
        components=["editorial-title", "glass-card", "metadata-caption"],
        motion=["fade", "slide-up"],
    ),
    PresentationComponentMeta(
        id="split-screen",
        name="Split Screen 50/50 Layout",
        type="layout",
        tags=["split", "50-50", "visual-thesis", "comparison", "clean"],
        visualIntensity=3,
        bestFor=["thesis", "photo-story", "product-preview", "team"],
        compatibleStyles=["premium-editorial", "minimal-premium", "cinematic-futuristic", "playful-youthful"],
        description="Clean 50/50 balance between bold takeaway text on the left and a high-resolution visual/mockup on the right.",
        components=["headline", "bullets-pill", "device-mockup", "photo-container"],
        motion=["slide-up", "fade"],
    ),
    PresentationComponentMeta(
        id="bento",
        name="Modern Bento Grid Layout",
        type="layout",
        tags=["bento", "grid", "cards", "modular", "high-density", "features"],
        visualIntensity=4,
        bestFor=["features", "capabilities", "product-tiers", "overview"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Asymmetric 4-box bento grid showcasing distinct capabilities with subtle hairline borders, badges, and glowing highlights.",
        components=["glass-card", "feature-badge", "mini-stat", "icon-node"],
        motion=["stagger-reveal", "scale"],
    ),
    PresentationComponentMeta(
        id="statement",
        name="One Big Idea Statement Layout",
        type="layout",
        tags=["statement", "one-big-idea", "breathing-room", "typography", "bold"],
        visualIntensity=2,
        bestFor=["breathing-room", "transition", "quote", "core-message"],
        compatibleStyles=["minimal-premium", "premium-editorial", "cinematic-futuristic"],
        description="Single monumental thesis statement giving audiences breathing room between complex analytical slides.",
        components=["monumental-headline", "eyebrow-pill"],
        motion=["fade", "zoom"],
    ),
    PresentationComponentMeta(
        id="timeline",
        name="Connected Roadmap Timeline Layout",
        type="layout",
        tags=["timeline", "roadmap", "milestones", "quarters", "process"],
        visualIntensity=3,
        bestFor=["roadmap", "milestones", "history", "execution"],
        compatibleStyles=["premium-editorial", "minimal-premium", "cinematic-futuristic", "playful-youthful"],
        description="Horizontal milestone roadmap with connected neon/champagne hairline axes and progressive node status tags.",
        components=["timeline-node", "timeline-axis", "milestone-badge"],
        motion=["slide-up", "stagger-reveal"],
    ),
    PresentationComponentMeta(
        id="process",
        name="Step-by-Step Flow Layout",
        type="layout",
        tags=["process", "flow", "steps", "sequential", "diagram"],
        visualIntensity=3,
        bestFor=["workflow", "pipeline", "user-journey", "architecture"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium", "playful-youthful"],
        description="Visual sequential flow converting paragraphs into clear horizontal arrow-linked stage blocks.",
        components=["process-step", "arrow-connector", "step-number"],
        motion=["stagger-reveal"],
    ),
    PresentationComponentMeta(
        id="data-story",
        name="Data Story & Metric Layout",
        type="layout",
        tags=["data", "metrics", "kpi", "chart", "statistics", "growth"],
        visualIntensity=3,
        bestFor=["kpis", "financials", "growth", "performance"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Pairing giant metric counters and embedded visualizations with concise analytical takeaway punchlines.",
        components=["giant-stat", "chart-container", "takeaway-pill"],
        motion=["fade", "slide-up"],
    ),
    PresentationComponentMeta(
        id="comparison",
        name="Side-by-Side Comparison Layout",
        type="layout",
        tags=["comparison", "before-after", "legacy-modern", "versus"],
        visualIntensity=3,
        bestFor=["competitive-analysis", "before-after", "architecture-shift"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="High-contrast dual column comparison contrasting legacy frictions against modern sovereign capabilities.",
        components=["comparison-column", "contrast-badge"],
        motion=["slide-up"],
    ),
    PresentationComponentMeta(
        id="case-study",
        name="Challenge-Solution-Impact Layout",
        type="layout",
        tags=["case-study", "validation", "customer", "results"],
        visualIntensity=3,
        bestFor=["customer-story", "proof-point", "validation"],
        compatibleStyles=["premium-editorial", "minimal-premium", "cinematic-futuristic"],
        description="Three-column progressive case study layout tracking Problem -> Architecture -> Quantifiable Outcome.",
        components=["story-card", "metric-pill"],
        motion=["stagger-reveal"],
    ),
    PresentationComponentMeta(
        id="closing",
        name="Executive Closing & CTA Layout",
        type="layout",
        tags=["closing", "cta", "contact", "final", "hero"],
        visualIntensity=4,
        bestFor=["closing", "final-hero", "cta"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium", "playful-youthful"],
        description="Authoritative closing statement paired with primary contact channels, author credentials, and live CTA.",
        components=["closing-headline", "cta-button", "contact-pill"],
        motion=["fade", "zoom"],
    ),
    PresentationComponentMeta(
        id="image-bleed",
        name="Full Bleed Visual Layout",
        type="layout",
        tags=["image-bleed", "bleed", "dramatic", "visual", "art-directed", "cinematic"],
        visualIntensity=5,
        bestFor=["product-reveal", "visual-thesis", "keynote", "brand"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative", "premium-editorial"],
        description="Dramatic visual showcase with contrast backdrop scrim, overlaid typography, and key punchlines.",
        components=["bleed-container", "scrim-overlay", "hero-title", "feature-card"],
        motion=["zoom", "fade"],
    ),

    # ── COMPONENTS ────────────────────────────────────────────────────────────
    PresentationComponentMeta(
        id="glass-card",
        name="Glassmorphic Container Card",
        type="component",
        tags=["glass", "blur", "card", "frosted", "container"],
        visualIntensity=3,
        bestFor=["cards", "bento", "features"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Frosted glass rounded surface with translucent background, hairline border, and subtle inner glow.",
    ),
    PresentationComponentMeta(
        id="floating-card",
        name="Floating Elevation Card",
        type="component",
        tags=["floating", "elevation", "depth", "shadow", "card"],
        visualIntensity=3,
        bestFor=["features", "bento", "split-screen"],
        compatibleStyles=["premium-editorial", "minimal-premium", "cinematic-futuristic"],
        description="Elevated card with deep drop shadow and layered depth off the canvas plane.",
    ),
    PresentationComponentMeta(
        id="giant-stat",
        name="Giant KPI Metric Counter",
        type="component",
        tags=["stat", "kpi", "number", "growth", "percentage"],
        visualIntensity=4,
        bestFor=["data-story", "financials", "traction"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Oversized 64pt+ numerical metric with colorful delta percentage indicator and two-line context label.",
    ),
    PresentationComponentMeta(
        id="quote",
        name="Editorial Quote Block",
        type="component",
        tags=["quote", "testimonial", "statement", "editorial", "voice"],
        visualIntensity=3,
        bestFor=["statement", "case-study", "thesis"],
        compatibleStyles=["premium-editorial", "minimal-premium", "cinematic-futuristic"],
        description="Monumental quotation with stylized accent quotation marks and executive attribution pill.",
    ),
    PresentationComponentMeta(
        id="feature-card",
        name="Structured Feature Card",
        type="component",
        tags=["feature", "card", "pillar", "bullets", "structured"],
        visualIntensity=2,
        bestFor=["bento", "cards-grid", "overview"],
        compatibleStyles=["minimal-premium", "premium-editorial", "playful-youthful"],
        description="Clean card with bold title header, subtitle, and concise high-signal bullet takeaways.",
    ),
    PresentationComponentMeta(
        id="comparison-table",
        name="Comparison Matrix Block",
        type="component",
        tags=["comparison", "table", "versus", "matrix", "legacy-modern"],
        visualIntensity=3,
        bestFor=["comparison", "competitive-analysis"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Side-by-side comparative column card contrasting legacy paradigms against modern architectures.",
    ),
    PresentationComponentMeta(
        id="timeline-node",
        name="Roadmap Timeline Node",
        type="component",
        tags=["timeline", "milestone", "node", "phase", "quarter"],
        visualIntensity=3,
        bestFor=["timeline", "roadmap", "milestones"],
        compatibleStyles=["premium-editorial", "minimal-premium", "cinematic-futuristic"],
        description="Connected chronological milestone node with active status badge, title, and milestone date.",
    ),
    PresentationComponentMeta(
        id="browser-mockup",
        name="macOS Browser Frame Mockup",
        type="component",
        tags=["mockup", "browser", "safari", "product", "demo"],
        visualIntensity=3,
        bestFor=["split-screen", "product-reveal", "features"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Safari-style desktop browser window chrome with colored traffic controls and URL address capsule.",
    ),
    PresentationComponentMeta(
        id="phone-mockup",
        name="Mobile Device Mockup Frame",
        type="component",
        tags=["mockup", "phone", "mobile", "ios", "app"],
        visualIntensity=3,
        bestFor=["split-screen", "product-reveal", "mobile"],
        compatibleStyles=["cinematic-futuristic", "playful-youthful", "minimal-premium"],
        description="Curved smartphone chassis mockup showing responsive application interface.",
    ),
    PresentationComponentMeta(
        id="device-mockup",
        name="Hardware Device Mockup Frame",
        type="component",
        tags=["mockup", "device", "hardware", "terminal", "iot"],
        visualIntensity=4,
        bestFor=["split-screen", "cinematic-hero", "hardware"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Sleek modern terminal device frame displaying live system telemetry or dashboards.",
    ),
    PresentationComponentMeta(
        id="process-flow",
        name="Horizontal Stage Flow Diagram",
        type="component",
        tags=["flow", "process", "pipeline", "horizontal"],
        visualIntensity=3,
        bestFor=["process", "architecture", "timeline"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Horizontal interconnected stage nodes linked by arrow paths showing clear procedural progression.",
    ),

    # ── EFFECTS ───────────────────────────────────────────────────────────────
    PresentationComponentMeta(
        id="glow",
        name="Radial Conic Glow",
        type="effect",
        tags=["glow", "aura", "ambient", "neon"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "cta"],
        compatibleStyles=["cinematic-futuristic"],
        description="Radial neon aura adding luminous ambient intensity behind focal visual assets.",
    ),
    PresentationComponentMeta(
        id="grain",
        name="Film Grain Texture",
        type="effect",
        tags=["grain", "film", "texture", "editorial", "analog"],
        visualIntensity=2,
        bestFor=["editorial", "statement", "cinematic-hero"],
        compatibleStyles=["premium-editorial", "experimental-creative"],
        description="Micro-textured analog grain overlay imparting tactile prestige and eliminating banding.",
    ),
    PresentationComponentMeta(
        id="gradient-mesh",
        name="Chromatic Gradient Mesh",
        type="effect",
        tags=["gradient", "mesh", "chromatic", "color", "background"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "image-bleed", "closing"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative", "playful-youthful"],
        description="Multi-point fluid chromatic mesh blending vibrant accent hues across dark surfaces.",
    ),
    PresentationComponentMeta(
        id="light-beam",
        name="Directional Light Beam",
        type="effect",
        tags=["light-beam", "laser", "cinema", "focus"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "statement"],
        compatibleStyles=["cinematic-futuristic"],
        description="Diagonal luminescent light beam casting directional highlight across dark slide canvas.",
    ),
    PresentationComponentMeta(
        id="particles",
        name="Floating Stardust Particle Field",
        type="effect",
        tags=["particles", "constellation", "depth", "stars"],
        visualIntensity=3,
        bestFor=["hero", "cinematic-hero", "background"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Subtle floating stardust particle nodes establishing multi-layer visual depth.",
    ),
    PresentationComponentMeta(
        id="perspective-grid",
        name="3D Perspective Horizon Grid",
        type="effect",
        tags=["grid", "perspective", "horizon", "retro", "synth"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "closing"],
        compatibleStyles=["cinematic-futuristic"],
        description="Floor plane receding wireframe grid conveying vast technological horizon.",
    ),
    PresentationComponentMeta(
        id="spotlight",
        name="Dynamic Key Spotlight",
        type="effect",
        tags=["spotlight", "lighting", "focus", "theatrical"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "split-screen"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Theatrical overhead key light highlighting hero subject while falloff darkens edges.",
    ),
    PresentationComponentMeta(
        id="glass",
        name="Refractive Glass Shader",
        type="effect",
        tags=["glass", "frosted", "refraction", "blur"],
        visualIntensity=3,
        bestFor=["bento", "cards-grid"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Backdrop-blur glass effect simulating physically frosted crystal or acrylic.",
    ),
    PresentationComponentMeta(
        id="shadow-depth",
        name="Ambient Shadow Occlusion Depth",
        type="effect",
        tags=["shadow", "depth", "occlusion", "realism"],
        visualIntensity=3,
        bestFor=["bento", "floating-card", "split-screen"],
        compatibleStyles=["premium-editorial", "minimal-premium", "cinematic-futuristic"],
        description="Multi-layered soft ambient drop shadows delivering physical elevation without harsh edges.",
    ),

    # ── TYPOGRAPHY ────────────────────────────────────────────────────────────
    PresentationComponentMeta(
        id="kinetic-title",
        name="Kinetic Oversized Headline",
        type="typography",
        tags=["typography", "kinetic", "headline", "oversized", "bold"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "statement", "closing"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative"],
        description="Monumental headline with deliberate word-weight hierarchy and highlighted emphasis keywords.",
    ),
    PresentationComponentMeta(
        id="giant-number",
        name="Giant Visual Metric Number",
        type="typography",
        tags=["typography", "giant-number", "stats", "delta"],
        visualIntensity=4,
        bestFor=["data-story", "stat-hero"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Super-bold 68pt+ typographic numeral conveying dramatic growth or scale.",
    ),
    PresentationComponentMeta(
        id="outlined-title",
        name="Outlined Wireframe Title",
        type="typography",
        tags=["typography", "outlined", "stroke", "futuristic", "wireframe"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "closing", "statement"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative"],
        description="Transparent fill headline with luminous outer hairline stroke defining architectural letterforms.",
    ),
    PresentationComponentMeta(
        id="gradient-title",
        name="Multi-Stop Gradient Title",
        type="typography",
        tags=["typography", "gradient", "color", "vibrant"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "statement"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative", "playful-youthful"],
        description="Luminous dual-tone linear color gradient sweeping horizontally through headline text.",
    ),
    PresentationComponentMeta(
        id="highlighted-word",
        name="Emphasis Word Capsule Tag",
        type="typography",
        tags=["typography", "highlight", "tag", "emphasis", "contrast"],
        visualIntensity=3,
        bestFor=["statement", "editorial", "bento"],
        compatibleStyles=["premium-editorial", "playful-youthful", "minimal-premium"],
        description="Accent color capsule background surrounding a singular focal keyword within headline.",
    ),
    PresentationComponentMeta(
        id="editorial-caption",
        name="Micro Editorial Caption",
        type="typography",
        tags=["typography", "caption", "metadata", "editorial", "refined"],
        visualIntensity=2,
        bestFor=["editorial", "case-study", "split-screen"],
        compatibleStyles=["premium-editorial", "minimal-premium"],
        description="Monospaced or small-caps metadata caption providing technical precision and context.",
    ),

    # ── DATA ──────────────────────────────────────────────────────────────────
    PresentationComponentMeta(
        id="bar-chart",
        name="Native Column / Bar Chart",
        type="data",
        tags=["chart", "bar", "column", "growth", "revenue", "data"],
        visualIntensity=3,
        bestFor=["data-story", "financials"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Editable native PowerPoint column chart rendered with theme palette accents.",
    ),
    PresentationComponentMeta(
        id="line-chart",
        name="Native Trend Line Chart",
        type="data",
        tags=["chart", "line", "trend", "velocity", "forecast", "data"],
        visualIntensity=3,
        bestFor=["data-story", "financials", "projections"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Editable native PowerPoint line chart showing continuous velocity and projection trajectories.",
    ),
    PresentationComponentMeta(
        id="donut-chart",
        name="Native Doughnut Share Chart",
        type="data",
        tags=["chart", "donut", "doughnut", "share", "allocation", "data"],
        visualIntensity=3,
        bestFor=["data-story", "market-share", "allocation"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "minimal-premium"],
        description="Segmented doughnut ring illustrating market share or resource distribution breakdown.",
    ),
    PresentationComponentMeta(
        id="radar-chart",
        name="Radar Capability Map",
        type="data",
        tags=["chart", "radar", "spider", "capabilities", "matrix", "data"],
        visualIntensity=4,
        bestFor=["data-story", "comparison", "capabilities"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Polygonal capability matrix benchmarking multiple operational vectors simultaneously.",
    ),

    # ── 3D ASSETS ─────────────────────────────────────────────────────────────
    PresentationComponentMeta(
        id="chrome-orb",
        name="Iridescent Chrome Orb",
        type="3d",
        tags=["3d", "chrome", "orb", "metallic", "iridescent"],
        visualIntensity=5,
        bestFor=["cinematic-hero", "split-screen"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative"],
        description="Reflective metallic chrome sphere reacting to directional studio lighting.",
    ),
    PresentationComponentMeta(
        id="glass-sphere",
        name="Frosted Glass Hologram Sphere",
        type="3d",
        tags=["3d", "glass", "sphere", "frosted", "depth"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "statement"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Translucent frosted glass volumetric sphere with internal refracted glow.",
    ),
    PresentationComponentMeta(
        id="metallic-ring",
        name="Torus Metallic Ring",
        type="3d",
        tags=["3d", "torus", "ring", "metallic", "orbit"],
        visualIntensity=5,
        bestFor=["cinematic-hero", "statement", "closing"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative"],
        description="Floating precision metallic torus ring representing infinity or cyclical loops.",
    ),
    PresentationComponentMeta(
        id="network-structure",
        name="Node Mesh Network Structure",
        type="3d",
        tags=["3d", "network", "mesh", "nodes", "graph", "ai"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "split-screen", "bento"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Three-dimensional constellation lattice of interconnected knowledge graph nodes.",
    ),
    PresentationComponentMeta(
        id="abstract-geometry",
        name="Sculptural Abstract Solid",
        type="3d",
        tags=["3d", "abstract", "sculpture", "geometry", "art"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "image-bleed"],
        compatibleStyles=["experimental-creative", "premium-editorial"],
        description="Procedural parametric sculptural geometry acting as an art-directed visual anchor.",
    ),

    # ── ANIMATIONS ────────────────────────────────────────────────────────────
    PresentationComponentMeta(
        id="fade",
        name="Smooth Opacity Dissolve",
        type="animation",
        tags=["animation", "fade", "dissolve", "subtle"],
        visualIntensity=2,
        bestFor=["statement", "editorial", "case-study"],
        compatibleStyles=["minimal-premium", "premium-editorial"],
        description="Subtle 0.4s cross-fade transition preserving dignified visual quietude.",
    ),
    PresentationComponentMeta(
        id="stagger-reveal",
        name="Staggered Entrance Sequence",
        type="animation",
        tags=["animation", "stagger", "reveal", "motion"],
        visualIntensity=3,
        bestFor=["cards", "bento", "timeline", "process"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial", "playful-youthful"],
        description="Cascading sequential reveal with 0.12s staggered delay between cards and nodes.",
    ),
    PresentationComponentMeta(
        id="morph",
        name="PowerPoint Morph Transition",
        type="animation",
        tags=["animation", "morph", "transition", "seamless"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "process", "bento"],
        compatibleStyles=["cinematic-futuristic", "premium-editorial"],
        description="Seamless slide-to-slide geometric transformation animating matching elements between slides.",
    ),
    PresentationComponentMeta(
        id="zoom",
        name="Dramatic Cinematic Zoom",
        type="animation",
        tags=["animation", "zoom", "scale", "hero"],
        visualIntensity=5,
        bestFor=["cinematic-hero", "closing"],
        compatibleStyles=["cinematic-futuristic", "experimental-creative"],
        description="Impactful forward lens punch zoom introducing pivotal thesis statements.",
    ),
    PresentationComponentMeta(
        id="slide-up",
        name="Upward Kinetic Rise",
        type="animation",
        tags=["animation", "slide-up", "rise", "modern"],
        visualIntensity=3,
        bestFor=["split-screen", "cards", "data-story"],
        compatibleStyles=["premium-editorial", "minimal-premium"],
        description="Upward elevation entrance mimicking high-end web interactions.",
    ),
    PresentationComponentMeta(
        id="slow-float",
        name="Ambient Slow Float Motion",
        type="animation",
        tags=["animation", "float", "ambient", "3d"],
        visualIntensity=4,
        bestFor=["cinematic-hero", "3d"],
        compatibleStyles=["cinematic-futuristic"],
        description="Subtle continuous floating oscillation imparting lifelike presence to 3D hero assets.",
    ),
]


class PresentationComponentRegistry:
    """Registry engine for presentation layouts, components, effects, and 3D assets."""

    def __init__(self) -> None:
        self._items: Dict[str, PresentationComponentMeta] = {
            item.id: item for item in CURATED_PRESENTATION_LIBRARY
        }
        self.export_to_media_agent()

    def export_to_media_agent(self) -> None:
        """Ensure media-agent/presentation directory structure is synchronized on disk."""
        try:
            for item in self._items.values():
                folder = MEDIA_AGENT_PRES_DIR / f"{item.type}s" / item.id
                folder.mkdir(parents=True, exist_ok=True)
                meta_file = folder / "metadata.json"
                if not meta_file.exists():
                    meta_file.write_text(json.dumps(asdict(item), indent=2), encoding="utf-8")
        except Exception as e:
            log.warning("Could not sync presentation registry to disk: %s", e)

    def search(
        self,
        query: str = "",
        type_filter: Optional[str] = None,
        intensity: Optional[int] = None,
        style: Optional[str] = None,
        limit: int = 10,
    ) -> List[PresentationComponentMeta]:
        """Search presentation component registry by keyword, type, intensity, and compatible style."""
        q = (query or "").lower().strip()
        results: List[Tuple[int, PresentationComponentMeta]] = []

        for item in self._items.values():
            if type_filter and item.type.lower() != type_filter.lower().rstrip("s"):
                continue

            if intensity is not None and item.visualIntensity > intensity:
                continue

            if style and item.compatibleStyles and style.lower() not in [s.lower() for s in item.compatibleStyles]:
                continue

            score = 0
            if q:
                if q in item.id.lower():
                    score += 5
                if q in item.name.lower():
                    score += 4
                if any(q in t.lower() for t in item.tags):
                    score += 3
                if any(q in b.lower() for b in item.bestFor):
                    score += 2
                if q in item.description.lower():
                    score += 1
                if score == 0:
                    continue
            else:
                score = item.visualIntensity

            results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    def get(self, item_id: str) -> Optional[PresentationComponentMeta]:
        """Retrieve presentation component by ID."""
        return self._items.get(item_id)

    def list_layouts(self) -> List[PresentationComponentMeta]:
        """List all available slide layouts."""
        return [item for item in self._items.values() if item.type == "layout"]

    def list_components(self) -> List[PresentationComponentMeta]:
        """List all available visual components."""
        return [item for item in self._items.values() if item.type == "component"]


_PRES_REGISTRY_INSTANCE: Optional[PresentationComponentRegistry] = None


def get_presentation_registry() -> PresentationComponentRegistry:
    """Get or initialize singleton presentation registry."""
    global _PRES_REGISTRY_INSTANCE
    if _PRES_REGISTRY_INSTANCE is None:
        _PRES_REGISTRY_INSTANCE = PresentationComponentRegistry()
    return _PRES_REGISTRY_INSTANCE

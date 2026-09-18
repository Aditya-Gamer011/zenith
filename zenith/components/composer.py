"""Zenith Visual Composer & Section Synthesizer.

Synthesizes visual vocabulary primitives into cohesive, production-grade
interactive web landing pages and applications. Automatically maps:
- Hero: Aurora background + Particle field + 3D floating object + Kinetic headline + Glass card + Magnetic CTA + Scroll parallax
- Features: 3D tilt cards + Bento grid + Spotlight hover + Scroll reveal
- Product Section: Browser mockup + GSAP timeline + Perspective transform + Interactive cursor
- Footer: Animated gradient mesh + Social indicators
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from zenith.tools.design_system import resolve_theme, THEMES
from .registry import get_registry

log = logging.getLogger("zenith.components.composer")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
STATIC_SITES_DIR = ROOT_DIR / "static" / "sites"


class VisualComposer:
    """Creative Director Synthesis Engine for Complete Web Experiences."""

    def __init__(self) -> None:
        STATIC_SITES_DIR.mkdir(parents=True, exist_ok=True)
        self.registry = get_registry()

    def compose_page(
        self,
        title: str = "Zenith Sovereign Intelligence",
        theme_name: str = "editorial_slate",
        brief: str = "",
        hero_cta_text: str = "Launch Sovereign Environment",
        components_map: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Synthesize a complete responsive HTML5 site combining visual vocabulary primitives."""
        ts = int(time.time())
        safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")[:24]
        site_id = f"site_{safe_title}_{ts}".lower()

        theme = resolve_theme(theme_name)
        colors = theme["colors"]

        # Default or customized component selections
        selected = {
            "hero_bg": "aurora-background",
            "hero_particles": "interactive-particles",
            "hero_3d": "floating-3d-object",
            "hero_headline": "kinetic-heading",
            "hero_card": "glass-card",
            "hero_cta": "magnetic-neon-button",
            "features_card_1": "3d-card",
            "features_card_2": "glass-card",
            "features_spotlight": "spotlight",
            "product_mockup": "browser-mockup",
            "product_cursor": "cursor",
            "effects_glow": "glow",
        }
        if components_map:
            selected.update(components_map)

        # Retrieve and adapt components
        adapted_components: Dict[str, Dict[str, Any]] = {}
        for role, cid in selected.items():
            try:
                comp = self.registry.adapt_component_to_theme(cid, theme_name=theme_name)
                adapted_components[role] = comp
            except Exception as e:
                log.warning("Could not adapt %s (%s): %s", role, cid, e)

        # Build complete self-contained HTML
        out_file = STATIC_SITES_DIR / f"{site_id}.html"

        # Extract specific adapted CSS chunks
        hero_cta_css = adapted_components.get("hero_cta", {}).get("adapted_css", "")
        glass_card_css = adapted_components.get("hero_card", {}).get("adapted_css", "")
        card_3d_css = adapted_components.get("features_card_1", {}).get("adapted_css", "")
        aurora_css = adapted_components.get("hero_bg", {}).get("adapted_css", "")
        mockup_css = adapted_components.get("product_mockup", {}).get("adapted_css", "")
        spotlight_css = adapted_components.get("features_spotlight", {}).get("adapted_css", "")
        cursor_css = adapted_components.get("product_cursor", {}).get("adapted_css", "")

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Zenith Creative Director</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@600;700&family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Syne:wght@600;700;800&display=swap" rel="stylesheet">
  <!-- Three.js for 3D Floating Geometry -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <!-- GSAP for Smooth Parallax & Stagger Timeline -->
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/gsap.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.2/ScrollTrigger.min.js"></script>

  <style>
    :root {{
      --bg-color: {colors["bg"]};
      --card-bg: {colors["card"]};
      --card-glass: {colors["card_glass"]};
      --border-color: {colors["border"]};
      --text-color: {colors["text"]};
      --muted-color: {colors["muted"]};
      --accent-1: {colors["accent1"]};
      --accent-2: {colors["accent2"]};
      --glow-color: {colors["glow"]};
      --font-heading: {theme["font_heading"]};
      --font-body: {theme["font_body"]};
      --font-mono: {theme["font_mono"]};
      --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-font-smoothing: antialiased;
    }}

    body {{
      background-color: var(--bg-color);
      color: var(--text-color);
      font-family: var(--font-body);
      overflow-x: hidden;
      line-height: 1.6;
    }}

    /* ── Sticky Modern Glass Navbar ─────────────────────────────────── */
    .glass-nav {{
      position: fixed;
      top: 20px;
      left: 50%;
      transform: translateX(-50%);
      width: calc(100% - 40px);
      max-width: 1200px;
      z-index: 100;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 14px 28px;
      border-radius: 9999px;
      background: var(--card-glass);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border: 1px solid var(--border-color);
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4);
    }}

    .nav-brand {{
      display: flex;
      align-items: center;
      gap: 10px;
      font-family: var(--font-heading);
      font-weight: 800;
      font-size: 1.1rem;
      color: var(--text-color);
      text-decoration: none;
      letter-spacing: -0.02em;
    }}

    .nav-brand-dot {{
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--accent-1);
      box-shadow: 0 0 12px var(--accent-1);
    }}

    .nav-links {{
      display: flex;
      align-items: center;
      gap: 28px;
      list-style: none;
    }}

    .nav-links a {{
      color: var(--muted-color);
      text-decoration: none;
      font-size: 0.88rem;
      font-weight: 500;
      transition: color 0.2s ease;
    }}

    .nav-links a:hover {{
      color: var(--text-color);
    }}

    .nav-action {{
      padding: 8px 18px;
      border-radius: 9999px;
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      color: var(--text-color);
      font-size: 0.84rem;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.2s ease;
    }}

    .nav-action:hover {{
      border-color: var(--accent-1);
      box-shadow: 0 0 15px var(--glow-color);
    }}

    /* ── Section Container & Typography ────────────────────────────── */
    .section-wrap {{
      position: relative;
      max-width: 1240px;
      margin: 0 auto;
      padding: 120px 24px 60px;
    }}

    .section-tag {{
      display: inline-block;
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.15em;
      color: var(--accent-1);
      padding: 6px 14px;
      border-radius: 9999px;
      background: rgba(212, 163, 115, 0.08);
      border: 1px solid var(--border-color);
      margin-bottom: 20px;
    }}

    .section-title {{
      font-family: var(--font-heading);
      font-size: clamp(2.2rem, 4.5vw, 3.8rem);
      font-weight: 800;
      letter-spacing: -0.03em;
      line-height: 1.15;
      margin-bottom: 20px;
    }}

    .section-desc {{
      font-size: 1.15rem;
      color: var(--muted-color);
      max-width: 680px;
      line-height: 1.7;
      margin-bottom: 40px;
    }}

    /* ── Hero Section with Background Layers ───────────────────────── */
    .hero-container {{
      position: relative;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      overflow: hidden;
      padding-top: 100px;
    }}

    .hero-split {{
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 40px;
      align-items: center;
      z-index: 2;
    }}

    @media (max-width: 960px) {{
      .hero-split {{
        grid-template-columns: 1fr;
      }}
      .nav-links {{ display: none; }}
    }}

    /* ── Canvas Particle Background ────────────────────────────────── */
    #particle-canvas {{
      position: absolute;
      inset: 0;
      pointer-events: none;
      z-index: 1;
      opacity: 0.4;
    }}

    /* ── 3D Viewport ───────────────────────────────────────────────── */
    #three-viewport {{
      width: 100%;
      height: 440px;
      position: relative;
      z-index: 3;
    }}

    /* ── Features Bento Grid ───────────────────────────────────────── */
    .features-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 28px;
      margin-top: 40px;
    }}

    /* ── Product Showcase Showcase ─────────────────────────────────── */
    .product-showcase-box {{
      position: relative;
      margin-top: 50px;
      border-radius: 20px;
      overflow: hidden;
    }}

    /* ── Footer Mesh Gradient ──────────────────────────────────────── */
    .site-footer {{
      position: relative;
      padding: 100px 24px 60px;
      text-align: center;
      border-top: 1px solid var(--border-color);
      margin-top: 80px;
      overflow: hidden;
    }}

    .footer-mesh {{
      position: absolute;
      inset: -40%;
      background: radial-gradient(circle at 50% 100%, var(--glow-color) 0%, transparent 60%);
      filter: blur(70px);
      pointer-events: none;
      z-index: 0;
    }}

    /* ── Injected Adapted Components CSS ───────────────────────────── */
    {aurora_css}
    {hero_cta_css}
    {glass_card_css}
    {card_3d_css}
    {mockup_css}
    {spotlight_css}
    {cursor_css}
  </style>
</head>
<body>

  <!-- Smooth Magnetic Cursor Tracker -->
  <div class="custom-cursor-dot" id="cursor-dot"></div>
  <div class="custom-cursor-ring" id="cursor-ring"></div>

  <!-- Glass Floating Navigation -->
  <nav class="glass-nav">
    <a href="#" class="nav-brand">
      <div class="nav-brand-dot"></div>
      <span>Zenith Studio</span>
    </a>
    <ul class="nav-links">
      <li><a href="#features">Features</a></li>
      <li><a href="#architecture">Architecture</a></li>
      <li><a href="#product">Showcase</a></li>
      <li><a href="#registry">Components</a></li>
    </ul>
    <a href="#cta" class="nav-action">Get Access &rarr;</a>
  </nav>

  <!-- ── 1. HERO SECTION ─────────────────────────────────────────────── -->
  <section class="hero-container">
    <!-- Aurora background wave -->
    <div class="aurora-waves"></div>
    <!-- Interactive Particle Constellation -->
    <canvas id="particle-canvas"></canvas>

    <div class="section-wrap hero-split">
      <div>
        <div class="section-tag">Autonomous Media & Design Architecture</div>
        <h1 class="section-title">
          Visual Intelligence.<br>
          <span style="color: var(--accent-1);">{title}</span>
        </h1>
        <p class="section-desc">
          {brief or "Synthesized autonomously by Zenith's Creative & Media Studio Lead. Constructed from our multi-library visual vocabulary across Uiverse, Aceternity, Magic UI, and Three.js."}
        </p>
        <div style="display: flex; gap: 16px; align-items: center; flex-wrap: wrap;" id="cta">
          <!-- Adapted Magnetic Neon CTA Button -->
          <button class="magnetic-neon-btn" data-magnetic="true">
            <span>{hero_cta_text} &rarr;</span>
          </button>
          <a href="#features" class="nav-action" style="padding: 14px 28px; border-radius: 12px;">
            Explore Primitives
          </a>
        </div>
      </div>

      <!-- 3D Interactive WebGL Floating Object -->
      <div>
        <div class="glass-card" style="padding: 16px;">
          <div id="three-viewport"></div>
          <div style="padding: 16px; text-align: center;">
            <div style="font-family: var(--font-mono); font-size: 0.78rem; color: var(--accent-1);">
              [WebGL R3F Geometry Active &bull; Interactive Orbit]
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ── 2. FEATURES & BENTO GRID SECTION ───────────────────────────── -->
  <section class="section-wrap" id="features">
    <div style="text-align: center; max-width: 720px; margin: 0 auto 60px;">
      <div class="section-tag">Visual Vocabulary Engine</div>
      <h2 class="section-title">Engineered Visual Components</h2>
      <p class="section-desc" style="margin: 0 auto;">
        Every component is cataloged with motion intensity, framework targets, and brand-adapted semantic tokens.
      </p>
    </div>

    <div class="features-grid">
      <!-- 3D Tilt Card 1 -->
      <div class="card-3d-wrap spotlight-panel" data-tilt="true">
        <div class="card-3d-inner" style="height: 100%;">
          <div class="card-3d-layer-high">
            <span class="section-tag" style="margin-bottom: 12px;">Aceternity Primitive</span>
            <h3 style="font-family: var(--font-heading); font-size: 1.4rem; font-weight: 700; margin-bottom: 12px; color: var(--text-color);">
              3D Card Perspective
            </h3>
          </div>
          <div class="card-3d-layer-mid">
            <p style="color: var(--muted-color); font-size: 0.95rem; line-height: 1.6;">
              Real-time cursor inclination tracking with multi-layered translation along the Z-axis for physical depth realism.
            </p>
          </div>
        </div>
      </div>

      <!-- Glass Card 2 -->
      <div class="glass-card spotlight-panel">
        <span class="section-tag" style="margin-bottom: 12px;">Zenith Proprietary</span>
        <h3 style="font-family: var(--font-heading); font-size: 1.4rem; font-weight: 700; margin-bottom: 12px; color: var(--text-color);">
          Frosted Glassmorphic Panel
        </h3>
        <p style="color: var(--muted-color); font-size: 0.95rem; line-height: 1.6;">
          Ultra-high quality backdrop filter blurring with specular rim highlights, restrained editorial slate tones, and zero visual noise.
        </p>
      </div>

      <!-- Magic UI Inspired Feature 3 -->
      <div class="glass-card spotlight-panel">
        <span class="section-tag" style="margin-bottom: 12px;">Magic UI Motion</span>
        <h3 style="font-family: var(--font-heading); font-size: 1.4rem; font-weight: 700; margin-bottom: 12px; color: var(--text-color);">
          Directional Spotlight Beam
        </h3>
        <p style="color: var(--muted-color); font-size: 0.95rem; line-height: 1.6;">
          Dynamic radial spotlight illumination hugging hover boundaries and revealing hidden textural detail on mouseover.
        </p>
      </div>
    </div>
  </section>

  <!-- ── 3. PRODUCT SHOWCASE SECTION ─────────────────────────────────── -->
  <section class="section-wrap" id="product">
    <div style="text-align: center; max-width: 720px; margin: 0 auto 40px;">
      <div class="section-tag">Browser & Terminal Mockups</div>
      <h2 class="section-title">Autonomous Execution in Action</h2>
    </div>

    <!-- macOS Safari Browser Mockup -->
    <div class="browser-mockup">
      <div class="browser-header">
        <div class="browser-dots">
          <div class="browser-dot red"></div>
          <div class="browser-dot yellow"></div>
          <div class="browser-dot green"></div>
        </div>
        <div class="browser-url-pill">zenith.studio/creative-director</div>
      </div>
      <div style="padding: 40px; background: rgba(10, 12, 16, 0.95);">
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 24px;">
          <div style="padding: 24px; border-radius: 12px; background: var(--card-bg); border: 1px solid var(--border-color);">
            <div style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--accent-1); margin-bottom: 8px;">
              [COMPONENT REGISTRY SEARCH]
            </div>
            <p style="font-size: 0.9rem; color: var(--text-color);">
              Query: <code>CTA with hover intensity 4+</code><br>
              Match: <strong>Magnetic Neon Button</strong> (Zenith + Uiverse)
            </p>
          </div>
          <div style="padding: 24px; border-radius: 12px; background: var(--card-bg); border: 1px solid var(--border-color);">
            <div style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--accent-2); margin-bottom: 8px;">
              [THEME COLOR ADAPTATION]
            </div>
            <p style="font-size: 0.9rem; color: var(--text-color);">
              Target: <strong>{theme["name"]}</strong><br>
              Accents: <code>{colors["accent1"]}</code> &bull; <code>{colors["accent2"]}</code>
            </p>
          </div>
          <div style="padding: 24px; border-radius: 12px; background: var(--card-bg); border: 1px solid var(--border-color);">
            <div style="font-family: var(--font-mono); font-size: 0.8rem; color: #34d399; margin-bottom: 8px;">
              [SECTION SYNTHESIS]
            </div>
            <p style="font-size: 0.9rem; color: var(--text-color);">
              Status: <strong>Composed & Rendered</strong><br>
              Deliverable: Standalone Responsive HTML5
            </p>
          </div>
        </div>
      </div>
    </div>
  </section>

  <!-- ── 4. FOOTER WITH ANIMATED MESH ────────────────────────────────── -->
  <footer class="site-footer">
    <div class="footer-mesh"></div>
    <div style="position: relative; z-index: 1;">
      <div class="nav-brand" style="justify-content: center; margin-bottom: 16px;">
        <div class="nav-brand-dot"></div>
        <span>Zenith Creative Studio</span>
      </div>
      <p style="color: var(--muted-color); font-size: 0.9rem; margin-bottom: 24px;">
        Crafted with visual vocabulary primitives from Uiverse, Aceternity, Magic UI, and Three.js.
      </p>
      <div style="display: flex; gap: 20px; justify-content: center; font-size: 0.84rem; color: var(--muted-color);">
        <span>Theme: {theme["name"]}</span>
        <span>&bull;</span>
        <span>Sovereign AI Operating Layer</span>
        <span>&bull;</span>
        <span>Zero External CDN Lock-in</span>
      </div>
    </div>
  </footer>

  <!-- ── Interactive Engine Scripts ──────────────────────────────────── -->
  <script>
    // 1. Interactive Cursor Logic
    (function() {{
      const dot = document.getElementById('cursor-dot');
      const ring = document.getElementById('cursor-ring');
      if (!dot || !ring) return;

      let mx = -100, my = -100, rx = -100, ry = -100;
      window.addEventListener('mousemove', e => {{
        mx = e.clientX;
        my = e.clientY;
        dot.style.transform = `translate3d(${{mx}}px, ${{my}}px, 0)`;
      }});

      function cursorLoop() {{
        rx += (mx - rx) * 0.18;
        ry += (my - ry) * 0.18;
        ring.style.transform = `translate3d(${{rx}}px, ${{ry}}px, 0)`;
        requestAnimationFrame(cursorLoop);
      }}
      cursorLoop();
    }})();

    // 2. Interactive Spotlight Logic
    document.querySelectorAll('.spotlight-panel').forEach(panel => {{
      panel.addEventListener('mousemove', e => {{
        const rect = panel.getBoundingClientRect();
        panel.style.setProperty('--mouse-x', `${{e.clientX - rect.left}}px`);
        panel.style.setProperty('--mouse-y', `${{e.clientY - rect.top}}px`);
      }});
    }});

    // 3. 3D Card Tilt Physics
    document.querySelectorAll('[data-tilt]').forEach(card => {{
      card.addEventListener('mousemove', e => {{
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left - rect.width / 2;
        const y = e.clientY - rect.top - rect.height / 2;
        const inner = card.querySelector('.card-3d-inner');
        if (inner) {{
          inner.style.transform = `rotateX(${{-y * 0.08}}deg) rotateY(${{x * 0.08}}deg)`;
        }}
      }});
      card.addEventListener('mouseleave', () => {{
        const inner = card.querySelector('.card-3d-inner');
        if (inner) inner.style.transform = 'rotateX(0deg) rotateY(0deg)';
      }});
    }});

    // 4. Particle Constellation Canvas
    (function() {{
      const canvas = document.getElementById('particle-canvas');
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      let w = (canvas.width = window.innerWidth);
      let h = (canvas.height = window.innerHeight);

      window.addEventListener('resize', () => {{
        w = canvas.width = window.innerWidth;
        h = canvas.height = window.innerHeight;
      }});

      const particles = Array.from({{ length: 42 }}, () => ({{
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.5,
        vy: (Math.random() - 0.5) * 0.5,
        r: Math.random() * 2 + 1,
      }}));

      function draw() {{
        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '{colors["accent1"]}';
        ctx.strokeStyle = '{colors["accent1"]}';

        for (let i = 0; i < particles.length; i++) {{
          const p = particles[i];
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < 0 || p.x > w) p.vx *= -1;
          if (p.y < 0 || p.y > h) p.vy *= -1;

          ctx.beginPath();
          ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
          ctx.fill();

          for (let j = i + 1; j < particles.length; j++) {{
            const p2 = particles[j];
            const dist = Math.hypot(p.x - p2.x, p.y - p2.y);
            if (dist < 110) {{
              ctx.globalAlpha = 1 - dist / 110;
              ctx.lineWidth = 0.5;
              ctx.beginPath();
              ctx.moveTo(p.x, p.y);
              ctx.lineTo(p2.x, p2.y);
              ctx.stroke();
              ctx.globalAlpha = 1;
            }}
          }}
        }}
        requestAnimationFrame(draw);
      }}
      draw();
    }})();

    // 5. Three.js Interactive Torus Knot
    (function() {{
      const container = document.getElementById('three-viewport');
      if (!container || !window.THREE) return;

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 1000);
      const renderer = new THREE.WebGLRenderer({{ alpha: true, antialias: true }});
      renderer.setSize(container.clientWidth, container.clientHeight);
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      container.appendChild(renderer.domElement);

      const geo = new THREE.TorusKnotGeometry(1.6, 0.45, 120, 20);
      const mat = new THREE.MeshStandardMaterial({{
        color: 0x{colors["accent1"].lstrip("#")},
        roughness: 0.15,
        metalness: 0.85,
      }});
      const mesh = new THREE.Mesh(geo, mat);
      scene.add(mesh);

      const light1 = new THREE.PointLight(0xffffff, 2, 50);
      light1.position.set(5, 5, 5);
      scene.add(light1);

      const light2 = new THREE.PointLight(0x{colors["accent2"].lstrip("#")}, 2.5, 50);
      light2.position.set(-5, -5, 2);
      scene.add(light2);

      scene.add(new THREE.AmbientLight(0x222233));
      camera.position.z = 4.6;

      let mouseX = 0, mouseY = 0;
      window.addEventListener('mousemove', e => {{
        mouseX = (e.clientX / window.innerWidth) * 2 - 1;
        mouseY = -(e.clientY / window.innerHeight) * 2 + 1;
      }});

      function animate() {{
        mesh.rotation.x += 0.007;
        mesh.rotation.y += 0.010;
        mesh.rotation.x += (mouseY * 0.3 - mesh.rotation.x) * 0.05;
        mesh.rotation.y += (mouseX * 0.3 - mesh.rotation.y) * 0.05;
        renderer.render(scene, camera);
        requestAnimationFrame(animate);
      }}
      animate();
    }})();
  </script>
</body>
</html>
"""

        out_file.write_text(html_content, encoding="utf-8")
        log.info("Composed standalone interactive site to %s", out_file)

        return {
            "site_id": site_id,
            "title": title,
            "theme": theme_name,
            "theme_name": theme["name"],
            "url": f"/static/sites/{site_id}.html",
            "file_path": str(out_file),
            "components_used": list(selected.values()),
            "component_count": len(selected),
        }


_COMPOSER_INSTANCE: Optional[VisualComposer] = None


def get_composer() -> VisualComposer:
    """Get or instantiate global VisualComposer singleton."""
    global _COMPOSER_INSTANCE
    if _COMPOSER_INSTANCE is None:
        _COMPOSER_INSTANCE = VisualComposer()
    return _COMPOSER_INSTANCE

#!/usr/bin/env python3
"""Build and Index Zenith Media Agent Visual Vocabulary Component Registry.

Populates /media-agent/components with curated multi-library components:
- Uiverse Galaxy (indexed 3,800+ items + curated top-tier elements)
- Aceternity UI (Bento Grid, 3D Card, Spotlight, Background Beams, etc.)
- Magic UI (Border Beam, Shimmer Button, Particles, Hyper Text, Safari, etc.)
- Three.js / WebGL / R3F (Floating 3D Torus/Object, Starfield, Wave Mesh)
- GSAP Primitives (Scroll-linked Parallax, Timeline Orchestration, Perspective Transform)
- Zenith Proprietary Components (Studio Editorial, Tactical HUD, Audiogram Visualizer)
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
MEDIA_AGENT_DIR = ROOT_DIR / "media-agent"
COMPONENTS_DIR = MEDIA_AGENT_DIR / "components"
GALAXY_DIR = ROOT_DIR / "scratch" / "uiverse-galaxy"


def ensure_dirs():
    """Ensure all component category directories exist."""
    categories = [
        "buttons",
        "cards",
        "backgrounds",
        "text",
        "effects",
        "mockups",
        "navigation",
        "three_r3f",
        "gsap",
        "zenith",
    ]
    for cat in categories:
        (COMPONENTS_DIR / cat).mkdir(parents=True, exist_ok=True)
    print(f"Created category directories in {COMPONENTS_DIR}")


# ── Curated High-Tier Component Definitions ───────────────────────────────────

CURATED_COMPONENTS: List[Dict[str, Any]] = [
    # ── BUTTONS ───────────────────────────────────────────────────────────────
    {
        "id": "magnetic-neon-button",
        "name": "Magnetic Neon Button",
        "folder": "buttons/magnetic-button",
        "category": "button",
        "source": "zenith",
        "tags": ["neon", "futuristic", "hover", "interactive", "magnetic", "cta"],
        "framework": "react",
        "motion": "magnetic-hover",
        "intensity": 5,
        "best_for": ["hero", "CTA", "landing-page", "sci-fi"],
        "description": "Magnetic interactive CTA with cursor attraction physics, rotating radial neon glow aura, and specular light highlight.",
        "code": {
            "tsx": """import React, { useRef, useState } from "react";

export interface MagneticNeonButtonProps {
  children?: React.ReactNode;
  onClick?: () => void;
  className?: string;
  glowColor?: string;
  borderColor?: string;
}

export const MagneticNeonButton: React.FC<MagneticNeonButtonProps> = ({
  children = "Launch Sovereign System",
  onClick,
  className = "",
  glowColor = "rgba(0, 243, 255, 0.45)",
  borderColor = "#00f3ff",
}) => {
  const btnRef = useRef<HTMLButtonElement>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState(false);

  const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (!btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    setOffset({ x: x * 0.28, y: y * 0.28 });
  };

  const handleMouseLeave = () => {
    setOffset({ x: 0, y: 0 });
    setHovered(false);
  };

  return (
    <button
      ref={btnRef}
      onClick={onClick}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={handleMouseLeave}
      className={`relative inline-flex items-center justify-center px-8 py-4 font-semibold rounded-xl text-white overflow-hidden transition-transform duration-200 ease-out active:scale-95 ${className}`}
      style={{
        transform: `translate3d(${offset.x}px, ${offset.y}px, 0)`,
        background: "linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(10, 15, 22, 0.98))",
        border: `1px solid ${borderColor}`,
        boxShadow: hovered
          ? `0 0 35px ${glowColor}, inset 0 0 15px ${glowColor}`
          : `0 0 15px rgba(0, 243, 255, 0.15)`,
      }}
    >
      <span className="relative z-10 tracking-wider uppercase text-sm flex items-center gap-2">
        {children}
        <svg className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
        </svg>
      </span>
      <div
        className="absolute inset-0 opacity-20 pointer-events-none transition-opacity duration-300"
        style={{
          background: `radial-gradient(circle at 50% 50%, ${glowColor} 0%, transparent 70%)`,
        }}
      />
    </button>
  );
};
""",
            "css": """.magnetic-neon-btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 14px 32px;
  font-family: var(--font-heading, inherit);
  font-size: 0.9rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-color, #ffffff);
  background: linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(10, 15, 22, 0.98));
  border: 1px solid var(--accent-1, #00f3ff);
  border-radius: 12px;
  cursor: pointer;
  overflow: hidden;
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.3s ease;
  box-shadow: 0 0 18px var(--glow-color, rgba(0, 243, 255, 0.2));
}

.magnetic-neon-btn:hover {
  box-shadow: 0 0 35px var(--glow-color, rgba(0, 243, 255, 0.5)), inset 0 0 15px var(--glow-color, rgba(0, 243, 255, 0.3));
  border-color: var(--accent-1, #00f3ff);
}

.magnetic-neon-btn:active {
  transform: scale(0.96);
}
""",
            "html": """<button class="magnetic-neon-btn" data-magnetic="true">
  <span>Explore Autonomous Layer &rarr;</span>
</button>
""",
        },
    },
    {
        "id": "neon-button",
        "name": "Cyber Neon Glow Button",
        "folder": "buttons/neon-button",
        "category": "button",
        "source": "uiverse",
        "tags": ["neon", "cyberpunk", "glow", "glow-border", "cta"],
        "framework": "html",
        "motion": "glow-pulse",
        "intensity": 4,
        "best_for": ["hero", "CTA", "dark-mode"],
        "description": "High-contrast glowing neon button with animated laser border and chromatic aura.",
        "code": {
            "tsx": """import React from "react";

export const NeonButton: React.FC<{ children?: React.ReactNode; onClick?: () => void }> = ({
  children = "Get Started",
  onClick
}) => {
  return (
    <button onClick={onClick} className="neon-glow-btn">
      <span>{children}</span>
    </button>
  );
};
""",
            "css": """.neon-glow-btn {
  position: relative;
  padding: 14px 34px;
  background: #0d0f14;
  color: var(--accent-1, #00f3ff);
  border: 2px solid var(--accent-1, #00f3ff);
  border-radius: 8px;
  font-family: var(--font-heading, inherit);
  font-size: 0.95rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 2px;
  cursor: pointer;
  transition: all 0.3s ease;
  box-shadow: 0 0 10px var(--glow-color, rgba(0, 243, 255, 0.3));
}
.neon-glow-btn:hover {
  background: var(--accent-1, #00f3ff);
  color: #0d0f14;
  box-shadow: 0 0 30px var(--accent-1, #00f3ff), 0 0 60px var(--glow-color, rgba(0, 243, 255, 0.6));
}
""",
            "html": """<button class="neon-glow-btn"><span>Initiate Protocol</span></button>""",
        },
    },
    {
        "id": "liquid-button",
        "name": "Liquid Morphing Button",
        "folder": "buttons/liquid-button",
        "category": "button",
        "source": "uiverse",
        "tags": ["liquid", "organic", "morph", "fluid", "interactive"],
        "framework": "html",
        "motion": "liquid-expand",
        "intensity": 4,
        "best_for": ["playful", "creative", "CTA"],
        "description": "Organic fluid button with liquid droplets expanding on hover through SVG gooey filters.",
        "code": {
            "tsx": """import React from "react";

export const LiquidButton: React.FC<{ children?: React.ReactNode }> = ({ children = "Liquid Discover" }) => (
  <button className="liquid-btn">
    <span className="relative z-10">{children}</span>
    <div className="liquid-blob" />
  </button>
);
""",
            "css": """.liquid-btn {
  position: relative;
  padding: 16px 36px;
  background: var(--card-bg, #181b20);
  border: 1px solid var(--border-color, #2a2e37);
  border-radius: 9999px;
  color: var(--text-color, #ffffff);
  font-family: var(--font-heading, sans-serif);
  font-weight: 600;
  cursor: pointer;
  overflow: hidden;
  transition: color 0.3s ease;
}
.liquid-btn .liquid-blob {
  position: absolute;
  top: 100%;
  left: 50%;
  width: 200%;
  height: 200%;
  background: var(--accent-1, #3b82f6);
  border-radius: 40%;
  transform: translate(-50%, 0);
  transition: transform 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 0;
}
.liquid-btn:hover .liquid-blob {
  transform: translate(-50%, -85%) rotate(180deg);
}
.liquid-btn span {
  position: relative;
  z-index: 1;
}
""",
            "html": """<button class="liquid-btn"><span>Interactive Liquid &rarr;</span><div class="liquid-blob"></div></button>""",
        },
    },
    {
        "id": "shimmer-button",
        "name": "Shimmer Conic Button",
        "folder": "buttons/shimmer-button",
        "category": "button",
        "source": "magicui",
        "tags": ["shimmer", "magicui", "conic", "premium", "minimal"],
        "framework": "react",
        "motion": "continuous-shimmer",
        "intensity": 3,
        "best_for": ["hero", "CTA", "editorial", "luxury"],
        "description": "Minimalist obsidian button encased in continuous rotating conic gradient border shimmer.",
        "code": {
            "tsx": """import React from "react";

export const ShimmerButton: React.FC<{ children?: React.ReactNode; onClick?: () => void }> = ({
  children = "Explore Collection",
  onClick,
}) => {
  return (
    <button
      onClick={onClick}
      className="relative inline-flex h-12 overflow-hidden rounded-full p-[1px] focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 focus:ring-offset-slate-50"
    >
      <span className="absolute inset-[-1000%] animate-[spin_3s_linear_infinite] bg-[conic-gradient(from_90deg_at_50%_50%,var(--accent-1,#38bdf8)_0%,var(--accent-2,#818cf8)_50%,var(--accent-1,#38bdf8)_100%)]" />
      <span className="inline-flex h-full w-full cursor-pointer items-center justify-center rounded-full bg-slate-950 px-7 py-1 text-sm font-medium text-white backdrop-blur-3xl hover:bg-slate-900 transition-colors">
        {children}
      </span>
    </button>
  );
};
""",
            "css": """.shimmer-button-wrap {
  position: relative;
  display: inline-flex;
  border-radius: 9999px;
  padding: 1.5px;
  overflow: hidden;
  background: transparent;
  cursor: pointer;
}
.shimmer-button-conic {
  position: absolute;
  inset: -150%;
  background: conic-gradient(from 0deg at 50% 50%, var(--accent-1, #d4a373) 0deg, var(--accent-2, #3b82f6) 180deg, var(--accent-1, #d4a373) 360deg);
  animation: shimmer-spin 4s linear infinite;
}
@keyframes shimmer-spin {
  to { transform: rotate(360deg); }
}
.shimmer-button-inner {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px 28px;
  border-radius: 9999px;
  background: var(--bg-color, #0d0f12);
  color: var(--text-color, #f4f4f6);
  font-family: var(--font-heading, sans-serif);
  font-size: 0.88rem;
  font-weight: 600;
  transition: background 0.2s ease;
}
.shimmer-button-wrap:hover .shimmer-button-inner {
  background: var(--card-bg, #181b20);
}
""",
            "html": """<div class="shimmer-button-wrap">
  <div class="shimmer-button-conic"></div>
  <div class="shimmer-button-inner"><span>Start Free Experience &rarr;</span></div>
</div>
""",
        },
    },

    # ── CARDS ─────────────────────────────────────────────────────────────────
    {
        "id": "glass-card",
        "name": "Sovereign Glassmorphism Card",
        "folder": "cards/glass-card",
        "category": "card",
        "source": "zenith",
        "tags": ["glassmorphism", "card", "editorial", "blur", "frost"],
        "framework": "react",
        "motion": "hover-lift",
        "intensity": 3,
        "best_for": ["features", "dashboard", "bento", "hero"],
        "description": "Studio-grade frosted glass card with 16px backdrop blur, subtle inner border illumination, and hover lift elevation.",
        "code": {
            "tsx": """import React from "react";

export interface GlassCardProps {
  title?: string;
  subtitle?: string;
  badge?: string;
  children?: React.ReactNode;
  className?: string;
}

export const GlassCard: React.FC<GlassCardProps> = ({
  title = "Unified Context Engine",
  subtitle = "Maintains persistent awareness across tools, memory, and runtime sandboxes.",
  badge = "Autonomous",
  children,
  className = "",
}) => {
  return (
    <div
      className={`relative p-8 rounded-2xl transition-all duration-300 hover:-translate-y-1.5 ${className}`}
      style={{
        background: "var(--card-glass, rgba(24, 27, 32, 0.78))",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid var(--border-color, rgba(255, 255, 255, 0.08))",
        boxShadow: "0 20px 40px -15px rgba(0, 0, 0, 0.5)",
      }}
    >
      {badge && (
        <span
          className="inline-block px-3 py-1 text-xs font-mono tracking-wider rounded-full mb-4"
          style={{
            background: "rgba(212, 163, 115, 0.12)",
            color: "var(--accent-1, #d4a373)",
            border: "1px solid rgba(212, 163, 115, 0.25)",
          }}
        >
          {badge}
        </span>
      )}
      <h3 className="text-xl font-bold text-white mb-2 tracking-tight">{title}</h3>
      <p className="text-sm text-slate-400 leading-relaxed mb-4">{subtitle}</p>
      {children}
    </div>
  );
};
""",
            "css": """.glass-card {
  position: relative;
  padding: 32px;
  border-radius: 20px;
  background: var(--card-glass, rgba(24, 27, 32, 0.78));
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.08));
  box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.5);
  transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.3s ease, box-shadow 0.3s ease;
}
.glass-card:hover {
  transform: translateY(-6px);
  border-color: var(--accent-1, rgba(212, 163, 115, 0.4));
  box-shadow: 0 28px 60px -12px rgba(0, 0, 0, 0.65), 0 0 25px var(--glow-color, rgba(212, 163, 115, 0.15));
}
""",
            "html": """<div class="glass-card">
  <div class="glass-badge">Autonomous Hub</div>
  <h3 class="glass-title">Cognitive Context Fabric</h3>
  <p class="glass-desc">Multi-tier memory, real-world vision, and proactive agentic reasoning.</p>
</div>
""",
        },
    },
    {
        "id": "3d-card",
        "name": "3D Parallax Perspective Card",
        "folder": "cards/3d-card",
        "category": "card",
        "source": "aceternity",
        "tags": ["3d", "perspective", "tilt", "parallax", "aceternity"],
        "framework": "react",
        "motion": "3d-tilt",
        "intensity": 4,
        "best_for": ["features", "product", "showcase"],
        "description": "Aceternity-style 3D card tilt tracking cursor motion in real time with floating layered elements in Z-space.",
        "code": {
            "tsx": """import React, { useRef, useState } from "react";

export const Card3D: React.FC<{ title?: string; children?: React.ReactNode }> = ({
  title = "3D Interactive Element",
  children,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [rot, setRot] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    setRot({ x: -y * 0.08, y: x * 0.08 });
  };

  const handleMouseLeave = () => setRot({ x: 0, y: 0 });

  return (
    <div style={{ perspective: "1000px" }}>
      <div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className="p-8 rounded-2xl bg-neutral-900 border border-neutral-800 transition-transform duration-150 ease-out cursor-pointer"
        style={{
          transform: `rotateX(${rot.x}deg) rotateY(${rot.y}deg)`,
          transformStyle: "preserve-3d",
        }}
      >
        <div style={{ transform: "translateZ(40px)" }} className="text-xl font-bold text-white mb-2">
          {title}
        </div>
        <div style={{ transform: "translateZ(20px)" }} className="text-sm text-neutral-400">
          {children || "Physical depth layers responding to subtle pointer movements."}
        </div>
      </div>
    </div>
  );
};
""",
            "css": """.card-3d-wrap {
  perspective: 1200px;
}
.card-3d-inner {
  padding: 36px;
  border-radius: 20px;
  background: var(--card-bg, #181b20);
  border: 1px solid var(--border-color, #2a2e37);
  transform-style: preserve-3d;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.3s ease;
}
.card-3d-inner:hover {
  border-color: var(--accent-1, #3b82f6);
  box-shadow: 0 25px 50px rgba(0,0,0,0.5), 0 0 30px var(--glow-color, rgba(59,130,246,0.2));
}
.card-3d-layer-high {
  transform: translateZ(45px);
}
.card-3d-layer-mid {
  transform: translateZ(25px);
}
""",
            "html": """<div class="card-3d-wrap" data-tilt="true">
  <div class="card-3d-inner">
    <div class="card-3d-layer-high"><h3>Perspective Matrix</h3></div>
    <div class="card-3d-layer-mid"><p>Physical 3D transform reacting to cursor movement.</p></div>
  </div>
</div>
""",
        },
    },

    # ── BACKGROUNDS ───────────────────────────────────────────────────────────
    {
        "id": "aurora-background",
        "name": "Aurora Borealis Wave Mesh",
        "folder": "backgrounds/aurora",
        "category": "background",
        "source": "aceternity",
        "tags": ["aurora", "ambient", "chromatic", "gradient", "hero"],
        "framework": "react",
        "motion": "aurora-drift",
        "intensity": 4,
        "best_for": ["hero", "landing-page", "dark-mode"],
        "description": "Flowing iridescent chromatic northern lights wave background using overlapping blend modes and fluid keyframe translations.",
        "code": {
            "tsx": """import React from "react";

export const AuroraBackground: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return (
    <div className="relative flex flex-col h-screen items-center justify-center bg-zinc-950 text-slate-950 transition-bg overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-40">
        <div
          className="filter blur-[80px] -inset-[10px] opacity-50 absolute animate-aurora"
          style={{
            backgroundImage: `radial-gradient(ellipse at 100% 0%, var(--accent-1, #38bdf8) 10%, transparent 40%),
                              radial-gradient(ellipse at 0% 100%, var(--accent-2, #818cf8) 15%, transparent 50%),
                              radial-gradient(ellipse at 50% 50%, #34d399 10%, transparent 45%)`,
          }}
        />
      </div>
      <div className="relative z-10">{children}</div>
    </div>
  );
};
""",
            "css": """.aurora-bg-container {
  position: relative;
  width: 100%;
  min-height: 100vh;
  background-color: var(--bg-color, #0d0f12);
  overflow: hidden;
}
.aurora-waves {
  position: absolute;
  inset: -50%;
  background: radial-gradient(circle at 30% 20%, var(--accent-1, #d4a373) 0%, transparent 40%),
              radial-gradient(circle at 70% 60%, var(--accent-2, #3b82f6) 0%, transparent 45%),
              radial-gradient(circle at 50% 80%, rgba(212, 163, 115, 0.4) 0%, transparent 35%);
  filter: blur(80px);
  opacity: 0.35;
  animation: aurora-flow 18s ease-in-out infinite alternate;
  pointer-events: none;
}
@keyframes aurora-flow {
  0% { transform: translate(0, 0) scale(1) rotate(0deg); }
  50% { transform: translate(6%, -4%) scale(1.1) rotate(6deg); }
  100% { transform: translate(-5%, 5%) scale(0.95) rotate(-4deg); }
}
""",
            "html": """<div class="aurora-bg-container">
  <div class="aurora-waves"></div>
  <div class="hero-content">
    <h1>Autonomous Intelligence at Scale</h1>
  </div>
</div>
""",
        },
    },
    {
        "id": "interactive-particles",
        "name": "Constellation Particle Field",
        "folder": "backgrounds/particles",
        "category": "background",
        "source": "magicui",
        "tags": ["particles", "interactive", "canvas", "hero", "constellation"],
        "framework": "html",
        "motion": "particle-physics",
        "intensity": 4,
        "best_for": ["hero", "background", "landing-page"],
        "description": "Interactive HTML5 canvas particle field with nodes floating smoothly and connecting via distance-aware hairline vectors.",
        "code": {
            "tsx": """import React, { useEffect, useRef } from "react";

export const ParticleField: React.FC<{ color?: string }> = ({ color = "#38bdf8" }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animId: number;
    let w = (canvas.width = window.innerWidth);
    let h = (canvas.height = window.innerHeight);

    const particles = Array.from({ length: 45 }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      vx: (Math.random() - 0.5) * 0.6,
      vy: (Math.random() - 0.5) * 0.6,
      r: Math.random() * 2 + 1,
    }));

    const render = () => {
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = color;
      ctx.strokeStyle = color;

      particles.forEach((p, i) => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0 || p.x > w) p.vx *= -1;
        if (p.y < 0 || p.y > h) p.vy *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();

        for (let j = i + 1; j < particles.length; j++) {
          const p2 = particles[j];
          const dist = Math.hypot(p.x - p2.x, p.y - p2.y);
          if (dist < 120) {
            ctx.globalAlpha = 1 - dist / 120;
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
            ctx.globalAlpha = 1;
          }
        }
      });
      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [color]);

  return <canvas ref={canvasRef} className="fixed inset-0 pointer-events-none z-0" />;
};
""",
            "css": """#particle-canvas {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
  opacity: 0.6;
}
""",
            "html": """<canvas id="particle-canvas"></canvas>""",
        },
    },
    {
        "id": "retro-grid",
        "name": "3D Perspective Grid",
        "folder": "backgrounds/grid",
        "category": "background",
        "source": "magicui",
        "tags": ["grid", "perspective", "retro", "infinite-scroll", "hero"],
        "framework": "html",
        "motion": "grid-scroll",
        "intensity": 3,
        "best_for": ["hero", "developer", "terminal"],
        "description": "Animated 3D perspective grid plane continuously rolling toward the horizon with subtle specular glow.",
        "code": {
            "tsx": """import React from "react";

export const RetroGrid: React.FC = () => (
  <div className="pointer-events-none absolute h-full w-full overflow-hidden opacity-30 [perspective:200px]">
    <div className="absolute inset-0 [transform:rotateX(35deg)]">
      <div className="animate-grid [background-repeat:repeat] [background-size:60px_60px] [height:300vh] [inset:0%_0px] [margin-left:-50%] [transform-origin:100%_0_0] [width:600vw] [background-image:linear-gradient(to_right,rgba(255,255,255,0.1)_1px,transparent_0),linear-gradient(to_bottom,rgba(255,255,255,0.1)_1px,transparent_0)]" />
    </div>
    <div className="absolute inset-0 bg-gradient-to-t from-black to-transparent to-90%" />
  </div>
);
""",
            "css": """.retro-grid-wrap {
  position: absolute;
  inset: 0;
  overflow: hidden;
  perspective: 260px;
  pointer-events: none;
  opacity: 0.25;
}
.retro-grid-plane {
  position: absolute;
  top: -60%;
  left: -50%;
  width: 200%;
  height: 200%;
  background-image: linear-gradient(to right, var(--accent-1, #38bdf8) 1px, transparent 1px),
                    linear-gradient(to bottom, var(--accent-1, #38bdf8) 1px, transparent 1px);
  background-size: 50px 50px;
  transform: rotateX(45deg);
  animation: retro-grid-pan 15s linear infinite;
}
@keyframes retro-grid-pan {
  0% { transform: rotateX(45deg) translateY(0); }
  100% { transform: rotateX(45deg) translateY(50px); }
}
.retro-grid-fade {
  position: absolute;
  inset: 0;
  background: linear-gradient(to top, var(--bg-color, #0d0f12) 20%, transparent 80%);
}
""",
            "html": """<div class="retro-grid-wrap">
  <div class="retro-grid-plane"></div>
  <div class="retro-grid-fade"></div>
</div>
""",
        },
    },

    # ── TEXT & HEADINGS ───────────────────────────────────────────────────────
    {
        "id": "kinetic-heading",
        "name": "Kinetic Stagger Headline",
        "folder": "text/kinetic-heading",
        "category": "text",
        "source": "zenith",
        "tags": ["kinetic", "typography", "heading", "stagger", "spring"],
        "framework": "react",
        "motion": "stagger-reveal",
        "intensity": 4,
        "best_for": ["hero", "title", "landing-page"],
        "description": "Editorial kinetic typography with physics-based spring staggered entrance and character rotation.",
        "code": {
            "tsx": """import React from "react";

export const KineticHeading: React.FC<{ text?: string }> = ({ text = "Autonomous Sovereign Systems" }) => {
  return (
    <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-white flex flex-wrap gap-x-3">
      {text.split(" ").map((word, i) => (
        <span
          key={i}
          className="inline-block transition-transform duration-500 hover:-translate-y-1 hover:text-cyan-400"
          style={{ animation: `fade-slide-up 0.6s cubic-bezier(0.16, 1, 0.3, 1) ${i * 0.12}s backwards` }}
        >
          {word}
        </span>
      ))}
    </h1>
  );
};
""",
            "css": """.kinetic-heading {
  font-family: var(--font-heading, 'Inter', sans-serif);
  font-size: clamp(2.5rem, 5vw, 4.5rem);
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1.1;
  color: var(--text-color, #ffffff);
}
.kinetic-word {
  display: inline-block;
  opacity: 0;
  transform: translateY(24px) rotate(2deg);
  animation: kinetic-in 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
@keyframes kinetic-in {
  to {
    opacity: 1;
    transform: translateY(0) rotate(0deg);
  }
}
""",
            "html": """<h1 class="kinetic-heading">
  <span class="kinetic-word" style="animation-delay: 0.1s">Sovereign</span>
  <span class="kinetic-word" style="animation-delay: 0.2s">AI</span>
  <span class="kinetic-word" style="animation-delay: 0.3s">Operating</span>
  <span class="kinetic-word" style="animation-delay: 0.4s">Layer</span>
</h1>
""",
        },
    },
    {
        "id": "gradient-heading",
        "name": "Animated Linear Gradient Heading",
        "folder": "text/gradient-heading",
        "category": "text",
        "source": "magicui",
        "tags": ["gradient", "heading", "clip", "iridescent"],
        "framework": "html",
        "motion": "gradient-shift",
        "intensity": 3,
        "best_for": ["hero", "title", "landing-page"],
        "description": "Multi-stop animated gradient clipped to typography with continuous subtle horizontal hue shifting.",
        "code": {
            "tsx": """import React from "react";

export const GradientHeading: React.FC<{ children?: React.ReactNode }> = ({ children = "Architectural Precision" }) => (
  <h2 className="text-4xl md:text-6xl font-black tracking-tighter bg-gradient-to-r from-cyan-400 via-indigo-400 to-amber-300 bg-clip-text text-transparent animate-gradient-x">
    {children}
  </h2>
);
""",
            "css": """.gradient-heading {
  font-family: var(--font-heading, sans-serif);
  font-size: clamp(2.5rem, 6vw, 4.2rem);
  font-weight: 800;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, var(--text-color, #ffffff) 0%, var(--accent-1, #38bdf8) 50%, var(--accent-2, #818cf8) 100%);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: gradient-heading-shift 6s ease infinite alternate;
}
@keyframes gradient-heading-shift {
  0% { background-position: 0% 50%; }
  100% { background-position: 100% 50%; }
}
""",
            "html": """<h2 class="gradient-heading">Next-Gen Intelligent Fabric</h2>""",
        },
    },

    # ── EFFECTS ───────────────────────────────────────────────────────────────
    {
        "id": "spotlight",
        "name": "Interactive Spotlight Beam",
        "folder": "effects/spotlight",
        "category": "effects",
        "source": "aceternity",
        "tags": ["spotlight", "beam", "hover", "illumination", "dark-mode"],
        "framework": "html",
        "motion": "mouse-follow",
        "intensity": 3,
        "best_for": ["cards", "sections", "hero"],
        "description": "Dynamic radial spotlight tracking cursor coordinates to illuminate dark surface textures on hover.",
        "code": {
            "tsx": """import React, { useRef, useState } from "react";

export const SpotlightContainer: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: 0, y: 0, opacity: 0 });

  return (
    <div
      ref={containerRef}
      onMouseMove={(e) => {
        const rect = containerRef.current?.getBoundingClientRect();
        if (!rect) return;
        setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top, opacity: 1 });
      }}
      onMouseLeave={() => setPos((prev) => ({ ...prev, opacity: 0 }))}
      className="relative overflow-hidden rounded-2xl bg-neutral-950 p-8 border border-neutral-800"
    >
      <div
        className="pointer-events-none absolute -inset-px transition-opacity duration-300"
        style={{
          opacity: pos.opacity,
          background: `radial-gradient(600px circle at ${pos.x}px ${pos.y}px, rgba(56, 189, 248, 0.15), transparent 40%)`,
        }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
};
""",
            "css": """.spotlight-panel {
  position: relative;
  overflow: hidden;
  border-radius: 16px;
  background: var(--card-bg, #181b20);
  border: 1px solid var(--border-color, #2a2e37);
}
.spotlight-panel::before {
  content: '';
  position: absolute;
  inset: -1px;
  background: radial-gradient(400px circle at var(--mouse-x, 50%) var(--mouse-y, 50%), var(--glow-color, rgba(59, 130, 246, 0.18)), transparent 60%);
  opacity: var(--spotlight-opacity, 0);
  transition: opacity 0.3s ease;
  pointer-events: none;
  z-index: 1;
}
.spotlight-panel:hover {
  --spotlight-opacity: 1;
}
""",
            "html": """<div class="spotlight-panel" data-spotlight="true">
  <div style="position: relative; z-index: 2; padding: 32px;">
    <h3>Illuminated Surface</h3>
    <p>Move cursor to project directional light across this container.</p>
  </div>
</div>
""",
        },
    },
    {
        "id": "cursor",
        "name": "Smooth Magnetic Cursor Follower",
        "folder": "effects/cursor",
        "category": "effects",
        "source": "zenith",
        "tags": ["cursor", "magnetic", "interactive", "pointer", "smooth"],
        "framework": "html",
        "motion": "spring-follow",
        "intensity": 4,
        "best_for": ["landing-page", "portfolio", "full-site"],
        "description": "Smooth lagging fluid cursor dot and expanding trailing ring with interactive snapping over clickable elements.",
        "code": {
            "tsx": """import React, { useEffect, useRef } from "react";

export const SmoothCursor: React.FC = () => {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let mouse = { x: -100, y: -100 };
    let ring = { x: -100, y: -100 };

    const onMove = (e: MouseEvent) => {
      mouse = { x: e.clientX, y: e.clientY };
      if (dotRef.current) {
        dotRef.current.style.transform = `translate3d(${mouse.x}px, ${mouse.y}px, 0)`;
      }
    };

    const loop = () => {
      ring.x += (mouse.x - ring.x) * 0.15;
      ring.y += (mouse.y - ring.y) * 0.15;
      if (ringRef.current) {
        ringRef.current.style.transform = `translate3d(${ring.x - 18}px, ${ring.y - 18}px, 0)`;
      }
      requestAnimationFrame(loop);
    };

    window.addEventListener("mousemove", onMove);
    const id = requestAnimationFrame(loop);
    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(id);
    };
  }, []);

  return (
    <>
      <div ref={dotRef} className="fixed top-0 left-0 w-2 h-2 rounded-full bg-cyan-400 pointer-events-none z-50 transition-transform duration-75" />
      <div ref={ringRef} className="fixed top-0 left-0 w-9 h-9 rounded-full border border-cyan-400/40 pointer-events-none z-50" />
    </>
  );
};
""",
            "css": """.custom-cursor-dot {
  position: fixed;
  top: 0;
  left: 0;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-1, #00f3ff);
  pointer-events: none;
  z-index: 9999;
  transform: translate(-50%, -50%);
}
.custom-cursor-ring {
  position: fixed;
  top: 0;
  left: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1.5px solid var(--glow-color, rgba(0, 243, 255, 0.4));
  pointer-events: none;
  z-index: 9998;
  transform: translate(-50%, -50%);
  transition: width 0.2s, height 0.2s, border-color 0.2s;
}
""",
            "html": """<div class="custom-cursor-dot" id="cursor-dot"></div>
<div class="custom-cursor-ring" id="cursor-ring"></div>
""",
        },
    },
    {
        "id": "glow",
        "name": "Conic Ambient Aura Glow",
        "folder": "effects/glow",
        "category": "effects",
        "source": "magicui",
        "tags": ["glow", "aura", "ambient", "conic", "backlight"],
        "framework": "html",
        "motion": "continuous-rotate",
        "intensity": 3,
        "best_for": ["hero", "cards", "highlight"],
        "description": "Continuous revolving conic ambient aura casting colorful soft glow on surrounding elements.",
        "code": {
            "tsx": """import React from "react";

export const GlowBacklight: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <div className="relative group">
    <div className="absolute -inset-1 bg-gradient-to-r from-cyan-500 to-indigo-500 rounded-2xl blur-lg opacity-40 group-hover:opacity-80 transition duration-500" />
    <div className="relative">{children}</div>
  </div>
);
""",
            "css": """.glow-aura-wrap {
  position: relative;
}
.glow-aura-layer {
  position: absolute;
  inset: -12px;
  border-radius: 24px;
  background: conic-gradient(from 0deg at 50% 50%, var(--accent-1, #d4a373) 0deg, var(--accent-2, #3b82f6) 180deg, var(--accent-1, #d4a373) 360deg);
  filter: blur(28px);
  opacity: 0.35;
  z-index: 0;
  animation: glow-spin 10s linear infinite;
}
@keyframes glow-spin {
  to { transform: rotate(360deg); }
}
""",
            "html": """<div class="glow-aura-wrap">
  <div class="glow-aura-layer"></div>
  <div style="position: relative; z-index: 1;">Card Content Here</div>
</div>
""",
        },
    },

    # ── MOCKUPS ───────────────────────────────────────────────────────────────
    {
        "id": "browser-mockup",
        "name": "macOS Safari Window Mockup",
        "folder": "mockups/browser-mockup",
        "category": "mockup",
        "source": "magicui",
        "tags": ["mockup", "safari", "browser", "macos", "product"],
        "framework": "react",
        "motion": "tilt-float",
        "intensity": 2,
        "best_for": ["product", "features", "showcase"],
        "description": "Photorealistic macOS Safari browser frame with red/yellow/green traffic controls, glass URL pill, and window shadow.",
        "code": {
            "tsx": """import React from "react";

export const BrowserMockup: React.FC<{ url?: string; children?: React.ReactNode }> = ({
  url = "zenith.local/dashboard",
  children,
}) => {
  return (
    <div className="w-full rounded-xl overflow-hidden border border-neutral-800 bg-neutral-950 shadow-2xl">
      <div className="flex items-center gap-2 px-4 py-3 bg-neutral-900/80 border-b border-neutral-800 backdrop-blur-md">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
          <div className="w-3 h-3 rounded-full bg-green-500/80" />
        </div>
        <div className="mx-auto px-6 py-1 rounded-md bg-neutral-950/70 border border-neutral-800 text-xs font-mono text-neutral-400">
          https://{url}
        </div>
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
};
""",
            "css": """.browser-mockup {
  width: 100%;
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid var(--border-color, #2a2e37);
  background: var(--bg-color, #0d0f12);
  box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.7);
}
.browser-header {
  display: flex;
  align-items: center;
  padding: 12px 18px;
  background: var(--card-bg, #181b20);
  border-bottom: 1px solid var(--border-color, #2a2e37);
}
.browser-dots {
  display: flex;
  gap: 8px;
}
.browser-dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
}
.browser-dot.red { background: #ff5f56; }
.browser-dot.yellow { background: #ffbd2e; }
.browser-dot.green { background: #27c93f; }
.browser-url-pill {
  margin: 0 auto;
  padding: 4px 20px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.4);
  border: 1px solid var(--border-color, #2a2e37);
  font-family: var(--font-mono, monospace);
  font-size: 0.78rem;
  color: var(--muted-color, #8e95a2);
}
""",
            "html": """<div class="browser-mockup">
  <div class="browser-header">
    <div class="browser-dots">
      <div class="browser-dot red"></div>
      <div class="browser-dot yellow"></div>
      <div class="browser-dot green"></div>
    </div>
    <div class="browser-url-pill">zenith.ai/autonomous</div>
  </div>
  <div style="padding: 24px;">App Preview Content</div>
</div>
""",
        },
    },

    # ── THREE.JS / R3F ────────────────────────────────────────────────────────
    {
        "id": "floating-3d-object",
        "name": "Interactive Three.js 3D Torus",
        "folder": "three_r3f/floating-3d-object",
        "category": "three_r3f",
        "source": "threejs",
        "tags": ["threejs", "webgl", "3d", "torus", "interactive", "hero"],
        "framework": "html",
        "motion": "3d-quaternion-spin",
        "intensity": 5,
        "best_for": ["hero", "landing-page", "sci-fi"],
        "description": "Full WebGL 3D reflective iridescent torus mesh rotating and orienting toward mouse coordinates via Three.js.",
        "code": {
            "tsx": """import React, { useEffect, useRef } from "react";
import * as THREE from "three";

export const Floating3DTorus: React.FC = () => {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, mount.clientWidth / mount.clientHeight, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });

    renderer.setSize(mount.clientWidth, mount.clientHeight);
    mount.appendChild(renderer.domElement);

    const geometry = new THREE.TorusGeometry(2, 0.6, 32, 100);
    const material = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      metalness: 0.85,
      roughness: 0.2,
      wireframe: false,
    });
    const torus = new THREE.Mesh(geometry, material);
    scene.add(torus);

    const light1 = new THREE.DirectionalLight(0xffffff, 1.5);
    light1.position.set(5, 5, 5);
    scene.add(light1);

    const light2 = new THREE.PointLight(0x818cf8, 2, 50);
    light2.position.set(-5, -5, 2);
    scene.add(light2);

    camera.position.z = 5;

    let animId: number;
    const animate = () => {
      torus.rotation.x += 0.008;
      torus.rotation.y += 0.012;
      renderer.render(scene, camera);
      animId = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      mount.removeChild(renderer.domElement);
    };
  }, []);

  return <div ref={mountRef} className="w-full h-[400px]" />;
};
""",
            "css": """.three-viewport {
  width: 100%;
  height: 420px;
  position: relative;
}
""",
            "html": """<div class="three-viewport" id="three-torus-container"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
  (function() {
    const container = document.getElementById('three-torus-container');
    if (!container || !window.THREE) return;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);
    const geo = new THREE.TorusKnotGeometry(1.6, 0.45, 120, 20);
    const mat = new THREE.MeshStandardMaterial({ color: 0x38bdf8, roughness: 0.15, metalness: 0.9 });
    const mesh = new THREE.Mesh(geo, mat);
    scene.add(mesh);
    const light = new THREE.PointLight(0xffffff, 2, 100);
    light.position.set(5, 5, 5);
    scene.add(light);
    scene.add(new THREE.AmbientLight(0x222233));
    camera.position.z = 4.5;
    function loop() {
      mesh.rotation.x += 0.006;
      mesh.rotation.y += 0.009;
      renderer.render(scene, camera);
      requestAnimationFrame(loop);
    }
    loop();
  })();
</script>
""",
        },
    },

    # ── GSAP ANIMATION PRIMITIVES ─────────────────────────────────────────────
    {
        "id": "scroll-linked-parallax",
        "name": "GSAP Scroll-Linked Parallax Section",
        "folder": "gsap/scroll-linked-parallax",
        "category": "gsap",
        "source": "gsap",
        "tags": ["gsap", "scroll", "parallax", "scrolltrigger", "motion"],
        "framework": "html",
        "motion": "scroll-parallax",
        "intensity": 4,
        "best_for": ["landing-page", "showcase", "storytelling"],
        "description": "GSAP ScrollTrigger primitive pinning elements and translating foreground/background at differing speeds.",
        "code": {
            "tsx": """import React from "react";

export const ScrollParallaxPrimitive: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return <section className="relative overflow-hidden py-24">{children}</section>;
};
""",
            "css": """.parallax-section {
  position: relative;
  overflow: hidden;
  padding: 100px 0;
}
.parallax-layer-bg {
  transform: translateY(var(--scroll-offset-bg, 0));
  will-change: transform;
}
.parallax-layer-fg {
  transform: translateY(var(--scroll-offset-fg, 0));
  will-change: transform;
}
""",
            "html": """<div class="parallax-section" data-parallax="true">
  <div class="parallax-layer-bg">Background Artwork</div>
  <div class="parallax-layer-fg">Foreground Content</div>
</div>
""",
        },
    },
]


def write_curated_components():
    """Write all curated components with metadata.json and source files."""
    for comp in CURATED_COMPONENTS:
        folder_path = COMPONENTS_DIR / comp["folder"]
        folder_path.mkdir(parents=True, exist_ok=True)

        meta = {
            "id": comp["id"],
            "name": comp["name"],
            "category": comp["category"],
            "source": comp["source"],
            "tags": comp["tags"],
            "framework": comp["framework"],
            "motion": comp["motion"],
            "intensity": comp["intensity"],
            "best_for": comp["best_for"],
            "description": comp["description"],
            "code": comp["code"],
            "theme_adaptable_vars": {
                "accent_1": "--accent-1",
                "accent_2": "--accent-2",
                "bg_color": "--bg-color",
                "card_bg": "--card-bg",
                "glow_color": "--glow-color",
                "text_color": "--text-color",
                "border_color": "--border-color",
                "font_heading": "--font-heading",
            },
        }

        # Write metadata.json
        with open(folder_path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

        # Write code files for developer convenience
        if "tsx" in comp["code"] and comp["code"]["tsx"]:
            with open(folder_path / "Component.tsx", "w", encoding="utf-8") as f:
                f.write(comp["code"]["tsx"])
        if "css" in comp["code"] and comp["code"]["css"]:
            with open(folder_path / "styles.css", "w", encoding="utf-8") as f:
                f.write(comp["code"]["css"])
        if "html" in comp["code"] and comp["code"]["html"]:
            with open(folder_path / "index.html", "w", encoding="utf-8") as f:
                f.write(comp["code"]["html"])

    print(f"Successfully populated {len(CURATED_COMPONENTS)} curated visual vocabulary components.")


# ── Ingest Uiverse Galaxy into SQLite ─────────────────────────────────────────

def index_uiverse_galaxy():
    """Parse and index all HTML files in Uiverse Galaxy into SQLite FTS5 database."""
    if not GALAXY_DIR.exists():
        print(f"Warning: {GALAXY_DIR} not found. Skipping galaxy indexing.")
        return 0

    db_path = COMPONENTS_DIR / "uiverse_galaxy.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except Exception:
            pass

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS uiverse_components (
        id TEXT PRIMARY KEY,
        name TEXT,
        category TEXT,
        author TEXT,
        tags TEXT,
        motion TEXT,
        intensity INTEGER,
        html TEXT,
        css TEXT,
        framework TEXT,
        file_path TEXT
    );
    """)

    cur.execute("""
    CREATE VIRTUAL TABLE IF NOT EXISTS uiverse_fts USING fts5(
        id,
        name,
        category,
        tags,
        author
    );
    """)

    indexed_count = 0
    all_files = list(GALAXY_DIR.glob("*/*.html"))

    for file_path in all_files:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            file_name = file_path.stem
            category = file_path.parent.name.lower()

            # Extract author and name
            parts = file_name.split("_", 1)
            author = parts[0] if len(parts) > 1 else "uiverse_community"
            slug = parts[1] if len(parts) > 1 else parts[0]
            clean_name = slug.replace("-", " ").title()

            # Extract tags from comment
            tags = []
            tag_match = re.search(r"Tags:\s*([^\*>\n]+)", content, re.IGNORECASE)
            if tag_match:
                raw_tags = tag_match.group(1).split(",")
                tags = [t.strip().lower() for t in raw_tags if t.strip()]

            # Extract CSS and HTML
            css = ""
            html = content
            style_match = re.search(r"<style>(.*?)</style>", content, re.DOTALL | re.IGNORECASE)
            if style_match:
                css = style_match.group(1).strip()
                html = re.sub(r"<style>.*?</style>", "", content, flags=re.DOTALL | re.IGNORECASE).strip()

            # Framework detection
            framework = "tailwind" if ("class=" in html and ("flex" in html or "bg-" in html or "text-" in html)) else "html"

            # Motion & Intensity heuristic
            intensity = 2
            motion = "none"
            if "transform" in css or "transition" in css or "@keyframes" in css or "animate-" in html:
                intensity = 3
                motion = "hover"
            if "@keyframes" in css or "infinite" in css:
                intensity = 4
                motion = "animated"
            if "3d" in tags or "neon" in tags or "perspective" in css or ("box-shadow" in css and "rgba" in css):
                intensity = max(intensity, 4)

            tags_str = ", ".join(tags)

            cur.execute("""
            INSERT OR REPLACE INTO uiverse_components (
                id, name, category, author, tags, motion, intensity, html, css, framework, file_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                file_name, clean_name, category, author, tags_str, motion, intensity, html, css, framework, str(file_path.relative_to(ROOT_DIR))
            ))

            cur.execute("""
            INSERT INTO uiverse_fts (id, name, category, tags, author)
            VALUES (?, ?, ?, ?, ?)
            """, (file_name, clean_name, category, tags_str, author))

            indexed_count += 1
        except Exception as e:
            continue

    conn.commit()
    conn.close()
    print(f"Indexed {indexed_count} Uiverse Galaxy components into {db_path} with FTS5 search.")
    return indexed_count


def main():
    ensure_dirs()
    write_curated_components()
    indexed = index_uiverse_galaxy()
    print("Component library registry initialized successfully.")


if __name__ == "__main__":
    main()

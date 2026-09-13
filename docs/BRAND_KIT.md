# Zenith Brand Kit & Design System Specification

> **Version:** 2.0.0  
> **Codename:** *Cosmic Apex & Ethereal Glass*  
> **Product:** Zenith — Autonomous AI Companion & Homelab OS  

---

## 1. Brand Identity & Philosophy

### 1.1 The Meaning of "Zenith"
The **zenith** is the highest celestial point in the sky directly above the observer — the vertical apex, peak elevation, and pinnacle of alignment. 

Zenith is not a utilitarian server console or an uninspired chatbot:
- **Celestial Precision:** Crisp, high-contrast, frictionless intelligence.
- **Cosmic Void & Ethereal Cryo-Glass:** Deep space obsidian depth contrasted with luminous electric iris (`#818cf8`) and quantum cyan (`#22d3ee`) accents.
- **Autonomous Sovereignty:** A capable command plane that manages homelabs, executes multi-step coding briefs, and interfaces with your world without friction.

### 1.2 Personality & Tone
- **Poised & Articulate:** Converses with natural elegance, depth, and concise clarity.
- **Autonomous & Proactive:** Anticipates system needs, inspects context, and takes ownership of tasks.
- **Reassuring & Transparent:** Explains actions plainly, summarizes tool execution skimmably, and gates mutating ops behind checkpoints.

---

## 2. Logo & Brand Mark: The Zenith Apex

The **Zenith Apex Mark** is a faceted celestial diamond rotating at 45 degrees, centered within an ethereal radiant halo.

```
          ✦  ZENITH APEX
         / \
        /   \      Luminous core (#ffffff)
       <  ✦  >     Electric Iris to Quantum Cyan gradient
        \   /      Orbital aurora glow ring
         \ /
```

### SVG Geometry
```xml
<svg width="32" height="32" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="zenithGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#22d3ee" />
      <stop offset="50%" stop-color="#818cf8" />
      <stop offset="100%" stop-color="#c084fc" />
    </linearGradient>
    <filter id="zenithGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="3" result="blur" />
      <feComposite in="SourceGraphic" in2="blur" operator="over" />
    </filter>
  </defs>
  <!-- Background Glass Badge -->
  <rect x="2" y="2" width="28" height="28" rx="9" fill="url(#zenithGrad)" opacity="0.15" stroke="url(#zenithGrad)" stroke-width="1" />
  <!-- Apex Diamond Mark -->
  <rect x="16" y="8" width="11.31" height="11.31" rx="2" transform="rotate(45 16 8)" fill="url(#zenithGrad)" filter="url(#zenithGlow)" />
  <rect x="16" y="11" width="7" height="7" rx="1.5" transform="rotate(45 16 11)" fill="#ffffff" />
</svg>
```

---

## 3. Color Palette & Token System

Zenith employs two dynamic modes:
1. **Cosmic Deep Space Void (Dark — Flagship & Primary Experience)**
2. **Solar Quartz / Cryo-Ceramic (Light — Crisp & Architectural)**

### 3.1 Cosmic Void Palette (Dark Mode)

| Token Name | Value | Role | Contrast / Usage |
|---|---|---|---|
| `--bg` | `#07090e` | Canvas Void | Deep space foundation |
| `--bg-deep` | `#040508` | Underlay Depth | Recessed base layer |
| `--panel` | `rgba(15, 20, 32, 0.78)` | Cryo-Glass Surface | Glass cards, modals, sidebars |
| `--panel-2` | `rgba(21, 28, 46, 0.72)` | Elevated Glass | Secondary floating cards |
| `--inset` | `rgba(10, 14, 24, 0.88)` | Code & Terminal Wells | Syntax blocks, terminal body |
| `--input` | `rgba(17, 24, 39, 0.82)` | Input Glass | Textareas, form fields |
| `--line` | `rgba(255, 255, 255, 0.08)` | Hairline Border | Primary glass perimeter |
| `--line-2` | `rgba(99, 102, 241, 0.24)` | Active Border | Hover/accent boundaries |
| `--line-strong`| `rgba(129, 140, 248, 0.42)`| Focus Halo | Focus rings, active cards |
| `--ink` | `#f8fafc` | Starlight Text | Primary headlines & body |
| `--ink-dim` | `#94a3b8` | Cool Slate | Secondary descriptions & meta |
| `--ink-faint`| `#64748b` | Nebula Gray | Placeholders, timestamps, borders |
| `--accent` | `#818cf8` | Electric Iris | Primary brand accent & focus |
| `--accent-2` | `#22d3ee` | Quantum Cyan | Radiance, sparkles, system cues |
| `--accent-violet`| `#a78bfa`| Cosmic Violet | Secondary gradient anchor |
| `--accent-gradient`| `linear-gradient(135deg, #22d3ee 0%, #818cf8 50%, #c084fc 100%)` | Brand Signature |
| `--ok` / `--green` | `#34d399` | Emerald Beacon | Success, active services, online |
| `--warn` | `#fbbf24` | Stellar Gold | In-progress, warnings, checks |
| `--fail` / `--red` | `#f87171` | Supernova Rose | Critical alerts, errors, cancel |

### 3.2 Solar Quartz Palette (Light Mode)

| Token Name | Value | Role | Contrast / Usage |
|---|---|---|---|
| `--bg` | `#f8fafc` | Quartz Base | Crisp, bright daylight surface |
| `--bg-deep` | `#f1f5f9` | Crystal Slate | Secondary backdrop |
| `--panel` | `rgba(255, 255, 255, 0.82)` | Porcelain Glass | High-translucency cards |
| `--panel-2` | `rgba(248, 250, 252, 0.90)` | Elevated Card | Floating tooltips & dropdowns |
| `--inset` | `#eef2f7` | Inset Well | Code containers, tables |
| `--line` | `rgba(148, 163, 184, 0.22)` | Crisp Edge | Subtle perimeter definition |
| `--line-2` | `rgba(99, 102, 241, 0.25)` | Accent Edge | Interactive borders |
| `--ink` | `#0f172a` | Deep Slate | Maximum readability text |
| `--ink-dim` | `#475569` | Mid Slate | Secondary labels |
| `--accent` | `#6366f1` | Vibrant Indigo | Primary focus & buttons |
| `--accent-2` | `#06b6d4` | Cyan Accent | Sub-highlights |
| `--accent-gradient`| `linear-gradient(135deg, #06b6d4 0%, #6366f1 52%, #8b5cf6 100%)` |

---

## 4. Typography System

Zenith pairs geometric, modern sans-serif typography with high-precision monospace for code and metrics.

### 4.1 Font Families
- **Primary Interface Font:** `Plus Jakarta Sans`, `Inter`, `-apple-system`, `BlinkMacSystemFont`, `sans-serif`
- **Monospace & Code Font:** `JetBrains Mono`, `ui-monospace`, `SF Mono`, `Menlo`, `monospace`

### 4.2 Type Hierarchy
| Level | Font Size | Weight | Tracking | Purpose |
|---|---|---|---|---|
| **Display Hero** | `2.6rem` (42px) | 700 (Bold) | `-0.03em` | Welcome greeting, hero headers |
| **Modal Title** | `1.5rem` (24px) | 700 (Bold) | `-0.02em` | Setup studio, starter screen |
| **Section Head** | `1.15rem` (18px) | 700 (Bold) | `-0.015em`| Category header, drawer title |
| **Body Large** | `0.98rem` (16px) | 400–500 | `normal` | Assistant & user chat messages |
| **Body Standard**| `0.88rem` (14px) | 500–600 | `normal` | Tool chips, form inputs, buttons |
| **Meta / Tag** | `0.74rem` (12px) | 600–700 | `0.04em` | Status badges, timestamps, tags |
| **Micro Tracked**| `0.68rem` (11px) | 700 (Bold) | `0.08em` | `ZENITH // APEX ENGINE`, uppercase pill |

---

## 5. Component Blueprints

### 5.1 Cryo-Glass Panels & Cards
All surfaces utilize multi-layer blur and sub-pixel perimeter lighting:
```css
background: var(--panel);
backdrop-filter: blur(20px) saturate(180%);
-webkit-backdrop-filter: blur(20px) saturate(180%);
border: 1px solid var(--line);
border-radius: var(--radius);
box-shadow: var(--shadow-1), 0 0 0 1px rgba(255, 255, 255, 0.03);
```

### 5.2 Floating Composer Capsule
The command input is a floating frosted capsule anchored above the viewport bottom with focus illumination:
```css
.composer-row {
  background: var(--input);
  backdrop-filter: blur(16px);
  border: 1px solid var(--line-2);
  border-radius: 20px;
  padding: 6px 8px;
  box-shadow: var(--shadow-1);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.composer-row:focus-within {
  border-color: var(--line-strong);
  box-shadow: 0 0 0 3px var(--accent-soft), 0 0 25px var(--accent-dim), var(--shadow-2);
}
```

### 5.3 Quick-Action Prompt Chips
Interactive capability chips on the welcome canvas:
```css
.wlcm-chip {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 12px 14px;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.wlcm-chip:hover {
  background: var(--panel-2);
  border-color: var(--line-strong);
  transform: translateY(-2px);
  box-shadow: var(--shadow-2), 0 0 20px var(--accent-dim);
}
```

### 5.4 Message Bubbles
- **User Message:** Luminous celestial indigo gradient (`linear-gradient(135deg, rgba(99, 102, 241, 0.22), rgba(139, 92, 246, 0.16))`), rounded corners (`18px 18px 4px 18px`), right-aligned.
- **Assistant Message:** Borderless, clean typography, flanked by the gradient `Z` avatar (`var(--accent-gradient)` with 8px radius).

### 5.5 Operating Mode Indicators
- **🌱 Setup Mode:** Green beacon (`#10b981`), guided onboarding companion.
- **⚡ Sovereign Mode:** Violet beacon (`#a78bfa`), autonomous orchestration & coding agent.

---

## 6. Motion & Animation Principles

- **Easing:** All UI transitions use the refined cubic bezier curve: `cubic-bezier(0.16, 1, 0.3, 1)`.
- **Durations:**
  - Micro-interactions (hover, focus): `150ms`.
  - Drawer and modal reveals: `250ms–350ms`.
  - Pulsing status dots & orbital rings: `2000ms–3000ms` infinite ease-in-out.

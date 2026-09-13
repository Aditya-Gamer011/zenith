/**
 * ZENITH · Liquid Glass & Chrome Fluid WebGL Shader Background
 *
 * Real-time GPU-accelerated fluid fragment shader creating luminous flowing
 * ribbons of liquid glass, polished chrome, and iridescent fluid on an obsidian canvas.
 *
 * Designed for the setup experience ("What should I call you", API key, etc.).
 * Fully responsive across desktop, tablet, and mobile with adaptive aspect framing.
 * High-performance 60 FPS rendering with blue-noise dithering and prefers-reduced-motion support.
 */

(function () {
  "use strict";

  // ══════════════════════════════════════════════════════════════════════════════
  // MODULAR TUNING PARAMETERS
  // ══════════════════════════════════════════════════════════════════════════════
  const LIQUID_CONFIG = {
    // Flow & Animation Speed
    speed: 0.12,                  // Fluid flow speed
    reducedMotionSpeed: 0.015,    // Substantially slowed speed for prefers-reduced-motion
    timeStartOffset: 8.0,         // Initial phase offset so ribbons look beautiful immediately

    // Spatial Framing & Streamline Geometry
    angleDeg: -32.0,              // Diagonal slant angle (degrees) across widescreen
    target1: 0.31,                // Primary ribbon streamline position (clears AI orb & deck)
    target2: 0.61,                // Secondary ribbon streamline position (upper echoing fold)

    // Lighting & Specular Chrome
    highlightIntensity: 1.0,      // Master highlight multiplier
    chromeSharpness: 18000.0,     // Razor-sharpness of polished chrome reflection line
    specularIntensity: 1.0,       // Studio key/rim specular multiplier

    // Color Palette (RGB Normalized 0.0 - 1.0)
    colors: {
      bgDeep:         [0.012, 0.020, 0.032], // #030508 Nearly black deep obsidian canvas
      bgMid:          [0.026, 0.036, 0.058], // #070B14 Obsidian gradient tint
      deepNavy:       [0.006, 0.022, 0.095], // Deep indigo body volume
      royalBlue:      [0.015, 0.090, 0.320], // Mid-body translucent fluid
      electricBlue:   [0.035, 0.300, 0.860], // Electric blue edge & fill light
      cyanGlow:       [0.090, 0.680, 0.950], // Luminous cyan fluid illumination
      whiteBlue:      [0.900, 0.955, 1.000], // Dominant white-blue core ribbon
      pureWhite:      [1.000, 1.000, 1.000], // Chrome specular crests & glints

      // Iridescent Refractive Edge Accents
      lavender:       [0.840, 0.780, 0.980], // Pale lavender
      violet:         [0.550, 0.280, 0.920], // Violet
      warmAmber:      [0.980, 0.650, 0.240], // Warm golden amber refraction
    }
  };

  const VS_SOURCE = `
    attribute vec2 a_pos;
    void main() {
      gl_Position = vec4(a_pos, 0.0, 1.0);
    }
  `;

  const FS_SOURCE = `
    precision highp float;
    uniform vec2 u_resolution;
    uniform float u_time;
    uniform vec2 u_mouse;
    uniform float u_reduced_motion;
    uniform float u_speed;
    uniform float u_angle;
    uniform float u_target1;
    uniform float u_target2;
    uniform float u_highlight;

    // Palette Uniforms
    uniform vec3 u_col_bg_deep;
    uniform vec3 u_col_bg_mid;
    uniform vec3 u_col_deep_navy;
    uniform vec3 u_col_royal_blue;
    uniform vec3 u_col_electric_blue;
    uniform vec3 u_col_cyan_glow;
    uniform vec3 u_col_white_blue;
    uniform vec3 u_col_pure_white;
    uniform vec3 u_col_lavender;
    uniform vec3 u_col_violet;
    uniform vec3 u_col_warm_amber;

    // 2D Rotation
    mat2 rot(float a) {
      float s = sin(a), c = cos(a);
      return mat2(c, -s, s, c);
    }

    // High-frequency blue noise hash for dithering
    float hash(vec2 p) {
      return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
    }

    // Smooth potential flow stream function with harmonic breathing
    float evaluateStream(vec2 p, float t, out float chi) {
      mat2 R = rot(u_angle);
      vec2 dp = R * p;
      chi = dp.x;

      // Harmonic slow-breathing clocks
      float t1 = t * 0.12;
      float t2 = t * 0.08;
      float t3 = t * 0.15;

      // Smooth vortex centers drifting in small bounded orbits
      vec2 c1 = vec2(-0.32 + 0.10 * sin(t1), 0.44 + 0.07 * cos(t2));
      vec2 c2 = vec2(0.40 + 0.09 * cos(t2 * 0.9), -0.08 + 0.08 * sin(t3));

      float v1 = 0.28 * exp(-dot(p - c1, p - c1) * 2.2);
      float v2 = -0.22 * exp(-dot(p - c2, p - c2) * 1.8);

      // Streamline field
      float psi = dp.y + v1 + v2;
      psi += 0.060 * sin(dp.x * 1.35 + t1) * exp(-dp.y * dp.y * 1.5);
      psi += 0.035 * cos(dp.x * 2.40 - t2);

      return psi;
    }

    // Evaluates 3D surface height fields and coordinates of the dual fluid ribbons
    void evaluateFluidRibbons(vec2 p, float t, float target1, float target2,
                             out float h1, out float h2, 
                             out float dist1, out float dist2, 
                             out float width1, out float width2, 
                             out float crestDist1, out float foldDist1,
                             out float chi) {
      float eps = 0.0035;
      float chiX, chiY;
      float psi = evaluateStream(p, t, chi);
      float psiX = evaluateStream(p + vec2(eps, 0.0), t, chiX);
      float psiY = evaluateStream(p + vec2(0.0, eps), t, chiY);

      vec2 gradPsi = vec2(psiX - psi, psiY - psi) / eps;
      float gradLen = max(0.001, length(gradPsi));

      // ── Primary Sovereign Ribbon 1 ────────────────────────────────────────
      // Target streamline in upper quadrant: clears AI orb and deck completely
      dist1 = (psi - target1) / gradLen; // Exact Euclidean distance to ribbon center

      // Dynamic width modulation along the flow: widens into broad sheet, narrows into tendril
      width1 = 0.34 + 0.11 * sin(chi * 1.15 + sin(t * 0.10) * 0.4) + 0.05 * cos(chi * 2.2 - t * 0.06);
      width1 = max(0.14, width1);

      // Asymmetric 3D liquid wave profile with curled rim and sharp crest
      float s1 = dist1 / width1;
      float s1Sq = s1 * s1;
      float hBase1 = exp(-s1Sq * 3.4) * smoothstep(1.22, 0.45, abs(s1));

      // Curled secondary ridge fold (at s1 = -0.38)
      foldDist1 = dist1 - (-0.38 * width1);
      float hFold1 = 0.28 * exp(-pow(s1 + 0.38, 2.0) * 22.0);

      // Razor-sharp primary crest ridge (at s1 = 0.08)
      crestDist1 = dist1 - (0.08 * width1);
      float hCrest1 = 0.38 * exp(-pow(s1 - 0.08, 2.0) * 16.0);

      h1 = hBase1 + hFold1 + hCrest1;

      // ── Secondary Translucent Ribbon 2 (Upper Echoing Fold) ───────────────
      dist2 = (psi - target2) / gradLen;

      width2 = 0.22 + 0.07 * cos(chi * 1.30 - t * 0.11);
      width2 = max(0.09, width2);

      float s2 = dist2 / width2;
      float s2Sq = s2 * s2;
      h2 = exp(-s2Sq * 4.2) * smoothstep(1.20, 0.50, abs(s2));
    }

    void main() {
      vec2 uv = (gl_FragCoord.xy - 0.5 * u_resolution.xy) / min(u_resolution.x, u_resolution.y);
      vec2 p = uv + (u_mouse - 0.5) * 0.025;

      float effectiveSpeed = (u_reduced_motion > 0.5) ? 0.015 : u_speed;
      float t = u_time * effectiveSpeed;

      // Responsive Aspect-Ratio Adaptive Framing
      float aspect = u_resolution.x / u_resolution.y;
      float portraitElevate = max(0.0, (1.35 - aspect) * 0.38);
      float target1 = u_target1 + portraitElevate;
      float target2 = u_target2 + portraitElevate * 0.85;

      // Evaluate ribbon geometry
      float h1, h2, dist1, dist2, width1, width2, crestDist1, foldDist1, chi;
      evaluateFluidRibbons(p, t, target1, target2, h1, h2, dist1, dist2, width1, width2, crestDist1, foldDist1, chi);

      float hComposite = h1 * 1.0 + h2 * 0.42;

      // Finite differences for smooth 3D surface normal
      float eps = 0.0035;
      float h1X, h2X, d1X, d2X, w1X, w2X, cr1X, fl1X, chiX;
      float h1Y, h2Y, d1Y, d2Y, w1Y, w2Y, cr1Y, fl1Y, chiY;
      evaluateFluidRibbons(p + vec2(eps, 0.0), t, target1, target2, h1X, h2X, d1X, d2X, w1X, w2X, cr1X, fl1X, chiX);
      evaluateFluidRibbons(p + vec2(0.0, eps), t, target1, target2, h1Y, h2Y, d1Y, d2Y, w1Y, w2Y, cr1Y, fl1Y, chiY);

      float hCompX = h1X * 1.0 + h2X * 0.42;
      float hCompY = h1Y * 1.0 + h2Y * 0.42;

      vec2 grad = vec2(hComposite - hCompX, hComposite - hCompY) / eps;
      vec3 N = normalize(vec3(grad * 0.55, 1.0));
      vec3 V = vec3(0.0, 0.0, 1.0);
      vec3 R = reflect(-V, N);

      // ── FRESNEL & OPTICAL DISPERSION ──────────────────────────────────────
      float NdotV = clamp(dot(N, V), 0.0, 1.0);
      float fresnel = pow(1.0 - NdotV, 2.7);

      // Key Light 1: Studio overhead softbox (top-left)
      vec3 L1 = normalize(vec3(-0.45, 0.72, 0.68));
      vec3 H1 = normalize(L1 + V);
      float NdotH1 = max(0.0, dot(N, H1));

      float specBroad = pow(NdotH1, 14.0) * 0.40;
      float specSharp = pow(NdotH1, 75.0) * 1.65 * u_highlight;
      float specChromeGlint = pow(NdotH1, 380.0) * 3.80 * u_highlight;

      // Fill Light: Luminous electric cyan fill from bottom-right
      vec3 L2 = normalize(vec3(0.68, -0.52, 0.50));
      vec3 H2 = normalize(L2 + V);
      float NdotH2 = max(0.0, dot(N, H2));
      float specRim = pow(NdotH2, 22.0) * 0.85;

      // ── RAZOR-SHARP POLISHED CHROME CREST LINES ───────────────────────────
      float spineWidth1 = width1 * 0.030;
      float spineWidth2 = width2 * 0.032;
      float foldWidth1  = width1 * 0.026;

      float chromeSpine1 = exp(-crestDist1 * crestDist1 / (spineWidth1 * spineWidth1));
      float chromeSoft1  = exp(-crestDist1 * crestDist1 / (spineWidth1 * spineWidth1 * 8.0));

      float chromeFold1  = exp(-foldDist1 * foldDist1 / (foldWidth1 * foldWidth1));
      float chromeFoldSoft1 = exp(-foldDist1 * foldDist1 / (foldWidth1 * foldWidth1 * 7.0));

      float chromeSpine2 = exp(-dist2 * dist2 / (spineWidth2 * spineWidth2));
      float chromeSoft2  = exp(-dist2 * dist2 / (spineWidth2 * spineWidth2 * 8.0));

      // Dynamic glint shimmer along the spine as waves ripple through
      float glintWave = 0.82 + 0.45 * sin(chi * 3.8 - t * 0.24);
      chromeSpine1 *= glintWave;

      // ── PRISMATIC IRIDESCENCE ALONG THIN REFRACTIVE GLASS EDGES ───────────
      float rimAngle = atan(grad.y, grad.x);
      float iridPhase = rimAngle * 1.50 + fresnel * 4.6 + chi * 0.70;

      vec3 iridColor = mix(
        mix(u_col_violet, u_col_lavender, 0.5 + 0.5 * sin(iridPhase)),
        u_col_warm_amber,
        clamp(0.5 + 0.5 * cos(iridPhase + 1.2), 0.0, 1.0)
      );
      // Thin edge mask where the glass is thin and glancing angle is high
      float s1Norm = abs(dist1 / width1);
      float edgeThinMask = smoothstep(0.55, 0.98, s1Norm) * smoothstep(0.18, 0.85, fresnel);
      vec3 edgeIridescence = iridColor * edgeThinMask * 1.40;

      // ── TRANSLUCENT FLUID & OBSIDIAN PALETTE ──────────────────────────────
      // Obsidian Canvas base (#030508 to #070B14)
      vec3 bg = mix(u_col_bg_deep, u_col_bg_mid, uv.y * 0.5 + 0.5);

      // Physical Beer-Lambert style volume absorption
      float density = clamp(hComposite * 1.15, 0.0, 1.0);
      vec3 liquid = mix(bg, u_col_deep_navy, smoothstep(0.02, 0.26, density));
      liquid = mix(liquid, u_col_royal_blue, smoothstep(0.20, 0.55, density) * 0.92);
      liquid = mix(liquid, u_col_electric_blue, smoothstep(0.48, 0.78, density) * 0.95);
      liquid = mix(liquid, u_col_cyan_glow, smoothstep(0.70, 0.95, density) * 0.85);

      // Subsurface glow and caustic aura diffusing through the glass body
      float sss = smoothstep(0.15, 0.60, h1) * (1.0 - smoothstep(0.60, 0.92, h1));
      float aura = exp(-dist1 * dist1 * 12.0) * 0.30 + exp(-dist2 * dist2 * 16.0) * 0.18;
      liquid += u_col_cyan_glow * (sss * 0.40 + aura);
      liquid += u_col_electric_blue * fresnel * density * 0.50;
      liquid += edgeIridescence;

      // Additive Studio Specular Highlights & Glints
      vec3 spec = u_col_pure_white * (specSharp + specChromeGlint) 
                + u_col_cyan_glow * specBroad 
                + u_col_electric_blue * specRim;
      spec *= smoothstep(0.06, 0.42, density);
      liquid += spec;

      // Additive Radiant Diamond Chrome Crest Line (blazes in pure white)
      vec3 chromeLine = u_col_white_blue * (chromeSoft1 * 0.55 + chromeFoldSoft1 * 0.38 + chromeSoft2 * 0.32)
                      + u_col_pure_white * (chromeSpine1 * 1.65 + chromeFold1 * 0.90 + chromeSpine2 * 0.90) * u_highlight;
      liquid += chromeLine * smoothstep(0.08, 0.45, density);

      // Ambient Occlusion in the groove between folds and ribbons
      float grooveDist = abs(dist1 - dist2);
      float ao = smoothstep(0.02, 0.22, grooveDist);
      liquid = mix(liquid * 0.70, liquid, ao);

      // Contrast Mask: Pure black outside the fluid manifold
      float mask = smoothstep(0.010, 0.20, density);
      vec3 finalColor = mix(bg, liquid, mask);

      // Soft Vignette
      float vignette = 1.0 - smoothstep(0.75, 1.55, length(uv * vec2(0.9, 1.0)));
      finalColor = mix(u_col_bg_deep, finalColor, vignette * 0.20 + 0.80);

      // Filmic Tonemapping
      finalColor = (finalColor * (1.0 + finalColor * 0.20)) / (1.0 + finalColor);

      // Blue-Noise Dither
      float dither = (hash(gl_FragCoord.xy + fract(u_time * 0.01)) - 0.5) / 255.0;
      finalColor += dither;

      gl_FragColor = vec4(finalColor, 1.0);
    }
  `;

  class LiquidGlassEngine {
    constructor(canvas, config = {}) {
      this.canvas = canvas;
      this.config = Object.assign({}, LIQUID_CONFIG, config);
      this.gl = null;
      this.program = null;
      this.animId = null;
      this.startTime = performance.now();
      this.mouseTarget = { x: 0.5, y: 0.5 };
      this.mouseCurrent = { x: 0.5, y: 0.5 };
      this.isRunning = false;
      this.onResize = this.resize.bind(this);
      this.onMouseMove = this.handleMouseMove.bind(this);

      this.init();
    }

    init() {
      if (!this.canvas) return;

      const glOpts = {
        alpha: false,
        depth: false,
        stencil: false,
        antialias: true,
        powerPreference: "high-performance",
        preserveDrawingBuffer: false,
      };

      this.gl = this.canvas.getContext("webgl", glOpts) || this.canvas.getContext("experimental-webgl", glOpts);
      if (!this.gl) {
        console.warn("[zenith-shader] WebGL unsupported, falling back to CSS dark luxury gradient.");
        this.canvas.style.background = "radial-gradient(ellipse at 30% 60%, #061836 0%, #030508 70%)";
        return;
      }

      const gl = this.gl;
      const vs = this.compileShader(gl.VERTEX_SHADER, VS_SOURCE);
      const fs = this.compileShader(gl.FRAGMENT_SHADER, FS_SOURCE);
      if (!vs || !fs) return;

      const program = gl.createProgram();
      gl.attachShader(program, vs);
      gl.attachShader(program, fs);
      gl.linkProgram(program);

      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.error("[zenith-shader] Program link failed:", gl.getProgramInfoLog(program));
        return;
      }
      this.program = program;

      // Full-screen Quad Geometry
      const posBuffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([
          -1.0, -1.0,
           1.0, -1.0,
          -1.0,  1.0,
          -1.0,  1.0,
           1.0, -1.0,
           1.0,  1.0,
        ]),
        gl.STATIC_DRAW
      );

      this.posLoc = gl.getAttribLocation(program, "a_pos");
      this.locs = {
        res: gl.getUniformLocation(program, "u_resolution"),
        time: gl.getUniformLocation(program, "u_time"),
        mouse: gl.getUniformLocation(program, "u_mouse"),
        reducedMotion: gl.getUniformLocation(program, "u_reduced_motion"),
        speed: gl.getUniformLocation(program, "u_speed"),
        angle: gl.getUniformLocation(program, "u_angle"),
        target1: gl.getUniformLocation(program, "u_target1"),
        target2: gl.getUniformLocation(program, "u_target2"),
        highlight: gl.getUniformLocation(program, "u_highlight"),

        // Colors
        bgDeep: gl.getUniformLocation(program, "u_col_bg_deep"),
        bgMid: gl.getUniformLocation(program, "u_col_bg_mid"),
        deepNavy: gl.getUniformLocation(program, "u_col_deep_navy"),
        royalBlue: gl.getUniformLocation(program, "u_col_royal_blue"),
        electricBlue: gl.getUniformLocation(program, "u_col_electric_blue"),
        cyanGlow: gl.getUniformLocation(program, "u_col_cyan_glow"),
        whiteBlue: gl.getUniformLocation(program, "u_col_white_blue"),
        pureWhite: gl.getUniformLocation(program, "u_col_pure_white"),
        lavender: gl.getUniformLocation(program, "u_col_lavender"),
        violet: gl.getUniformLocation(program, "u_col_violet"),
        warmAmber: gl.getUniformLocation(program, "u_col_warm_amber"),
      };

      window.addEventListener("resize", this.onResize);
      window.addEventListener("mousemove", this.onMouseMove, { passive: true });
      this.resize();
    }

    compileShader(type, src) {
      const gl = this.gl;
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        console.error("[zenith-shader] Shader compile error:", gl.getShaderInfoLog(s));
        gl.deleteShader(s);
        return null;
      }
      return s;
    }

    resize() {
      if (!this.canvas || !this.gl) return;
      // Cap DPR to 1.5 to guarantee high-end 60 FPS performance on 4K / retina displays
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      const w = Math.round(window.innerWidth * dpr);
      const h = Math.round(window.innerHeight * dpr);

      if (this.canvas.width !== w || this.canvas.height !== h) {
        this.canvas.width = w;
        this.canvas.height = h;
        this.gl.viewport(0, 0, w, h);
      }
    }

    handleMouseMove(e) {
      this.mouseTarget.x = e.clientX / window.innerWidth;
      this.mouseTarget.y = 1.0 - (e.clientY / window.innerHeight);
    }

    start() {
      if (this.isRunning) return;
      this.isRunning = true;
      this.startTime = performance.now();
      this.resize();

      const loop = (now) => {
        if (!this.isRunning) return;
        this.render(now);
        this.animId = requestAnimationFrame(loop);
      };
      this.animId = requestAnimationFrame(loop);
    }

    stop() {
      this.isRunning = false;
      if (this.animId) {
        cancelAnimationFrame(this.animId);
        this.animId = null;
      }
    }

    render(now) {
      const gl = this.gl;
      if (!gl || !this.program) return;

      const elapsed = (now - this.startTime) / 1000;
      const prefersReduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

      // Smooth mouse interpolation
      this.mouseCurrent.x += (this.mouseTarget.x - this.mouseCurrent.x) * 0.04;
      this.mouseCurrent.y += (this.mouseTarget.y - this.mouseCurrent.y) * 0.04;

      gl.useProgram(this.program);
      gl.enableVertexAttribArray(this.posLoc);
      gl.vertexAttribPointer(this.posLoc, 2, gl.FLOAT, false, 0, 0);

      const rad = (this.config.angleDeg * Math.PI) / 180.0;

      gl.uniform2f(this.locs.res, this.canvas.width, this.canvas.height);
      gl.uniform1f(this.locs.time, elapsed + this.config.timeStartOffset);
      gl.uniform2f(this.locs.mouse, this.mouseCurrent.x, this.mouseCurrent.y);
      gl.uniform1f(this.locs.reducedMotion, prefersReduced ? 1.0 : 0.0);
      gl.uniform1f(this.locs.speed, this.config.speed);
      gl.uniform1f(this.locs.angle, rad);
      gl.uniform1f(this.locs.target1, this.config.target1);
      gl.uniform1f(this.locs.target2, this.config.target2);
      gl.uniform1f(this.locs.highlight, this.config.highlightIntensity);

      // Upload Colors
      const c = this.config.colors;
      gl.uniform3fv(this.locs.bgDeep, c.bgDeep);
      gl.uniform3fv(this.locs.bgMid, c.bgMid);
      gl.uniform3fv(this.locs.deepNavy, c.deepNavy);
      gl.uniform3fv(this.locs.royalBlue, c.royalBlue);
      gl.uniform3fv(this.locs.electricBlue, c.electricBlue);
      gl.uniform3fv(this.locs.cyanGlow, c.cyanGlow);
      gl.uniform3fv(this.locs.whiteBlue, c.whiteBlue);
      gl.uniform3fv(this.locs.pureWhite, c.pureWhite);
      gl.uniform3fv(this.locs.lavender, c.lavender);
      gl.uniform3fv(this.locs.violet, c.violet);
      gl.uniform3fv(this.locs.warmAmber, c.warmAmber);

      gl.drawArrays(gl.TRIANGLES, 0, 6);
    }

    destroy() {
      this.stop();
      window.removeEventListener("resize", this.onResize);
      window.removeEventListener("mousemove", this.onMouseMove);
    }
  }

  // Global Singleton Interface
  let instance = null;

  window.ZenithLiquidShader = {
    init: function (canvasElement, customConfig) {
      if (!instance && canvasElement) {
        instance = new LiquidGlassEngine(canvasElement, customConfig);
      }
      return instance;
    },
    start: function () {
      if (!instance) {
        const c = document.getElementById("cinema-liquid-shader");
        if (c) instance = new LiquidGlassEngine(c);
      }
      if (instance) instance.start();
    },
    stop: function () {
      if (instance) instance.stop();
    },
    getInstance: function () {
      return instance;
    }
  };
})();

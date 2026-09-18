/* ZENITH frontend — WebSocket chat, streaming, voice, state.
   Zenith is a personal assistant, not an ops console. Vanilla JS, no build
   step. Talks to the FastAPI/WS contract + /api/state. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);

  /* state */
  let ws = null;
  let reconnectTimer = null;
  let heartbeatTimer = null;
  let typingEl = null;
  let streamBuffer = "";
  let ackPendingDivider = false;
  let awaiting = false;

  const SEND_ICON_SVG = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="5 12 12 5 19 12"></polyline></svg>`;
  const STOP_ICON_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="14" height="14" rx="2.5" fill="currentColor"/></svg>`;

  function setGenerating(isGen) {
    const btn = $("send-btn");
    if (!btn) return;
    if (isGen) {
      btn.classList.add("stop");
      btn.innerHTML = STOP_ICON_SVG;
      btn.title = "Stop generating (Esc)";
      btn.setAttribute("aria-label", "Stop generating");
    } else {
      btn.classList.remove("stop");
      btn.innerHTML = SEND_ICON_SVG;
      btn.title = "Send";
      btn.setAttribute("aria-label", "Send");
    }
  }

  function stopGenerating() {
    if (!awaiting) return;
    clearTimeout(awaitingTimer);
    try {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "stop" }));
      }
      fetch("/api/chat/stop", { method: "POST" }).catch(() => {});
    } catch (_) {}
    if (streamBuffer) {
      streamBuffer += "\n\n*(generation stopped)*";
    }
    finishStream(streamBuffer);
    awaiting = false;
    setGenerating(false);
  }

  // voice — hands-free live conversation (no push-to-talk)
  let micStream = null;
  let audioCtx = null;
  let analyser = null;
  let orbAnim = null;
  let recorder = null;
  let volume = 0;
  let micReady = false;       // getUserMedia resolved → UI shows "mic ready"
  let voicePaused = false;    // listening paused (orb tap on mobile / G)
  let voiceStatusRemote = "voice · G";
  let zenithVoiceSpoken = true; // spoken replies on by default; toggled inline
  // live-convo state
  let vad = {
    enabled: false,           // VAD is armed only while Zenith is not mid-turn
    speech: false,            // currently capturing speech
    speechStartMs: 0,
    silenceStartMs: 0,
    cfg: { silence_ms: 1300, min_speech_ms: 250, max_utterance_ms: 20000 },
  };
  let voiceBusy = false;      // guard: a transcribe/agent cycle is in flight
  let processingSpeech = false; // transcribe in-flight
  let utterQueue = [];        // utterances captured while Zenith was thinking

  // Erase a stale live-WS refusal when the server restarts (the container
  // deploys new Live code; a fresh WS will work again). Refreshing the voice
  // status re-checks readiness, so we reset the guard there.
  let lastLiveWsRefusedAt = 0;

  // Live input runs at the model's native 16 kHz. The browser mic may be
  // 48 kHz, so the capture ScriptProcessor decimates to 16k mono before PCM.
  const LIVE_PCM_RATE = 16000;
  const LIVE_OUTPUT_RATE = 24000;



  let currentUser = null;

  /* ── User & Profile Management (Zero-Auth Standalone Mode) ── */
  async function loadCurrentUser() {
    try {
      const resp = await fetch("/api/auth/me");
      if (resp.ok) {
        const data = await resp.json();
        if (data && data.user) {
          currentUser = data.user;
          if (currentUser.name && !window._zenithUserName) {
            window._zenithUserName = currentUser.name;
          }
        }
      }
    } catch (e) {
      console.warn("[zenith] Failed to load current user:", e);
    }
  }

  function showApp() {
    const starterScreen = $("starter-screen");
    const setupScreen = $("setup-screen");
    const appRoot = $("app-root");
    if (starterScreen) starterScreen.style.display = "none";
    if (setupScreen) setupScreen.style.display = "none";
    if (appRoot) appRoot.style.display = "flex";

    // Stop liquid shader to conserve 100% GPU resources when in console
    if (window.ZenithLiquidShader) {
      window.ZenithLiquidShader.stop();
    }

    // Personalized greeting & profile in top header
    const rawName = (currentUser && (currentUser.name || currentUser.username)) || window._zenithUserName || "Friend";
    const userName = rawName ? (rawName.charAt(0).toUpperCase() + rawName.slice(1)) : "Friend";
    const userEmail = (currentUser && currentUser.email) || "";

    const h = new Date(Date.now() + 330 * 60000).getUTCHours();
    let g = "Good evening";
    if (h >= 5 && h < 12) g = "Good morning";
    else if (h >= 12 && h < 17) g = "Good afternoon";
    else if (h >= 17 || h < 4) g = "Good evening";
    else g = "Good morning";

    const greetEl = $("wlcm-greet");
    if (greetEl) greetEl.textContent = g;
    const greetSoft = document.querySelector("#wlcm-title .wlcm-soft");
    if (greetSoft) greetSoft.textContent = `, ${userName}`;


    const userMenu = $("hdr-user-menu");
    const userAvatar = $("hdr-user-avatar");
    const userUname = $("hdr-user-name");
    const dropName = $("hdr-dropdown-name");
    const dropEmail = $("hdr-dropdown-email");

    if (userMenu) userMenu.style.display = "block";
    if (userAvatar) {
      if (currentUser && currentUser.picture) {
        userAvatar.innerHTML = `<img src="${esc(currentUser.picture)}" alt="${esc(userName)}" />`;
      } else {
        userAvatar.textContent = (userName[0] || "U").toUpperCase();
      }
    }
    if (userUname) userUname.textContent = userName;
    if (dropName) dropName.textContent = userName;
    if (dropEmail) dropEmail.textContent = userEmail;
  }

  function wireUserMenu() {
    const userBtn = $("hdr-user-btn");
    const dropdown = $("hdr-user-dropdown");
    if (userBtn) {
      userBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        if (dropdown) dropdown.style.display = "none";
        openSetupWizard({ isFirstTime: false });
      });
    }
  }

  /* ══════════════════════════════════════════════════════════════════════════════
     ZENITH — Operating Modes, Live Theming & Starter Profile
     ══════════════════════════════════════════════════════════════════════════════ */

  function updateDisplayedUserName(name) {
    if (!name) return;
    window._zenithUserName = name;
    if (currentUser) {
      currentUser.name = name;
      currentUser.username = name.toLowerCase().replace(/\s+/g, "_");
    }
    const formattedName = name.charAt(0).toUpperCase() + name.slice(1);
    const greetSoft = document.querySelector("#wlcm-title .wlcm-soft");
    if (greetSoft) greetSoft.textContent = `, ${formattedName}`;
    const wlcmName = $("wlcm-name");
    if (wlcmName) wlcmName.textContent = `, ${formattedName}`;
    const userUname = $("hdr-user-name");
    if (userUname) userUname.textContent = formattedName;
    const dropName = $("hdr-dropdown-name");
    if (dropName) dropName.textContent = formattedName;
    const userAvatar = $("hdr-user-avatar");
    if (userAvatar && !(currentUser && currentUser.picture)) {
      userAvatar.textContent = formattedName.charAt(0).toUpperCase();
    }
    const starterName = $("starter-name");
    if (starterName) starterName.value = formattedName;
  }

  function showToast(icon, message, durationMs = 3500) {
    const container = $("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.innerHTML = `<span class="toast-icon">${icon}</span><span class="toast-text">${esc(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("toast-fadeout");
      setTimeout(() => toast.remove(), 300);
    }, durationMs);
  }

  function applyLiveTheme(accentColor, customCss) {
    if (accentColor) {
      document.documentElement.style.setProperty("--accent", accentColor);
      document.documentElement.style.setProperty("--accent-soft", accentColor + "25");
      document.documentElement.style.setProperty("--accent-glow", accentColor + "45");
    }
    const liveStyle = $("live-custom-css");
    if (liveStyle && customCss) {
      liveStyle.textContent = customCss;
    }
    const themeLink = $("custom-theme-link");
    if (themeLink) {
      themeLink.href = "/static/custom_theme.css?t=" + Date.now();
    }
  }

  function resetLiveTheme() {
    document.documentElement.style.removeProperty("--accent");
    document.documentElement.style.removeProperty("--accent-soft");
    document.documentElement.style.removeProperty("--accent-glow");
    const liveStyle = $("live-custom-css");
    if (liveStyle) liveStyle.textContent = "";
    const themeLink = $("custom-theme-link");
    if (themeLink) {
      themeLink.href = "/static/custom_theme.css?t=" + Date.now();
    }
  }

  let currentZenithMode = "setup";

  function applyZenithMode(mode, modeTitle) {
    currentZenithMode = (mode === "sovereign") ? "sovereign" : "setup";
    const pill = $("setup-mode-active-pill");
    const desc = $("setup-mode-desc-text");
    const btnSetup = $("mode-btn-setup");
    const btnSovereign = $("mode-btn-sovereign");
    const hdrPill = $("hdr-mode-pill");
    const hdrText = $("hdr-mode-text");
    const tpMode = $("tp-mode-val");

    if (currentZenithMode === "sovereign") {
      if (pill) {
        pill.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> <span>Sovereign</span>`;
        pill.className = "setup-mode-active-pill sovereign";
      }
      if (desc) {
        desc.textContent = "Autonomous operations, direct command, and homelab execution.";
      }
      if (btnSovereign) btnSovereign.classList.add("active");
      if (btnSetup) btnSetup.classList.remove("active");
      if (hdrPill) hdrPill.classList.add("sovereign");
      if (hdrText) hdrText.textContent = "Sovereign";
      if (tpMode) tpMode.textContent = "Sovereign Mode";
    } else {
      if (pill) {
        pill.innerHTML = `<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z"/><path d="M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/><path d="M12 2v2"/><path d="M12 22v-2"/></svg> <span>Setup</span>`;
        pill.className = "setup-mode-active-pill";
      }
      if (desc) {
        desc.textContent = "Guided companion helping you set up tools and integrations.";
      }
      if (btnSetup) btnSetup.classList.add("active");
      if (btnSovereign) btnSovereign.classList.remove("active");
      if (hdrPill) hdrPill.classList.remove("sovereign");
      if (hdrText) hdrText.textContent = "Setup";
      if (tpMode) tpMode.textContent = "Setup Mode";
    }
  }

  async function setZenithMode(targetMode) {
    const target = (targetMode === "sovereign") ? "sovereign" : "setup";
    try {
      const resp = await fetch("/api/mode", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: target, reason: "Switched in Settings Studio" }),
      });
      if (resp.ok) {
        const data = await resp.json();
        applyZenithMode(data.mode || target, data.message);
        showToast(target === "sovereign" ? "⚡" : "🌱", `Switched to ${target === "sovereign" ? "Sovereign" : "Setup"} Mode`);
      }
    } catch (e) {
      console.warn("[zenith] Failed to switch mode:", e);
    }
  }

  function wireSettingsModeSelector() {
    const btnSetup = $("mode-btn-setup");
    const btnSovereign = $("mode-btn-sovereign");

    if (btnSetup) {
      btnSetup.addEventListener("click", () => {
        setZenithMode("setup");
      });
    }
    if (btnSovereign) {
      btnSovereign.addEventListener("click", () => {
        setZenithMode("sovereign");
      });
    }
    initZenithMode();
  }

  async function initZenithMode() {
    try {
      const resp = await fetch("/api/mode");
      if (resp.ok) {
        const data = await resp.json();
        if (data && data.mode) {
          applyZenithMode(data.mode, data.name);
        }
      }
    } catch (e) {
      console.warn("[zenith] Could not fetch current mode:", e);
    }
  }

  /* ══════════════════════════════════════════════════════════════════════════════
     ZENITH — Cinematic Movie Onboarding Engine
     Moves through night sky, zooms into clouds, fades to dark, discovers name,
     compliments name, verifies Gemini key, welcomes user, and presents 2 choices.
     ══════════════════════════════════════════════════════════════════════════════ */
  let cinematicStarfieldLoop = null;
  let cinematicFlightTimer = null;
  let cinematicRevealTimer = null;
  let flightGeneration = 0;
  let currentOnboardingName = "";

  function generateNameCompliment(name) {
    const raw = (name || "").trim();
    const displayName = raw ? esc(raw.charAt(0).toUpperCase() + raw.slice(1)) : "Friend";

    const compliments = [
      {
        quote: `“Good to have you onboard, ${displayName}. Let's get things moving.”`,
        sub: "Profile saved • Ready to configure workspace"
      },
      {
        quote: `“Welcome, ${displayName}. Let's get your environment dialed in.”`,
        sub: "Profile saved • Ready to configure workspace"
      },
      {
        quote: `“Good to meet you, ${displayName}. Let's build something great.”`,
        sub: "Profile saved • Ready to configure workspace"
      }
    ];

    let hash = 0;
    for (let i = 0; i < raw.length; i++) hash = (hash * 31 + raw.charCodeAt(i)) >>> 0;
    return compliments[hash % compliments.length];
  }

  /* ── Cinema Audio & Synthesizer Engine (Cinematic Web Audio) ── */
  const CinemaAudio = (() => {
    let ctx = null;
    let isMuted = false;
    let droneGain = null;
    let droneOscs = [];
    let windGain = null;
    let windFilter = null;
    let windSource = null;
    let rumbleGain = null;
    let rumbleOsc = null;

    function getAudioContext() {
      if (!ctx) {
        const AudioClass = window.AudioContext || window.webkitAudioContext;
        if (AudioClass) {
          ctx = new AudioClass();
        }
      }
      if (ctx && ctx.state === "suspended") {
        ctx.resume().catch(() => {});
      }
      return ctx;
    }

    function toggleMute() {
      isMuted = !isMuted;
      if (isMuted) {
        stopAll();
      }
      return isMuted;
    }

    function stopAll() {
      try {
        if (droneGain && ctx) {
          droneGain.gain.cancelScheduledValues(ctx.currentTime);
          droneGain.gain.setValueAtTime(droneGain.gain.value, ctx.currentTime);
          droneGain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.3);
        }
        if (windGain && ctx) {
          windGain.gain.cancelScheduledValues(ctx.currentTime);
          windGain.gain.setValueAtTime(windGain.gain.value, ctx.currentTime);
          windGain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.3);
        }
        if (rumbleGain && ctx) {
          rumbleGain.gain.cancelScheduledValues(ctx.currentTime);
          rumbleGain.gain.setValueAtTime(rumbleGain.gain.value, ctx.currentTime);
          rumbleGain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.3);
        }
        setTimeout(() => {
          droneOscs.forEach((o) => {
            try {
              o.stop();
              o.disconnect();
            } catch (e) {}
          });
          droneOscs = [];
          if (windSource) {
            try {
              windSource.stop();
              windSource.disconnect();
            } catch (e) {}
            windSource = null;
          }
          if (rumbleOsc) {
            try {
              rumbleOsc.stop();
              rumbleOsc.disconnect();
            } catch (e) {}
            rumbleOsc = null;
          }
        }, 350);
      } catch (e) {}
    }

    function startFlightAudio() {
      if (isMuted) return;
      const ac = getAudioContext();
      if (!ac) return;

      try {
        stopAll();
        const now = ac.currentTime;

        // Cinematic velvet low-end chord drone (D2=73.42Hz, A2=110Hz, D3=146.83Hz, F#3=185Hz)
        droneGain = ac.createGain();
        droneGain.gain.setValueAtTime(0.001, now);
        droneGain.gain.exponentialRampToValueAtTime(0.18, now + 1.2);

        const filter = ac.createBiquadFilter();
        filter.type = "lowpass";
        filter.frequency.setValueAtTime(180, now);
        filter.frequency.exponentialRampToValueAtTime(460, now + 3.2);
        filter.Q.setValueAtTime(2.2, now);

        const freqs = [73.42, 110.0, 146.83, 184.99];
        freqs.forEach((freq, idx) => {
          const osc = ac.createOscillator();
          osc.type = "sine";
          // Subtle organic detune
          osc.frequency.setValueAtTime(freq + (idx % 2 === 0 ? 0.35 : -0.28), now);
          osc.connect(filter);
          osc.start(now);
          droneOscs.push(osc);
        });

        filter.connect(droneGain);
        droneGain.connect(ac.destination);

        // Organic Pink Noise Atmospheric Wind / Cloud Glide
        const bufferSize = Math.floor(ac.sampleRate * 4.5);
        const noiseBuffer = ac.createBuffer(1, bufferSize, ac.sampleRate);
        const output = noiseBuffer.getChannelData(0);
        let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
        for (let i = 0; i < bufferSize; i++) {
          const white = Math.random() * 2 - 1;
          b0 = 0.99886 * b0 + white * 0.0555179;
          b1 = 0.99332 * b1 + white * 0.0750759;
          b2 = 0.96900 * b2 + white * 0.1538520;
          b3 = 0.86650 * b3 + white * 0.3104856;
          b4 = 0.55000 * b4 + white * 0.5329522;
          b5 = -0.7616 * b5 - white * 0.0168980;
          output[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + white * 0.5362) * 0.045;
          b6 = white * 0.115926;
        }

        windSource = ac.createBufferSource();
        windSource.buffer = noiseBuffer;

        windFilter = ac.createBiquadFilter();
        windFilter.type = "bandpass";
        windFilter.frequency.setValueAtTime(280, now);
        // During cloud canopy penetration, air rushes past with surging energy
        windFilter.frequency.exponentialRampToValueAtTime(960, now + 3.2);
        windFilter.Q.setValueAtTime(1.6, now);

        windGain = ac.createGain();
        windGain.gain.setValueAtTime(0.001, now);
        windGain.gain.exponentialRampToValueAtTime(0.06, now + 1.2);
        windGain.gain.exponentialRampToValueAtTime(0.24, now + 3.2);
        windGain.gain.exponentialRampToValueAtTime(0.001, now + 4.5);

        windSource.connect(windFilter);
        windFilter.connect(windGain);
        windGain.connect(ac.destination);
        windSource.start(now);

        // Low-frequency atmospheric pressure rumble as canopy is penetrated
        rumbleOsc = ac.createOscillator();
        rumbleOsc.type = "sine";
        rumbleOsc.frequency.setValueAtTime(42, now);
        rumbleOsc.frequency.exponentialRampToValueAtTime(30, now + 4.2);

        rumbleGain = ac.createGain();
        rumbleGain.gain.setValueAtTime(0.0001, now);
        rumbleGain.gain.setValueAtTime(0.0001, now + 1.8);
        rumbleGain.gain.exponentialRampToValueAtTime(0.15, now + 3.0);
        rumbleGain.gain.exponentialRampToValueAtTime(0.0001, now + 4.5);

        rumbleOsc.connect(rumbleGain);
        rumbleGain.connect(ac.destination);
        rumbleOsc.start(now + 1.8);
      } catch (e) {
        console.warn("[cinema] audio error:", e);
      }
    }

    function playVoidDrop() {
      if (isMuted) return;
      const ac = getAudioContext();
      if (!ac) return;
      try {
        stopAll();
        const now = ac.currentTime;
        // Deep cinema sub-impact (55Hz -> 24Hz) into absolute silence
        const osc = ac.createOscillator();
        const gain = ac.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(60, now);
        osc.frequency.exponentialRampToValueAtTime(24, now + 0.8);
        gain.gain.setValueAtTime(0.35, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.95);
        osc.connect(gain);
        gain.connect(ac.destination);
        osc.start(now);
        osc.stop(now + 1.0);
      } catch (e) {}
    }

    function playCoreAwaken() {
      if (isMuted) return;
      const ac = getAudioContext();
      if (!ac) return;
      try {
        const now = ac.currentTime;
        // Calm crystal glass pad chord: D4 (293.66), A4 (440), E5 (659.25)
        const freqs = [293.66, 440.0, 659.25];
        freqs.forEach((freq, idx) => {
          const osc = ac.createOscillator();
          const gain = ac.createGain();
          const t = now + idx * 0.06;
          osc.type = "sine";
          osc.frequency.setValueAtTime(freq, t);
          gain.gain.setValueAtTime(0.001, t);
          gain.gain.linearRampToValueAtTime(0.09, t + 0.04);
          gain.gain.exponentialRampToValueAtTime(0.0001, t + 1.8);
          osc.connect(gain);
          gain.connect(ac.destination);
          osc.start(t);
          osc.stop(t + 2.0);
        });
      } catch (e) {}
    }

    function playPraiseChime() {
      if (isMuted) return;
      const ac = getAudioContext();
      if (!ac) return;
      try {
        const now = ac.currentTime;
        // High-end glass two-tone: A4 (440) -> E5 (659.25)
        [440.0, 659.25].forEach((freq, idx) => {
          const osc = ac.createOscillator();
          const gain = ac.createGain();
          const t = now + idx * 0.09;
          osc.type = "sine";
          osc.frequency.setValueAtTime(freq, t);
          gain.gain.setValueAtTime(0.001, t);
          gain.gain.linearRampToValueAtTime(0.08, t + 0.03);
          gain.gain.exponentialRampToValueAtTime(0.0001, t + 1.2);
          osc.connect(gain);
          gain.connect(ac.destination);
          osc.start(t);
          osc.stop(t + 1.3);
        });
      } catch (e) {}
    }

    function playIgniteSurge() {
      if (isMuted) return;
      const ac = getAudioContext();
      if (!ac) return;
      try {
        const now = ac.currentTime;
        // Warm cinematic harmonic swell (smooth low-pass sweep, no harsh buzz)
        const osc = ac.createOscillator();
        const gain = ac.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(110, now);
        osc.frequency.exponentialRampToValueAtTime(330, now + 0.8);

        const filter = ac.createBiquadFilter();
        filter.type = "lowpass";
        filter.frequency.setValueAtTime(180, now);
        filter.frequency.exponentialRampToValueAtTime(900, now + 0.7);

        gain.gain.setValueAtTime(0.001, now);
        gain.gain.linearRampToValueAtTime(0.12, now + 0.25);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 1.2);

        osc.connect(filter);
        filter.connect(gain);
        gain.connect(ac.destination);
        osc.start(now);
        osc.stop(now + 1.3);

        // Accompanying calm high harmonic bell
        const bell = ac.createOscillator();
        const bellGain = ac.createGain();
        bell.type = "sine";
        bell.frequency.setValueAtTime(880, now + 0.1);
        bellGain.gain.setValueAtTime(0.001, now + 0.1);
        bellGain.gain.linearRampToValueAtTime(0.06, now + 0.15);
        bellGain.gain.exponentialRampToValueAtTime(0.0001, now + 1.4);
        bell.connect(bellGain);
        bellGain.connect(ac.destination);
        bell.start(now + 0.1);
        bell.stop(now + 1.5);
      } catch (e) {}
    }

    function playBlip() {
      if (isMuted) return;
      const ac = getAudioContext();
      if (!ac) return;
      try {
        const now = ac.currentTime;
        // 12ms acoustic tactile micro-click (like modern premium UI haptics)
        const osc = ac.createOscillator();
        const gain = ac.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(340, now);
        osc.frequency.exponentialRampToValueAtTime(180, now + 0.012);
        gain.gain.setValueAtTime(0.08, now);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.014);
        osc.connect(gain);
        gain.connect(ac.destination);
        osc.start(now);
        osc.stop(now + 0.016);
      } catch (e) {}
    }

    return {
      getAudioContext,
      toggleMute,
      stopAll,
      startFlightAudio,
      playVoidDrop,
      playCoreAwaken,
      playPraiseChime,
      playIgniteSurge,
      playBlip,
      isMuted: () => isMuted,
    };
  })();

  function speakZenithDialogue(text, onEnd) {
    if (!('speechSynthesis' in window)) {
      if (onEnd) onEnd();
      return;
    }
    try {
      window.speechSynthesis.cancel();
      const clean = (text || "").replace(/[“”—✦•]/g, " ").replace(/\s+/g, " ").trim();
      if (!clean) {
        if (onEnd) onEnd();
        return;
      }
      const utter = new SpeechSynthesisUtterance(clean);
      utter.rate = 1.02;
      utter.pitch = 1.05;

      const voices = window.speechSynthesis.getVoices();
      if (voices && voices.length) {
        const preferred = voices.find(
          (v) => (v.name.includes("Natural") || v.name.includes("Google") || v.name.includes("Samantha") || v.name.includes("Neerja")) && v.lang.startsWith("en")
        );
        if (preferred) utter.voice = preferred;
      }

      const viz = $("cinema-voice-viz");
      utter.onstart = () => {
        if (viz) viz.classList.add("is-speaking");
      };
      utter.onend = () => {
        if (viz) viz.classList.remove("is-speaking");
        if (onEnd) onEnd();
      };
      utter.onerror = () => {
        if (viz) viz.classList.remove("is-speaking");
        if (onEnd) onEnd();
      };

      window.speechSynthesis.speak(utter);
    } catch (e) {
      if (onEnd) onEnd();
    }
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // VOLUMETRIC 3D CLOUD FLIGHT ENGINE (60 FPS, Zero Seams, Silky Smooth)
  // ─────────────────────────────────────────────────────────────────────────────
  const PRELOAD_MOON_IMG = new Image();
  PRELOAD_MOON_IMG.src = "/static/landing-art/moon-feathered.png";

  const PRELOAD_HORIZON_IMG = new Image();
  PRELOAD_HORIZON_IMG.src = "/static/landing-art/clouds-horizon-feathered.png";

  function initCinematicFlightEngine(options = {}) {
    const canvas = $("cinema-flight-canvas");
    const hud = $("cinema-flight-hud");
    const hudStatus = $("hud-status-text");
    const hudCoord = $("hud-coord-text");
    const hudTagline = $("hud-tagline-text");
    const heroTitle = $("cinema-hero-title");

    if (!canvas) return { stop: () => {}, renderAtSeconds: () => {} };

    const ctx = canvas.getContext("2d");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = window.innerWidth;
    let height = window.innerHeight;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    ctx.scale(dpr, dpr);

    const onResize = () => {
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      ctx.scale(dpr, dpr);
    };
    window.addEventListener("resize", onResize);

    // 1. Procedural Soft Cloud Lobe Textures (Zero rectangular borders)
    function createCloudSprite(type) {
      const size = 320;
      const c = document.createElement("canvas");
      c.width = size;
      c.height = size;
      const cx = c.getContext("2d");
      const half = size / 2;

      if (type === "cumulus") {
        // Multi-lobed billowy cumulus puff with lunar rim light
        const lobes = [
          { x: 0, y: 0, r: 100 },
          { x: -45, y: -20, r: 75 },
          { x: 40, y: -25, r: 80 },
          { x: -65, y: 20, r: 65 },
          { x: 60, y: 25, r: 70 },
          { x: -15, y: 45, r: 65 },
          { x: 20, y: -50, r: 60 },
          { x: -30, y: -45, r: 55 },
        ];

        lobes.forEach(l => {
          const lx = half + l.x;
          const ly = half + l.y;
          const g = cx.createRadialGradient(lx - l.r * 0.25, ly - l.r * 0.25, 0, lx, ly, l.r);
          g.addColorStop(0, "rgba(235, 243, 255, 0.40)");
          g.addColorStop(0.35, "rgba(175, 200, 230, 0.25)");
          g.addColorStop(0.70, "rgba(80, 110, 155, 0.10)");
          g.addColorStop(1.0, "rgba(15, 25, 45, 0)");
          cx.fillStyle = g;
          cx.beginPath();
          cx.arc(lx, ly, l.r, 0, Math.PI * 2);
          cx.fill();
        });
      } else if (type === "mist") {
        // Soft diffused atmospheric vapor
        const g = cx.createRadialGradient(half, half, 0, half, half, half);
        g.addColorStop(0, "rgba(225, 238, 255, 0.24)");
        g.addColorStop(0.4, "rgba(150, 185, 225, 0.14)");
        g.addColorStop(0.75, "rgba(70, 105, 150, 0.04)");
        g.addColorStop(1.0, "rgba(10, 20, 40, 0)");
        cx.fillStyle = g;
        cx.beginPath();
        cx.arc(half, half, half, 0, Math.PI * 2);
        cx.fill();
      } else if (type === "cirrus") {
        // Stretched horizontal cirrus wisp
        const g = cx.createRadialGradient(half, half, 0, half, half, half);
        g.addColorStop(0, "rgba(240, 248, 255, 0.30)");
        g.addColorStop(0.5, "rgba(160, 190, 235, 0.12)");
        g.addColorStop(1.0, "rgba(10, 20, 40, 0)");
        cx.save();
        cx.translate(half, half);
        cx.scale(1.8, 0.55);
        cx.fillStyle = g;
        cx.beginPath();
        cx.arc(0, 0, half * 0.55, 0, Math.PI * 2);
        cx.fill();
        cx.restore();
      }
      return c;
    }

    const spriteCumulus = createCloudSprite("cumulus");
    const spriteMist = createCloudSprite("mist");
    const spriteCirrus = createCloudSprite("cirrus");

    // Pre-loaded seamless feathered crescent moon & horizon assets
    const moonImg = PRELOAD_MOON_IMG;
    const horizonCloudsImg = PRELOAD_HORIZON_IMG;

    // 2. 3D Particles
    const numStars = 180;
    const stars = [];
    for (let i = 0; i < numStars; i++) {
      stars.push({
        x: (Math.random() - 0.5) * 2800,
        y: (Math.random() - 0.5) * 1800 - 180,
        z: 200 + Math.random() * 2400,
        initialZ: 200 + Math.random() * 2400,
        size: Math.random() * 1.3 + 0.5,
      });
    }

    // 180 Volumetric Cloud Clusters (Canyon walls + Dense Deck Core + Cirrus)
    const numClouds = 180;
    const clouds = [];
    for (let i = 0; i < numClouds; i++) {
      let x, y, z, sprite, scale, alpha;

      if (i < 45) {
        // Left Canyon Wall (flanking cloud towers rushing past left)
        x = -380 - Math.random() * 850;
        y = -180 + Math.random() * 520;
        z = 150 + Math.random() * 2400;
        sprite = Math.random() > 0.35 ? spriteCumulus : spriteMist;
        scale = 1.6 + Math.random() * 2.0;
        alpha = 0.60 + Math.random() * 0.35;
      } else if (i < 90) {
        // Right Canyon Wall (flanking cloud towers rushing past right)
        x = 380 + Math.random() * 850;
        y = -180 + Math.random() * 520;
        z = 150 + Math.random() * 2400;
        sprite = Math.random() > 0.35 ? spriteCumulus : spriteMist;
        scale = 1.6 + Math.random() * 2.0;
        alpha = 0.60 + Math.random() * 0.35;
      } else if (i < 165) {
        // Cloud Deck Core (The cloud deck we dive DIRECTLY THROUGH!)
        x = (Math.random() - 0.5) * 850;
        y = 20 + Math.random() * 340;
        z = 100 + Math.random() * 2600;
        sprite = Math.random() > 0.35 ? spriteCumulus : spriteMist;
        scale = 2.2 + Math.random() * 2.5;
        alpha = 0.75 + Math.random() * 0.25;
      } else {
        // High Cirrus Wisps passing overhead
        x = (Math.random() - 0.5) * 1800;
        y = -240 - Math.random() * 350;
        z = 250 + Math.random() * 2200;
        sprite = spriteCirrus;
        scale = 2.2 + Math.random() * 1.8;
        alpha = 0.45 + Math.random() * 0.35;
      }

      clouds.push({
        x, y, z,
        initialZ: z,
        sprite, scale,
        rot: Math.random() * Math.PI * 2,
        rotSpeed: (Math.random() - 0.5) * 0.003,
        alpha,
      });
    }

    // High-Speed Condensation Streamers (Moisture streaks whipping across canopy)
    const numStreamers = 50;
    const streamers = [];
    for (let i = 0; i < numStreamers; i++) {
      const angle = Math.random() * Math.PI * 2;
      const dist = 50 + Math.random() * 850;
      streamers.push({
        x: Math.cos(angle) * dist,
        y: Math.sin(angle) * dist,
        initialZ: 150 + Math.random() * 1800,
        len: 35 + Math.random() * 75,
        alpha: 0.30 + Math.random() * 0.55,
        width: 1.0 + Math.random() * 2.2,
      });
    }

    let isRunning = true;
    let animLoopId = null;
    const startTime = performance.now();

    function drawFlightFrame(elapsed, now) {
      const HOLD_SECS = 4.5;
      let speed = 12;
      let cameraPitch = 0;
      let cloudDensity = 0.20;
      let voidDarkness = 0;

      if (elapsed < HOLD_SECS) {
        speed = 12;
        cameraPitch = 0;
        cloudDensity = 0.20;
        voidDarkness = 0;
      } else if (elapsed < HOLD_SECS + 1.4) {
        const p = (elapsed - HOLD_SECS) / 1.4;
        speed = 28 + p * 56;
        cameraPitch = p * 140;
        cloudDensity = 0.20 + p * 0.80;
      } else if (elapsed < HOLD_SECS + 2.8) {
        speed = 84;
        cameraPitch = 140;
        cloudDensity = 1.0;
      } else if (elapsed < HOLD_SECS + 3.8) {
        const p = (elapsed - (HOLD_SECS + 2.8)) / 1.0;
        speed = Math.max(0, 84 * (1 - p * p));
        cameraPitch = 140 * (1 - p);
        cloudDensity = Math.max(0, 1.0 - p * 1.5);
        voidDarkness = Math.min(1.0, p * 1.4);
      } else {
        speed = 0;
        cloudDensity = 0;
        voidDarkness = 1.0;
        if (isRunning && options && typeof options.onComplete === "function") {
          isRunning = false;
          options.onComplete();
        }
      }

      // Title & tagline updates
      if (hudTagline) {
        if (elapsed <= HOLD_SECS) {
          hudTagline.textContent = "Autonomous AI Operating Layer";
        } else if (elapsed <= HOLD_SECS + 1.4) {
          hudTagline.textContent = "Approaching cloud canyon descent corridor...";
        } else if (elapsed <= HOLD_SECS + 2.8) {
          hudTagline.textContent = "Navigating dense silver cloud deck...";
        } else {
          hudTagline.textContent = "Clearing cloud base into obsidian void...";
        }
      }
      if (heroTitle) {
        if (elapsed <= HOLD_SECS) {
          heroTitle.style.opacity = "1";
        } else if (elapsed <= HOLD_SECS + 1.2) {
          heroTitle.style.opacity = String(Math.max(0, 1 - (elapsed - HOLD_SECS) / 1.2));
        } else {
          heroTitle.style.opacity = "0";
        }
      }
      if (hudStatus) {
        if (elapsed <= HOLD_SECS) hudStatus.textContent = "ORBITAL CRUISE // ZENITH ACTIVE";
        else if (elapsed <= HOLD_SECS + 1.4) hudStatus.textContent = "ENTERING CLOUD CANYON";
        else if (elapsed <= HOLD_SECS + 2.8) hudStatus.textContent = "PENETRATING CLOUD DECK";
        else hudStatus.textContent = "BREAKTHROUGH COMPLETE";
      }
      if (hudCoord) {
        if (elapsed <= HOLD_SECS) hudCoord.textContent = "ALT 38,000 FT // SPEED 320 KTS";
        else if (elapsed <= HOLD_SECS + 1.4) hudCoord.textContent = "ALT 18,000 FT // SPEED 540 KTS";
        else if (elapsed <= HOLD_SECS + 2.8) hudCoord.textContent = "ALT 7,500 FT // ZERO VISIBILITY";
        else hudCoord.textContent = "ALT 1,000 FT // LEVEL FLIGHT";
      }

      // Micro-turbulence during dense cloud transit
      let shakeX = 0;
      let shakeY = 0;
      if (elapsed >= HOLD_SECS + 0.8 && elapsed <= HOLD_SECS + 2.9) {
        const turbPhase = Math.sin(((elapsed - (HOLD_SECS + 0.8)) / 2.1) * Math.PI);
        const mag = turbPhase * 3.6;
        shakeX = Math.sin(now * 0.045) * mag + Math.sin(now * 0.11) * (mag * 0.4);
        shakeY = Math.cos(now * 0.038) * (mag * 0.75) + Math.cos(now * 0.092) * (mag * 0.3);
      }

      const cx = width / 2 + shakeX;
      const cy = height / 2 + shakeY;
      const fov = 420;

      // 1. Deep Space Nocturnal Sky
      const skyGrad = ctx.createLinearGradient(0, 0, 0, height);
      skyGrad.addColorStop(0, "#020409");
      skyGrad.addColorStop(0.55, "#060a14");
      skyGrad.addColorStop(0.85, "#0a1222");
      skyGrad.addColorStop(1.0, "#0e182e");
      ctx.fillStyle = skyGrad;
      ctx.fillRect(0, 0, width, height);

      // 2. Stars
      const starFade = elapsed < HOLD_SECS ? 1.0 : Math.max(0, 1 - ((elapsed - HOLD_SECS) / 2.6));
      if (starFade > 0.01) {
        for (let i = 0; i < numStars; i++) {
          const s = stars[i];
          const starOffset = elapsed < HOLD_SECS ? elapsed * 50 : (HOLD_SECS * 50 + (elapsed - HOLD_SECS) * 350);
          const curZ = ((s.initialZ - starOffset) % 2400 + 2400) % 2400 + 50;
          const prevZ = curZ + speed * 0.5;

          const k = fov / curZ;
          const pk = fov / prevZ;
          const px = s.x * k + cx;
          const py = (s.y - cameraPitch * 0.8) * k + cy;
          const ppx = s.x * pk + cx;
          const ppy = (s.y - cameraPitch * 0.8) * pk + cy;

          if (px >= 0 && px <= width && py >= 0 && py <= height) {
            const alpha = Math.min(1, (1 - curZ / 2400) * 1.4) * starFade;
            ctx.strokeStyle = `rgba(225, 238, 255, ${alpha.toFixed(3)})`;
            ctx.lineWidth = s.size;
            ctx.beginPath();
            ctx.moveTo(ppx, ppy);
            ctx.lineTo(px, py);
            ctx.stroke();
          }
        }
      }

      // 3. Crescent Moon (Positioned lower-left on horizon, zooms past left peripheral)
      if (moonImg.complete && moonImg.naturalWidth > 0 && elapsed < HOLD_SECS + 2.8) {
        const moonProgress = elapsed <= HOLD_SECS ? 0 : Math.min(1.0, (elapsed - HOLD_SECS) / 2.2);
        const moonX = width * 0.15 - (moonProgress ** 1.6) * width * 0.42;
        const moonY = height * 0.44 - (moonProgress ** 1.6) * height * 0.48;
        const moonScale = 0.42 + (moonProgress ** 2.0) * 1.8;
        const moonAlpha = Math.max(0, 1.0 - (moonProgress ** 2.8) * 1.5);

        if (moonAlpha > 0.01) {
          ctx.save();
          ctx.globalAlpha = moonAlpha;
          const mw = 380 * moonScale;
          const mh = 380 * moonScale;

          const moonGlow = ctx.createRadialGradient(moonX, moonY, mw * 0.1, moonX, moonY, mw * 0.85);
          moonGlow.addColorStop(0, "rgba(255, 248, 220, 0.20)");
          moonGlow.addColorStop(0.4, "rgba(240, 230, 190, 0.07)");
          moonGlow.addColorStop(1, "rgba(200, 220, 255, 0)");
          ctx.fillStyle = moonGlow;
          ctx.beginPath();
          ctx.arc(moonX, moonY, mw * 0.85, 0, Math.PI * 2);
          ctx.fill();

          ctx.drawImage(moonImg, moonX - mw / 2, moonY - mh / 2, mw, mh);
          ctx.restore();
        }
      }

      // 4. Distant Horizon Cloud Sea
      if (horizonCloudsImg.complete && horizonCloudsImg.naturalWidth > 0 && elapsed < HOLD_SECS + 3.0) {
        const horizProgress = elapsed <= HOLD_SECS ? 0 : (elapsed - HOLD_SECS);
        const horizAlpha = Math.max(0, 1.0 - (horizProgress / 2.6) ** 2.0);
        if (horizAlpha > 0.01) {
          ctx.save();
          ctx.globalAlpha = horizAlpha * 0.82;
          const hw = width * 1.5;
          const hh = height * 0.58;
          const hx = (width - hw) / 2;
          const hy = height * 0.46 - cameraPitch * 0.45;
          ctx.drawImage(horizonCloudsImg, hx, hy, hw, hh);
          ctx.restore();
        }
      }

      // 5. 3D Volumetric Clouds (Flying directly THROUGH them!)
      if (cloudDensity > 0.01) {
        const projected = [];
        for (let i = 0; i < numClouds; i++) {
          const c = clouds[i];
          const cloudOffset = elapsed < HOLD_SECS ? elapsed * 80 : (HOLD_SECS * 80 + (elapsed - HOLD_SECS) * 750);
          const curZ = ((c.initialZ - cloudOffset) % 2500 + 2500) % 2500 + 30;
          projected.push({ ...c, curZ });
        }
        projected.sort((a, b) => b.curZ - a.curZ);

        for (let i = 0; i < numClouds; i++) {
          const c = projected[i];
          const k = fov / Math.max(c.curZ, 25);
          const px = c.x * k + cx;
          const py = (c.y - cameraPitch) * k + cy;
          const rad = 320 * c.scale * k * 0.42;

          if (px + rad > -120 && px - rad < width + 120 && py + rad > -120 && py - rad < height + 120) {
            let pAlpha = c.alpha * cloudDensity;
            if (c.curZ > 1500) {
              pAlpha *= (2500 - c.curZ) / 1000;
            } else if (c.curZ < 280) {
              pAlpha *= (c.curZ - 30) / 250;
            }
            pAlpha = Math.max(0, Math.min(0.85, pAlpha));

            if (pAlpha > 0.01 && rad > 5) {
              ctx.save();
              ctx.globalAlpha = pAlpha;
              ctx.translate(px, py);
              ctx.rotate(c.rot);
              ctx.drawImage(c.sprite, -rad, -rad, rad * 2, rad * 2);
              ctx.restore();
            }
          }
        }

        // 6. Condensation Streamers
        if (speed > 35 && cloudDensity > 0.3) {
          ctx.lineCap = "round";
          for (let i = 0; i < numStreamers; i++) {
            const s = streamers[i];
            const streamOffset = elapsed < HOLD_SECS ? 0 : (elapsed - HOLD_SECS) * 1200;
            const curZ = ((s.initialZ - streamOffset) % 1800 + 1800) % 1800 + 20;
            const prevZ = curZ + speed * 1.6;

            const k = fov / curZ;
            const pk = fov / prevZ;
            const px = s.x * k + cx;
            const py = (s.y - cameraPitch * 0.6) * k + cy;
            const ppx = s.x * pk + cx;
            const ppy = (s.y - cameraPitch * 0.6) * pk + cy;

            if (px >= -50 && px <= width + 50 && py >= -50 && py <= height + 50) {
              const alpha = Math.min(0.72, (1 - curZ / 1800) * s.alpha * cloudDensity);
              if (alpha > 0.02) {
                ctx.strokeStyle = `rgba(220, 238, 255, ${alpha.toFixed(3)})`;
                ctx.lineWidth = Math.max(0.8, s.width * k * 0.85);
                ctx.beginPath();
                ctx.moveTo(ppx, ppy);
                ctx.lineTo(px, py);
                ctx.stroke();
              }
            }
          }
        }

        // 7. Dynamic Volumetric Mist Fog Blanket
        if (cloudDensity > 0.35) {
          const fogAlpha = ((cloudDensity - 0.35) / 0.65) * 0.44;
          const fogGrad = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(width, height) * 0.85);
          fogGrad.addColorStop(0, `rgba(210, 228, 250, ${(fogAlpha * 0.75).toFixed(3)})`);
          fogGrad.addColorStop(0.55, `rgba(145, 180, 220, ${(fogAlpha * 0.42).toFixed(3)})`);
          fogGrad.addColorStop(1.0, `rgba(40, 65, 105, ${fogAlpha.toFixed(3)})`);
          ctx.fillStyle = fogGrad;
          ctx.fillRect(0, 0, width, height);
        }
      }

      // 8. Total Obsidian Void Transition
      if (voidDarkness > 0.01) {
        ctx.fillStyle = `rgba(0, 0, 0, ${voidDarkness.toFixed(3)})`;
        ctx.fillRect(0, 0, width, height);
      }

      if (hud) {
        hud.style.opacity = elapsed >= (HOLD_SECS + 3.6) ? "0" : "1";
      }
    }

    function renderLoop(now) {
      if (!isRunning) return;
      const elapsed = (now - startTime) / 1000;
      drawFlightFrame(elapsed, now);
      animLoopId = requestAnimationFrame(renderLoop);
    }
    animLoopId = requestAnimationFrame(renderLoop);

    return {
      stop: () => {
        isRunning = false;
        if (animLoopId) cancelAnimationFrame(animLoopId);
        window.removeEventListener("resize", onResize);
        if (hud) {
          hud.style.opacity = "0";
          hud.style.display = "none";
        }
      },
      renderAtSeconds: (s) => {
        drawFlightFrame(s, s * 1000);
      },
      freezeAtSeconds: (s) => {
        isRunning = false;
        if (animLoopId) cancelAnimationFrame(animLoopId);
        if (cinematicFlightTimer) {
          clearTimeout(cinematicFlightTimer);
          cinematicFlightTimer = null;
        }
        if (cinematicRevealTimer) {
          clearTimeout(cinematicRevealTimer);
          cinematicRevealTimer = null;
        }
        const d = $("cinema-content-deck");
        if (d) d.classList.remove("deck-active");
        const st = $("cinema-stage");
        if (st) st.classList.remove("flight-done");
        drawFlightFrame(s, s * 1000);
      }
    };
  }

  let cinematicTelemetryTimers = [];

  window.openStarterScreen = openStarterScreen;

  function openStarterScreen(setupStatus, forcePlay = false) {
    const starterScreen = $("starter-screen");
    const setupScreen = $("setup-screen");
    const loginScreen = $("login-screen");
    const forbiddenScreen = $("forbidden-screen");
    const appRoot = $("app-root");
    const stage = $("cinema-stage");
    const deck = $("cinema-content-deck");
    const nameInp = $("starter-name");

    const hudStatus = $("hud-status-text");
    const hudCoord = $("hud-coord-text");
    const hudTagline = $("hud-tagline-text");

    if (setupScreen) setupScreen.style.display = "none";
    if (loginScreen) loginScreen.style.display = "none";
    if (forbiddenScreen) forbiddenScreen.style.display = "none";
    if (appRoot) appRoot.style.display = "none";

    if (!starterScreen) return;
    starterScreen.style.display = "flex";

    // Pre-populate name if available
    if (setupStatus && setupStatus.user_name && nameInp && !nameInp.value) {
      nameInp.value = setupStatus.user_name;
    } else if (nameInp && !nameInp.value) {
      nameInp.value = "";
    }

    // Reset step states
    showCinemaStep("name");

    // Clear prior timers and active animations
    if (cinematicFlightTimer) {
      clearTimeout(cinematicFlightTimer);
      cinematicFlightTimer = null;
    }
    if (cinematicRevealTimer) {
      clearTimeout(cinematicRevealTimer);
      cinematicRevealTimer = null;
    }
    if (window._activeFlightEngineInstance) {
      window._activeFlightEngineInstance.stop();
      window._activeFlightEngineInstance = null;
    }
    if (window._activeStarfieldInstance) {
      window._activeStarfieldInstance.stop();
      window._activeStarfieldInstance = null;
    }
    cinematicTelemetryTimers.forEach(t => clearTimeout(t));
    cinematicTelemetryTimers = [];

    // Reset visuals for playback - force CSS keyframes to restart from 0s
    if (stage) {
      stage.classList.remove("is-flying", "flight-done");
      void stage.offsetWidth; // Force reflow
      stage.classList.add("is-flying");
    }
    const voidCurtain = $("cinema-void-curtain");
    if (voidCurtain) {
      voidCurtain.style.transition = "none";
      voidCurtain.style.opacity = "0";
      void voidCurtain.offsetWidth;
      voidCurtain.style.transition = "";
    }
    if (deck) {
      deck.classList.remove("deck-active");
    }
    const hud = $("cinema-flight-hud");
    if (hud) {
      hud.style.display = "flex";
      hud.style.opacity = "1";
    }

    // Initial Telemetry text — Sleek, chill, confident
    if (hudStatus) hudStatus.textContent = "ORBITAL CRUISE // ZENITH ACTIVE";
    if (hudCoord) hudCoord.textContent = "ALT 38,000 FT // SPEED 320 KTS";
    const currentGen = ++flightGeneration;
    let flightEnded = false;
    const endFlightAndReveal = () => {
      if (currentGen !== flightGeneration || flightEnded) return;
      flightEnded = true;
      if (cinematicFlightTimer) {
        clearTimeout(cinematicFlightTimer);
        cinematicFlightTimer = null;
      }
      if (cinematicRevealTimer) {
        clearTimeout(cinematicRevealTimer);
        cinematicRevealTimer = null;
      }
      cinematicTelemetryTimers.forEach(t => clearTimeout(t));
      cinematicTelemetryTimers = [];
      if (window._activeFlightEngineInstance) {
        window._activeFlightEngineInstance.stop();
        window._activeFlightEngineInstance = null;
      }

      // Audio impact into void
      CinemaAudio.playVoidDrop();

      // Everything goes dark, then AI core reveals with liquid glass shader background
      if (stage) stage.classList.add("flight-done");
      if (hud) {
        hud.style.opacity = "0";
        hud.style.display = "none";
      }

      // Activate real-time Liquid Glass WebGL shader
      if (window.ZenithLiquidShader) {
        window.ZenithLiquidShader.start();
      }
      const shaderCanvas = $("cinema-liquid-shader");
      if (shaderCanvas) shaderCanvas.classList.add("is-visible");

      const doReveal = () => {
        if (deck) deck.classList.add("deck-active");
        CinemaAudio.playCoreAwaken();
        speakZenithDialogue("What should I call you?");
        if (nameInp) {
          nameInp.focus();
          nameInp.select();
        }
      };

      if (!forcePlay) {
        doReveal();
      } else {
        cinematicRevealTimer = setTimeout(doReveal, 450);
      }
    };

    if (!forcePlay) {
      endFlightAndReveal();
      return;
    }

    // Start Cinematic Audio
    CinemaAudio.startFlightAudio();

    // Track launch timestamp
    window._zenithFlightStartedAt = performance.now();

    // Launch Volumetric 3D Cloud Flight Engine
    const flightEngine = initCinematicFlightEngine({
      onComplete: () => endFlightAndReveal()
    });
    window._activeFlightEngineInstance = flightEngine;

    // Safety fallback timeout in case requestAnimationFrame is inactive
    cinematicFlightTimer = setTimeout(endFlightAndReveal, 11000);

    // Skip flight handler
    const skipBtn = $("cinema-skip-btn");
    if (skipBtn) {
      skipBtn.onclick = (e) => {
        e.preventDefault();
        endFlightAndReveal();
      };
    }
  }

  function showCinemaStep(stepKey) {
    const steps = {
      name: $("cinema-step-name"),
      compliment: $("cinema-step-compliment"),
      profile: $("cinema-step-profile"),
      key: $("cinema-step-key"),
      welcome: $("cinema-step-welcome"),
    };

    Object.entries(steps).forEach(([k, el]) => {
      if (!el) return;
      if (k === stepKey) {
        el.style.display = "block";
        el.classList.add("is-active");
      } else {
        el.style.display = "none";
        el.classList.remove("is-active");
      }
    });

    const orb = $("cinema-core-orb");
    if (orb) {
      if (stepKey === "welcome") {
        orb.style.boxShadow = "0 4px 20px rgba(0, 0, 0, 0.9), 0 0 0 1px rgba(255, 255, 255, 0.2)";
      } else {
        orb.style.boxShadow = "";
      }
    }
  }

  function sendInitialSetupGreeting(userName) {
    hideWelcome();
    const greetHtml = `
      <p>Hello, <strong>${esc(userName)}</strong>! I'm Zenith, your personal companion and command engine. ✨</p>
      <p>I'm currently in <strong>🌱 Setup Mode</strong> — my primary goal is to help you set up more stuff (keys, secrets, tools, and integrations) so everything works seamlessly for you.</p>
      <div style="margin: 10px 0; padding: 12px 14px; background: var(--panel-2); border-left: 3px solid #10b981; border-radius: 6px; font-size: 13px; line-height: 1.5;">
        <strong>Here are things we can set up together:</strong>
        <ul style="margin: 6px 0 0 18px; padding: 0;">
          <li><strong>API Keys &amp; Secrets:</strong> Ask me <em>"What can I set up?"</em> to see all available integrations (Resend/Gmail for emailing files, GitHub token for PRs &amp; code reviews, Groq Whisper for instant voice, Home Assistant for smart home, Google Maps).</li>
          <li><strong>Save keys directly:</strong> You can paste any key right here in chat and I'll save and activate it for you!</li>
          <li><strong>Live UI Customization:</strong> Say <em>"Make your accent emerald"</em> or <em>"Switch to dark cyan theme"</em> and I'll edit my interface live.</li>
        </ul>
      </div>
      <p style="color: var(--sub); font-size: 12.5px;">
        💡 <em>Whenever you're ready or if you don't want to set up anything right now, just say "Skip setup" or "Switch to sovereign mode" (or change mode in Settings ⚙️) and we'll dive straight into autonomous work!</em>
      </p>
    `;
    addBubble("assistant", greetHtml);
  }

  function wireStarterScreen() {
    const starterScreen = $("starter-screen");
    if (!starterScreen) return;

    const nameInp = $("starter-name");
    const nameSubmitBtn = $("cinema-name-submit-btn");
    const complimentText = $("cinema-compliment-text");
    const complimentSub = $("cinema-compliment-sub");

    const bdayInp = $("starter-birthday");
    const hobbiesInp = $("starter-hobbies");
    const bioInp = $("starter-bio");
    const profileHeading = $("cinema-profile-heading");
    const profileSubmitBtn = $("cinema-profile-submit-btn");
    const profileSkipBtn = $("cinema-profile-skip-btn");

    const keyInp = $("starter-gemini-key");
    const toggleBtn = $("starter-key-toggle-btn");
    const pasteKeyBtn = $("cinema-paste-key-btn");
    const testBtn = $("starter-test-key-btn");
    const statusEl = $("starter-key-status");
    const spinner = $("starter-test-spinner");
    const testBtnText = $("starter-test-btn-text");
    const launchBtn = $("starter-launch-btn");
    const launchSpinner = $("starter-launch-spinner");
    const launchText = $("starter-launch-btn-text");

    const welcomeText = $("cinema-welcome-text");
    const optSettings = $("cinema-opt-settings");
    const optOperations = $("cinema-opt-operations");
    const btnStartOps = $("cinema-btn-start-ops");

    const soundBtn = $("cinema-sound-btn");
    const soundIconOn = $("cinema-sound-icon-on");
    const soundIconOff = $("cinema-sound-icon-off");
    const soundLabel = $("cinema-sound-label");

    if (soundBtn) {
      soundBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        const muted = CinemaAudio.toggleMute();
        if (soundIconOn) soundIconOn.style.display = muted ? "none" : "inline-block";
        if (soundIconOff) soundIconOff.style.display = muted ? "inline-block" : "none";
        if (soundLabel) soundLabel.textContent = muted ? "Muted" : "Audio FX";
        soundBtn.classList.toggle("is-muted", muted);
        if (!muted) {
          CinemaAudio.playBlip();
        }
      };
    }

    // Ensure audio context unlocks on first user touch / click
    starterScreen.addEventListener("pointerdown", () => {
      CinemaAudio.getAudioContext();
    }, { passive: true });

    // ── Step 1: Name Submission ───────────────────────────────────────────────
    let complimentAutoTimer = null;

    const advanceToCompliment = () => {
      const nameVal = nameInp ? nameInp.value.trim() : "";
      currentOnboardingName = nameVal || "Friend";

      const comp = generateNameCompliment(currentOnboardingName);
      if (complimentText) complimentText.innerHTML = comp.quote;
      if (complimentSub) complimentSub.textContent = comp.sub;

      showCinemaStep("compliment");
      CinemaAudio.playPraiseChime();
      speakZenithDialogue(comp.quote);

      // Auto-advance to Profile step after 2.7 seconds
      if (complimentAutoTimer) clearTimeout(complimentAutoTimer);
      complimentAutoTimer = setTimeout(() => {
        advanceToProfile();
      }, 2700);
    };

    if (nameSubmitBtn) {
      nameSubmitBtn.addEventListener("click", advanceToCompliment);
    }
    if (nameInp) {
      nameInp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          advanceToCompliment();
        }
      });
    }

    // ── Step 2: Name Compliment Beat -> Profile Entry ─────────────────────────
    const advanceToProfile = () => {
      if (complimentAutoTimer) clearTimeout(complimentAutoTimer);
      if (profileHeading && currentOnboardingName) {
        profileHeading.textContent = `Tell me a little about yourself, ${currentOnboardingName}`;
      }
      showCinemaStep("profile");
      CinemaAudio.playBlip();
      speakZenithDialogue(`Tell me a little about yourself, ${currentOnboardingName}, or skip to continue.`);
      if (bdayInp) {
        setTimeout(() => bdayInp.focus(), 150);
      }
    };

    const handleProfileContinue = () => {
      const bday = bdayInp ? bdayInp.value.trim() : "";
      const hobbies = hobbiesInp ? hobbiesInp.value.trim() : "";
      const bio = bioInp ? bioInp.value.trim() : "";
      window._onboardingProfile = {
        birthday: bday,
        hobbies: hobbies,
        bio: bio,
      };
      advanceToKey();
    };

    const handleProfileSkip = () => {
      window._onboardingProfile = {
        birthday: "",
        hobbies: "",
        bio: "",
      };
      advanceToKey();
    };

    if (profileSubmitBtn) {
      profileSubmitBtn.addEventListener("click", handleProfileContinue);
    }
    if (profileSkipBtn) {
      profileSkipBtn.addEventListener("click", handleProfileSkip);
    }

    // ── Step 3: Profile -> Gemini Key Entry ──────────────────────────────────
    const advanceToKey = () => {
      if (complimentAutoTimer) clearTimeout(complimentAutoTimer);
      showCinemaStep("key");
      CinemaAudio.playBlip();
      speakZenithDialogue("Connect your Gemini API Key to get started.");
      if (keyInp) {
        setTimeout(() => keyInp.focus(), 150);
      }
    };

    // ── Step 3: Key Utilities (Toggle & Paste) ─────────────────────────────────
    if (toggleBtn && keyInp) {
      toggleBtn.addEventListener("click", () => {
        const isPass = keyInp.type === "password";
        keyInp.type = isPass ? "text" : "password";
        toggleBtn.style.color = isPass ? "#ffffff" : "#71717a";
        CinemaAudio.playBlip();
      });
    }

    if (pasteKeyBtn && keyInp) {
      pasteKeyBtn.addEventListener("click", async () => {
        try {
          const text = await navigator.clipboard.readText();
          if (text) {
            keyInp.value = text.trim();
            showToast("📋", "Key pasted from clipboard");
            CinemaAudio.playBlip();
          }
        } catch (e) {
          keyInp.focus();
        }
      });
    }

    // ── Key Testing Link ──────────────────────────────────────────────────────
    async function testCurrentKey() {
      const key = keyInp ? keyInp.value.trim() : "";
      if (!key) {
        if (statusEl) {
          statusEl.className = "starter-key-status error";
          statusEl.textContent = "Please enter your Gemini API key before testing.";
          statusEl.style.display = "block";
        }
        return false;
      }

      CinemaAudio.playBlip();
      if (spinner) spinner.style.display = "inline-block";
      if (testBtnText) testBtnText.textContent = "Testing...";
      if (testBtn) testBtn.disabled = true;
      if (statusEl) statusEl.style.display = "none";

      try {
        const resp = await fetch("/api/setup/test-key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gemini_api_key: key }),
        });
        const result = await resp.json();
        if (result.valid || result.ok) {
          if (statusEl) {
            statusEl.className = "starter-key-status success";
            statusEl.textContent = `✓ ${result.message || "Key verified successfully!"}`;
            statusEl.style.display = "block";
          }
          CinemaAudio.playPraiseChime();
          return true;
        } else {
          if (statusEl) {
            statusEl.className = "starter-key-status error";
            statusEl.textContent = `✕ ${result.error || "Key test failed. Check key & try again."}`;
            statusEl.style.display = "block";
          }
          return false;
        }
      } catch (e) {
        if (statusEl) {
          statusEl.className = "starter-key-status error";
          statusEl.textContent = `✕ Network error testing key: ${e.message}`;
          statusEl.style.display = "block";
        }
        return false;
      } finally {
        if (spinner) spinner.style.display = "none";
        if (testBtnText) testBtnText.textContent = "Test Key";
        if (testBtn) testBtn.disabled = false;
      }
    }

    if (testBtn) {
      testBtn.addEventListener("click", testCurrentKey);
    }

    // ── Save Key & Proceed ───────────────────────────────────────────────────
    async function handleAwakenEngine() {
      const key = keyInp ? keyInp.value.trim() : "";
      const name = currentOnboardingName || (nameInp ? nameInp.value.trim() : "Friend");

      if (!key) {
        if (statusEl) {
          statusEl.className = "starter-key-status error";
          statusEl.textContent = "Google Gemini API Key is required to continue.";
          statusEl.style.display = "block";
        }
        if (keyInp) keyInp.focus();
        return;
      }

      CinemaAudio.playBlip();
      if (launchSpinner) launchSpinner.style.display = "inline-block";
      if (launchText) launchText.textContent = "Verifying...";
      if (launchBtn) launchBtn.disabled = true;

      try {
        // Step A: Test Key directly first
        const testResp = await fetch("/api/setup/test-key", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gemini_api_key: key }),
        });
        const testRes = await testResp.json();
        if (!testRes.valid && !testRes.ok) {
          throw new Error(testRes.error || "Key verification failed with Google AI Studio.");
        }

        // Step B: Save Configuration
        if (launchText) launchText.textContent = "Saving...";
        const profile = window._onboardingProfile || {};
        const updates = {
          GEMINI_API_KEY: key,
          ZENITH_MODE: "setup",
        };
        if (name) {
          updates.USER_NAME = name;
        }
        if (profile.birthday) {
          updates.USER_BIRTHDAY = profile.birthday;
        }
        if (profile.hobbies) {
          updates.USER_HOBBIES = profile.hobbies;
        }
        if (profile.bio) {
          updates.USER_BIO = profile.bio;
        }

        const resp = await fetch("/api/setup/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ updates }),
        });

        if (!resp.ok) {
          const err = await resp.json();
          throw new Error(err.error || "Failed to save configuration");
        }

        if (name) {
          updateDisplayedUserName(name);
        }

        // Step C: Summarize profile & store in Zenith's long-term memory
        if (launchText) launchText.textContent = "Remembering profile...";
        try {
          await fetch("/api/setup/summarize-profile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: name,
              birthday: profile.birthday || "",
              hobbies: profile.hobbies || "",
              bio: profile.bio || "",
            }),
          });
        } catch (sumErr) {
          console.warn("Profile summarization notice:", sumErr);
        }

        // Step D: Advance to Step 4 (Welcome & Two Options)
        if (welcomeText) {
          welcomeText.textContent = `You're all set, ${name}.`;
        }
        showCinemaStep("welcome");
        CinemaAudio.playIgniteSurge();
        speakZenithDialogue(`You're all set, ${name}. Ready when you are.`);

      } catch (e) {
        if (statusEl) {
          statusEl.className = "starter-key-status error";
          statusEl.textContent = `✕ ${e.message}`;
          statusEl.style.display = "block";
        }
      } finally {
        if (launchSpinner) launchSpinner.style.display = "none";
        if (launchText) launchText.textContent = "Save & Continue";
        if (launchBtn) launchBtn.disabled = false;
      }
    }

    if (launchBtn) {
      launchBtn.addEventListener("click", handleAwakenEngine);
    }
    if (keyInp) {
      keyInp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          handleAwakenEngine();
        }
      });
    }

    // ── Step 4 Option 1: Set Up Other Stuff ───────────────────────────────────
    const handleOpenSettings = () => {
      CinemaAudio.playBlip();
      CinemaAudio.stopAll();
      starterScreen.style.display = "none";
      openSetupWizard({ isFirstTime: true });
      showToast("🌱", "Opened Configuration Studio");
    };

    if (optSettings) {
      optSettings.addEventListener("click", handleOpenSettings);
    }

    // ── Step 4 Option 2: Start Operations ─────────────────────────────────────
    const handleStartOperations = () => {
      const name = currentOnboardingName || (nameInp ? nameInp.value.trim() : "Friend");
      CinemaAudio.playBlip();
      CinemaAudio.stopAll();
      starterScreen.style.display = "none";
      showApp();
      startApp();

      showToast("⚡", "Zenith Command Console Active!");
      setTimeout(() => {
        sendInitialSetupGreeting(name);
      }, 600);
    };

    if (optOperations) {
      optOperations.addEventListener("click", handleStartOperations);
    }
    if (btnStartOps) {
      btnStartOps.addEventListener("click", (e) => {
        e.stopPropagation();
        handleStartOperations();
      });
    }

    // Global expose for replaying intro anytime
    window.replayZenithIntro = () => {
      openStarterScreen({ user_name: window._zenithUserName || currentOnboardingName || "Friend" }, true);
    };
    window.showCinemaStep = showCinemaStep;
  }

  /* ══════════════════════════════════════════════════════════════════════════════
     ZENITH — Setup Wizard & Secrets Manager (General Use)
     ══════════════════════════════════════════════════════════════════════════════ */
  let catalogData = null;
  let setupActiveTab = "brain";
  let setupIsFirstTime = false;

  async function initSetupStatus() {
    try {
      const resp = await fetch("/api/setup/status");
      if (!resp.ok) return null;
      const data = await resp.json();
      if (data && data.user_name) {
        window._zenithUserName = data.user_name;
        const wlcmName = $("wlcm-name");
        if (wlcmName) wlcmName.textContent = `, ${data.user_name}`;
      }
      return data;
    } catch (e) {
      console.warn("[zenith] Failed to check setup status:", e);
      return null;
    }
  }

  function wireSetupWizard() {
    // Wire Settings button in header
    const settingsBtn = $("settings-btn");
    if (settingsBtn) {
      settingsBtn.addEventListener("click", () => {
        openSetupWizard({ isFirstTime: false });
      });
    }

    // Wire dropdown item
    const hdrSettingsLink = $("hdr-settings-link");
    if (hdrSettingsLink) {
      hdrSettingsLink.addEventListener("click", () => {
        const drop = $("hdr-user-dropdown");
        if (drop) drop.style.display = "none";
        openSetupWizard({ isFirstTime: false });
      });
    }

    // Wire Close button
    const closeBtn = $("setup-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        closeSetupWizard();
      });
    }

    // Wire Replay Intro button
    const replayIntroBtn = $("setup-replay-intro-btn");
    if (replayIntroBtn) {
      replayIntroBtn.addEventListener("click", () => {
        closeSetupWizard();
        openStarterScreen({ user_name: window._zenithUserName || "Friend" }, true);
      });
    }

    // Wire Sidebar Navigation
    const tabsBar = $("setup-tabs-bar");
    if (tabsBar) {
      tabsBar.addEventListener("click", (e) => {
        const btn = e.target.closest(".setup-nav-item");
        if (!btn) return;
        const tab = btn.getAttribute("data-tab");
        if (!tab) return;
        switchSetupTab(tab);
      });
    }

    // Wire Save button
    const saveBtn = $("setup-save-btn");
    if (saveBtn) {
      saveBtn.addEventListener("click", handleSaveSetup);
    }

    // Keyboard shortcuts: Cmd/Ctrl + Enter to save, Escape to close (if not first-time)
    document.addEventListener("keydown", (e) => {
      const setupScreen = $("setup-screen");
      if (!setupScreen || setupScreen.style.display === "none") return;

      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        handleSaveSetup();
      } else if (e.key === "Escape" && !setupIsFirstTime) {
        e.preventDefault();
        closeSetupWizard();
      }
    });
  }

  const SETUP_ICONS = {
    brain: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 4.44-2.04z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-4.44-2.04z"/></svg>`,
    profile: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
    voice: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>`,
    email: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>`,
    maps_calendar: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21"/><line x1="9" y1="3" x2="9" y2="18"/><line x1="15" y1="6" x2="15" y2="21"/></svg>`,
    cloud: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/></svg>`,
    smart_home: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
    security: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
    art_design: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/><circle cx="7.5" cy="11.5" r="1.5" fill="currentColor"/><circle cx="10.5" cy="7.5" r="1.5" fill="currentColor"/><circle cx="14.5" cy="7.5" r="1.5" fill="currentColor"/><circle cx="17.5" cy="11.5" r="1.5" fill="currentColor"/></svg>`,
  };

  const SETUP_CATEGORIES = [
    { id: "brain", name: "AI Brain", icon: SETUP_ICONS.brain, eyebrow: "Core Intelligence", desc: "Powers reasoning, conversation, tool execution, and fallback LLM routing." },
    { id: "profile", name: "User Profile", icon: SETUP_ICONS.profile, eyebrow: "Identity & Memory", desc: "Your name, timezone, email, and personal background context for memory." },
    { id: "voice", name: "Voice & Speech", icon: SETUP_ICONS.voice, eyebrow: "Realtime Audio", desc: "Live voice streaming, Groq Whisper STT, and natural neural TTS voices." },
    { id: "email", name: "Email", icon: SETUP_ICONS.email, eyebrow: "Messaging & Digests", desc: "Resend, SMTP, and Gmail credentials for proactive morning & evening digests." },
    { id: "maps_calendar", name: "Maps & Calendar", icon: SETUP_ICONS.maps_calendar, eyebrow: "Location & Schedule", desc: "Interactive Google Maps embeds, route directions, and Google Calendar sync." },
    { id: "art_design", name: "Art & Design", icon: SETUP_ICONS.art_design, eyebrow: "Design Integrations", desc: "Connect Figma and Canva for AI-powered design creation, asset export, and file inspection." },
    { id: "cloud", name: "Cloud & GitHub", icon: SETUP_ICONS.cloud, eyebrow: "Developer Tools", desc: "GitHub account, Personal Access Tokens, Cloudflare DNS, and Vercel tools." },
    { id: "smart_home", name: "Smart Home", icon: SETUP_ICONS.smart_home, eyebrow: "Homelab Operations", desc: "Home Assistant REST integration, media player control, and Jellyfin keys." },
    { id: "security", name: "Security", icon: SETUP_ICONS.security, eyebrow: "Access & Safety", desc: "Shell execution safeguards, Docker control flags, and authentication mode." },
  ];

  function switchSetupTab(tabId) {
    setupActiveTab = tabId;

    // Update sidebar nav active item
    document.querySelectorAll(".setup-nav-item").forEach((btn) => {
      if (btn.getAttribute("data-tab") === tabId) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    // Update main panels
    document.querySelectorAll(".setup-category-panel").forEach((panel) => {
      if (panel.getAttribute("data-category") === tabId) {
        panel.classList.add("active");
      } else {
        panel.classList.remove("active");
      }
    });

    // Update right panel header metadata
    const catMeta = SETUP_CATEGORIES.find((c) => c.id === tabId);
    if (catMeta) {
      const eyebrow = $("setup-cat-eyebrow");
      const title = $("setup-cat-title");
      const desc = $("setup-cat-desc");
      if (eyebrow) eyebrow.textContent = catMeta.eyebrow || "Category";
      if (title) title.innerHTML = `<span class="setup-cat-title-icon">${catMeta.icon}</span> <span>${esc(catMeta.name)}</span>`;
      if (desc) desc.textContent = catMeta.desc || "";
    }
  }

  function updateReadinessIndicator() {
    const geminiInp = document.querySelector('input[data-key="GEMINI_API_KEY"]');
    const geminiVal = geminiInp ? geminiInp.value.trim() : "";
    const catalogItem = catalogData ? catalogData.find((c) => c.key === "GEMINI_API_KEY") : null;
    const isConfigured = Boolean(geminiVal || (catalogItem && catalogItem.is_set));

    const pctEl = $("setup-readiness-pct");
    const fillEl = $("setup-progress-fill");
    const hintEl = $("setup-readiness-hint");
    const dotEl = $("setup-status-dot");
    const statusText = $("setup-status-text");

    if (isConfigured) {
      if (pctEl) { pctEl.textContent = "✓ Ready"; pctEl.classList.add("ready"); }
      if (fillEl) { fillEl.style.width = "100%"; fillEl.classList.add("ready"); }
      if (hintEl) hintEl.textContent = "Gemini key set · Ready to launch";
      if (dotEl) dotEl.classList.add("ready");
      if (statusText && setupIsFirstTime) statusText.textContent = "✓ Ready to save configuration and launch Zenith";
    } else {
      if (pctEl) { pctEl.textContent = "1 Required"; pctEl.classList.remove("ready"); }
      if (fillEl) { fillEl.style.width = "25%"; fillEl.classList.remove("ready"); }
      if (hintEl) hintEl.textContent = "Google Gemini API Key required";
      if (dotEl) dotEl.classList.remove("ready");
      if (statusText && setupIsFirstTime) statusText.textContent = "Fill in your Gemini API key to activate";
    }
  }

  async function openSetupWizard({ isFirstTime = false } = {}) {
    setupIsFirstTime = isFirstTime;
    const setupScreen = $("setup-screen");
    const loginScreen = $("login-screen");
    const forbiddenScreen = $("forbidden-screen");
    const appRoot = $("app-root");
    const closeBtn = $("setup-close-btn");
    const skipBtn = $("setup-skip-btn");
    const titleEl = $("setup-title");
    const saveBtnText = $("setup-save-btn-text");
    const statusText = $("setup-status-text");

    if (isFirstTime) {
      if (loginScreen) loginScreen.style.display = "none";
      if (forbiddenScreen) forbiddenScreen.style.display = "none";
      if (appRoot) appRoot.style.display = "none";
      if (closeBtn) {
        closeBtn.style.display = "flex";
        closeBtn.onclick = () => {
          closeSetupWizard();
          const s = $("starter-screen");
          if (s) s.style.display = "flex";
        };
      }
      if (skipBtn) {
        skipBtn.style.display = "inline-flex";
        skipBtn.textContent = "← Back to Quick Setup";
        skipBtn.onclick = () => {
          closeSetupWizard();
          const s = $("starter-screen");
          if (s) s.style.display = "flex";
        };
      }
      if (titleEl) titleEl.textContent = "Settings Studio";
      if (saveBtnText) saveBtnText.textContent = "Save & Launch Zenith";
      if (statusText) statusText.textContent = "Enter your Gemini API key to activate";
    } else {
      if (closeBtn) {
        closeBtn.style.display = "flex";
        closeBtn.onclick = closeSetupWizard;
      }
      if (skipBtn) {
        skipBtn.style.display = "inline-flex";
        skipBtn.textContent = "Close";
        skipBtn.onclick = closeSetupWizard;
      }
      if (titleEl) titleEl.textContent = "Settings & Secrets";
      if (saveBtnText) saveBtnText.textContent = "Save Changes";
      if (statusText) statusText.textContent = "Changes will be saved to .env and reloaded";
    }

    if (setupScreen) setupScreen.style.display = "flex";
    await loadSetupCatalog();
  }

  function closeSetupWizard() {
    const setupScreen = $("setup-screen");
    if (setupScreen) setupScreen.style.display = "none";
  }

  async function loadSetupCatalog() {
    const panelsContainer = $("setup-category-panels");
    if (!panelsContainer) return;

    try {
      const resp = await fetch("/api/setup/config");
      if (!resp.ok) {
        panelsContainer.innerHTML = `<div class="setup-test-result error">Failed to load configuration catalog.</div>`;
        return;
      }
      const data = await resp.json();
      catalogData = data.catalog || [];
      renderSetupCatalog(catalogData);
      updateReadinessIndicator();
    } catch (err) {
      console.error("[zenith] Error loading setup catalog:", err);
      panelsContainer.innerHTML = `<div class="setup-test-result error">Error loading setup: ${esc(err.message)}</div>`;
    }
  }

  function renderSetupCatalog(catalog) {
    const panelsContainer = $("setup-category-panels");
    const tabsBar = $("setup-tabs-bar");
    if (!panelsContainer || !tabsBar) return;

    // 1. Render Left Sidebar Navigation List
    let navHtml = "";
    SETUP_CATEGORIES.forEach((cat) => {
      const items = catalog.filter((c) => c.category === cat.id);
      const configuredCount = items.filter((c) => c.is_set).length;
      const hasRequired = items.some((c) => c.required);
      const isActive = cat.id === setupActiveTab;

      let pillHtml = "";
      if (hasRequired) {
        const reqItem = items.find((c) => c.required);
        if (reqItem && reqItem.is_set) {
          pillHtml = `<span class="setup-nav-pill ok">✓ Ready</span>`;
        } else {
          pillHtml = `<span class="setup-nav-pill req">1 Req</span>`;
        }
      } else {
        pillHtml = `<span class="setup-nav-pill count">${configuredCount} set</span>`;
      }

      navHtml += `
        <button type="button" class="setup-nav-item ${isActive ? "active" : ""}" data-tab="${cat.id}">
          <span class="setup-nav-left">
            <span class="setup-nav-icon">${cat.icon}</span>
            <span class="setup-nav-text">${esc(cat.name)}</span>
          </span>
          ${pillHtml}
        </button>
      `;
    });
    tabsBar.innerHTML = navHtml;

    // 2. Render Right Panels & Cards
    let panelsHtml = "";

    SETUP_CATEGORIES.forEach((cat) => {
      const items = catalog.filter((c) => c.category === cat.id);
      const isActive = cat.id === setupActiveTab;

      panelsHtml += `<div class="setup-category-panel ${isActive ? "active" : ""}" data-category="${cat.id}">`;

      // Special: Integration cards at top of Brain, Art & Design, and Cloud panels
      if (cat.id === "brain") {
        panelsHtml += `<div class="integration-cards-container" id="brain-cards"></div>`;
      } else if (cat.id === "art_design") {
        panelsHtml += `<div class="integration-cards-container" id="art-design-cards"></div>`;
      } else if (cat.id === "cloud") {
        panelsHtml += `<div class="integration-cards-container" id="cloud-cards"></div>`;
      }

      if (items.length === 0 && cat.id !== "art_design") {
        panelsHtml += `<div class="setup-card-desc">No settings in this category.</div>`;
      } else {
        items.forEach((item) => {
          const isHero = item.key === "GEMINI_API_KEY";
          const reqBadge = item.required
            ? `<span class="setup-badge-req">Required</span>`
            : `<span class="setup-badge-opt">Optional</span>`;

          const activeBadge = item.is_set
            ? `<span class="setup-badge-active" title="Value is configured"><svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg> Configured: ${esc(item.current_display)}</span>`
            : "";

          const whereLink = item.where_to_get_url
            ? `<a href="${esc(item.where_to_get_url)}" target="_blank" rel="noopener noreferrer" class="setup-guide-link">
                 <span>Get key from ${esc(item.where_to_get_label || "provider")}</span>
                 <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
               </a>`
            : "";

          const guideSteps = item.guide_steps && item.guide_steps.length > 0
            ? `<button type="button" class="setup-guide-toggle" onclick="var el=this.nextElementSibling; el.style.display = el.style.display==='none'?'block':'none';">
                 <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                 <span>Where to find this / instructions ▾</span>
               </button>
               <div class="setup-guide-box" style="display:none;margin-top:8px">
                 <ol>${item.guide_steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>
               </div>`
            : "";

          // Control Element based on field_type
          let controlHtml = "";
          const fType = item.field_type || (item.is_secret ? "secret" : "text");

          if (fType === "switch") {
            const isChecked = item.is_set
              ? ["yes", "true", "1", "on"].includes(String(item.current_display || "").toLowerCase())
              : ["yes", "true", "1", "on"].includes(String(item.default || "").toLowerCase());

            controlHtml = `
              <div class="setup-switch-row">
                <span class="setup-switch-label">Enable ${esc(item.label)}</span>
                <label class="setup-switch">
                  <input type="checkbox" class="setup-input-switch" data-key="${item.key}" ${isChecked ? "checked" : ""}>
                  <span class="setup-slider"></span>
                </label>
              </div>
            `;
          } else if (fType === "select" && item.options && item.options.length > 0) {
            const currVal = item.is_set ? item.current_display : (item.default || "");
            controlHtml = `
              <select class="setup-select" data-key="${item.key}">
                ${item.options.map((opt) => `
                  <option value="${esc(opt.value)}" ${opt.value === currVal ? "selected" : ""}>
                    ${esc(opt.label)}
                  </option>
                `).join("")}
              </select>
            `;
          } else if (fType === "textarea") {
            controlHtml = `
              <textarea
                class="setup-textarea"
                data-key="${item.key}"
                placeholder="${esc(item.placeholder || "")}"
                rows="3"
              >${esc(item.value || "")}</textarea>
            `;
          } else if (fType === "timezone") {
            controlHtml = `
              <div class="setup-input-wrapper">
                <input
                  type="text"
                  class="setup-input"
                  data-key="${item.key}"
                  placeholder="${esc(item.placeholder || "e.g. Asia/Kolkata, America/New_York")}"
                  value="${esc(item.value || item.default || "")}"
                  autocomplete="off"
                  spellcheck="false"
                />
                <button type="button" class="setup-detect-btn" title="Detect local timezone from browser" onclick="
                  var inp = this.previousElementSibling;
                  try {
                    var tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
                    if (tz) { inp.value = tz; this.textContent = '✓ ' + tz; }
                  } catch (e) {}
                ">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3Z"/></svg>
                  <span>Auto-detect</span>
                </button>
              </div>
            `;
          } else {
            // Standard text or secret input
            const testBtn = item.key === "GEMINI_API_KEY"
              ? `<button type="button" class="setup-test-btn" id="setup-test-gemini-btn">
                   <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
                   <span>Test Key</span>
                 </button>`
              : "";

            const eyeBtn = item.is_secret
              ? `<button type="button" class="setup-eye-btn" title="Show / hide key" onclick="
                   var inp = this.previousElementSibling;
                   if (inp.type === 'password') { inp.type = 'text'; this.innerHTML = '<svg width=\\'15\\' height=\\'15\\' viewBox=\\'0 0 24 24\\' fill=\\'none\\' stroke=\\'currentColor\\' stroke-width=\\'2\\'><path d=\\'M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24\\'/><line x1=\\'1\\' y1=\\'1\\' x2=\\'23\\' y2=\\'23\\'/></svg>'; }
                   else { inp.type = 'password'; this.innerHTML = '<svg width=\\'15\\' height=\\'15\\' viewBox=\\'0 0 24 24\\' fill=\\'none\\' stroke=\\'currentColor\\' stroke-width=\\'2\\'><path d=\\'M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z\\'/><circle cx=\\'12\\' cy=\\'12\\' r=\\'3\\'/></svg>'; }
                 ">
                   <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                 </button>`
              : "";

            controlHtml = `
              <div class="setup-input-wrapper">
                <input
                  type="${item.is_secret ? "password" : "text"}"
                  class="setup-input"
                  data-key="${item.key}"
                  placeholder="${esc(item.placeholder || (item.is_set ? "Leave blank to keep current key" : ""))}"
                  value="${item.is_secret ? "" : esc(item.value || "")}"
                  autocomplete="off"
                  spellcheck="false"
                />
                ${eyeBtn}
                ${testBtn}
              </div>
              ${item.key === "GEMINI_API_KEY" ? `<div id="gemini-test-feedback" style="display:none"></div>` : ""}
            `;
          }

          const star = item.required ? `<span class="setup-required-star" title="Mandatory field">*</span>` : "";

          panelsHtml += `
            <div class="setup-card ${isHero ? "hero" : ""}" id="card-${item.key}">
              <div class="setup-card-header">
                <div class="setup-card-title-box">
                  <div class="setup-card-title-row">
                    <span class="setup-card-label">${esc(item.label)}${star}</span>
                    ${reqBadge}
                    ${activeBadge}
                  </div>
                  <p class="setup-card-desc">${esc(item.description)}</p>
                </div>
              </div>

              ${whereLink || guideSteps ? `
                <div class="setup-guide-row">
                  ${whereLink}
                  ${guideSteps}
                </div>` : ""}

              ${controlHtml}
            </div>
          `;
        });
      }

      panelsHtml += `</div>`;
    });

    panelsContainer.innerHTML = panelsHtml;

    // Wire Gemini Test Key button
    const testGeminiBtn = $("setup-test-gemini-btn");
    if (testGeminiBtn) {
      testGeminiBtn.addEventListener("click", handleTestGeminiKey);
    }

    // Wire live input listener for Gemini key to update readiness bar instantly
    const geminiInput = document.querySelector('input[data-key="GEMINI_API_KEY"]');
    if (geminiInput) {
      geminiInput.addEventListener("input", () => {
        updateReadinessIndicator();
      });
    }

    // Sync header metadata for current tab
    switchSetupTab(setupActiveTab);

    // Load integration cards for Art & Design
    loadIntegrationCards();
  }

  // ── Integration Cards System ──────────────────────────────────────────────

  const INTEGRATION_PROVIDERS = [
    {
      id: "antigravity",
      category: "brain",
      name: "Google Antigravity Worker",
      description: "Autonomous coding agent running on port 8022. Executes terminal commands, file refactors, and test suites with gemini-3.1-pro-high.",
      logo: `<svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/><polygon points="12 6 15 12 9 12 12 6" fill="currentColor"/></svg>`,
      scopes: "Autonomous coding agent, terminal builds, tests (port 8022)",
    },
    {
      id: "figma",
      category: "art_design",
      name: "Figma",
      description: "Read designs, inspect nodes, export assets, and create layouts through the Figma Plugin Bridge.",
      logo: `<svg viewBox="0 0 38 57" width="28" height="42" xmlns="http://www.w3.org/2000/svg"><path d="M19 28.5a9.5 9.5 0 1 1 0-19 9.5 9.5 0 0 1 0 19z" fill="#1abcfe"/><path d="M0 47.5A9.5 9.5 0 0 1 9.5 38H19v9.5a9.5 9.5 0 1 1-19 0z" fill="#0acf83"/><path d="M19 0v19h9.5a9.5 9.5 0 1 0 0-19H19z" fill="#ff7262"/><path d="M0 9.5A9.5 9.5 0 0 0 9.5 19H19V0H9.5A9.5 9.5 0 0 0 0 9.5z" fill="#f24e1e"/><path d="M0 28.5A9.5 9.5 0 0 0 9.5 38H19V19H9.5A9.5 9.5 0 0 0 0 28.5z" fill="#a259ff"/></svg>`,
      scopes: "current_user:read, file_content:read",
    },
    {
      id: "canva",
      category: "art_design",
      name: "Canva",
      description: "List designs, create new graphics, and export artwork through the Canva Connect API.",
      logo: `<img src="/static/canva-logo.png" alt="Canva" width="32" height="32" style="object-fit:contain;" />`,
      scopes: "design:content:read, design:meta:read, profile:read",
    },
    {
      id: "github",
      category: "cloud",
      name: "GitHub",
      description: "Connect GitHub to auto-retrieve account username, PAT access token, repo access, and populate settings.",
      logo: `<svg viewBox="0 0 24 24" width="32" height="32" fill="none" xmlns="http://www.w3.org/2000/svg"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" fill="#f0f6fc"/></svg>`,
      scopes: "repo, read:user",
    },
    {
      id: "cloudflare",
      category: "cloud",
      name: "Cloudflare",
      description: "Connect Cloudflare API token to auto-detect root domains, manage DNS records, and configure Tunnels.",
      logo: `<img src="/static/cloudflare-logo.png" alt="Cloudflare" width="32" height="32" style="object-fit:contain;" />`,
      scopes: "zone:read, dns:edit",
    },
  ];

  const STATUS_LABELS = {
    connected: { text: "Connected", cls: "connected", icon: "✓" },
    expired: { text: "Connection Expired", cls: "expired", icon: "⟳" },
    error: { text: "Error", cls: "error", icon: "✗" },
    not_connected: { text: "Not Connected", cls: "not-connected", icon: "○" },
  };

  async function loadIntegrationCards() {
    let statusData = {};
    try {
      const resp = await fetch("/api/integrations/status");
      if (resp.ok) statusData = await resp.json();
    } catch (e) {
      console.warn("[zenith] Could not load integration status:", e);
    }
    const integrations = statusData.integrations || [];

    ["brain", "art_design", "cloud"].forEach((catId) => {
      const containerId = `${catId.replace("_", "-")}-cards`;
      const container = document.getElementById(containerId);
      if (!container) return;

      const providers = INTEGRATION_PROVIDERS.filter((p) => p.category === catId);
      let titleText = "Connected Developer Services";
      let subText = "Connect developer services to auto-retrieve API keys, tokens, and domain settings.";
      if (catId === "brain") {
        titleText = "Autonomous Coding Agents & Workers";
        subText = "Connect Google Antigravity to unlock autonomous multi-file coding, terminal builds, and test verification.";
      } else if (catId === "art_design") {
        titleText = "Connected Design Tools";
        subText = "Connect your design tools to enable AI-powered design operations.";
      }

      let html = `<div class="integration-cards-header">
        <h3 class="integration-cards-title">${esc(titleText)}</h3>
        <p class="integration-cards-subtitle">${esc(subText)}</p>
      </div><div class="integration-cards-grid">`;

      providers.forEach((provider) => {
        const conn = integrations.find((i) => i.provider === provider.id) || {};
        let status = conn.status || (statusData[`${provider.id}_configured`] ? "connected" : "not_connected");
        if (provider.id === "antigravity") {
          status = statusData.antigravity_configured ? "connected" : "not_connected";
        }
        const sl = STATUS_LABELS[status] || STATUS_LABELS.not_connected;
        const isConnected = status === "connected";
        let userName = conn.provider_user_name || "";
        if (provider.id === "antigravity" && isConnected) {
          userName = "gemini-3.1-pro-high (Port 8022)";
        }
        const lastSync = conn.last_sync_at || conn.connected_at || "";
        const configured = statusData[`${provider.id}_configured`] || isConnected || (provider.id === "github" || provider.id === "cloudflare");

        let actionsHtml = "";
        if (isConnected) {
          actionsHtml = `
            <div class="intg-card-actions">
              <button class="intg-btn intg-btn-connected" disabled>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                Connected
              </button>
              <button class="intg-btn intg-btn-disconnect" onclick="window.__zenithDisconnect('${provider.id}')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
                Disconnect
              </button>
              <button class="intg-btn intg-btn-secondary" onclick="window.__zenithManagePerms('${provider.id}')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                Manage Permissions
              </button>
            </div>`;
        } else {
          actionsHtml = `
            <div class="intg-card-actions">
              <button class="intg-btn intg-btn-connect" onclick="window.__zenithConnect('${provider.id}')">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
                Connect ${provider.name}
              </button>
            </div>`;
        }

        let metaHtml = "";
        if (isConnected && userName) {
          metaHtml += `<div class="intg-card-meta-item"><span class="intg-meta-label">Account:</span> <span class="intg-meta-value">${esc(userName)}</span></div>`;
        }
        if (isConnected && lastSync) {
          const d = new Date(lastSync);
          const rel = isNaN(d.getTime()) ? lastSync : d.toLocaleString();
          metaHtml += `<div class="intg-card-meta-item"><span class="intg-meta-label">Connected:</span> <span class="intg-meta-value">${esc(rel)}</span></div>`;
        }

        html += `
          <div class="intg-card" data-provider="${provider.id}">
            <div class="intg-card-top">
              <div class="intg-card-logo">${provider.logo}</div>
              <div class="intg-card-info">
                <div class="intg-card-name">${esc(provider.name)}</div>
                <div class="intg-card-status ${sl.cls}">
                  <span class="intg-status-icon">${sl.icon}</span>
                  <span>${sl.text}</span>
                </div>
              </div>
            </div>
            <p class="intg-card-desc">${esc(provider.description)}</p>
            <div class="intg-card-scopes"><span class="intg-scopes-label">Scopes:</span> ${esc(provider.scopes)}</div>
            ${metaHtml ? `<div class="intg-card-meta">${metaHtml}</div>` : ""}
            ${actionsHtml}
          </div>`;
      });

      html += `</div>`;
      container.innerHTML = html;
    });
  }

  // Global handlers for integration buttons
  let _oauthPopup = null;
  let _agyPollInterval = null;

  async function showAntigravityAuthModal() {
    const modal = document.getElementById("agy-auth-modal");
    if (!modal) return;

    modal.style.display = "flex";
    const statusText = document.getElementById("agy-modal-status-text");
    const statusTitle = document.getElementById("agy-modal-status-title");
    const pulseRing = document.getElementById("agy-modal-pulse");
    const footerHint = document.getElementById("agy-modal-footer-hint");

    if (statusTitle) statusTitle.textContent = "Initiating Google OAuth Authorization...";
    if (statusText) statusText.textContent = "Reaching the Antigravity worker daemon on your host...";
    if (pulseRing) pulseRing.style.display = "block";
    if (footerHint) footerHint.textContent = "Connecting to worker...";

    try {
      const resp = await fetch("/api/integrations/antigravity/authorize", { method: "POST" });
      const data = await resp.json();

      if (data.already_authenticated) {
        if (statusTitle) statusTitle.textContent = "Already Authenticated! 🎉";
        if (statusText) statusText.textContent = "Antigravity CLI is already authorized with Google and ready for autonomous operations.";
        if (pulseRing) pulseRing.style.display = "none";
        if (footerHint) footerHint.textContent = "Authenticated";
        setTimeout(() => {
          modal.style.display = "none";
          loadIntegrationCards();
        }, 1800);
        return;
      }

      if (!resp.ok) {
        if (statusTitle) statusTitle.textContent = "Worker Offline";
        if (statusText) statusText.textContent = data.error || "Antigravity worker daemon is offline. Please start it on the host.";
        if (pulseRing) pulseRing.style.display = "none";
        if (footerHint) footerHint.textContent = "Error";
        return;
      }

      if (statusTitle) statusTitle.textContent = "Google OAuth Prompt Active";
      if (statusText) statusText.textContent = data.message || "A browser window was opened for Google sign-in. Confirm permissions to proceed.";
      if (footerHint) footerHint.textContent = "Listening for token confirmation...";

      // Poll worker status until token acquired
      if (_agyPollInterval) clearInterval(_agyPollInterval);
      _agyPollInterval = setInterval(async () => {
        try {
          const stResp = await fetch("/api/worker/status");
          if (stResp.ok) {
            const st = await stResp.json();
            if (st.authenticated) {
              clearInterval(_agyPollInterval);
              _agyPollInterval = null;
              if (statusTitle) statusTitle.textContent = "Connected Successfully! 🚀";
              if (statusText) statusText.textContent = "Google Antigravity is now connected! Autonomous frontier coding worker is fully online.";
              if (pulseRing) pulseRing.style.display = "none";
              if (footerHint) footerHint.textContent = "Authorization confirmed!";
              setTimeout(() => {
                modal.style.display = "none";
                loadIntegrationCards();
              }, 2000);
            }
          }
        } catch (err) {
          // ignore transient poll error
        }
      }, 1500);

    } catch (e) {
      if (statusTitle) statusTitle.textContent = "Connection Error";
      if (statusText) statusText.textContent = e.message;
      if (pulseRing) pulseRing.style.display = "none";
    }
  }

  window.__zenithConnect = async function (provider) {
    if (provider === "antigravity") {
      showAntigravityAuthModal();
      return;
    }
    try {
      const resp = await fetch(`/api/integrations/${provider}/authorize`);
      const data = await resp.json();

      if (data.need_config) {
        showIntgConfigModal(data);
        return;
      }

      if (data.url) {
        // Open OAuth sign-in window (GitHub / Figma / Canva / Cloudflare)
        _oauthPopup = window.open(data.url, `zenith_${provider}_oauth`, "width=600,height=700,left=200,top=100");
        return;
      }

      if (data.error) {
        alert(data.error);
      }
    } catch (e) {
      alert("Failed to start authorization: " + e.message);
    }
  };

  function showIntgConfigModal(data) {
    const modal = document.getElementById("intg-config-modal");
    const title = document.getElementById("intg-modal-title");
    const desc = document.getElementById("intg-modal-desc");
    const fieldsContainer = document.getElementById("intg-modal-fields");
    const devLink = document.getElementById("intg-modal-dev-link");
    const saveBtn = document.getElementById("intg-modal-save-btn");

    if (!modal) return;

    title.textContent = `${data.name} App Credentials Required`;
    desc.textContent = data.instructions || `${data.name} requires a registered Client ID & Secret for 1-click OAuth authorization.`;
    if (data.dev_url) {
      devLink.href = data.dev_url;
      devLink.style.display = "inline-flex";
    } else {
      devLink.style.display = "none";
    }

    fieldsContainer.innerHTML = (data.fields || []).map(f => `
      <div class="intg-modal-field">
        <label class="intg-modal-label">${esc(f.label)}</label>
        <input type="text" class="setup-input intg-modal-input" data-key="${esc(f.key)}" placeholder="${esc(f.placeholder || '')}" autocomplete="off" spellcheck="false" />
      </div>
    `).join("");

    saveBtn.onclick = async () => {
      const payload = {};
      const inputs = fieldsContainer.querySelectorAll("input[data-key]");
      let missing = false;
      inputs.forEach(inp => {
        const val = inp.value.trim();
        if (!val) missing = true;
        payload[inp.getAttribute("data-key")] = val;
      });

      if (missing) {
        alert("Please fill in all required credentials.");
        return;
      }

      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";
      try {
        const saveResp = await fetch("/api/setup/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (!saveResp.ok) throw new Error("Failed to save credentials.");

        modal.style.display = "none";
        // Re-trigger connection with saved credentials!
        window.__zenithConnect(data.provider);
      } catch (err) {
        alert(err.message);
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Save & Authorize";
      }
    };

    modal.style.display = "flex";
  }

  window.__zenithDisconnect = async function (provider) {
    const provName = provider.charAt(0).toUpperCase() + provider.slice(1);
    if (!confirm(`Disconnect ${provName}? This will remove the stored connection.`)) return;
    try {
      await fetch(`/api/integrations/${provider}/disconnect`, { method: "POST" });
      if (provider === "github") {
        const userInp = document.querySelector('input[data-key="GITHUB_USER"]');
        const tokenInp = document.querySelector('input[data-key="GITHUB_TOKEN"]');
        if (userInp) userInp.value = "";
        if (tokenInp) tokenInp.value = "";
      } else if (provider === "cloudflare") {
        const tokenInp = document.querySelector('input[data-key="CLOUDFLARE_API_TOKEN"]');
        const zoneInp = document.querySelector('input[data-key="CLOUDFLARE_ZONE"]');
        if (tokenInp) tokenInp.value = "";
        if (zoneInp) zoneInp.value = "";
      }
      loadIntegrationCards();
      loadSetupCatalog();
    } catch (e) {
      alert("Failed to disconnect: " + e.message);
    }
  };

  window.__zenithManagePerms = function (provider) {
    const urls = {
      figma: "https://www.figma.com/settings",
      canva: "https://www.canva.com/settings/apps",
      github: "https://github.com/settings/tokens",
      cloudflare: "https://dash.cloudflare.com/profile/api-tokens",
    };
    window.open(urls[provider] || "#", "_blank");
  };

  // Listen for OAuth callback messages
  window.addEventListener("message", (event) => {
    if (event.data && event.data.type === "zenith-oauth-callback") {
      loadIntegrationCards();
      loadSetupCatalog();
      if (event.data.success && _oauthPopup) {
        try { _oauthPopup.close(); } catch (e) {}
        _oauthPopup = null;
      }
    }
  });

  async function handleTestGeminiKey() {
    const geminiInput = document.querySelector('input[data-key="GEMINI_API_KEY"]');
    const feedback = $("gemini-test-feedback");
    const testBtn = $("setup-test-gemini-btn");
    if (!geminiInput || !feedback) return;

    const val = geminiInput.value.trim();
    if (!val) {
      feedback.style.display = "block";
      feedback.className = "setup-test-result error";
      feedback.textContent = "Please paste your Gemini API key in the field first to test it.";
      return;
    }

    testBtn.disabled = true;
    testBtn.innerHTML = `<span>Testing...</span>`;
    feedback.style.display = "block";
    feedback.className = "setup-test-result";
    feedback.textContent = "Connecting to Google AI Studio...";

    try {
      const resp = await fetch("/api/setup/test-key", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ gemini_api_key: val }),
      });
      const resData = await resp.json();
      if (resData.valid) {
        feedback.className = "setup-test-result success";
        feedback.innerHTML = `<strong>✓ Verified!</strong> ${esc(resData.message)} (${resData.models_count || 0} models available).`;
        updateReadinessIndicator();
      } else {
        feedback.className = "setup-test-result error";
        feedback.innerHTML = `<strong>Verification failed:</strong> ${esc(resData.error || "Unknown error")}`;
      }
    } catch (e) {
      feedback.className = "setup-test-result error";
      feedback.innerHTML = `<strong>Error:</strong> ${esc(e.message)}`;
    } finally {
      testBtn.disabled = false;
      testBtn.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg><span>Test Key</span>`;
    }
  }

  async function handleSaveSetup() {
    const saveBtn = $("setup-save-btn");
    const spinner = $("setup-btn-spinner");
    const statusText = $("setup-status-text");

    const updates = {};

    // 1. Text & password inputs
    document.querySelectorAll(".setup-input").forEach((inp) => {
      const k = inp.getAttribute("data-key");
      const v = inp.value.trim();
      if (v) {
        updates[k] = v;
      }
    });

    // 2. Switch toggles
    document.querySelectorAll(".setup-input-switch").forEach((sw) => {
      const k = sw.getAttribute("data-key");
      updates[k] = sw.checked ? "yes" : "no";
    });

    // 3. Dropdown selects
    document.querySelectorAll(".setup-select").forEach((sel) => {
      const k = sel.getAttribute("data-key");
      const v = sel.value.trim();
      if (v) {
        updates[k] = v;
      }
    });

    // 4. Textareas
    document.querySelectorAll(".setup-textarea").forEach((ta) => {
      const k = ta.getAttribute("data-key");
      const v = ta.value.trim();
      if (v) {
        updates[k] = v;
      }
    });

    // Validation: ensure Gemini key is present either in updates or current config
    const geminiItem = catalogData ? catalogData.find((c) => c.key === "GEMINI_API_KEY") : null;
    const hasGemini = Boolean(updates["GEMINI_API_KEY"] || (geminiItem && geminiItem.is_set));

    if (!hasGemini) {
      switchSetupTab("brain");
      const gCard = $("card-GEMINI_API_KEY");
      if (gCard) {
        gCard.scrollIntoView({ behavior: "smooth", block: "center" });
        const gInp = gCard.querySelector("input");
        if (gInp) gInp.focus();
      }
      alert("Please enter a Google Gemini API Key. It is the only required key to power Zenith.");
      return;
    }

    saveBtn.disabled = true;
    if (spinner) spinner.style.display = "inline-block";
    if (statusText) statusText.textContent = "Saving secrets and configuring Zenith...";

    try {
      const resp = await fetch("/api/setup/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ updates }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        alert(err.error || "Failed to save configuration. Please ensure Gemini API Key is valid.");
        if (statusText) statusText.textContent = "Error saving configuration.";
        saveBtn.disabled = false;
        if (spinner) spinner.style.display = "none";
        return;
      }

      const res = await resp.json();
      if (statusText) statusText.textContent = "✓ Configuration saved! Launching Zenith...";

      setTimeout(async () => {
        closeSetupWizard();

        if (setupIsFirstTime) {
          await loadCurrentUser();
          showApp();
          startApp();
          showToast("🌱", "Zenith is awake in Setup Mode!");
          setTimeout(() => {
            sendInitialSetupGreeting(window._zenithUserName || "Friend");
          }, 600);
        } else {
          await loadCurrentUser();
          showApp();
          loadState();
          loadBriefing();
          showToast("✓", "Settings saved successfully");
        }
      }, 700);
    } catch (e) {
      alert("Error saving setup: " + e.message);
      if (statusText) statusText.textContent = "Save error: " + e.message;
      saveBtn.disabled = false;
      if (spinner) spinner.style.display = "none";
    }
  }

  let appStarted = false;
  function startApp() {
    if (appStarted) return;
    appStarted = true;

    wireUI();
    wireConfirmDock();

    // On desktop the daybook starts open; on mobile it starts closed.
    if (window.innerWidth > 920) setSide(true);
    else setSide(false);

    wireTerminalUI();
    wireOperatingLayerUI();
    initWS();
    loadState();
    loadBriefing();
    loadVoiceConfig();
    window.addEventListener("beforeunload", () => ws && ws.close());

    // When the window crosses the desktop/mobile line, reconcile the drawer
    let lastW = window.innerWidth;
    window.addEventListener("resize", () => {
      const crossing = (lastW <= 920) !== (window.innerWidth <= 920);
      lastW = window.innerWidth;
      if (crossing) setSide(window.innerWidth > 920);
    });

    // UI sandbox: replay a sample task once, in the DOM only
    if (location.hash === "#demo" || location.search.includes("demo=1")) {
      demoReplay();
    }
  }

  /* ── boot ─────────────────────────────────────────── */
  async function boot() {
    console.log("[zenith] app.js — Initializing Zenith");
    wireTheme();
    wireUserMenu();
    wireSettingsModeSelector();
    wireStarterScreen();
    wireSetupWizard();

    // Check first-time setup status before anything else
    const forceIntro = location.search.includes("intro=1") || location.search.includes("onboarding=1") || location.hash === "#onboarding" || location.hash === "#intro";
    const forceSetup = location.search.includes("setup=1") || location.hash === "#setup";
    const forceSteps = location.search.includes("steps=1") || location.search.includes("setup_steps=1") || location.hash === "#steps";

    if (forceSetup) {
      await openSetupWizard({ isFirstTime: false });
      return;
    }

    if (forceSteps) {
      openStarterScreen(null, false);
      const stage = $("cinema-stage");
      if (stage) stage.classList.add("flight-done");
      const hud = $("cinema-flight-hud");
      if (hud) { hud.style.opacity = "0"; hud.style.display = "none"; }
      const deck = $("cinema-content-deck");
      if (deck) deck.classList.add("deck-active");
      if (window.ZenithLiquidShader) window.ZenithLiquidShader.start();
      const shaderCanvas = $("cinema-liquid-shader");
      if (shaderCanvas) shaderCanvas.classList.add("is-visible");
      return;
    }

    if (forceIntro) {
      openStarterScreen(null, true);
      initSetupStatus().then((status) => {
        if (status && status.user_name) {
          const nameInp = $("starter-name");
          if (nameInp && !nameInp.value) nameInp.value = status.user_name;
        }
      });
      return;
    }

    const setupStatus = await initSetupStatus();
    if (setupStatus && (!setupStatus.setup_completed || !setupStatus.has_gemini_key)) {
      openStarterScreen(setupStatus, false);
      return;
    }

    await loadCurrentUser();
    showApp();
    startApp();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  /* Demo replay drives the same renderers the live wire uses.
   Load the app with ?demo=1 to see Zenith working a sample task. */
  async function demoReplay() {
    const seq = [
      ["user", "homelab overview, weather in dehradun, and what's overdue on my calendar"],
      ["agent_start", { prompt: "homelab overview, weather in dehradun, and what's overdue on my calendar" }],
      ["tool_start", { name: "fleet.overview", args: "{\"scope\":\"all\"}" }],
      ["tool_result", { name: "fleet.overview", ok: true }],
      ["tool_start", { name: "weather.current", args: "{\"place\":\"dehradun\"}" }],
      ["tool_result", { name: "weather.current", ok: true }],
      ["tool_start", { name: "calendar.overdue", args: "{}" }],
      ["tool_result", { name: "calendar.overdue", ok: true }],
      ["text", { text: "19 containers up · no failures.\n\nWeather in Dehradun is **27°C**, scattered clouds, humidity 74%.\n\nCalendar: 1 overdue task — *revise physics*." }],
      ["done", { text: "19 containers up · no failures.\n\nWeather in Dehradun is **27°C**, scattered clouds, humidity 74%.\n\nCalendar: 1 overdue task — *revise physics*." }],
    ];
    hideWelcome();
    for (const [type, payload] of seq) {
      if (type === "user") {
        addBubble("user", esc(payload));
      } else {
        route({ type, ...payload });
      }
      await new Promise((r) => setTimeout(r, type === "done" ? 120 : 320));
    }
  }

  /* ── dom wiring ──────────────────────────────────────── */

  function voiceOpen() {
    const vmod = $("vmod");
    return vmod && vmod.classList.contains("open");
  }

  function onVoiceBtn() {
    if (voiceOpen()) {
      closeVoice();
    } else {
      openVoice();
    }
  }

  function wireUI() {
    const input = $("inp");
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input.value); }
      });
      input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 140) + "px";
      });
    }

    const sendBtn = $("send-btn");
    if (sendBtn) {
      sendBtn.addEventListener("click", () => {
        if (awaiting) {
          stopGenerating();
        } else {
          send($("inp").value);
        }
      });
    }

    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && awaiting) {
        e.preventDefault();
        stopGenerating();
      }
    });

    // Zenith Quick-Action Prompt Chips
    document.addEventListener("click", (e) => {
      const chip = e.target.closest(".wlcm-chip");
      if (chip) {
        const p = chip.getAttribute("data-prompt");
        if (p) {
          const inp = $("inp");
          if (inp) {
            inp.value = p;
            inp.focus();
            inp.style.height = "auto";
            inp.style.height = Math.min(inp.scrollHeight, 140) + "px";
          }
        }
      }
    });

    // Mic + header voice buttons both toggle the voice layer (no more
    // hold-to-talk). Prevents text-select on mobile taps.
    const micBtn = $("mic-btn");
    if (micBtn) {
      micBtn.addEventListener("click", (e) => { e.stopPropagation(); onVoiceBtn(); });
      micBtn.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); });
    }

    const voiceBtn = $("voice-btn");
    if (voiceBtn) {
      voiceBtn.addEventListener("click", (e) => { e.stopPropagation(); onVoiceBtn(); });
      voiceBtn.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); });
    }

    // Orb/canvas: click toggles pause/resume of continuous listening. The canvas
    // is now the ONLY orb (the static div overlay was removed in v31), so the
    // wrap and canvas share one handler and taps can't hit a hidden orb.
    const orbWrap = $("orb-wrap");
    if (orbWrap) {
      orbWrap.addEventListener("click", (e) => { e.stopPropagation(); toggleVoiceListen(); });
      orbWrap.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); });
    }

    const orbCanvas = $("orb-canvas");
    if (orbCanvas) {
      orbCanvas.addEventListener("click", (e) => { e.stopPropagation(); toggleVoiceListen(); });
      orbCanvas.addEventListener("pointerdown", (e) => { e.stopPropagation(); e.preventDefault(); });
    }

    // The transcript line also toggles pause/resume; mobile no-select via css.
    const vText = $("v-text");
    if (vText) vText.addEventListener("click", (e) => { e.stopPropagation(); toggleVoiceListen(); });

    const clearBtn = $("clear-btn");
    if (clearBtn) clearBtn.addEventListener("click", clearConversation);

    // Proactive alert bar removed — Zenith surfaces work inline, not as banners.

    const vClose = $("v-close");
    if (vClose) {
      vClose.addEventListener("click", (e) => { e.stopPropagation(); closeVoice(); });
    }

    // Keyboard: Space = push-to-talk while the voice layer is open; Esc closes.
    // Guarded so typing in the chat box or executing-log keeps working normally.
    window.addEventListener("keydown", (e) => {
      if (e.repeat) return;
      const k = e.key;
      const typingTarget = (e.target && e.target.tagName &&
        /INPUT|TEXTAREA/.test(e.target.tagName)) || e.isComposing;
      if (k === "Escape" && voiceOpen()) { e.preventDefault(); closeVoice(); return; }
      // Ctrl/Cmd+Space = global voice toggle (open/close).
      if ((e.ctrlKey || e.metaKey) && k === " ") {
        e.preventDefault();
        if (voiceOpen()) closeVoice(); else { openVoice(); }
        return;
      }
      // Plain Space (voice open) = send the current utterance immediately.
      if (voiceOpen() && k === " " && !typingTarget && !e.ctrlKey && !e.altKey && !e.metaKey) {
        e.preventDefault();
        flushLiveUtterance();
      }
    });
    window.addEventListener("keyup", (e) => {
      if (e.key === " " && voiceOpen() && !e.ctrlKey && !e.altKey && !e.metaKey) { /* no-op */ }
    });

    const memBtn = $("mem-btn");
    if (memBtn) memBtn.addEventListener("click", toggleSide);


    const sideCloseBtn = $("side-close-btn");
    if (sideCloseBtn) sideCloseBtn.addEventListener("click", closeSide);

    const sideBackdrop = $("side-backdrop");
    if (sideBackdrop) sideBackdrop.addEventListener("click", closeSide);

    const daybookFab = $("daybook-fab");
    if (daybookFab) daybookFab.addEventListener("click", () => openSide());

    const sidebar = $("sidebar");
    if (sidebar) sidebar.addEventListener("click", (e) => { if (e.target === e.currentTarget) toggleSide(); });

    // Touch swipe-to-close gesture on mobile sidebar
    let touchStartX = 0;
    if (sidebar) {
      sidebar.addEventListener("touchstart", (e) => {
        touchStartX = e.changedTouches[0].screenX;
      }, { passive: true });
      sidebar.addEventListener("touchend", (e) => {
        const touchEndX = e.changedTouches[0].screenX;
        if (touchEndX - touchStartX > 50) closeSide(); // Swiped right -> close
      }, { passive: true });
    }

    // Drag & Drop File Upload Overlay
    const dropOverlay = $("drop-overlay");
    if (dropOverlay) {
      window.addEventListener("dragenter", (e) => {
        e.preventDefault();
        dropOverlay.classList.add("active");
      });
      window.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropOverlay.classList.add("active");
      });
      dropOverlay.addEventListener("dragleave", (e) => {
        if (e.target === dropOverlay) dropOverlay.classList.remove("active");
      });
      window.addEventListener("drop", (e) => {
        e.preventDefault();
        dropOverlay.classList.remove("active");
        const files = Array.from((e.dataTransfer || {}).files || []);
        if (files.length) {
          files.forEach(f => uploadFileObj(f));
        }
      });
    }

    // Global Paste (Ctrl+V / Cmd+V) handler for images and files
    window.addEventListener("paste", (e) => {
      const items = Array.from((e.clipboardData || {}).items || []);
      const fileItems = items.filter(item => item.kind === "file");
      if (fileItems.length) {
        fileItems.forEach(item => {
          const blob = item.getAsFile();
          if (blob) uploadFileObj(blob);
        });
      }
    });

    // Wire modern Figma-grade components
    wireCommandPalette();
    wireTelemetryPopover();
    wireModePill();
    wireDaybookTabs();
    wireScrollBottomBtn();
    wireMessageActionsAndCodeCopy();
  }

  /* ── Modern Component Wiring ────────────────────────── */

  function sendDirect(text) {
    if (!text) return;
    hideWelcome();
    const inp = $("inp");
    if (inp) {
      inp.value = text;
      send(text);
    }
  }

  function wireCommandPalette() {
    const modal = $("cmd-palette-modal");
    const trigger = $("cmd-palette-btn");
    const input = $("cmd-palette-input");
    const list = $("cmd-palette-list");
    if (!modal || !input || !list) return;

    const commands = [
      // SYSTEM & HOMELAB
      { id: "sys-docker", group: "System & Homelab", icon: "🐳", title: "Check Docker & Containers", hint: "Inspect running services, status & health", action: () => sendDirect("Check system status and running Docker containers") },
      { id: "sys-hw", group: "System & Homelab", icon: "📊", title: "Host Hardware & Telemetry", hint: "View CPU, RAM, disk, and load metrics", action: () => sendDirect("Show host CPU, memory, and disk usage metrics") },
      { id: "sys-tunnel", group: "System & Homelab", icon: "🌐", title: "Inspect Cloudflare Tunnel & Ingress", hint: "Check tunnel status and public ingress routes", action: () => sendDirect("Inspect Cloudflare tunnel status and public routes") },

      // AGENT & ACTIONS
      { id: "agent-code", group: "Intelligence & Agents", icon: "💻", title: "Launch Autonomous Coding Agent", hint: "Submit a software engineering brief to the worker", action: () => sendDirect("Start a coding agent to build a new feature in my workspace") },
      { id: "agent-research", group: "Intelligence & Agents", icon: "🔍", title: "Deep Web Research", hint: "Multi-source research synthesis with citations", action: () => sendDirect("Search the web for the latest updates on AI agents and reasoning models") },
      { id: "mail-summary", group: "Intelligence & Agents", icon: "✉️", title: "Read & Summarize Emails", hint: "Check unread mail and draft replies", action: () => sendDirect("Check my unread emails and summarize any important messages") },
      { id: "agenda-today", group: "Intelligence & Agents", icon: "📅", title: "View Agenda & Schedule", hint: "Review today's to-dos, reminders, and calendar", action: () => sendDirect("What are my to-dos and upcoming events for today?") },
      { id: "theme-custom", group: "Intelligence & Agents", icon: "🎨", title: "Customize UI Theme", hint: "Live-tweak colors, typography, or custom CSS", action: () => sendDirect("Open UI Customizer and show me the available themes") },

      // CONTROLS & NAVIGATION
      { id: "nav-agents", group: "Navigation & Views", icon: "👥", title: "Organization & Multi-Agent Roster", hint: "View departments, specialists, capabilities & custom hires", action: () => { if (window.toggleContextDrawer) window.toggleContextDrawer("ctx-agents"); } },
      { id: "nav-daybook", group: "Navigation & Views", icon: "📋", title: "Toggle Daybook Sidebar", hint: "Open to-dos, calendar & recent notes", action: () => toggleSide() },
      { id: "nav-logs", group: "Navigation & Views", icon: "📜", title: "Toggle Execution Logs Drawer", hint: "View raw tool execution logs in real-time", action: () => onTermBtn() },
      { id: "nav-voice", group: "Navigation & Views", icon: "🎙️", title: "Open Hands-Free Voice (Space)", hint: "Conversational voice interface with speech orb", action: () => onVoiceBtn() },
      { id: "nav-settings", group: "Navigation & Views", icon: "⚙️", title: "Open Settings & Secrets Studio", hint: "Configure Gemini, GitHub, Home Assistant & more", action: () => openSetupWizard({ isFirstTime: false }) },
      { id: "nav-clear", group: "Navigation & Views", icon: "🗑️", title: "Clear Conversation History", hint: "Start a fresh chat turn", action: () => clearConversation() },
    ];

    let selectedIdx = 0;
    let filteredCommands = [...commands];

    function renderCommandList() {
      list.innerHTML = "";
      if (filteredCommands.length === 0) {
        list.innerHTML = `<div style="padding: 24px; text-align: center; color: var(--ink-faint); font-size: 0.85rem">No matching commands found.</div>`;
        return;
      }

      let currentGrp = "";
      filteredCommands.forEach((cmd, idx) => {
        if (cmd.group !== currentGrp) {
          currentGrp = cmd.group;
          const grpEl = document.createElement("div");
          grpEl.className = "cmd-group-label";
          grpEl.textContent = currentGrp;
          list.appendChild(grpEl);
        }
        const item = document.createElement("div");
        item.className = "cmd-item" + (idx === selectedIdx ? " selected" : "");
        item.setAttribute("data-idx", idx);
        item.innerHTML = `
          <span class="cmd-item-icon">${cmd.icon}</span>
          <div class="cmd-item-info">
            <div class="cmd-item-title">${esc(cmd.title)}</div>
            <div class="cmd-item-hint">${esc(cmd.hint)}</div>
          </div>
        `;
        item.addEventListener("click", () => {
          closePalette();
          cmd.action();
        });
        list.appendChild(item);
      });

      const selEl = list.querySelector(".cmd-item.selected");
      if (selEl) selEl.scrollIntoView({ block: "nearest" });
    }

    function openPalette() {
      filteredCommands = [...commands];
      selectedIdx = 0;
      input.value = "";
      modal.style.display = "flex";
      renderCommandList();
      setTimeout(() => input.focus(), 50);
    }

    function closePalette() {
      modal.style.display = "none";
    }

    if (trigger) trigger.addEventListener("click", openPalette);

    window.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (modal.style.display === "flex") closePalette();
        else openPalette();
      } else if (e.key === "Escape" && modal.style.display === "flex") {
        closePalette();
      }
    });

    modal.addEventListener("click", (e) => {
      if (e.target === modal) closePalette();
    });

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      if (!q) {
        filteredCommands = [...commands];
      } else {
        filteredCommands = commands.filter(c =>
          c.title.toLowerCase().includes(q) ||
          c.hint.toLowerCase().includes(q) ||
          c.group.toLowerCase().includes(q)
        );
      }
      selectedIdx = 0;
      renderCommandList();
    });

    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (filteredCommands.length > 0) {
          selectedIdx = (selectedIdx + 1) % filteredCommands.length;
          renderCommandList();
        }
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        if (filteredCommands.length > 0) {
          selectedIdx = (selectedIdx - 1 + filteredCommands.length) % filteredCommands.length;
          renderCommandList();
        }
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredCommands.length > 0 && filteredCommands[selectedIdx]) {
          const cmd = filteredCommands[selectedIdx];
          closePalette();
          cmd.action();
        }
      }
    });
  }

  function wireTelemetryPopover() {
    const btn = $("hdr-telemetry-btn");
    const pop = $("telemetry-popover");
    const closeBtn = $("tp-close-btn");
    const btnDocker = $("tp-btn-docker");
    const btnSwitch = $("tp-btn-switch-mode");

    if (!btn || !pop) return;

    function toggle() {
      const isVisible = pop.style.display !== "none";
      if (isVisible) {
        pop.style.display = "none";
      } else {
        pop.style.display = "block";
        const modeVal = $("tp-mode-val");
        if (modeVal) {
          modeVal.textContent = currentZenithMode === "sovereign" ? "Sovereign" : "Setup";
        }
      }
    }

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggle();
    });

    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        pop.style.display = "none";
      });
    }

    if (btnDocker) {
      btnDocker.addEventListener("click", () => {
        pop.style.display = "none";
        sendDirect("Check system status and running Docker containers");
      });
    }

    if (btnSwitch) {
      btnSwitch.addEventListener("click", () => {
        pop.style.display = "none";
        setZenithMode(currentZenithMode === "sovereign" ? "setup" : "sovereign");
      });
    }

    document.addEventListener("click", (e) => {
      if (!pop.contains(e.target) && e.target !== btn && !btn.contains(e.target)) {
        pop.style.display = "none";
      }
    });
  }

  function wireModePill() {
    const pill = $("hdr-mode-pill");
    if (!pill) return;
    pill.addEventListener("click", () => {
      const nextMode = currentZenithMode === "sovereign" ? "setup" : "sovereign";
      setZenithMode(nextMode);
    });
  }

  function wireDaybookTabs() {
    const tabAgenda = $("tab-agenda");
    const tabNotes = $("tab-notes");
    const tabHomelab = $("tab-homelab");
    const paneAgenda = $("pane-agenda");
    const paneNotes = $("pane-notes");
    const paneHomelab = $("pane-homelab");

    const tabs = [
      { btn: tabAgenda, pane: paneAgenda },
      { btn: tabNotes, pane: paneNotes },
      { btn: tabHomelab, pane: paneHomelab },
    ];

    tabs.forEach(({ btn, pane }) => {
      if (!btn || !pane) return;
      btn.addEventListener("click", () => {
        tabs.forEach(t => {
          if (t.btn) t.btn.classList.remove("active");
          if (t.pane) t.pane.style.display = "none";
        });
        btn.classList.add("active");
        pane.style.display = "block";
      });
    });

    const todoForm = $("quick-todo-form");
    const todoInput = $("quick-todo-input");
    if (todoForm && todoInput) {
      todoForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = todoInput.value.trim();
        if (!text) return;
        todoInput.value = "";
        sendDirect(`Add to my to-dos: ${text}`);
        showToast("✓", "To-do added to Daybook");
      });
    }

    const noteForm = $("quick-note-form");
    const noteInput = $("quick-note-input");
    if (noteForm && noteInput) {
      noteForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = noteInput.value.trim();
        if (!text) return;
        noteInput.value = "";
        sendDirect(`Save note: ${text}`);
        showToast("📝", "Note saved to Daybook");
      });
    }

    const hlRefresh = $("homelab-refresh-btn");
    const hlCheckAll = $("hl-check-all-btn");
    if (hlRefresh) {
      hlRefresh.addEventListener("click", () => {
        sendDirect("Check system status and running Docker containers");
      });
    }
    if (hlCheckAll) {
      hlCheckAll.addEventListener("click", () => {
        sendDirect("Perform complete homelab health check: containers, disk, memory, and services");
      });
    }
  }

  function wireScrollBottomBtn() {
    const btn = $("scroll-bottom-btn");
    const badge = $("scroll-new-badge");
    const chat = $("chat");
    if (!btn || !chat) return;

    chat.addEventListener("scroll", () => {
      const distFromBottom = chat.scrollHeight - chat.scrollTop - chat.clientHeight;
      if (distFromBottom > 150) {
        btn.style.display = "inline-flex";
      } else {
        btn.style.display = "none";
        if (badge) badge.style.display = "none";
      }
    });

    btn.addEventListener("click", () => {
      chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });
      btn.style.display = "none";
      if (badge) badge.style.display = "none";
    });
  }

  function wireMessageActionsAndCodeCopy() {
    document.addEventListener("click", (e) => {
      // Code block copy button
      const codeBtn = e.target.closest(".code-copy-btn");
      if (codeBtn) {
        const targetId = codeBtn.getAttribute("data-target");
        const codeEl = targetId ? document.getElementById(targetId) : null;
        const codeText = codeEl ? codeEl.textContent : "";
        if (codeText) {
          navigator.clipboard.writeText(codeText).then(() => {
            const origHtml = codeBtn.innerHTML;
            codeBtn.innerHTML = `<span>✓</span><span>Copied!</span>`;
            codeBtn.style.color = "#34d399";
            setTimeout(() => {
              codeBtn.innerHTML = origHtml;
              codeBtn.style.removeProperty("color");
            }, 2000);
          }).catch(() => {});
        }
        return;
      }

      // Message copy button
      const copyBtn = e.target.closest(".copy-msg-btn");
      if (copyBtn) {
        const msgBody = copyBtn.closest(".m").querySelector(".m-body");
        if (msgBody) {
          navigator.clipboard.writeText(msgBody.innerText).then(() => {
            showToast("✓", "Message copied to clipboard");
          });
        }
        return;
      }

      // Message speak aloud button
      const speakBtn = e.target.closest(".speak-msg-btn");
      if (speakBtn) {
        const msgBody = speakBtn.closest(".m").querySelector(".m-body");
        if (msgBody) {
          speak(msgBody.innerText);
        }
        return;
      }

      // Message pin to notes button
      const pinBtn = e.target.closest(".pin-msg-btn");
      if (pinBtn) {
        const msgBody = pinBtn.closest(".m").querySelector(".m-body");
        if (msgBody) {
          const text = msgBody.innerText.slice(0, 200);
          sendDirect(`Save note: ${text}`);
          showToast("📌", "Saved snippet to notes");
        }
        return;
      }
    });
  }

  function openSide() { setSide(true); }
  function closeSide() { setSide(false); }

  function setSide(open) {
    const sb = $("sidebar");
    const bd = $("side-backdrop");
    if (sb) sb.classList.toggle("open", open);
    if (bd) bd.classList.toggle("show", open);
    const fab = $("daybook-fab");
    if (fab) fab.classList.toggle("hidden", open);
    if (open && window._lastGraphData) {
      setTimeout(() => renderGraph(window._lastGraphData), 50);
    }
  }

  function toggleSide() {
    const sb = $("sidebar");
    if (!sb) return;
    setSide(!sb.classList.contains("open"));
  }

  /* ── theme (dark mode) ────────────────────────────── */
  function applyThemeUI() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    const moon = $("icon-moon"), sun = $("icon-sun");
    if (moon) moon.style.display = dark ? "none" : "";
    if (sun) sun.style.display = dark ? "" : "none";
    const btn = $("theme-btn");
    if (btn) btn.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  }

  function wireTheme() {
    const btn = $("theme-btn");
    if (!btn) return;
    applyThemeUI();
    btn.addEventListener("click", () => {
      const el = document.documentElement;
      const dark = el.getAttribute("data-theme") !== "dark";
      el.setAttribute("data-theme", dark ? "dark" : "light");
      try { localStorage.setItem("zenith-theme", dark ? "dark" : "light"); } catch {}
      applyThemeUI();
    });
  }

  /* ── opening briefing: Zenith greets then smoothly animates into summary ─── */
  let briefingShown = false;
  let summaryAnimationTimer = null;

  function animateSubtitleTo(newText) {
    const sub = $("wlcm-subtitle");
    if (!sub) return;
    const current = (sub.textContent || "").trim();
    if (current === newText.trim()) return;

    // Phase 1: Smooth fade & slight upward drift out
    sub.style.transition = "opacity 0.32s cubic-bezier(0.4, 0, 0.2, 1), transform 0.32s cubic-bezier(0.4, 0, 0.2, 1)";
    sub.style.opacity = "0";
    sub.style.transform = "translateY(-4px)";

    setTimeout(() => {
      // Check welcome element is still visible
      const w = $("welcome");
      if (!w || w.style.display === "none") return;

      sub.textContent = newText;
      // Phase 2: Position slightly below and smoothly glide up into place
      sub.style.transition = "none";
      sub.style.transform = "translateY(5px)";
      void sub.offsetHeight; // Force reflow
      sub.style.transition = "opacity 0.48s cubic-bezier(0.16, 1, 0.3, 1), transform 0.48s cubic-bezier(0.16, 1, 0.3, 1)";
      sub.style.opacity = "1";
      sub.style.transform = "translateY(0)";
    }, 340);
  }

  function scheduleSummaryAnimation(targetText, delayMs = 1800) {
    clearTimeout(summaryAnimationTimer);
    summaryAnimationTimer = setTimeout(() => {
      const w = $("welcome");
      if (w && w.style.display !== "none") {
        animateSubtitleTo(targetText);
      }
    }, delayMs);
  }

  async function loadBriefing() {
    if (location.hash === "#demo" || location.search.includes("demo=1")) return;
    const bootStart = Date.now();
    try {
      const r = await fetch("/api/briefing");
      if (!r.ok) return;
      const d = await r.json();
      const summary = (d && d.summary) || (d && d.greeting) || "";
      if (!summary || summary.trim().length < 5) return;
      briefingShown = true;
      window._lastBriefingSummary = summary;

      let clean = summary.trim();
      const stripped = clean.replace(/^(Good\s+(morning|afternoon|evening|night)|Hello)[^.]*\.\s*/i, "");
      const targetSummary = (stripped && stripped.length > 10) ? stripped : clean;

      // Show salutation for a sec or two (1.8s), then smoothly animate into the summary
      const elapsed = Date.now() - bootStart;
      const delay = Math.max(200, 1800 - elapsed);
      scheduleSummaryAnimation(targetSummary, delay);
    } catch (e) {
      console.warn("Briefing unavailable:", e);
    }
  }




  /* ── websocket ─────────────────────────────────────── */

  let pendingPrompt = null;
  let awaitingTimer = null;
  const WATCHDOG_INACTIVITY_MS = 120000; // 120 seconds of inactivity before watchdog fires

  function refreshWatchdog(timeoutMs = WATCHDOG_INACTIVITY_MS) {
    if (!awaiting) return;
    clearTimeout(awaitingTimer);
    awaitingTimer = setTimeout(() => {
      if (awaiting) {
        awaiting = false;
        setGenerating(false);
        if (typingEl) { typingEl.remove(); typingEl = null; }
        addBubble("assistant", renderMD("_I'm still thinking — say again or type a new message._"));
        scroll();
        pumpOutQueue();
      }
    }, timeoutMs);
  }

  function clearWatchdog() {
    clearTimeout(awaitingTimer);
    awaitingTimer = null;
  }

  function initWS() {
    if (!currentUser) return;
    if (ws && ws.readyState === WebSocket.OPEN) return;
    clearTimeout(reconnectTimer);
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    try {
      ws = new WebSocket(`${proto}//${location.host}/ws/chat`);
    } catch {
      scheduleReconnect();
      return;
    }
    ws.onopen = () => {
      clearWatchdog();
      setConn(true);
      if (pendingConfirmDecision && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "confirm", id: pendingConfirmDecision.id, decision: pendingConfirmDecision.decision }));
        pendingConfirmDecision = null;
        pendingConfirm = null;
      }
      heartbeatTimer = setInterval(() => {
        if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "ping" }));
      }, 15000);
      if (pendingPrompt) {
        const p = pendingPrompt;
        pendingPrompt = null;
        send(p);
      }
    };
    ws.onmessage = (e) => {
      let m;
      try { m = JSON.parse(e.data); } catch { return; }
      if (m.type === "pong") return;
      // Active server event received: refresh the inactivity watchdog so long-running tasks are never prematurely aborted
      refreshWatchdog();
      if (m.type === "error" && (m.error === "forbidden" || (m.message && m.message.includes("perms")))) {
        showForbiddenScreen(currentUser, m.message);
        return;
      }
      route(m);
    };
    ws.onclose = (e) => {
      setConn(false);
      clearInterval(heartbeatTimer);
      if (e.code === 4001) {
        clearTimeout(awaitingTimer);
        awaiting = false;
        setGenerating(false);
        showLoginScreen();
        return;
      }
      if (e.code === 4003) {
        clearTimeout(awaitingTimer);
        awaiting = false;
        setGenerating(false);
        showForbiddenScreen(currentUser, "You don't have perms to access this.");
        return;
      }
      scheduleReconnect();
    };
    ws.onerror = () => {
      try { ws.close(); } catch {}
    };
  }

  function scheduleReconnect() {
    if (!currentUser) return;
    clearTimeout(reconnectTimer);
    reconnectTimer = setTimeout(initWS, 2500);
  }

  // Instant re-connect and state-sync when the user returns to the tab
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
        initWS();
      } else if (ws && ws.readyState === WebSocket.OPEN) {
        try { ws.send(JSON.stringify({ type: "ping" })); } catch {}
      }
    }
  });

  function setConn() {
    // No connection pill in the header anymore — Zenith stays calm either way.
  }

  /* ── confirmation dock (mutating-tool checkpoint) ─────── */
  let pendingConfirm = null;
  let pendingConfirmDecision = null;
  let confirmTimer = null;
  const CONFIRM_TIMEOUT_MS = 180000; // matches CONFIRM_TIMEOUT server default

  function wireConfirmDock() {
    const approve = $("confirm-approve");
    const deny = $("confirm-deny");
    if (approve) approve.addEventListener("click", () => resolveConfirm(true));
    if (deny) deny.addEventListener("click", () => resolveConfirm(false));
  }

  function showConfirm(m) {
    pendingConfirm = m.id || null;
    const dock = $("confirm-dock");
    if (!dock) return;
    const title = $("confirm-title");
    const msg = $("confirm-msg");
    const ic = $("confirm-ic");
    const tool = (m.tool || "").toLowerCase();
    if (title) title.textContent = tool
      ? `Approve ${tool.replace(/_/g, " ")}?`
      : "Approve this action?";
    if (msg) msg.textContent = m.message || "Zenith wants to do something that changes things.";
    if (ic) ic.textContent = tool === "shell" ? "$" : "⚠";
    dock.hidden = false;
    dock.classList.add("show");
    clearTimeout(confirmTimer);
    // Auto-refuse if the user never answers — never let the gate hang forever.
    confirmTimer = setTimeout(() => {
      if (pendingConfirm) resolveConfirm(false, true);
    }, CONFIRM_TIMEOUT_MS);
  }

  function resolveConfirm(decision, timedOut = false) {
    if (!pendingConfirm) return;
    const dock = $("confirm-dock");
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "confirm", id: pendingConfirm, decision }));
      pendingConfirm = null;
    } else {
      // Reconnection in flight: buffer decision so it sends immediately on ws.onopen
      pendingConfirmDecision = { id: pendingConfirm, decision };
    }
    if (dock) { dock.classList.remove("show"); dock.hidden = true; }
    if (timedOut) logTerminal("confirmation timed out — action refused", "err");
  }

  function clearConfirm() {
    pendingConfirm = null;
    clearTimeout(confirmTimer);
    const dock = $("confirm-dock");
    if (dock) { dock.classList.remove("show"); dock.hidden = true; }
  }

  /* ── proactive chips (quiet, non-interrupting nudges) ── */
  function addProactiveChip(alert) {
    const msgs = $("msgs");
    if (!msgs) return;
    const chip = document.createElement("div");
    chip.className = "proactive-chip";
    const title = (alert && alert.title) || "Zenith";
    const message = (alert && alert.message) || "";
    chip.innerHTML = `<span class="pc-ic">✦</span><span class="pc-title">${esc(title)}</span><span class="pc-msg">${esc(message)}</span>`;
    msgs.appendChild(chip);
    scroll();
  }

  /* ── incoming msg routing ───────────────────────────── */

  function route(m) {
    switch (m.type) {
      case "confirm":
        showConfirm(m);
        break;
      case "proactive":
        if (m.alert) addProactiveChip(m.alert);
        break;
      case "status":
        setConn(true);
        logTerminal("connected · ws ready", "sys");
        break;
      case "text":
        if (ackPendingDivider) {
          if (streamBuffer && !streamBuffer.includes("\n\n---\n\n")) {
            streamBuffer += "\n\n---\n\n";
          }
          ackPendingDivider = false;
        }
        streamBuffer += m.text;
        syncStream();
        break;
      case "ack":
        if (m.text) {
          streamBuffer = m.text;
          ackPendingDivider = true;
          syncStream();
        }
        if (m.audio) {
          playLiveAudio(m.audio, m.model, m.audio_mime);
        }
        break;
      case "tool_start":
        if ((m.delegated_agent || m.run_id) && getDelegationCard(m)) {
          appendDelegationStep(m);
        } else {
          addToolChip(m.name, m.args);
        }
        logTerminal(`call ${m.name} → ${JSON.stringify(m.args || {})}`, "tool");
        break;
      case "tool_result":
        if ((m.delegated_agent || m.run_id) && getDelegationCard(m)) {
          updateDelegationStep(m);
        } else {
          addToolResult(m);
        }
        logTerminal(`${m.name} → ${m.ok ? "ok" : "fail"}${m.result ? " · " + String(m.result).slice(0, 90) : ""}`, m.ok ? "succ" : "err");
        break;
      case "delegation_start":
        handleDelegationStart(m);
        logTerminal(`[DELEGATION] ${m.agent_name || m.department} ← ${m.task || ""}`, "tool");
        break;
      case "delegation_done":
        handleDelegationDone(m);
        logTerminal(`[DELEGATION] ${m.department} finished (${m.status}, ${m.tool_calls || 0} tools)`, "succ");
        break;
      case "agent_start":
        beginTurn(m.prompt);
        logTerminal(`starting · ${m.prompt || "task"}`, "sys");
        break;
      case "done":
        if (typeof m.text === "string") {
          finishStream(m.text);
          finishTurn();
          finishStateSoon();
          logTerminal("task complete", "sys");
        } else if (m.text && m.text.audio) {
          finishStream("");
          playLiveAudio(m.text.audio, m.text.model, m.text.audio_mime);
          finishTurn();
          finishStateSoon();
          logTerminal("task complete (gemini live)", "sys");
        }
        if (m.audio) {
          playLiveAudio(m.audio, m.model, m.audio_mime);
        }
        break;
      case "error":
        if (m.error === "unauthorized") {
          showLoginScreen();
          if (ws) {
            try { ws.close(); } catch {}
            ws = null;
          }
          return;
        }
        errorOut(m.error);
        logTerminal(`error · ${m.error}`, "err");
        break;
      case "cleared":
        clearChatDOM();
        logTerminal("conversation cleared", "sys");
        break;

      case "zenith_mode_changed":
      case "zenith_mode_changed":
        applyZenithMode(m.mode, m.mode_title);
        showToast(m.mode === "sovereign" ? "⚡" : "🌱", `Operating Mode: ${m.mode_title || m.mode}`);
        logTerminal(`[MODE] Switched to ${m.mode_title || m.mode}`, "sys");
        break;

      case "ui_theme_updated":
        applyLiveTheme(m.accent_color, m.custom_css);
        showToast("🎨", "UI theme customized by Zenith");
        logTerminal("[THEME] Live styles applied by Zenith", "sys");
        break;

      case "ui_theme_reset":
        resetLiveTheme();
        showToast("🎨", "UI theme reset to default");
        logTerminal("[THEME] Live styles reset to default", "sys");
        break;

      case "user_profile_updated":
        if (m.user_name) {
          updateDisplayedUserName(m.user_name);
          showToast("👤", `Profile updated: ${m.user_name}`);
        }
        break;

      default: break;
    }
  }

  /* ── chat rendering ─────────────────────────────────── */

  function addBubble(role, html) {
    hideWelcome();
    const d = document.createElement("div");
    d.className = "mg " + role;
    d.innerHTML = `<div class="m ${role}"><div class="m-body">${html}</div></div>`;
    if (role === "assistant") {
      const actions = document.createElement("div");
      actions.className = "msg-action-bar";
      actions.innerHTML = `
        <button type="button" class="msg-action-btn copy-msg-btn" title="Copy response">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        </button>
        <button type="button" class="msg-action-btn speak-msg-btn" title="Read aloud">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
        </button>
        <button type="button" class="msg-action-btn pin-msg-btn" title="Save to Daybook notes">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
        </button>
      `;
      const mWrap = d.querySelector(".m.assistant");
      if (mWrap) mWrap.appendChild(actions);
    }
    $("msgs").appendChild(d);
    scroll();
    return d;
  }

  function hideWelcome() {
    const w = document.querySelector(".welcome");
    if (w) {
      w.style.display = "none";
      w.style.padding = "0";
    }
    hideUserChrome();
  }

  function hideUserChrome() {
    // After the first task, remove decorative welcome-shell edges.
  }

  function makeTyping() {
    if (typingEl) return typingEl;
    const d = document.createElement("div");
    d.className = "mg assistant";
    d.innerHTML = `<div class="m assistant"><div class="m-body"><div class="dots" style="display:flex;align-items:center;gap:5px"><span></span><span></span><span></span></div></div></div>`;
    $("msgs").appendChild(d);
    typingEl = d;
    scroll();
    return d;
  }

  function showThinking() { makeTyping(); }

  /* One gentle chip per request, with the step traces beneath it. */
  let turnStartTs = null;

  function beginTurn(prompt) {
    clearConfirm();  // a new request supersedes any pending confirmation
    turnStartTs = Date.now();
    streamBuffer = "";
    ackPendingDivider = false;
    const p = document.createElement("div");
    p.className = "turn-chip";
    p.innerHTML = `<span class="tc-mark">◷</span><span class="tc-label">working on it</span><span class="tc-prompt">${esc((prompt || "").slice(0, 60))}</span><span class="tl-dur"></span>`;
    $("msgs").appendChild(p);
    scroll();
    makeTyping();
  }

  function syncStream() {
    if (!typingEl) makeTyping();
    typingEl.querySelector(".m-body").innerHTML = renderMD(streamBuffer);
    scroll();
  }

  function finishStream(finalText) {
    clearTimeout(awaitingTimer);
    if (finalText) streamBuffer = finalText;
    const textToDeliver = streamBuffer || finalText;

    if (typingEl) {
      if (textToDeliver) {
        typingEl.querySelector(".m-body").innerHTML = renderMD(textToDeliver);
        const mWrap = typingEl.querySelector(".m.assistant");
        if (mWrap && !mWrap.querySelector(".msg-action-bar")) {
          const actions = document.createElement("div");
          actions.className = "msg-action-bar";
          actions.innerHTML = `
            <button type="button" class="msg-action-btn copy-msg-btn" title="Copy response">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            </button>
            <button type="button" class="msg-action-btn speak-msg-btn" title="Read aloud">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
            </button>
            <button type="button" class="msg-action-btn pin-msg-btn" title="Save to Daybook notes">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"></path></svg>
            </button>
          `;
          mWrap.appendChild(actions);
        }
      } else {
        typingEl.remove();
      }
      typingEl = null;
    } else if (textToDeliver) {
      addBubble("assistant", renderMD(textToDeliver));
    }

    streamBuffer = "";
    ackPendingDivider = false;
    awaiting = false;
    setGenerating(false);
    pumpOutQueue();  // multi-message in a row: send the next queued prompt
    scroll();

    // If a second utterance queued while Zenith was thinking, keep listening:
    // the queue flush happens after the current reply finishes.
    if (voiceOpen()) {
      // spoken reply (if enabled) then hand the floor back
      voiceBusy = true;
      speak(textToDeliver, () => {
        onVoiceTurnDone();
      });
      if (!textToDeliver) onVoiceTurnDone();
    } else {
      voiceBusy = false;
    }
  }

  // After Zenith finishes replying, drain any queued utterances and re-arm VAD.
  function onVoiceTurnDone() {
    voiceBusy = false;
    if (!voiceOpen()) return;
    if (utterQueue.length) drainUtterQueue();
    else {
      recalibrateVad();
      // In streaming mode the same persistent Live session keeps listening —
      // just make sure the capture/playback plumbing is still attached.
      resolveLive();
    }
    refreshVoiceStatus();
  }

  function drainUtterQueue() {
    const next = utterQueue.shift();
    if (next && String(next).trim()) {
      // brief spacing so two requests don't stack as one
      $("v-text").textContent = `“${String(next).trim()}”`;
      setTimeout(() => flushQueueItem(next), 250);
      return;
    }
    vad.enabled = true;
    // Re-arm the rolling recorder so the next utterance is captured.
    if (voiceOpen() && micReady) {
      setTimeout(() => { if (voiceOpen() && micReady) startMediaRecorder(); }, 200);
    }
  }

  // Re-measure the ambient noise floor after Zenith stops speaking, so the
  // previous reply (or a loud noise) can't poison the next speech detection.
  function recalibrateVad() {
    vad._calibUntil = performance.now() + 600;
    vad._calibSum = 0;
    vad._calibN = 0;
    vad._noise = 0;
    vad.speech = false;
    vad._onsetMs = 0;
  }

  function finishTurn() {
    if (turnStartTs !== null) {
      const elapsed = Math.max(0, Date.now() - turnStartTs);
      const s = (elapsed / 1000).toFixed(1);
      const chips = $("msgs").querySelectorAll(".turn-chip");
      const last = chips[chips.length - 1];
      if (last) {
        const dur = last.querySelector(".tl-dur");
        if (dur) dur.textContent = `· ${s}s`;
      }
      turnStartTs = null;
    }

    // Safety sweep: ensure NO delegation card or sub-agent tool remains stuck in running state
    const runningCards = $("msgs") ? $("msgs").querySelectorAll(".delegation-card.running") : [];
    runningCards.forEach(card => {
      handleDelegationDone({
        status: "done",
        tool_calls: card._stepsCount || 0,
        run_id: card._runId,
        department: card._dept,
      });
    });
    activeDelegationCards.clear();
    activeDelegationCard = null;
  }

  function cancelTurn() {
    turnStartTs = null;
  }

  function errorOut(msg) {
    clearTimeout(awaitingTimer);
    if (typingEl) { typingEl.remove(); typingEl = null; }
    addBubble("assistant", `<p class="err-text">✕ ${esc(msg || "Something went wrong.")}</p>`);
    streamBuffer = "";
    ackPendingDivider = false;
    awaiting = false;
    setGenerating(false);
    cancelTurn();
    pumpOutQueue();

    // Mark any running delegation cards as failed
    const runningCards = $("msgs") ? $("msgs").querySelectorAll(".delegation-card.running") : [];
    runningCards.forEach(card => {
      handleDelegationDone({
        status: "fail",
        result: msg || "Turn interrupted",
        run_id: card._runId,
        department: card._dept,
      });
    });
    activeDelegationCards.clear();
    activeDelegationCard = null;
  }

  /* ── tool chips ───────────────────────────────────────── */

  const STEP_ICONS = {
    weather: "☀", calendar: "◫", mail: "✉", email: "✉", homelab: "⬡", fleet: "⬡",
    system: "◇", commute: "⌖", maps: "⌖", homeassistant: "◒", research: "⌕",
    web: "⌕", browser: "◫", delegate: "⚡", coding: "💻", code: "💻",
    hr: "👥", hire: "👥", creative: "🎨", pptx: "📊", operations: "⚙", docker: "🐳",
    media: "🎬", tts: "🎙️", speech: "🎙️", audio: "🎵", video: "🎥",
    collage: "🖼️", meme: "🎭", palette: "🎨", gif: "🎞️", trim: "✂️", compress: "🗜️",
  };
  function toolIconFor(name) {
    const n = (name || "").toLowerCase();
    for (const k in STEP_ICONS) if (n.includes(k)) return STEP_ICONS[k];
    return "◦";
  }

  function componentString(name, title, inner, tag) {
    const t = new Date().toLocaleTimeString([], { hour12: false });
    const icon = toolIconFor(name);
    return `<div class="tl-row">
  <span class="tl-mark ${tag === "run" ? "running" : ""}">${icon}</span>
  <span class="tc-name">${renderMD(esc(name))}</span>
  ${inner ? `<span class="tc-arg">${renderMD(inner)}</span>` : ""}
  ${tag ? `<span class="tl-tag ${esc(tag)}">${tag === "run" ? "working" : tag === "ok" ? "done" : "failed"}</span>` : ""}
  <span class="tl-dur">@${t}</span>
</div>`;
  }

  const DEPT_ICONS = {
    communication: "📬",
    coding: "💻",
    hr: "👥",
    research: "🔍",
    operations: "⚙️",
    productivity: "🗓️",
    creative: "🎨",
    media: "🎬",
    utility: "🔌",
  };

  const activeDelegationCards = new Map();
  let activeDelegationCard = null;

  function createDelegationCard(dept, task, agentName, runId) {
    const icon = DEPT_ICONS[dept] || "🤖";
    const displayName = agentName || (dept ? (dept.charAt(0).toUpperCase() + dept.slice(1) + " Specialist") : "Departmental Specialist");

    const card = document.createElement("div");
    card.className = "delegation-card running";
    card.id = `delegation-${runId || dept || Date.now()}`;
    card.setAttribute("data-dept", dept || "");
    if (runId) card.setAttribute("data-run-id", runId);
    card._dept = dept;
    card._runId = runId || "";
    card._stepsCount = 0;

    card.innerHTML = `
      <div class="delegation-hdr">
        <div class="delegation-agent-info">
          <span class="delegation-icon">${icon}</span>
          <span class="delegation-title">${esc(displayName)} <span class="delegation-badge">${esc(dept || 'autonomous')}</span></span>
        </div>
        <span class="delegation-status running">Working...</span>
      </div>
      <div class="delegation-body">
        <div class="delegation-task"><strong>Mission:</strong> ${renderMD(task || 'Executing assigned mission...')}</div>
        <div class="delegation-steps" style="display:none"></div>
      </div>
    `;

    const hdr = card.querySelector(".delegation-hdr");
    const body = card.querySelector(".delegation-body");
    hdr.addEventListener("click", () => {
      body.style.display = body.style.display === "none" ? "flex" : "none";
      scroll();
    });

    $("msgs").appendChild(card);
    activeDelegationCard = card;
    if (runId) activeDelegationCards.set(runId, card);
    if (dept) activeDelegationCards.set(dept, card);
    scroll();
    return card;
  }

  function getDelegationCard(m) {
    if (!m) return activeDelegationCard;
    if (m.run_id && activeDelegationCards.has(m.run_id)) {
      return activeDelegationCards.get(m.run_id);
    }
    if (m.delegated_agent && activeDelegationCards.has(m.delegated_agent)) {
      return activeDelegationCards.get(m.delegated_agent);
    }
    if (m.department && activeDelegationCards.has(m.department)) {
      return activeDelegationCards.get(m.department);
    }
    // Search DOM by run_id
    if (m.run_id) {
      const el = document.getElementById(`delegation-${m.run_id}`) || document.querySelector(`[data-run-id="${m.run_id}"]`);
      if (el) return el;
    }
    // Search DOM by department / delegated_agent
    const d = m.delegated_agent || m.department;
    if (d) {
      const el = document.querySelector(`.delegation-card.running[data-dept="${d}"]`);
      if (el) return el;
      const allRunning = document.querySelectorAll(".delegation-card.running");
      for (const c of allRunning) {
        if (c._dept === d) return c;
      }
    }
    if (activeDelegationCard && activeDelegationCard.classList.contains("running")) {
      return activeDelegationCard;
    }
    return document.querySelector(".delegation-card.running") || activeDelegationCard;
  }

  function handleDelegationStart(m) {
    let card = null;
    if (m.run_id && activeDelegationCards.has(m.run_id)) {
      card = activeDelegationCards.get(m.run_id);
    } else if (m.department && activeDelegationCards.has(m.department)) {
      const cand = activeDelegationCards.get(m.department);
      if (cand && cand.classList.contains("running") && (!cand._runId || cand._runId === m.run_id)) {
        card = cand;
      }
    } else if (activeDelegationCard && activeDelegationCard.classList.contains("running") && (!activeDelegationCard._runId || activeDelegationCard._runId === m.run_id) && (!activeDelegationCard._dept || activeDelegationCard._dept === m.department)) {
      card = activeDelegationCard;
    } else if (m.department) {
      const runningDom = document.querySelector(`.delegation-card.running[data-dept="${m.department}"]`);
      if (runningDom && (!runningDom._runId || runningDom._runId === m.run_id)) {
        card = runningDom;
      }
    }

    if (!card) {
      card = createDelegationCard(m.department, m.task, m.agent_name, m.run_id);
    } else {
      if (m.run_id) {
        card._runId = m.run_id;
        card.id = `delegation-${m.run_id}`;
        card.setAttribute("data-run-id", m.run_id);
        activeDelegationCards.set(m.run_id, card);
      }
      if (m.department) {
        card._dept = m.department;
        card.setAttribute("data-dept", m.department);
        activeDelegationCards.set(m.department, card);
      }
      activeDelegationCard = card;

      if (m.agent_name || m.department) {
        const titleEl = card.querySelector(".delegation-title");
        if (titleEl) {
          const dName = m.agent_name || (m.department ? (m.department.charAt(0).toUpperCase() + m.department.slice(1) + " Specialist") : "Departmental Specialist");
          titleEl.innerHTML = `${esc(dName)} <span class="delegation-badge">${esc(m.department || 'autonomous')}</span>`;
        }
        const iconEl = card.querySelector(".delegation-icon");
        if (iconEl && m.department && DEPT_ICONS[m.department]) {
          iconEl.textContent = DEPT_ICONS[m.department];
        }
      }
      if (m.task) {
        const taskEl = card.querySelector(".delegation-task");
        if (taskEl) taskEl.innerHTML = `<strong>Mission:</strong> ${renderMD(m.task)}`;
      }
      const statusEl = card.querySelector(".delegation-status");
      if (statusEl) {
        statusEl.className = "delegation-status running";
        statusEl.textContent = "Working...";
      }
      card.classList.add("running");
      card.classList.remove("done", "fail");
    }
  }

  function appendDelegationStep(m) {
    const card = getDelegationCard(m);
    if (!card) return;
    const stepsBox = card.querySelector(".delegation-steps");
    if (!stepsBox) return;
    stepsBox.style.display = "flex";

    card._stepsCount = (card._stepsCount || 0) + 1;
    const stepRow = document.createElement("div");
    stepRow.className = "delegation-step-row";
    stepRow.id = `step-${m.name}-${Date.now()}`;
    stepRow._toolName = m.name;

    let argDesc = "";
    try {
      const a = typeof m.args === "string" ? JSON.parse(m.args) : m.args;
      argDesc = Object.values(a || {}).map(v => typeof v === "object" ? JSON.stringify(v) : String(v)).join(" · ");
      if (argDesc.length > 60) argDesc = argDesc.slice(0, 58) + "...";
    } catch {}

    stepRow.innerHTML = `
      <div class="delegation-step-left">
        <span class="tl-mark running" style="font-size:0.7rem">↳</span>
        <span class="delegation-step-name">${esc(m.name)}</span>
        ${argDesc ? `<span class="delegation-step-args">(${esc(argDesc)})</span>` : ""}
      </div>
      <span class="tl-tag run">working</span>
    `;

    stepsBox.appendChild(stepRow);
    scroll();
  }

  function updateDelegationStep(m) {
    const card = getDelegationCard(m);
    if (!card) return;
    const stepsBox = card.querySelector(".delegation-steps");
    if (!stepsBox) return;

    const rows = stepsBox.querySelectorAll(".delegation-step-row");
    for (let i = rows.length - 1; i >= 0; i--) {
      if (rows[i]._toolName === m.name && !rows[i]._done) {
        rows[i]._done = true;
        const tag = rows[i].querySelector(".tl-tag");
        if (tag) {
          tag.className = "tl-tag " + (m.ok ? "ok" : "fail");
          tag.textContent = m.ok ? "done" : "fail";
        }
        const mark = rows[i].querySelector(".tl-mark");
        if (mark) mark.classList.remove("running");
        break;
      }
    }
    scroll();
  }

  function handleDelegationDone(m) {
    const card = getDelegationCard(m);
    if (!card) return;
    const isOk = m.status === "done" || m.ok === true || m.status === "completed" || m.status === "success";
    const statusEl = card.querySelector(".delegation-status");
    if (statusEl) {
      statusEl.className = "delegation-status " + (isOk ? "done" : "fail");
      statusEl.textContent = isOk
        ? `✓ Completed (${m.tool_calls || card._stepsCount || 0} tools)`
        : `✗ Issue (${m.status || "failed"})`;
    }
    card.classList.remove("running");
    card.classList.add(isOk ? "done" : "fail");

    // Close any lingering running step tags inside the card
    const stepsBox = card.querySelector(".delegation-steps");
    if (stepsBox) {
      stepsBox.querySelectorAll(".tl-tag.run").forEach(tag => {
        tag.className = "tl-tag " + (isOk ? "ok" : "fail");
        tag.textContent = isOk ? "done" : "fail";
      });
      stepsBox.querySelectorAll(".tl-mark.running").forEach(mark => {
        mark.classList.remove("running");
      });
    }

    if (m.result && !card.querySelector(".delegation-result-snippet")) {
      const body = card.querySelector(".delegation-body");
      if (body) {
        const snippet = document.createElement("div");
        snippet.className = "delegation-result-snippet";
        snippet.textContent = String(m.result).slice(0, 600);
        body.appendChild(snippet);
      }
    }

    if (m.run_id) activeDelegationCards.delete(m.run_id);
    if (card._runId) activeDelegationCards.delete(card._runId);
    if (m.department && activeDelegationCards.get(m.department) === card) activeDelegationCards.delete(m.department);
    if (card._dept && activeDelegationCards.get(card._dept) === card) activeDelegationCards.delete(card._dept);
    if (activeDelegationCard === card) {
      const nextRunning = document.querySelector(".delegation-card.running");
      activeDelegationCard = nextRunning || null;
    }
    scroll();
  }

  function addToolChip(name, args) {
    if (name === "delegate_task" || name === "ask_specialist") {
      let dDept = "";
      let dTask = "";
      try {
        const parsed = typeof args === "string" ? JSON.parse(args) : args;
        dDept = (parsed.department || parsed.name || "").trim().toLowerCase();
        dTask = parsed.task || parsed.mission || parsed.question || "";
      } catch {}
      if (dDept && activeDelegationCards.has(dDept)) {
        const existing = activeDelegationCards.get(dDept);
        if (existing && existing.classList.contains("running")) {
          return;
        }
      }
      createDelegationCard(dDept, dTask);
      return;
    }
    if (name === "delegate_parallel") {
      let tasks = [];
      try {
        const parsed = typeof args === "string" ? JSON.parse(args) : args;
        tasks = parsed.tasks || [];
      } catch {}
      tasks.forEach(t => {
        const d = (t.department || t.name || "").trim().toLowerCase();
        const taskText = t.task || t.mission || "";
        if (d && activeDelegationCards.has(d)) {
          const existing = activeDelegationCards.get(d);
          if (existing && existing.classList.contains("running")) return;
        }
        createDelegationCard(d, taskText);
      });
      return;
    }

    window._lastToolChip = { name, args };
    const wrap = document.createElement("div");
    wrap.className = "tool-chip-wrap";

    const d = document.createElement("div");
    d.className = "tool-chip";
    d.title = "Click to toggle arguments & result";
    d._toolName = name;
    d._toolArgs = args;

    let desc = "";
    try { desc = toolDesc(args); } catch {}

    d.innerHTML = `<div class="tool-log" style="margin:0">${componentString(name, null, desc ? esc(desc) : null, "run")}</div>`;
    wrap.appendChild(d);

    let parsedArgs = null;
    try {
      parsedArgs = typeof args === "string" ? JSON.parse(args) : args;
    } catch {}

    const isEmail = (name || "").includes("email") || (name || "").includes("mail");

    let card = null;
    if (isEmail) {
      card = createEmailPreviewCard(parsedArgs || args);
      card.style.display = "none";
    }
    if (!card) {
      card = createToolDetailsCard(name, args, null);
      card.style.display = "none";
    }

    if (card) wrap.appendChild(card);

    d.addEventListener("click", () => {
      const targetCard = wrap.querySelector(".email-preview-card, .tool-details-card");
      if (targetCard) {
        const isHidden = targetCard.style.display === "none";
        targetCard.style.display = isHidden ? "block" : "none";
      }
      scroll();
    });

    $("msgs").appendChild(wrap);
    scroll();
  }

  function addToolResult(m) {
    if (m.name === "delegate_task" || m.name === "delegate_parallel" || m.name === "ask_specialist") {
      const isOk = m.ok !== false;
      const resText = m.result || m.content || "";
      const runningCards = document.querySelectorAll(".delegation-card.running");
      if (runningCards.length > 0) {
        runningCards.forEach(card => {
          handleDelegationDone({
            status: isOk ? "done" : "fail",
            result: resText,
            tool_calls: card._stepsCount || 0,
            run_id: card._runId,
            department: card._dept,
          });
        });
      }
      return;
    }

    const wraps = $("msgs").querySelectorAll(".tool-chip-wrap");
    const lastWrap = wraps[wraps.length - 1];
    if (lastWrap) {
      const chip = lastWrap.querySelector(".tool-chip");
      if (chip) {
        chip._toolResult = m;
        chip.classList.add(m.cancelled ? "fail" : (m.ok ? "ok" : "fail"));
        if (m.cancelled) chip.classList.add("cancelled");
        // swap the transient "run" tag for the final ok/fail state
        const tag = chip.querySelector(".tl-tag.run");
        if (tag) {
          tag.textContent = m.cancelled ? "cancelled" : (m.ok ? "ok" : "fail");
          tag.className = "tl-tag " + (m.cancelled ? "fail" : (m.ok ? "ok" : "fail"));
        }
      }
      const emailCard = lastWrap.querySelector(".email-preview-card");
      if (emailCard && m.result && typeof m.result === "string") {
        const lines = m.result.split("\n");
        const bodyIdx = lines.findIndex(l => l.trim() === "");
        if (bodyIdx > -1) {
          const bodyText = lines.slice(bodyIdx + 1).join("\n").trim();
          if (bodyText) {
            const bodyEl = emailCard.querySelector(".ep-body");
            if (bodyEl) bodyEl.textContent = bodyText;
          }
        }
      }
    }
  }

  function createEmailPreviewCard(args) {
    let to = "", subject = "", body = "", attachment = "";

    if (typeof args === "object" && args !== null) {
      to = args.to || args.recipient || "";
      subject = args.subject || "";
      body = args.body || args.message || "";
      attachment = args.attachment_path || args.attachment || "";
    } else if (typeof args === "string") {
      try {
        const o = JSON.parse(args);
        to = o.to || o.recipient || "";
        subject = o.subject || "";
        body = o.body || o.message || "";
        attachment = o.attachment_path || o.attachment || "";
      } catch {
        const lines = args.split("\n");
        lines.forEach(l => {
          if (l.toLowerCase().startsWith("to:")) to = l.slice(3).trim();
          else if (l.toLowerCase().startsWith("subject:")) subject = l.slice(8).trim();
          else if (l.toLowerCase().startsWith("body:")) body = l.slice(5).trim();
        });
        if (!body) body = args;
      }
    }

    if (!to && !subject && !body) return null;

    // Mirror the backend: if the model passed literal backslash-n, show real
    // line breaks in the preview too (a\nb\nc → a b c on separate lines).
    if (body) {
      try {
        const un = JSON.parse('"' + body.replace(/'/g, "\\'") + '"');
        if (typeof un === "string") body = un;
      } catch {}
      body = body.replace(/\\n/g, "\n").replace(/\\r/g, "");
    }

    const card = document.createElement("div");
    card.className = "email-preview-card";
    card.innerHTML = `
      <div class="ep-hdr">
        <div class="ep-row"><span class="ep-lbl">✉️ Drafted Email Preview</span></div>
        ${to ? `<div class="ep-row">To: <span>${esc(to)}</span></div>` : ""}
        ${subject ? `<div class="ep-row">Subject: <span>${esc(subject)}</span></div>` : ""}
        ${attachment ? `<div class="ep-row">Attachment: <span>📎 ${esc(attachment)}</span></div>` : ""}
      </div>
      <div class="ep-body">${esc(body || "(no content yet)")}</div>
    `;
    return card;
  }

  function createToolDetailsCard(name, args, result) {
    const card = document.createElement("div");
    card.className = "tool-details-card";

    let argsStr = "";
    try { argsStr = typeof args === "string" ? args : JSON.stringify(args, null, 2); } catch { argsStr = String(args); }

    let resStr = "";
    if (result) {
      resStr = typeof result.result === "string" ? result.result : JSON.stringify(result.result, null, 2);
    }

    card.innerHTML = `
      <div class="tdc-hdr"><strong>What Zenith ran:</strong> ${esc(name)}</div>
      <div class="tdc-sec"><strong>Arguments:</strong><pre>${esc(argsStr)}</pre></div>
      ${resStr ? `<div class="tdc-sec"><strong>Result:</strong><pre>${esc(resStr)}</pre></div>` : ""}
    `;
    return card;
  }

  function toolDesc(args) {
    if (!args) return "";
    let o;
    try { o = typeof args === "string" ? JSON.parse(args) : args; } catch { return ""; }
    if (!o || typeof o !== "object") return "";
    if (o.department && o.task) {
      const t = String(o.task).length > 60 ? String(o.task).slice(0, 60) + "…" : o.task;
      return `[${o.department}] ${t}`;
    }
    const key = Object.keys(o)[0];
    if (!key) return "";
    const v = o[key];
    const s = typeof v === "string" ? v : JSON.stringify(v);
    return s && s.length > 70 ? s.slice(0, 70) + "…" : (s || "");
  }

  function scroll() {
    requestAnimationFrame(() => {
      const c = $("chat");
      if (!c) return;
      const distFromBottom = c.scrollHeight - c.scrollTop - c.clientHeight;
      const btn = $("scroll-bottom-btn");
      const badge = $("scroll-new-badge");
      if (distFromBottom > 160) {
        if (btn) btn.style.display = "inline-flex";
        if (badge) badge.style.display = "inline";
        return;
      }
      c.scrollTop = c.scrollHeight;
    });
  }

  function esc(s) {
    return s
      ? String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      : "";
  }

  /* small markdown-lite renderer (sanitized) */
  function renderMD(text) {
    if (!text) return "";

    // Protect Google Maps & God's Eye View iframes so they render as interactive HTML widgets
    const mapIframes = [];
    let processed = text.replace(/(?:```[a-z]*\s*)?(<iframe\b[^>]*src=["'](https:\/\/www\.google\.com\/maps\/embed[^"']*|\/gev[^"']*|https?:\/\/[^"']*(?:4173|\/gev)[^"']*)["'][^>]*>[\s\S]*?<\/iframe>)(?:\s*```)?/gi, (_, iframeHtml, src) => {
      const idx = mapIframes.length;
      const isGev = src.includes("/gev") || src.includes("4173");
      mapIframes.push({ src, isGev });
      return `___ZENITH_MAP_IFRAME_${idx}___`;
    });

    // Protect fenced code blocks with language support & copy button FIRST
    const codeBlocks = [];
    processed = processed.replace(/```([a-zA-Z0-9_+-]+)?\s*[\r\n]([\s\S]*?)```/g, (_, lang, code) => {
      const idx = codeBlocks.length;
      const l = (lang || "code").toLowerCase();
      codeBlocks.push({ lang: l, code: (code || "").trimEnd() });
      return `___ZENITH_CODE_BLOCK_${idx}___`;
    });
    processed = processed.replace(/```([\s\S]*?)```/g, (_, code) => {
      const idx = codeBlocks.length;
      codeBlocks.push({ lang: "code", code: (code || "").trimEnd() });
      return `___ZENITH_CODE_BLOCK_${idx}___`;
    });

    let out = esc(processed);

    // inline code
    out = out.replace(/`([^`]+)`/g, "<code>$1</code>");

    // bold + italic
    out = out.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    out = out.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");

    // headings
    out = out.replace(/^(#{1,6})\s+(.+)$/gm, (_, h, txt) => `<strong style="font-family:var(--mono);letter-spacing:.1em;text-transform:uppercase;font-size:.8em">${txt}</strong>`);

    // bullet / numbered lists
    out = out.replace(/^\s*[-*]\s+(.+)$/gm, (_, it) => `<span style="display:block;padding-left:12px;font-family:var(--mono)">• ${it}</span>`);
    out = out.replace(/^\s*(\d+)\.\s+(.+)$/gm, (_, n, it) => `<span style="display:block;padding-left:12px;font-family:var(--mono)">${n}. ${it}</span>`);

    // images (markdown ![alt](url))
    out = out.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g,
      (_, alt, src) => `<img src="${esc(src)}" alt="${esc(alt)}" style="max-width:100%;max-height:400px;border-radius:10px;margin:8px 0;display:block;border:1px solid var(--line-2);box-shadow:0 6px 20px rgba(0,0,0,0.35)"/>`);

    // links (only http/https/relative, sanitized)
    out = out.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+|\/static\/[^)\s]+)\)/g,
      (_, t, u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${t}</a>`);

    // hr
    out = out.replace(/^\s*(---+|\*\*\*+)\s*$/gm, "<hr/>");

    // newlines
    out = out.replace(/\n/g, "<br/>");

    // Restore protected Google Maps & God's Eye View iframes
    mapIframes.forEach((item, idx) => {
      const src = typeof item === "string" ? item : item.src;
      const isGev = typeof item === "object" && item.isGev;
      const wrapClass = isGev ? "map-embed-wrapper gev-embed-wrapper" : "map-embed-wrapper";
      const height = isGev ? "420px" : "380px";
      const gevBar = isGev ? `
        <div class="gev-embed-bar">
          <div class="gev-embed-title">
            <span class="gev-badge-dot"></span>
            <span>GOD'S EYE VIEW 3D</span>
          </div>
          <div class="gev-embed-actions">
            <button type="button" class="gev-fullscreen-btn" onclick="window.toggleGevFullscreen && window.toggleGevFullscreen(this)" title="Toggle Full Screen">
              <svg class="gev-btn-icon" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
              <span class="gev-btn-label">Full Screen</span>
            </button>
          </div>
        </div>` : "";
      const htmlEmbed = `<div class="${wrapClass}">${gevBar}<iframe src="${esc(src)}" style="width:100%;height:${height};border:0;display:block;" loading="lazy" allowfullscreen referrerpolicy="no-referrer-when-downgrade"></iframe></div>`;
      out = out.replace(esc(`___ZENITH_MAP_IFRAME_${idx}___`), htmlEmbed);
      out = out.replace(`___ZENITH_MAP_IFRAME_${idx}___`, htmlEmbed);
    });

    // Restore protected code blocks with modern header, badge & copy button
    codeBlocks.forEach((b, idx) => {
      const codeId = "code-" + Math.random().toString(36).slice(2, 9);
      const htmlBlock = `<div class="code-block-container">
        <div class="code-block-header">
          <span class="code-lang-tag"><span>💻</span>${esc(b.lang)}</span>
          <button type="button" class="code-copy-btn" data-target="${codeId}">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
            <span>Copy</span>
          </button>
        </div>
        <pre><code id="${codeId}">${esc(b.code)}</code></pre>
      </div>`;
      out = out.replace(`___ZENITH_CODE_BLOCK_${idx}___`, htmlBlock);
      out = out.replace(esc(`___ZENITH_CODE_BLOCK_${idx}___`), htmlBlock);
    });

    return out;
  }

  /* ── file upload & attachments ──────────────────────── */

  let attachedFiles = [];
  let isUploadingFile = false;

  function formatFileSize(bytes) {
    if (!bytes || bytes <= 0) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(1024));
    return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + " " + units[i];
  }

  function renderAttachments() {
    const tray = $("attachment-tray");
    if (!tray) return;
    if (!attachedFiles.length && !isUploadingFile) {
      tray.style.display = "none";
      tray.innerHTML = "";
      return;
    }
    tray.style.display = "flex";
    let html = attachedFiles.map((f, idx) => {
      let iconHtml = "";
      if (f.is_image) {
        iconHtml = `<img class="attach-badge-thumb" src="${esc(f.url)}" alt="${esc(f.filename)}" />`;
      } else {
        const ext = (f.filename || "").split(".").pop().toUpperCase().slice(0, 4) || "FILE";
        iconHtml = `<div class="attach-badge-icon">${esc(ext)}</div>`;
      }
      const sizeStr = f.size ? formatFileSize(f.size) : "";
      return `
        <div class="attach-badge">
          ${iconHtml}
          <div class="attach-badge-info">
            <span class="attach-badge-name" title="${esc(f.filename)}">${esc(f.filename)}</span>
            ${sizeStr ? `<span class="attach-badge-meta">${esc(sizeStr)}</span>` : ""}
          </div>
          <button type="button" class="rm-btn" data-idx="${idx}" title="Remove file" aria-label="Remove">✕</button>
        </div>
      `;
    }).join("");

    if (isUploadingFile) {
      html += `
        <div class="attach-badge" style="opacity:0.75">
          <div class="attach-badge-icon" style="background:rgba(99,102,241,0.25)">⏳</div>
          <div class="attach-badge-info">
            <span class="attach-badge-name">Uploading…</span>
            <span class="attach-badge-meta">Processing file</span>
          </div>
        </div>
      `;
    }

    tray.innerHTML = html;

    tray.querySelectorAll(".rm-btn").forEach(btn => {
      btn.onclick = (e) => {
        e.stopPropagation();
        const idx = parseInt(btn.dataset.idx, 10);
        attachedFiles.splice(idx, 1);
        renderAttachments();
      };
    });
  }

  async function uploadFileObj(file, customName) {
    if (!file) return;
    isUploadingFile = true;
    renderAttachments();

    const formData = new FormData();
    formData.append("file", file, customName || file.name || "attachment");
    try {
      const res = await fetch("/api/upload", { method: "POST", body: formData });
      if (res.ok) {
        const data = await res.json();
        if (data.status === "ok") {
          attachedFiles.push(data);
        } else {
          console.warn("[zenith] Upload error:", data.message);
          toast(data.message || "Failed to upload file", "warn");
        }
      } else {
        toast("Upload failed with server error", "warn");
      }
    } catch (err) {
      console.warn("Upload failed:", err);
      toast("Could not upload file — network error", "warn");
    } finally {
      isUploadingFile = false;
      renderAttachments();
    }
  }

  function initAttachmentHandlers() {
    const attachBtn = $("attach-btn");
    const attachDropup = $("attach-dropup");
    const optCamera = $("attach-opt-camera");
    const optGallery = $("attach-opt-gallery");
    const optDoc = $("attach-opt-doc");

    const inputCamera = $("attach-input-camera");
    const inputGallery = $("attach-input-gallery");
    const inputDoc = $("attach-input-doc");
    const fileInput = $("file-input");
    const inp = $("inp");

    function toggleAttachDropup(open) {
      if (!attachDropup || !attachBtn) return;
      const isOpen = typeof open === "boolean" ? open : !attachDropup.classList.contains("open");
      if (isOpen) {
        attachDropup.classList.add("open");
        attachBtn.classList.add("active");
        attachBtn.setAttribute("aria-expanded", "true");
      } else {
        attachDropup.classList.remove("open");
        attachBtn.classList.remove("active");
        attachBtn.setAttribute("aria-expanded", "false");
      }
    }

    if (attachBtn) {
      attachBtn.onclick = (e) => {
        e.stopPropagation();
        toggleAttachDropup();
      };
    }

    // Close on click outside
    document.addEventListener("click", (e) => {
      if (attachDropup && attachDropup.classList.contains("open")) {
        const wrapper = $("attach-wrapper");
        if (wrapper && !wrapper.contains(e.target)) {
          toggleAttachDropup(false);
        }
      }
    });

    // Close on Escape
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && attachDropup && attachDropup.classList.contains("open")) {
        toggleAttachDropup(false);
      }
    });

    // Option: Gallery
    if (optGallery && inputGallery) {
      optGallery.onclick = () => {
        toggleAttachDropup(false);
        inputGallery.click();
      };
      inputGallery.onchange = (e) => {
        const files = Array.from(e.target.files || []);
        files.forEach(f => uploadFileObj(f));
        inputGallery.value = "";
      };
    }

    // Option: Documents
    if (optDoc && inputDoc) {
      optDoc.onclick = () => {
        toggleAttachDropup(false);
        inputDoc.click();
      };
      inputDoc.onchange = (e) => {
        const files = Array.from(e.target.files || []);
        files.forEach(f => uploadFileObj(f));
        inputDoc.value = "";
      };
    }

    // Option: Camera
    if (optCamera) {
      optCamera.onclick = () => {
        toggleAttachDropup(false);
        openCameraSnapshot();
      };
    }
    if (inputCamera) {
      inputCamera.onchange = (e) => {
        const files = Array.from(e.target.files || []);
        files.forEach(f => uploadFileObj(f));
        inputCamera.value = "";
      };
    }
    if (fileInput) {
      fileInput.onchange = (e) => {
        const files = Array.from(e.target.files || []);
        files.forEach(f => uploadFileObj(f));
        fileInput.value = "";
      };
    }

    // Interactive Camera Snapshot Flow
    let snapStream = null;
    let snapFacing = "user";

    async function openCameraSnapshot() {
      const modal = $("camera-snap-modal");
      const video = $("camera-snap-video");
      const preview = $("camera-snap-preview");
      const loading = $("camera-snap-loading");
      const liveControls = $("camera-snap-live-controls");
      const reviewControls = $("camera-snap-review-controls");
      const closeBtn = $("camera-snap-close");
      const backdrop = $("camera-snap-backdrop");
      const shutterBtn = $("camera-shutter-btn");
      const retakeBtn = $("camera-snap-retake");
      const confirmBtn = $("camera-snap-confirm");
      const flipBtn = $("camera-snap-flip");
      const canvas = $("camera-snap-canvas");

      if (!modal || !video) {
        if (inputCamera) inputCamera.click();
        return;
      }

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        if (inputCamera) inputCamera.click();
        return;
      }

      modal.style.display = "flex";
      video.style.display = "block";
      if (preview) preview.style.display = "none";
      if (loading) loading.style.display = "flex";
      if (liveControls) liveControls.style.display = "flex";
      if (reviewControls) reviewControls.style.display = "none";

      function closeSnapModal() {
        if (snapStream) {
          snapStream.getTracks().forEach(t => t.stop());
          snapStream = null;
        }
        modal.style.display = "none";
      }

      if (closeBtn) closeBtn.onclick = closeSnapModal;
      if (backdrop) backdrop.onclick = closeSnapModal;

      async function startLiveCam(facing) {
        if (snapStream) {
          snapStream.getTracks().forEach(t => t.stop());
          snapStream = null;
        }
        if (loading) loading.style.display = "flex";
        try {
          snapStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: facing, width: { ideal: 1280 }, height: { ideal: 720 } },
            audio: false
          });
          video.srcObject = snapStream;
          await video.play();
          if (loading) loading.style.display = "none";
        } catch (err) {
          console.warn("[zenith] Camera snapshot failed:", err);
          closeSnapModal();
          if (inputCamera) inputCamera.click();
        }
      }

      await startLiveCam(snapFacing);

      if (flipBtn) {
        flipBtn.style.display = "inline-flex";
        flipBtn.onclick = () => {
          snapFacing = (snapFacing === "user") ? "environment" : "user";
          startLiveCam(snapFacing);
        };
      }

      let capturedBlob = null;

      if (shutterBtn && canvas) {
        shutterBtn.onclick = () => {
          if (!video.videoWidth) return;
          canvas.width = video.videoWidth;
          canvas.height = video.videoHeight;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
          canvas.toBlob((blob) => {
            capturedBlob = blob;
            const dataUrl = canvas.toDataURL("image/jpeg", 0.92);
            if (preview) {
              preview.src = dataUrl;
              preview.style.display = "block";
            }
            video.style.display = "none";
            if (liveControls) liveControls.style.display = "none";
            if (reviewControls) reviewControls.style.display = "flex";
          }, "image/jpeg", 0.92);
        };
      }

      if (retakeBtn) {
        retakeBtn.onclick = () => {
          capturedBlob = null;
          if (preview) preview.style.display = "none";
          video.style.display = "block";
          if (liveControls) liveControls.style.display = "flex";
          if (reviewControls) reviewControls.style.display = "none";
        };
      }

      if (confirmBtn) {
        confirmBtn.onclick = () => {
          if (capturedBlob) {
            const snapFile = new File([capturedBlob], `photo_${Date.now()}.jpg`, { type: "image/jpeg" });
            uploadFileObj(snapFile);
          }
          closeSnapModal();
        };
      }
    }

    if (inp) {
      // Paste files (e.g. screenshots from clipboard)
      inp.addEventListener("paste", (e) => {
        const items = Array.from((e.clipboardData || {}).items || []);
        const fileItems = items.filter(item => item.kind === "file");
        if (fileItems.length) {
          fileItems.forEach(item => {
            const blob = item.getAsFile();
            if (blob) uploadFileObj(blob, `pasted_${Date.now()}.png`);
          });
        }
      });

      // Drag and drop files
      const inputArea = document.querySelector(".input-area");
      if (inputArea) {
        inputArea.addEventListener("dragover", (e) => {
          e.preventDefault();
          inputArea.style.borderColor = "var(--violet)";
        });
        inputArea.addEventListener("dragleave", (e) => {
          e.preventDefault();
          inputArea.style.borderColor = "";
        });
        inputArea.addEventListener("drop", (e) => {
          e.preventDefault();
          inputArea.style.borderColor = "";
          const files = Array.from(e.dataTransfer.files || []);
          files.forEach(f => uploadFileObj(f));
        });
      }
    }
  }

  /* ── actions ────────────────────────────────────────── */

  /* Outgoing message queue — lets Zenith send several messages in a row.
     Turns stay serial on the server (no interleaving), but typing a new
     message while one is still being answered enqueues it instead of
     silently dropping it. A pump flushes one at a time. */
  let outQueue = [];

  function send(text, opts) {
    opts = opts || {};
    const t = (text || "").trim();
    if (!t && !attachedFiles.length) return;
    if (!ws || ws.readyState !== 1) {
      pendingPrompt = text;
      initWS();
      return;
    }
    outQueue.push({ text: t, opts });
    pumpOutQueue();

    // Without a new message, nothing else to do — the pump handles the turn.
    turnStartTs = Date.now();
  }

  function pumpOutQueue() {
    if (outQueue.length === 0 || awaiting) return;
    const item = outQueue.shift();
    const text = item.text;
    const opts = item.opts || {};
    awaiting = true;
    setGenerating(true);
    // Inactivity watchdog: resets on every incoming token/tool step from the server,
    // only firing if there is absolute silence for WATCHDOG_INACTIVITY_MS (120s).
    refreshWatchdog();
    hideWelcome();

    let fullPrompt = text || "Please inspect the attached file/image.";
    let filesToSend = [];

    if (attachedFiles.length) {
      filesToSend = attachedFiles.slice();
      const fileNotes = attachedFiles.map(f =>
        `- ${f.is_image ? 'Image' : 'File'}: ${f.filename} (saved path: "${f.path}", url: "${f.url}")`
      ).join("\n");
      fullPrompt = `${fullPrompt}\n\n[User Attached Files & Images]:\n${fileNotes}`;

      const previewsHtml = attachedFiles.map(f => {
        if (f.is_image) {
          return `<div style="margin-top:8px"><img src="${esc(f.url)}" style="max-width:280px;max-height:220px;border-radius:10px;border:1px solid var(--line);display:block;box-shadow:0 4px 14px rgba(0,0,0,0.25);"/></div>`;
        } else {
          return `<div style="margin-top:6px;font-size:0.8rem;color:var(--ink);background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);padding:5px 12px;border-radius:10px;display:inline-flex;align-items:center;gap:8px;"><span style="font-size:1.1rem">📄</span> <span style="font-weight:500">${esc(f.filename)}</span></div>`;
        }
      }).join("");

      addBubble("user", `<p class="r-line">${esc(text || "Attached files:")}</p>${previewsHtml}`);

      attachedFiles = [];
      renderAttachments();
    } else {
      addBubble("user", `<p class="r-line">${esc(text)}</p>`);
    }

    // Tag the WS message so Zenith knows the turn arrived by voice — it can
    // tailor its reply (and the memory layer can attribute it correctly).
    const msg = { type: "chat", prompt: fullPrompt, files: filesToSend };
    if (opts.voice) {
      msg.voice = true;
      // Keep the transcript honest for the user.
      const lastBubble = $("msgs").querySelector(".mg.user:last-of-type .r-line");
      if (lastBubble && !lastBubble.textContent.includes("🎙")) {
        lastBubble.textContent = "🎙 " + lastBubble.textContent;
      }
    }
    ws.send(JSON.stringify(msg));
    $("inp").value = "";
    $("inp").style.height = "auto";
  }

  async function clearConversation() {
    try { await fetch("/api/clear", { method: "POST" }); } catch {}
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "clear" }));
    $("msgs").innerHTML = resetWelcomeHTML();
    typingEl = null;
    streamBuffer = "";
    ackPendingDivider = false;
    awaiting = false;
    setGenerating(false);
    turnStartTs = null;
  }

  function clearChatDOM() {
    $("msgs").innerHTML = resetWelcomeHTML();
    typingEl = null;
    streamBuffer = "";
    ackPendingDivider = false;
    awaiting = false;
    setGenerating(false);
    turnStartTs = null;
    clearConfirm();
    cancelTurn();
  }

  /* Welcome block is a plain status header — rebuild it after clears. */
  function resetWelcomeHTML() {
    const h = new Date(Date.now() + 330 * 60000).getUTCHours();
    let g = "Good evening";
    if (h >= 5 && h < 12) g = "Good morning";
    else if (h >= 12 && h < 17) g = "Good afternoon";
    else if (h >= 17 || h < 4) g = "Good evening";
    else g = "Good morning";
    const rawName = window._zenithUserName || (currentUser && (currentUser.name || currentUser.username)) || "Friend";
    const uName = rawName ? (rawName.charAt(0).toUpperCase() + rawName.slice(1)) : "Friend";

    if (window._lastBriefingSummary) {
      const clean = window._lastBriefingSummary.trim();
      const stripped = clean.replace(/^(Good\s+(morning|afternoon|evening|night)|Hello)[^.]*\.\s*/i, "");
      const targetSummary = (stripped && stripped.length > 10) ? stripped : clean;
      scheduleSummaryAnimation(targetSummary, 1800);
    }

    return `<div class="welcome" id="welcome">
  <div class="wlcm-title" id="wlcm-title"><span class="wlcm-greet" id="wlcm-greet">${g}</span><span class="wlcm-soft" id="wlcm-name">, ${esc(uName)}</span></div>
  <p class="wlcm-subtitle" id="wlcm-subtitle">How can I help you today?</p>
</div>`;
  }

  /* ── state / side panels ────────────────────────────── */

  function finishStateSoon() {
    setTimeout(() => loadState(), 800);
  }

  async function loadState() {
    const stateR = await fetch("/api/state").catch(() => null);
    if (stateR && stateR.ok) {
      const d = await stateR.json();
      if (d) {
        renderAgenda(d);
        if (d.graph) {
          window._lastGraphData = d.graph;
          renderGraph(d.graph);
        }
      }
    }
  }

  function renderAgenda(d) {
    renderTodos(d.todos || []);
    renderEvents(d.events || []);
    renderNotes(d.notes || []);
    if (d.graph) {
      window._lastGraphData = d.graph;
      renderGraph(d.graph);
    }
  }

  function renderTodos(rows) {
    const box = $("todo-list");
    if (!box) return;
    const cleanRows = (rows || []).filter(t => t.title && !t.title.toLowerCase().includes("deepseek"));
    if (!cleanRows.length) { box.innerHTML = `<div class="placeholder">None.</div>`; return; }
    box.innerHTML = cleanRows.slice(0, 12).map((t) =>
      `<div class="agenda-item"><span class="agenda-tag">${t.done ? "✓" : "•"}</span><span class="agenda-text ${t.done ? "done" : ""}">${esc(t.title)}</span></div>`
    ).join("");
  }

  function renderEvents(rows) {
    const box = $("event-list");
    if (!box) return;
    const now = new Date();
    const curYear = now.getFullYear();
    const curMonth = now.getMonth();
    const curDate = now.getDate();

    const thisMonthEvents = (rows || []).filter((e) => {
      if (!e.at) return true;
      try {
        const d = new Date(e.at);
        if (isNaN(d.getTime())) return true;
        // Must be in current month & year
        if (d.getFullYear() !== curYear || d.getMonth() !== curMonth) {
          return false;
        }
        // If it's an all-day date string (e.g. "YYYY-MM-DD"), include if today or future day of the month
        if (e.at.length <= 10) {
          return d.getDate() >= curDate;
        }
        // For timed events: must not be in the past (allow 15 min grace window for active events)
        return d.getTime() >= (now.getTime() - 15 * 60 * 1000);
      } catch {
        return true;
      }
    });

    if (!thisMonthEvents.length) { box.innerHTML = `<div class="placeholder">Nothing scheduled for this month.</div>`; return; }
    box.innerHTML = thisMonthEvents.slice(0, 8).map((e) => {
      let time = "";
      try { time = new Date(e.at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); } catch {}
      return `<div class="agenda-item"><span class="ev-time">${time}</span><span class="agenda-text">${esc(e.title)}</span></div>`;
    }).join("");
  }

  function renderNotes(rows) {
    const box = $("notes-list");
    if (!box) return;
    if (!rows.length) { box.innerHTML = `<div class="placeholder">None yet.</div>`; return; }
    box.innerHTML = rows.slice(0, 10).map((n) =>
      `<div class="agenda-item note-item"><span class="agenda-text">${esc(n.title)}</span><span class="agenda-k">${esc(n.updated_at || "")}</span></div>`
    ).join("");
  }

  /* ── Live Terminal Feed & Drawer ────────────────────────────────────────────── */
  function logTerminal(msg, type = "sys") {
    /* Kept as a quiet trace — Zenith prefers to show work inline, not in logs. */
    const body = $("term-body");
    if (!body) return;
    const timeStr = new Date().toLocaleTimeString();
    const line = document.createElement("div");
    line.className = `term-line ${type}`;
    line.textContent = `[${timeStr}] ${msg}`;
    body.appendChild(line);

    while (body.childNodes.length > 250) {
      body.removeChild(body.firstChild);
    }

    const chk = $("term-autoscroll-chk");
    if (!chk || chk.checked) {
      body.scrollTop = body.scrollHeight;
    }
  }

  function wireTerminalUI() {
    const termBtn = $("term-btn");
    const drawer = $("term-drawer");
    const closeBtn = $("term-close-btn");
    const clearBtn = $("term-clear-btn");

    if (termBtn && drawer) {
      termBtn.addEventListener("click", () => {
        const isHidden = drawer.style.display === "none";
        drawer.style.display = isHidden ? "flex" : "none";
      });
    }
    if (closeBtn && drawer) {
      closeBtn.addEventListener("click", () => {
        drawer.style.display = "none";
      });
    }
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        const body = $("term-body");
        if (body) body.innerHTML = `<div class="term-line sys">[SYSTEM] Operational log cleared.</div>`;
      });
    }
  }

  /* ── Operating Layer, Camera Vision & Unified Context UI ───────────────────── */
  function wireOperatingLayerUI() {
    const camBtn = $("camera-btn");
    const camModal = $("camera-modal");
    const camCloseBtn = $("camera-close-btn");
    const camStartBtn = $("cam-start-feed-btn");
    const camVideo = $("cam-video");
    const camPlaceholder = $("cam-placeholder");
    const camLed = $("cam-led");
    const camPresenceBadge = $("cam-presence-text");
    const camHudSource = $("cam-hud-source");
    const camHudGesture = $("cam-hud-gesture");
    const camAnalysisResult = $("cam-analysis-result");
    const camQaInput = $("cam-qa-input");
    const camQaSubmit = $("cam-qa-submit");

    let camStream = null;
    let camSource = "camera";
    let visionPollTimer = null;

    function openCameraModal() {
      if (camModal) camModal.style.display = "flex";
      syncPrivacyStatus();
    }
    function closeCameraModal() {
      if (camModal) camModal.style.display = "none";
      if (camStream) {
        camStream.getTracks().forEach(t => t.stop());
        camStream = null;
      }
      if (camVideo) camVideo.style.display = "none";
      if (camPlaceholder) camPlaceholder.style.display = "flex";
      if (camLed) camLed.classList.remove("live");
      if (visionPollTimer) { clearInterval(visionPollTimer); visionPollTimer = null; }
      fetch("/api/vision/camera/stop", { method: "POST" }).catch(() => {});
    }

    if (camBtn) camBtn.addEventListener("click", openCameraModal);
    if (camCloseBtn) camCloseBtn.addEventListener("click", closeCameraModal);

    if (camStartBtn) {
      camStartBtn.addEventListener("click", async () => {
        camStartBtn.textContent = "Connecting...";
        try {
          if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            try {
              camStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
              if (camVideo) {
                camVideo.srcObject = camStream;
                camVideo.style.display = "block";
              }
              if (camPlaceholder) camPlaceholder.style.display = "none";
            } catch (e) {
              console.warn("Browser camera access prompt declined or unsupported; using server feed", e);
            }
          }
          await fetch("/api/vision/camera/start", { method: "POST" });
          if (camLed) camLed.classList.add("live");
          if (camPresenceBadge) camPresenceBadge.textContent = "User Present";
          if (camHudGesture) camHudGesture.textContent = "GESTURE: TRACKING";

          if (!visionPollTimer) {
            visionPollTimer = setInterval(async () => {
              try {
                const res = await fetch("/api/vision/detect", { method: "POST" });
                const data = await res.json();
                if (data.ok && data.detection) {
                  const g = data.detection.gesture || "none";
                  if (camHudGesture) camHudGesture.textContent = `GESTURE: ${g.toUpperCase()}`;
                  if (camPresenceBadge) {
                    camPresenceBadge.textContent = data.detection.presence ? "User Present" : "Away";
                  }
                  if (g === "thumbs_up") {
                    const confirmDock = $("confirm-dock");
                    if (confirmDock && confirmDock.style.display !== "none") {
                      const approveBtn = $("confirm-allow");
                      if (approveBtn) approveBtn.click();
                    }
                  }
                }
              } catch (_) {}
            }, 3000);
          }
        } catch (err) {
          showToast("Camera activation error: " + err.message, "err");
        } finally {
          camStartBtn.textContent = "Activate Camera";
        }
      });
    }

    const btnSrcWebcam = $("cam-src-webcam");
    const btnSrcScreen = $("cam-src-screen");
    if (btnSrcWebcam && btnSrcScreen) {
      btnSrcWebcam.addEventListener("click", () => {
        btnSrcWebcam.classList.add("active");
        btnSrcScreen.classList.remove("active");
        camSource = "camera";
        if (camHudSource) camHudSource.textContent = "SOURCE: WEBCAM";
      });
      btnSrcScreen.addEventListener("click", () => {
        btnSrcScreen.classList.add("active");
        btnSrcWebcam.classList.remove("active");
        camSource = "screen";
        if (camHudSource) camHudSource.textContent = "SOURCE: SCREEN";
      });
    }

    const actQr = $("cam-act-qr");
    const actDescribe = $("cam-act-describe");
    const actGesture = $("cam-act-gesture");

    if (actQr) {
      actQr.addEventListener("click", async () => {
        if (camAnalysisResult) {
          camAnalysisResult.style.display = "block";
          camAnalysisResult.textContent = "Scanning for QR / barcodes...";
        }
        try {
          const res = await fetch("/api/vision/scan_qr", { method: "POST" });
          const data = await res.json();
          if (data.ok && data.result && data.result.detected) {
            camAnalysisResult.textContent = `[QR Code Payload]:\n${data.result.data}`;
          } else {
            camAnalysisResult.textContent = "No QR code detected in the frame.";
          }
        } catch (e) {
          if (camAnalysisResult) camAnalysisResult.textContent = "QR scan error: " + e.message;
        }
      });
    }

    if (actDescribe) {
      actDescribe.addEventListener("click", () => {
        if (camQaInput) camQaInput.value = "Describe what is visible in detail.";
        if (camQaSubmit) camQaSubmit.click();
      });
    }

    if (actGesture) {
      actGesture.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/vision/detect", { method: "POST" });
          const data = await res.json();
          if (camAnalysisResult) {
            camAnalysisResult.style.display = "block";
            camAnalysisResult.textContent = `[Vision Detection]:\nPresence: ${data.detection?.presence ? 'Present' : 'Away'}\nGesture: ${data.detection?.gesture || 'none'}`;
          }
        } catch (e) {
          if (camAnalysisResult) camAnalysisResult.textContent = "Detection error: " + e.message;
        }
      });
    }

    async function submitVisionQa() {
      const q = (camQaInput?.value || "").trim();
      if (!q) return;
      if (camAnalysisResult) {
        camAnalysisResult.style.display = "block";
        camAnalysisResult.textContent = `Analyzing ${camSource}...`;
      }
      try {
        const res = await fetch("/api/vision/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: q, source: camSource })
        });
        const data = await res.json();
        if (data.ok && data.result) {
          camAnalysisResult.textContent = data.result.analysis || "Analysis complete.";
        } else {
          camAnalysisResult.textContent = "Visual QA error: " + (data.result?.error || "Unable to analyze.");
        }
      } catch (err) {
        if (camAnalysisResult) camAnalysisResult.textContent = "Inference failed: " + err.message;
      }
    }

    if (camQaSubmit) camQaSubmit.addEventListener("click", submitVisionQa);
    if (camQaInput) {
      camQaInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); submitVisionQa(); }
      });
    }

    // ── Context Drawer Wiring ──
    const ctxBtn = $("context-btn");
    const ctxDrawer = $("context-drawer");
    const ctxCloseBtn = $("context-drawer-close-btn");
    const ctxGhostBtn = $("ctx-ghost-toggle-btn");

    function toggleContextDrawer(targetTab) {
      if (!ctxDrawer) return;
      const isHidden = ctxDrawer.style.display === "none";
      if (isHidden) {
        ctxDrawer.style.display = "flex";
        if (ctxBtn) ctxBtn.classList.add("active");
        const termDrawer = $("term-drawer");
        if (termDrawer) termDrawer.style.display = "none";
        if (targetTab) switchContextTab(targetTab);
        refreshContextDrawer();
      } else {
        const activeTab = document.querySelector(".ctx-tab.active");
        if (targetTab && activeTab && activeTab.dataset.tab !== targetTab) {
          switchContextTab(targetTab);
        } else {
          ctxDrawer.style.display = "none";
          if (ctxBtn) ctxBtn.classList.remove("active");
        }
      }
    }
    window.toggleContextDrawer = toggleContextDrawer;

    if (ctxBtn) ctxBtn.addEventListener("click", () => toggleContextDrawer("ctx-overview"));
    if (ctxCloseBtn) ctxCloseBtn.addEventListener("click", () => {
      if (ctxDrawer) ctxDrawer.style.display = "none";
      if (ctxBtn) ctxBtn.classList.remove("active");
    });

    function switchContextTab(tabId) {
      document.querySelectorAll(".ctx-tab").forEach(t => {
        t.classList.toggle("active", t.dataset.tab === tabId);
      });
      document.querySelectorAll(".ctx-pane").forEach(p => {
        p.style.display = p.id === ("pane-" + tabId) ? "flex" : "none";
      });
      if (tabId === "ctx-agents") loadAgentsPane();
      if (tabId === "ctx-activity") loadActivityPane();
      if (tabId === "ctx-memory") loadMemoryPane();
      if (tabId === "ctx-privacy") loadPrivacyPane();
      if (tabId === "ctx-overview") loadOverviewPane();
    }

    document.querySelectorAll(".ctx-tab").forEach(tab => {
      tab.addEventListener("click", () => switchContextTab(tab.dataset.tab));
    });

    let _allSystemTools = [];
    let _selectedToolsForForge = new Set();
    let _agentForgeInitialized = false;

    async function loadAgentsPane() {
      const deptsList = $("ctx-depts-list");
      const customList = $("ctx-custom-list");
      const runsList = $("ctx-runs-list");
      if (!deptsList) return;

      if (!_agentForgeInitialized) {
        initAgentForge();
        _agentForgeInitialized = true;
      }

      try {
        const resp = await fetch("/api/agents/roster");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        const roster = data.roster || [];
        const runs = data.active_runs || [];

        const builtins = roster.filter(a => a.type === "builtin");
        const custom = roster.filter(a => a.type === "custom");

        if ($("ctx-stat-depts")) $("ctx-stat-depts").textContent = String(builtins.length);
        if ($("ctx-stat-custom")) $("ctx-stat-custom").textContent = String(custom.length);
        const totalTools = roster.reduce((acc, a) => acc + (a.tools ? a.tools.length : 0), 0);
        if ($("ctx-stat-tools")) $("ctx-stat-tools").textContent = String(totalTools);

        const deptIcons = {
          communication: "📬",
          coding: "💻",
          hr: "👥",
          research: "🔍",
          operations: "⚙️",
          productivity: "🗓️",
          creative: "🎨",
          media: "🎬",
          utility: "🔌",
        };


        deptsList.innerHTML = builtins.map(d => {
          const icon = deptIcons[d.id] || "🤖";
          const tools = d.tools || [];
          return `
            <div class="dept-card" data-dept="${esc(d.id)}">
              <div class="dept-card-hdr">
                <span class="dept-card-title">${icon} ${esc(d.name)}</span>
                <span class="dept-card-badge">${tools.length} capabilities</span>
              </div>
              <div class="dept-card-desc">${esc(d.description)}</div>
              <div class="dept-actions">
                <button type="button" class="dept-tools-toggle" data-target="tools-${esc(d.id)}">
                  ▸ View allocated tools (${tools.length})
                </button>
                <button type="button" class="ctx-mini-btn dept-dispatch-btn" data-dept="${esc(d.id)}" data-name="${esc(d.name)}">
                  ⚡ Dispatch
                </button>
              </div>
              <div class="dept-tools-list" id="tools-${esc(d.id)}" style="display:none">
                ${tools.map(t => `<span class="tool-pill">${esc(t)}</span>`).join("")}
              </div>
            </div>
          `;
        }).join("");

        deptsList.querySelectorAll(".dept-tools-toggle").forEach(btn => {
          btn.addEventListener("click", () => {
            const listEl = $(btn.dataset.target);
            if (listEl) {
              const isClosed = listEl.style.display === "none";
              listEl.style.display = isClosed ? "flex" : "none";
              btn.textContent = (isClosed ? "▾ Hide allocated tools" : "▸ View allocated tools") + ` (${listEl.children.length})`;
            }
          });
        });

        deptsList.querySelectorAll(".dept-dispatch-btn").forEach(btn => {
          btn.addEventListener("click", () => {
            const dept = btn.dataset.dept;
            const name = btn.dataset.name || dept;
            const task = prompt(`Assign a mission to ${name} (${dept}):`);
            if (task && task.trim()) {
              const msgInput = $("msg");
              if (msgInput) {
                msgInput.value = `Delegate to ${dept}: ${task.trim()}`;
                msgInput.focus();
                if (window.toggleContextDrawer) window.toggleContextDrawer();
              }
            }
          });
        });

        if (customList) {
          if (custom.length === 0) {
            customList.innerHTML = `<div class="placeholder" style="font-size: 0.76rem; color: var(--ink-dim); padding: 8px 0;">No custom agents hired yet. Click "+ Hire Specialist" or ask Zenith / HR to hire one.</div>`;
          } else {
            customList.innerHTML = custom.map(c => {
              const tools = c.tools || [];
              return `
                <div class="custom-agent-item" data-id="${esc(c.id)}">
                  <div class="custom-agent-hdr">
                    <span class="dept-card-title">🤖 ${esc(c.name)} <span class="flow-badge">${esc(c.id)}</span></span>
                    <div class="custom-agent-actions">
                      <button type="button" class="ctx-mini-btn" data-action="inspect" data-id="${esc(c.id)}">Inspect</button>
                      <button type="button" class="ctx-mini-btn" data-action="fire" data-id="${esc(c.id)}" style="color:#ef4444">Retire</button>
                    </div>
                  </div>
                  <div class="dept-card-desc"><strong>Dept:</strong> ${esc(c.department || 'Special Operations')} · ${esc(c.description || '')}</div>
                  <div style="font-size: 0.68rem; color: var(--ink-faint); font-family: var(--mono); margin-top: 2px;">Tools (${tools.length}): ${esc(tools.join(', '))}</div>
                </div>
              `;
            }).join("");

            customList.querySelectorAll("button[data-action='fire']").forEach(btn => {
              btn.addEventListener("click", async () => {
                if (!confirm(`Are you sure you want to retire and remove agent '${btn.dataset.id}'?`)) return;
                try {
                  const delRes = await fetch(`/api/agents/${encodeURIComponent(btn.dataset.id)}`, { method: "DELETE" });
                  const resData = await delRes.json();
                  toast(resData.message || "Agent retired");
                  loadAgentsPane();
                } catch (err) {
                  toast("Failed to retire agent: " + err.message);
                }
              });
            });

            customList.querySelectorAll("button[data-action='inspect']").forEach(btn => {
              btn.addEventListener("click", async () => {
                try {
                  const insRes = await fetch(`/api/agents/${encodeURIComponent(btn.dataset.id)}`);
                  const insData = await insRes.json();
                  if (insData.profile) {
                    alert(`Agent: ${insData.profile.name} (#${insData.profile.id})\nDepartment: ${insData.profile.department}\nDescription: ${insData.profile.description}\nTools: ${(insData.profile.tools || []).join(', ')}\n\nSystem Prompt:\n${insData.profile.system}`);
                  }
                } catch (err) {
                  toast("Failed to inspect: " + err.message);
                }
              });
            });
          }
        }

        if (runsList) {
          if (runs.length === 0) {
            runsList.innerHTML = `<div class="placeholder" style="font-size: 0.76rem; color: var(--ink-dim); padding: 8px 0;">No active or recent agent missions.</div>`;
          } else {
            runsList.innerHTML = runs.slice(0, 8).map(r => `
              <div class="delegation-step-row" style="padding: 6px 0;">
                <div class="delegation-step-left">
                  <span class="flow-badge">#${esc(r.id)}</span>
                  <span style="font-weight:600; color:var(--ink)">${esc(r.name)}</span>
                  <span style="color:var(--ink-dim); font-size:0.7rem">${esc((r.goal || '').slice(0, 60))}</span>
                </div>
                <span class="tl-tag ${r.status === 'done' ? 'ok' : (r.status === 'running' ? 'run' : 'fail')}">${esc(r.status)} (${r.tool_calls || 0} tools)</span>
              </div>
            `).join("");
          }
        }

        const bbFeed = $("ctx-blackboard-feed");
        if (bbFeed) {
          try {
            const bbRes = await fetch("/api/agents/blackboard?limit=8");
            const bbData = await bbRes.json();
            const findings = bbData.findings || [];
            if (findings.length === 0) {
              bbFeed.innerHTML = `<div class="placeholder" style="font-size: 0.76rem; color: var(--ink-dim); padding: 8px 0;">No shared blackboard updates yet.</div>`;
            } else {
              bbFeed.innerHTML = findings.map(f => `
                <div class="blackboard-item">
                  <div class="blackboard-meta">
                    <span class="blackboard-topic">${esc(f.department)} · ${esc(f.topic)}</span>
                    <span class="blackboard-time">${esc(f.created_at || '')}</span>
                  </div>
                  <div class="blackboard-content">${esc(f.content)}</div>
                </div>
              `).join("");
            }
          } catch (err) {
            console.error("Failed to load blackboard feed:", err);
          }
        }
      } catch (err) {
        console.error("Failed to load organization roster:", err);
      }
    }

    function initAgentForge() {
      const toggleBtn = $("ctx-agent-forge-toggle-btn");
      const forgeCard = $("ctx-agent-forge-card");
      const closeBtn = $("ctx-agent-forge-close-btn");
      const cancelBtn = $("forge-cancel-btn");
      const submitBtn = $("forge-submit-btn");
      const filterInput = $("forge-tools-filter");
      const picker = $("forge-tools-picker");
      const refreshBtn = $("ctx-roster-refresh-btn");
      const bbRefreshBtn = $("ctx-bb-refresh-btn");

      if (refreshBtn) refreshBtn.addEventListener("click", () => loadAgentsPane());
      if (bbRefreshBtn) bbRefreshBtn.addEventListener("click", () => loadAgentsPane());

      const toggleForge = (show) => {
        if (!forgeCard) return;
        forgeCard.style.display = show ? "block" : "none";
        if (show && _allSystemTools.length === 0) {
          loadSystemToolsForForge();
        }
      };

      if (toggleBtn) toggleBtn.addEventListener("click", () => {
        const isHidden = forgeCard.style.display === "none";
        toggleForge(isHidden);
      });
      if (closeBtn) closeBtn.addEventListener("click", () => toggleForge(false));
      if (cancelBtn) cancelBtn.addEventListener("click", () => toggleForge(false));

      async function loadSystemToolsForForge() {
        if (!picker) return;
        try {
          picker.innerHTML = '<span style="font-size:0.7rem; color:var(--ink-dim)">Loading catalog...</span>';
          const resp = await fetch("/api/agents/tools");
          const data = await resp.json();
          _allSystemTools = data.tools || [];
          renderForgeTools();
        } catch (err) {
          picker.innerHTML = '<span style="color:#ef4444">Failed to load tools catalog</span>';
        }
      }

      function renderForgeTools() {
        if (!picker) return;
        const flt = (filterInput ? filterInput.value : "").toLowerCase().trim();
        const filtered = _allSystemTools.filter(t => !flt || t.name.toLowerCase().includes(flt) || (t.description || "").toLowerCase().includes(flt));

        picker.innerHTML = filtered.map(t => {
          const isSel = _selectedToolsForForge.has(t.name);
          return `
            <span class="forge-tool-chip ${isSel ? 'selected' : ''}" data-tool="${esc(t.name)}" title="${esc(t.description)}">
              <span>${isSel ? '✓' : '+'}</span>
              <span>${esc(t.name)}</span>
            </span>
          `;
        }).join("");

        picker.querySelectorAll(".forge-tool-chip").forEach(chip => {
          chip.addEventListener("click", () => {
            const toolName = chip.dataset.tool;
            if (_selectedToolsForForge.has(toolName)) {
              _selectedToolsForForge.delete(toolName);
            } else {
              _selectedToolsForForge.add(toolName);
            }
            if ($("forge-selected-count")) $("forge-selected-count").textContent = String(_selectedToolsForForge.size);
            renderForgeTools();
          });
        });
      }

      if (filterInput) {
        filterInput.addEventListener("input", () => renderForgeTools());
      }

      if (submitBtn) {
        submitBtn.addEventListener("click", async () => {
          const id = ($("forge-agent-id")?.value || "").trim().toLowerCase().replace(/\\s+/g, "_");
          const name = ($("forge-agent-name")?.value || "").trim();
          const dept = ($("forge-agent-dept")?.value || "").trim();
          const desc = ($("forge-agent-desc")?.value || "").trim();
          const prompt = ($("forge-agent-prompt")?.value || "").trim();
          const statusEl = $("forge-status-msg");

          if (!id || !prompt) {
            alert("Agent Identifier and System Prompt are required.");
            return;
          }

          submitBtn.disabled = true;
          submitBtn.textContent = "Hiring...";
          if (statusEl) {
            statusEl.style.display = "block";
            statusEl.textContent = "Registering agent in SQLite store...";
            statusEl.style.color = "var(--ink-dim)";
          }

          try {
            const hireRes = await fetch("/api/agents/hire", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                id,
                name: name || id,
                department: dept || "Special Operations",
                role_description: desc || "Autonomous specialist",
                system_prompt: prompt,
                tools: Array.from(_selectedToolsForForge),
              }),
            });
            const hireData = await hireRes.json();
            if (hireData.ok) {
              toast(hireData.message || "Agent hired successfully!");
              toggleForge(false);
              loadAgentsPane();
            } else {
              alert(hireData.message || "Failed to hire agent");
            }
          } catch (err) {
            alert("Error: " + err.message);
          } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = "Hire & Persist Agent";
          }
        });
      }
    }

    async function refreshContextDrawer() {
      await Promise.all([loadOverviewPane(), syncPrivacyStatus()]);
    }

    function renderSensoryGrid(privacy) {
      const grid = $("ctx-sensor-grid");
      if (!grid) return;
      const isGhost = Boolean(privacy.ghost_mode);
      const s = privacy.sensors || {};
      const sensors = [
        { name: "Screen Vision", active: !isGhost && Boolean(s.screen_awareness) },
        { name: "Activity Watch", active: !isGhost && Boolean(s.activity_watch) },
        { name: "Camera Vision", active: !isGhost && Boolean(s.camera && (camStream !== null)) },
        { name: "Browser Use", active: !isGhost && Boolean(s.browser_automation) },
      ];
      grid.innerHTML = sensors.map(item => `
        <div class="ctx-sensor-cell">
          <div class="ctx-sensor-info">
            <span class="ctx-sensor-name">${esc(item.name)}</span>
            <span class="ctx-sensor-status ${item.active ? 'active' : 'paused'}">
              ${item.active ? 'ACTIVE' : (isGhost ? 'GHOST PAUSED' : 'OFFLINE')}
            </span>
          </div>
          <span class="ctx-sensor-indicator ${item.active ? 'active' : 'paused'}"></span>
        </div>
      `).join("");
    }

    async function loadOverviewPane() {
      try {
        const [screenRes, privRes] = await Promise.all([
          fetch("/api/screen/status").catch(() => null),
          fetch("/api/privacy/status").catch(() => null),
        ]);
        if (screenRes && screenRes.ok) {
          const data = await screenRes.json();
          if (data.ok && data.active_window) {
            const w = data.active_window;
            const appVal = $("ctx-app-val");
            const titleVal = $("ctx-title-val");
            const flowVal = $("ctx-workflow-val");
            if (appVal) appVal.textContent = w.app_name || "--";
            if (titleVal) titleVal.textContent = w.window_title || "--";
            if (flowVal) flowVal.textContent = (w.workflow || "STANDBY").toUpperCase();
          }
        }
        if (privRes && privRes.ok) {
          const pData = await privRes.json();
          if (pData.ok && pData.privacy) {
            renderSensoryGrid(pData.privacy);
          }
        }
      } catch (_) {}
    }

    async function loadActivityPane() {
      try {
        const [sumRes, timeRes] = await Promise.all([
          fetch("/api/activity/summary"),
          fetch("/api/activity/timeline?limit=30")
        ]);
        const sumData = await sumRes.json();
        const timeData = await timeRes.json();

        if (sumData.ok && sumData.summary) {
          const s = sumData.summary;
          const statAct = $("ctx-stat-active");
          const statIdle = $("ctx-stat-idle");
          const statEvt = $("ctx-stat-events");
          if (statAct) statAct.textContent = `${s.active_minutes || 0}m`;
          if (statIdle) statIdle.textContent = `${s.idle_minutes || 0}m`;
          if (statEvt) statEvt.textContent = `${s.total_events || 0}`;
        }

        const list = $("ctx-timeline-list");
        if (list && timeData.ok && timeData.timeline) {
          if (timeData.timeline.length === 0) {
            list.innerHTML = `<div class="placeholder">No activity recorded yet (or Ghost Mode enabled).</div>`;
          } else {
            list.innerHTML = timeData.timeline.map(ev => `
              <div class="ctx-flow-item" style="padding:4px 0; border-bottom:1px solid var(--line);">
                <span class="flow-badge" style="font-size:0.65rem;">${esc(ev.category)}</span>
                <strong>${esc(ev.app_name)}</strong>
                <span style="color:var(--ink-dim); font-size:0.72rem; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">"${esc(ev.window_title)}"</span>
                <span style="font-family:var(--mono); font-size:0.68rem; color:var(--ink-dim);">${ev.duration_seconds}s</span>
              </div>
            `).join("");
          }
        }
      } catch (e) {
        console.warn("Failed to load activity timeline", e);
      }
    }

    const actRefreshBtn = $("ctx-act-refresh-btn");
    if (actRefreshBtn) actRefreshBtn.addEventListener("click", loadActivityPane);

    async function loadMemoryPane() {
      const tierSel = $("ctx-mem-tier-sel");
      const tier = tierSel ? tierSel.value : "";
      try {
        const url = tier ? `/api/memory/mem0/all?tier=${encodeURIComponent(tier)}` : "/api/memory/mem0/all";
        const res = await fetch(url);
        const data = await res.json();
        const list = $("ctx-memory-list");
        if (list && data.ok && data.memories) {
          if (data.memories.length === 0) {
            list.innerHTML = `<div class="placeholder">No Mem0 memories stored in this tier.</div>`;
          } else {
            list.innerHTML = data.memories.map(m => `
              <div class="ctx-card" style="margin-bottom:6px; padding:8px 12px; display:flex; align-items:flex-start; justify-content:space-between; gap:10px;">
                <div>
                  <div style="display:flex; align-items:center; gap:6px; margin-bottom:4px;">
                    <span class="flow-badge">${esc(m.tier)}</span>
                    <span style="font-size:0.7rem; color:var(--ink-dim); font-family:var(--mono);">#${m.id} · ${esc(m.topic)}</span>
                  </div>
                  <div style="font-size:0.78rem; color:var(--ink);">${esc(m.content)}</div>
                </div>
                <button type="button" class="ctx-mini-btn" style="color:var(--fail);" onclick="window.deleteMem0Item && window.deleteMem0Item(${m.id})">✕</button>
              </div>
            `).join("");
          }
        }
      } catch (e) {
        console.warn("Failed to load Mem0 memories", e);
      }
    }

    window.deleteMem0Item = async function(id) {
      try {
        await fetch(`/api/memory/mem0/${id}`, { method: "DELETE" });
        loadMemoryPane();
      } catch (_) {}
    };

    const tierSel = $("ctx-mem-tier-sel");
    if (tierSel) tierSel.addEventListener("change", loadMemoryPane);

    const memAddBtn = $("ctx-mem-add-btn");
    if (memAddBtn) {
      memAddBtn.addEventListener("click", async () => {
        const input = $("ctx-mem-add-input");
        const tier = $("ctx-mem-add-tier")?.value || "project";
        const text = (input?.value || "").trim();
        if (!text) return;
        try {
          await fetch("/api/memory/mem0/add", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ content: text, tier: tier, topic: "user_note" })
          });
          if (input) input.value = "";
          loadMemoryPane();
        } catch (e) {
          showToast("Failed to save memory: " + e.message, "err");
        }
      });
    }

    async function loadPrivacyPane() {
      try {
        const res = await fetch("/api/privacy/status");
        const data = await res.json();
        if (data.ok && data.privacy) {
          const p = data.privacy;
          const chkScreen = $("priv-chk-screen");
          const chkAct = $("priv-chk-activity");
          const chkCam = $("priv-chk-camera");
          const chkBrowser = $("priv-chk-browser");
          const chkMem = $("priv-chk-memory");

          if (chkScreen) chkScreen.checked = p.sensors.screen_awareness;
          if (chkAct) chkAct.checked = p.sensors.activity_watch;
          if (chkCam) chkCam.checked = p.sensors.camera;
          if (chkBrowser) chkBrowser.checked = p.sensors.browser_automation;
          if (chkMem) chkMem.checked = p.sensors.memory_recording;

          const blockAppsList = $("ctx-blocklist-apps");
          if (blockAppsList && p.blocked_apps) {
            blockAppsList.innerHTML = p.blocked_apps.map(a => `<span class="block-tag">${esc(a)}</span>`).join("");
          }
        }
      } catch (_) {}
    }

    [
      { id: "priv-chk-screen", sensor: "screen_awareness" },
      { id: "priv-chk-activity", sensor: "activity_watch" },
      { id: "priv-chk-camera", sensor: "camera" },
      { id: "priv-chk-browser", sensor: "browser_automation" },
      { id: "priv-chk-memory", sensor: "memory_recording" },
    ].forEach(({ id, sensor }) => {
      const el = $(id);
      if (el) {
        el.addEventListener("change", async () => {
          await fetch("/api/privacy/sensor", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sensor: sensor, enabled: el.checked })
          });
          syncPrivacyStatus();
        });
      }
    });

    async function toggleGhostMode() {
      try {
        const res = await fetch("/api/privacy/ghost_mode", { method: "POST" });
        const data = await res.json();
        syncPrivacyStatus();
        showToast(`Ghost Mode is now ${data.ghost_mode ? 'ENABLED (All sensors offline)' : 'DISABLED'}`);
      } catch (_) {}
    }

    if (ctxGhostBtn) ctxGhostBtn.addEventListener("click", toggleGhostMode);

    async function syncPrivacyStatus() {
      try {
        const res = await fetch("/api/privacy/status");
        const data = await res.json();
        if (data.ok && data.privacy) {
          const p = data.privacy;
          const isGhost = p.ghost_mode;

          if (ctxGhostBtn) {
            ctxGhostBtn.classList.toggle("active", isGhost);
            const lbl = $("ctx-ghost-label");
            if (lbl) lbl.textContent = `Ghost Mode: ${isGhost ? 'ON' : 'OFF'}`;
          }
          renderSensoryGrid(p);
        }
      } catch (_) {}
    }

    syncPrivacyStatus();
    setInterval(syncPrivacyStatus, 20000);
  }

  function renderGraph() {}
  window.renderGraph = renderGraph;

  /* ── Audio Waveform Visualizer ───────────────────────────────────────────── */
  let waveAnim = null;
  function startWaveformAnim() {
    const canvas = $("waveform-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let phase = 0;

    function renderFrame() {
      if (!voiceOpen()) {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (waveAnim) { cancelAnimationFrame(waveAnim); waveAnim = null; }
        return;
      }
      waveAnim = requestAnimationFrame(renderFrame);
      phase += 0.08;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const w = canvas.width;
      const h = canvas.height;
      const midY = h / 2;
      const vol = Math.max(0.15, volume * 2.5);

      const numBars = 22;
      const barWidth = 4;
      const gap = (w - (numBars * barWidth)) / (numBars + 1);

      for (let i = 0; i < numBars; i++) {
        const x = gap + i * (barWidth + gap);
        const amp = Math.sin(phase + i * 0.4) * 10 * vol + (vol * 6);
        const barH = Math.max(4, Math.min(h - 6, amp));
        const gradient = ctx.createLinearGradient(0, midY - barH / 2, 0, midY + barH / 2);
        gradient.addColorStop(0, "var(--accent)");
        gradient.addColorStop(0.5, "var(--accent-dim)");
        gradient.addColorStop(1, "#d9b6a0");

        ctx.fillStyle = gradient;
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(x, midY - barH / 2, barWidth, barH, 2);
        } else {
          ctx.rect(x, midY - barH / 2, barWidth, barH);
        }
        ctx.fill();
      }
    }
    if (waveAnim) cancelAnimationFrame(waveAnim);
    renderFrame();
  }

  function renderAgentList(agents) {
    const box = $("agent-list");
    if (!agents.length) { box.innerHTML = `<div class="placeholder">Idle.</div>`; return; }
    box.innerHTML = agents.slice(0, 8).map((a) => {
      const cls = a.status === "done" ? "ok" : a.status === "error" ? "err" : "run";
      const recent = (a.recent || []).slice(-2).map((s) => s.summary || "").filter(Boolean).join(" · ");
      const byline = a.status === "running"
        ? `<span class="agent-step">step ${a.steps || 0}${recent ? " · " + esc(recent) : ""}</span>`
        : (a.status === "done" ? "" : "");
      return `<div class="agent-item"><span class="agent-name">${esc(a.name)}<span class="agent-sub">${esc((a.goal || "").slice(0, 40) || "")}</span></span><span class="agent-status ${cls}">${esc(a.status)}</span></div>${byline ? `<div class="agent-progress">${byline}</div>` : ""}`;
    }).join("");
  }

  // ─ agent launch ───────────────────────────────────────────
  function wireAgents() {
    const inp = $("agent-goal");
    const goBtn = $("agent-go");
    const sendAgent = () => {
      const goal = (inp.value || "").trim();
      if (!goal) return;
      send(goal);
      inp.value = "";
      setTimeout(loadState, 400);
    };
    goBtn.addEventListener("click", sendAgent);
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAgent(); } });
    document.querySelectorAll(".agent-op-presets .chip").forEach((b) => {
      b.addEventListener("click", () => {
        const kind = b.dataset.agent || "general";
        send(`Launch a ${kind} agent: ${inp.value.trim() || "general research"}.`);
        inp.value = "";
        setTimeout(loadState, 400);
      });
    });
  }

  /* ── fleet / system chip ────────────────────────────── */

  async function loadFleet() {
    try {
      const r = await fetch("/api/state");
      if (r.ok) {
        const d = await r.json();
        if (d && d.graph) renderGraph(d.graph);
      }
    } catch {}

    // system chip: host vitals via the chat route is an LLM call — keep it simple:
    // fetch from the health endpoint (uptime + memory) for a live stat.
    try {
      const resp = await fetch("/api/health");
      if (resp.ok) {
        const h = await resp.json();
        const up = h.uptime ? Math.round(h.uptime / 60) + "m" : "?";
        $("sys-chip").textContent = `up ${up} · mem ${h.memory ? h.memory.entities + "e" : "?"}/graph`;
        renderIntegrations(h.integrations || {});
      }
    } catch {}

    // integrations strip in sidebar
    function renderIntegrations(ints) {
      const box = $("int-status");
      if (!box) return;
      const items = [
        ["gm", "gmail", ints.gmail_read],
        ["re", "resend", ints.resend_send],
        ["cl", "calendar", ints.google_calendar],
        ["mp", "maps", ints.google_maps],
        ["cf", "cloudflare", ints.cloudflare],
        ["vc", "vercel", ints.vercel],
      ];
      box.innerHTML = items.map(([tag, name, ok]) =>
        `<div class="int-item" title="${name}"><span class="fleet-stat ${ok ? "up" : "down"}"></span><span class="int-name">${name}</span></div>`
      ).join("");
    }

    // fleet box: live container list from the read-only endpoint.
    const fleetBox = $("fleet-box");
    try {
      const fr = await fetch("/api/fleet");
      if (fr.ok) {
        const d = await fr.json();
        const cs = d.containers || [];
        if (!cs.length) {
          fleetBox.innerHTML = `<div class="placeholder">${d.error ? "Docker unreachable." : "No containers."}</div>`;
        } else {
          fleetBox.innerHTML = cs.slice(0, 30).map((c) =>
            `<div class="fleet-item"><span class="fleet-stat ${c.up ? "up" : "down"}"></span><span class="fleet-name" title="${esc(c.image || "")}">${esc(c.name)}</span><span class="fleet-status">${esc(c.state)}</span></div>`
          ).join("");
        }
      } else {
        fleetBox.innerHTML = `<div class="placeholder">Fleet unavailable.</div>`;
      }
    } catch {
      fleetBox.innerHTML = `<div class="placeholder">Fleet unavailable.</div>`;
    }
  }

  // ── Gemini Live persistent native-audio state ──
  let useStreamingTTS = false;
  let useLiveStreaming = true; // default true when server supports live
  let liveWs = null;
  let liveWsNominal = false;
  let liveAudioCtx = null;
  let liveGain = null;
  let liveAnalyser = null;
  let liveActiveSources = [];
  let liveNextPlayTime = 0;
  let liveAudioStart = 0;
  let liveTalkStart = 0;
  let liveUserDetectPending = false;
  let liveWsRefused = false;
  let liveVoiceBright = false;
  let liveStreaming = false;
  let liveAudioThisTurn = 0;
  let liveReplyEnd = 0;
  let liveCaptureNode = null;
  let liveAssistantTranscript = "";

  /* Pull live-conversation tuning (silence/speech thresholds) from the server. */
  async function loadVoiceConfig() {
    try {
      const r = await fetch("/api/voice/status");
      if (r.ok) {
        const d = await r.json();
        const c = vad.cfg;
        c.silence_ms = d.silence_ms || 1300;
        c.min_speech_ms = d.min_speech_ms || 250;
        c.max_utterance_ms = d.max_utterance_ms || 20000;
        voiceStatusRemote = d.stt_ready ? "voice" : "voice · mic offline";
        if (d.tts_stream === true) useStreamingTTS = true;
        // When the server can run a persistent Gemini Live session, prefer
        // streaming voice over the per-utterance transcribe → TTS round trip.
        if (d.live_ready === true) {
          useLiveStreaming = true;
          // The server restarted since our last refusal may have happened (it
          // only refreshes on config refresh) — give live streaming another
          // chance instead of staying stuck on the classic path all session.
          liveWsRefused = false;
        }

        try { localStorage.setItem("voice-cfg", JSON.stringify(c)); } catch {}
      }
    } catch {}
  }

  /* ── JARVIS-style live voice: VAD + Groq STT + streaming TTS ──
     Hands-free: the mic stays on, a voice-activity detector finds utterance
     boundaries in the browser (no cost for silence), each utterance goes to
     Groq Whisper via /api/transcribe, then into the normal agent/WS pipeline.
     Zenith speaks replies (Edge, streaming), and you can just keep talking. */

  let selectedFemaleVoice = null;
  let isListening = false;
  let speechRecognizer = null;

  function loadFemaleVoice() {
    if (!window.speechSynthesis) return;
    const voices = window.speechSynthesis.getVoices();
    if (!voices || !voices.length) return;

    const priorityFemalePatterns = [
      /Microsoft.*(Aria|Jenny|Natural|Zira)/i,
      /Google.*(US|UK|Female|Natural)/i,
      /Samantha/i,
      /Victoria/i,
      /Karen/i,
      /Fiona/i,
      /Moira/i,
      /Veena/i,
      /Female/i,
      /Woman/i
    ];

    for (const pattern of priorityFemalePatterns) {
      const v = voices.find(v => pattern.test(v.name) && (v.lang.startsWith("en")));
      if (v) {
        selectedFemaleVoice = v;
        break;
      }
    }
    if (!selectedFemaleVoice) {
      selectedFemaleVoice = voices.find(v => v.lang.startsWith("en")) || voices[0];
    }
  }

  if (window.speechSynthesis) {
    loadFemaleVoice();
    window.speechSynthesis.onvoiceschanged = loadFemaleVoice;
  }

  let mediaRecorder = null;
  let audioChunks = [];
  let pendingUtterChunks = null; // snapshot of the stopped utterance's audio

  function startMediaRecorder() {
    if (!micStream || !window.MediaRecorder) return;
    if (useLiveStreaming && !liveWsRefused) {
      // Live mode: PCM already streams up via the capture node — no MediaRecorder
      // needed. Just make sure the persistent session is open and capturing.
      openLiveStreaming();
      return;
    }
    try {
      if (mediaRecorder && mediaRecorder.state !== "inactive") { return; }
      const mimeType = MediaRecorder.isTypeSupported("audio/webm") ? "audio/webm" :
                     MediaRecorder.isTypeSupported("audio/ogg") ? "audio/ogg" : "";

      audioChunks = [];
      mediaRecorder = mimeType ? new MediaRecorder(micStream, { mimeType }) : new MediaRecorder(micStream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunks.push(e.data);
          // Cap memory only (about 30s).
          if (audioChunks.length > 100) audioChunks.splice(0, audioChunks.length - 100);
        }
      };
      mediaRecorder.start(300);
    } catch (err) {
      console.warn("MediaRecorder start error:", err);
    }
  }

  // Stop the recorder cleanly (per-utterance). The final ondataavailable fires
  // async, so we snapshot the chunk buffer here; a new recorder for the next
  // phrase may start before sendRecordedAudio runs, so sendRecordedAudio must
  // use pendingUtterChunks (not the live audioChunks).
  function stopMediaRecorder() {
    if (useLiveStreaming && !liveWsRefused && liveWs && liveWs.readyState === WebSocket.OPEN) {
      // Live mode streams PCM as you talk (liveStreaming active during VAD).
      // We don't need the MediaRecorder at all — just end the audio turn and
      // the model's native reply streams back down on its own.
      stopLiveStreaming();
      liveFinishUtterance();
      return;
    }
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      pendingUtterChunks = audioChunks.slice(); // snapshot the finished utterance
      try { mediaRecorder.stop(); } catch {}
    }
    // Do NOT null mediaRecorder here — the object is still referenced until the
    // next startMediaRecorder() replaces it.
  }

  async function sendRecordedAudio() {
    // Read from the snapshot taken at stop() (the finished utterance). The
    // live audioChunks may already belong to a new recorder for the next phrase.
    const chunks = pendingUtterChunks || audioChunks;
    if (!chunks || chunks.length === 0) {
      processingSpeech = false; refreshVoiceStatus(); return false;
    }

    const mimeType = mediaRecorder ? mediaRecorder.mimeType || "audio/webm" : "audio/webm";
    // Send pre-roll + the utterance. Whisper trims leading/trailing silence
    // itself, so a little lead-in is harmless and never cuts the first word.
    const audioBlob = new Blob(chunks, { type: mimeType });
    pendingUtterChunks = null;

    if (audioBlob.size < 1000) {
      processingSpeech = false; refreshVoiceStatus(); return false;
    }

    $("v-status").textContent = "voice · heard · thinking…";
    setVoiceState("processing");

    const ext = (mimeType.match(/audio\/(\w+)/) || [])[1] || "webm";
    const formData = new FormData();
    formData.append("audio", audioBlob, `speech.${ext}`);
    formData.append("mime", mimeType);

    try {
      const resp = await fetch("/api/transcribe", { method: "POST", body: formData });
      const isLiveAudio = (resp.headers.get("x-zenith-live") === "1");
      if (resp.ok) {
        if (isLiveAudio) {
          // Gemini Live native audio — play the model's spoken reply directly.
          // The response carries its real container in the content-type header
          // (webm most often on the default audio modality).
          $("v-text").textContent = "heard — Zenith is answering…";
          $("v-status").textContent = "voice · heard · thinking…";
          const blob = await resp.blob();
          const url = URL.createObjectURL(blob);
          stopAssistantSpeech();
          const audio = new Audio(url);
          window.zenithAudio = audio;
          audio.volume = 0.95;
          audio.onended = () => {
            URL.revokeObjectURL(url);
            $("v-text").textContent = "keep talking — Zenith will listen.";
            setVoiceState("idle");
            if (voiceOpen()) refreshVoiceStatus();
            onVoiceTurnDone();
          };
          audio.onerror = () => { URL.revokeObjectURL(url); onVoiceTurnDone(); };
          audio.play();
          return true;
        }
        const data = await resp.json();
        if (data.status === "ok" && data.text) {
          $("v-text").textContent = `“${data.text}”`;
          $("v-status").textContent = "voice · heard · thinking…";
          queueSpeech(data.text);
          return true;
        }
      if (data.status === "ok" && !data.text.trim()) {
          // Server said "no speech detected" — nothing to run through the agent.
          $("v-text").textContent = "i didn't catch that — mind saying it once more?";
        }
      } else {
        $("v-text").textContent = "i couldn't hear that — mind saying it once more?";
      }
    } catch (err) {
      console.warn("Server STT error:", err);
      $("v-text").textContent = "voice service hiccuped — try again";
    }
    processingSpeech = false;
    setVoiceState("idle");
    refreshVoiceStatus();
    // Re-arm the rolling recorder + VAD so the next utterance is captured.
    if (voiceOpen() && micReady && !voiceBusy) {
      setTimeout(() => { if (voiceOpen() && micReady) startMediaRecorder(); }, 250);
    }
    return false;
  }

  /* ── Gemini Live streaming voice (/ws/live) ──────────────
     When the server is live_ready, the voice layer uses a persistent WebSocket
     session instead of per-utterance STT/TTS. Raw PCM16 (16 kHz) audio flows up
     as you speak; the model's native audio streams back down (server resamples
     the 24k output to 16k), decoded with AudioContext and played. VAD still
     decides WHEN you're speaking — the Live session simply replaces the
     mediaChunks → transcribe → speak pipeline. */

  function openLiveStreaming() {
    if (!useLiveStreaming || liveWs || liveWsRefused) return;
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    let s;
    try {
      s = new WebSocket(`${proto}//${location.host}/ws/live`);
    } catch { liveWsRefused = true; return; }
    liveWs = s;
    liveWsNominal = false;
    s._uplinking = false;
    liveStreaming = false;
    liveUserDetectPending = true;

    s.onopen = () => {
      liveWsNominal = true;
      if (liveWs && liveWs.readyState === WebSocket.OPEN) wireLiveCapture();
    };

    s.onmessage = async (e) => {
      if (typeof e.data === "string") {
        let m;
        try { m = JSON.parse(e.data); } catch { return; }
        switch (m.type) {
          case "ready":
            liveWsNominal = true;
            wireLiveCapture();
            if (m.model) {
              const cleanModel = m.model.replace(/^models\//, "");
              const vStatus = $("v-status");
              if (vStatus) vStatus.textContent = `voice · connected (${cleanModel})`;
            }
            break;
          case "heard":
            liveUserDetectPending = false;
            liveTalkStart = performance.now();
            if (m.text) {
              const vText = $("v-text");
              if (vText) vText.textContent = `“${m.text}”`;
              const vStatus = $("v-status");
              if (vStatus) vStatus.textContent = "voice · heard · thinking…";
              setVoiceState("processing");
            }
            break;
          case "interrupted":
            stopLivePlayback();
            liveStreaming = false;
            liveAssistantTranscript = "";
            liveUserDetectPending = false;
            setVoiceState("listening");
            if ($("v-status")) $("v-status").textContent = "voice · listening…";
            break;
          case "tool":
            if (m.name) {
              const toolName = m.name.replace(/_/g, " ");
              const vStatus = $("v-status");
              if (vStatus) vStatus.textContent = `voice · running ${toolName}…`;
              const vText = $("v-text");
              if (vText && !liveStreaming && !liveAssistantTranscript) vText.textContent = `Executing ${toolName}…`;
            }
            break;
          case "assistant_text":
            if (m.text) {
              liveAssistantTranscript = (liveAssistantTranscript ? liveAssistantTranscript + " " : "") + m.text;
              const vText = $("v-text");
              if (vText) vText.textContent = liveAssistantTranscript;
              const vStatus = $("v-status");
              if (vStatus) vStatus.textContent = "voice · Zenith speaking…";
              setVoiceState("processing");
            }
            break;
          case "done": {
            const hadAudio = (liveAudioThisTurn > 0) || (liveActiveSources.length > 0) || Boolean(liveAssistantTranscript);
            liveStreaming = false;
            liveUserDetectPending = true;
            liveFinishModelAudio();
            liveAudioThisTurn = 0;
            if (!hadAudio && voiceOpen()) {
              const vText = $("v-text");
              if (vText) vText.textContent = "I didn't quite catch that — say that again?";
              const vStatus = $("v-status");
              if (vStatus) vStatus.textContent = "voice · listening…";
              setVoiceState("listening");
            } else {
              setTimeout(() => {
                if (voiceOpen() && !liveStreaming && liveActiveSources.length === 0) {
                  const vText = $("v-text");
                  if (vText && vText.textContent === liveAssistantTranscript) {
                    vText.textContent = "keep talking — Zenith will listen.";
                  }
                  liveAssistantTranscript = "";
                  refreshVoiceStatus();
                }
              }, 3500);
            }
            break;
          }
          case "error": {
            const soft = /no (audio|turn)|empty|no model/i.test(m.error || "");
            if (soft) break;
            liveWsRefused = true;
            lastLiveWsRefusedAt = Date.now();
            liveFinishModelAudio();
            if (liveWs && liveWs.readyState === WebSocket.OPEN) liveWs.close();
            break;
          }
        }
        return;
      }
      if (e.data instanceof Blob) {
        const ab = await e.data.arrayBuffer();
        const n = ab.byteLength;
        if (n) {
          liveStreaming = true;
          liveAudioThisTurn += n;
          liveStartModelAudio();
          const f = new Float32Array(n / 2);
          const d = new DataView(ab);
          for (let i = 0; i < f.length; i++) f[i] = d.getInt16(i * 2, true) / 32768;
          queueLiveAudioChunk(f, LIVE_OUTPUT_RATE);
        }
      }
    };

    s.onclose = () => {
      liveWs = null;
      liveWsNominal = false;
      liveStreaming = false;
      liveUserDetectPending = true;
      if (useLiveStreaming && !liveWsRefused && voiceOpen()) {
        setTimeout(() => {
          if (voiceOpen() && useLiveStreaming && !liveWsRefused && !liveWs) openLiveStreaming();
        }, 1000);
      }
    };
    s.onerror = () => { try { s.close(); } catch {} };
  }

  // Attach a ScriptProcessor capture node to the live session (one per open).
  // Exact high-precision resampling to 16 kHz for Gemini Live.
  function wireLiveCapture() {
    if (!audioCtx || !micStream || liveCaptureNode) return;
    let src = null;
    try { src = audioCtx.createMediaStreamSource(micStream); } catch { return; }
    const inRate = audioCtx.sampleRate || 48000;

    const cap = audioCtx.createScriptProcessor(4096, 1, 1);
    cap.onaudioprocess = (e) => {
      if (!liveWs || liveWs.readyState !== WebSocket.OPEN || !useLiveStreaming || liveWsRefused) return;
      if (!vad.speech) {
        liveWs._uplinking = false;
        return;
      }
      liveWs._uplinking = true;
      const ch = e.inputBuffer.getChannelData(0);
      const targetLen = Math.floor(ch.length * LIVE_PCM_RATE / inRate);
      const pcm = new Int16Array(targetLen);
      for (let i = 0; i < targetLen; i++) {
        const srcPos = i * inRate / LIVE_PCM_RATE;
        const i0 = Math.floor(srcPos);
        const frac = srcPos - i0;
        const s0 = ch[i0] || 0;
        const s1 = (i0 + 1 < ch.length) ? ch[i0 + 1] : s0;
        const s = s0 + (s1 - s0) * frac;
        pcm[i] = Math.max(-32768, Math.min(32767, Math.round(s * 32767)));
      }
      try { liveWs.send(pcm.buffer); } catch {}
    };
    try { src.connect(cap); } catch {}
    const sink = audioCtx.createGain();
    sink.gain.value = 0;
    cap.connect(sink);
    sink.connect(audioCtx.destination);
    liveCaptureNode = cap;
    liveAudioCtx = audioCtx;

    if (audioCtx.state === "suspended") { audioCtx.resume().catch(() => {}); }
  }

  function ensureLiveDecoder() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (!liveGain) {
      liveGain = audioCtx.createGain();
      liveGain.gain.value = 0.95;
      liveAnalyser = audioCtx.createAnalyser();
      liveAnalyser.fftSize = 64;
      liveGain.connect(liveAnalyser);
      liveAnalyser.connect(audioCtx.destination);
    }
  }

  function queueLiveAudioChunk(f32Array, sampleRate = LIVE_OUTPUT_RATE) {
    if (!f32Array || !f32Array.length) return;
    ensureLiveDecoder();
    if (!liveAudioCtx) liveAudioCtx = audioCtx;
    if (liveAudioCtx.state === "suspended") liveAudioCtx.resume().catch(() => {});

    try {
      const buf = liveAudioCtx.createBuffer(1, f32Array.length, sampleRate);
      buf.getChannelData(0).set(f32Array);

      const src = liveAudioCtx.createBufferSource();
      src.buffer = buf;
      src.connect(liveGain);

      const now = liveAudioCtx.currentTime;
      if (liveNextPlayTime < now) {
        liveNextPlayTime = now + 0.04;
      }
      src.start(liveNextPlayTime);
      liveActiveSources.push(src);

      src.onended = () => {
        const idx = liveActiveSources.indexOf(src);
        if (idx !== -1) liveActiveSources.splice(idx, 1);
        if (liveActiveSources.length === 0 && !liveStreaming) {
          refreshVoiceStatus();
        }
      };

      liveNextPlayTime += buf.duration;
      const msRemaining = (liveNextPlayTime - now) * 1000;
      liveReplyEnd = performance.now() + Math.max(250, msRemaining);
      liveAudioStart = performance.now();
    } catch (e) {
      console.warn("[zenith] live chunk queue error:", e);
    }
  }

  function stopLivePlayback() {
    for (const src of liveActiveSources) {
      try { src.stop(); } catch {}
    }
    liveActiveSources = [];
    liveNextPlayTime = 0;
    liveStreaming = false;
    liveReplyEnd = 0;
  }

  function liveStartModelAudio() {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    try { if (window.zenithAudio) { window.zenithAudio.pause(); window.zenithAudio = null; } } catch {}
    liveVoiceBright = true;
    if (!liveTalkStart) liveTalkStart = performance.now();
  }

  function liveFinishModelAudio() {
    liveStreaming = false;
    liveUserDetectPending = true;
    if (voiceOpen() && audioCtx && audioCtx.state === "suspended") audioCtx.resume().catch(() => {});
    setTimeout(() => { if (voiceOpen() && useLiveStreaming && !liveWsRefused && !liveWs) openLiveStreaming(); }, 180);
  }

  function liveFinishUtterance() {
    if (!liveWs || liveWs.readyState !== WebSocket.OPEN) return;
    liveAssistantTranscript = "";
    liveNextPlayTime = 0;
    stopLivePlayback();
    if (liveWs) liveWs._uplinking = false;
    try { liveWs.send(JSON.stringify({ type: "end" })); } catch {}
  }

  function stopLiveStreaming() {
    if (liveAudioCtx) {
      if (liveAudioCtx.state === "suspended") liveAudioCtx.resume().catch(() => {});
    }
    liveStreaming = false;
  }

  function resolveLive() {
    if (voiceOpen() && audioCtx && micStream && !liveCaptureNode) wireLiveCapture();
    if (voiceOpen() && liveWs && liveWs.readyState === WebSocket.CLOSED) openLiveStreaming();
  }

  function shutdownLive(closeSock) {
    stopLivePlayback();
    if (liveCaptureNode) {
      try { liveCaptureNode.disconnect(); } catch {}
      liveCaptureNode = null;
    }
    if (liveWs) {
      if (closeSock) {
        try { if (liveWs.readyState === WebSocket.OPEN) liveWs.send(JSON.stringify({ type: "close" })); } catch {}
        try { liveWs.close(); } catch {}
      }
      liveWs = null;
    }
    liveWsNominal = false;
    liveStreaming = false;
    if (liveGain) { try { liveGain.disconnect(); } catch {} liveGain = null; }
    if (liveAnalyser) { try { liveAnalyser.disconnect(); } catch {} liveAnalyser = null; }
  }

  function setFlag() { /* reserved space for future live-state badges */ }

  // While Zenith is mid-turn, new utterances queue and flush after it's done —
  // natural multi-part conversation without interleaving the agent mid-round.
  function queueSpeech(text) {
    processingSpeech = false;
    if (voiceBusy || awaiting) {
      utterQueue.push(text);
      return;
    }
    send(text, { voice: true });
    // Recording restarts once Zenith finishes the turn (drainUtterQueue) — but
    // also re-arm here if we're idle so the mic stays live for the next phrase.
    if (voiceOpen() && micReady && !voiceBusy) {
      setTimeout(() => { if (voiceOpen() && micReady && !voiceBusy) startMediaRecorder(); }, 400);
    }
  }

  // Queue flush also passes voice:true so Zenith keeps attribution consistent.
  function flushQueueItem(text) {
    send(text, { voice: true });
  }

  async function toggleVoiceListen() {
    if (!voiceOpen()) { await openVoice(); return; }
    if (!micReady || !micStream || !micStream.active) return;

    // Orb tap = pause/resume continuous listening.
    stopAssistantSpeech();
    if (voicePaused) { voicePaused = false; vad.enabled = true; refreshVoiceStatus(); startMediaRecorder(); }
    else { voicePaused = true; vad.enabled = false; vad.speech = false; stopMediaRecorder(); refreshVoiceStatus(); }
  }

  /** Space key: send whatever we have right now (treat as finish). */
  function flushLiveUtterance() {
    if (!voiceOpen() || !micReady) return;
    if (vad.speech) { // hard stop the current capture
      vad.speech = false;
      vad.silenceStartMs = 0;
      finishUtteranceNow();
    } else if (processingSpeech) {
      // transcribe in flight — nothing to flush
    }
  }

  function setVoiceState(state) {
    const mod = $("vmod");
    if (!mod) return;
    mod.classList.toggle("voice-listening", state === "listening");
    mod.classList.toggle("voice-processing", state === "processing");
    mod.classList.toggle("voice-paused", state === "paused");
  }

  function refreshVoiceStatus() {
    const st = $("v-status");
    if (!st) return;
    const spoken = zenithVoiceSpoken;
    let s;
    if (!micReady) {
      s = "voice · mic offline";
    } else if (!vad.enabled) {
      s = "voice · " + (voicePaused ? "paused" : "off");
    } else if (vad.speech) {
      s = "voice · listening…";
    } else if (processingSpeech) {
      s = "voice · heard · thinking…";
    } else if (isSpeakingState()) {
      s = "voice · speaking…";
    } else {
      s = "voice · listening";
    }
    s += (zenithVoiceSpoken ? "" : " · replies off");
    st.textContent = s;
    setVoiceState(!vad.enabled ? "paused" : (vad.speech ? "listening" : (processingSpeech ? "processing" : "idle")));
  }

  function isSpeakingState() {
    return (liveActiveSources.length > 0)
      || (performance.now() < liveReplyEnd)
      || !!(window.zenithAudio && !window.zenithAudio.paused)
      || (window.speechSynthesis && window.speechSynthesis.speaking);
  }

  window.addEventListener("keydown", (e) => {
    if (!voiceOpen()) return;
    const k = (e.key || "").toLowerCase();
    if ((k === "g") && !zenithVoiceSpoken) { zenithVoiceSpoken = true; refreshVoiceStatus(); return; }
    if ((k === "e") && !e.metaKey && !e.ctrlKey && !e.altKey) { zenithVoiceSpoken = false; refreshVoiceStatus(); return; }
  });

  // ── Voice-activity detection (frame loop) ──────────────────────────
  // Adaptive RMS vs. a rolling noise floor → speech start/end. Runs on the
  // existing rAF orb loop so it costs nothing extra.
  // VAD runs whenever the mic is live and not paused — even while Zenith is
  // mid-turn. Speech detected during a turn goes into the queue instead of
  // being lost (the old early-return made VAD stick forever after one turn).
  function vadFrame(t) {
    if (!voiceOpen() || !micReady || !analyser) return;

    const buf = new Float32Array(analyser.fftSize);
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (let i = 0; i < buf.length; i++) { const v = buf[i]; sum += v * v; }
    const rms = Math.sqrt(sum / buf.length);

    // Calibration window: measure ambient noise, keep Zenith quiet until done.
    if (vad._calibUntil && t < vad._calibUntil) {
      vad._calibSum += rms; vad._calibN++;
      vad._noise = (vad._calibSum / vad._calibN) || 0.006;
      return;
    }
    vad._calibUntil = 0;

    const cfg = vad.cfg;
    // Adaptive noise floor. Slow rise when quiet, so a sustained room hum or
    // fan can't trip "speaking", and fast follow when loud so a shout resets it.
    let noise = vad._noise || 0;
    if (rms < noise) {
      // Louder floor: relax down slowly to the quieter ambient.
      noise += (rms - noise) * 0.08;
    } else {
      // Keep the floor low-ish when air is quiet; don't chase up into speech.
      noise += (rms - noise) * 0.002;
    }
    vad._noise = noise;

    // On-set threshold: comfortably above the noise floor + a small absolute
    // floor (so silence/really-quiet never trips). Release uses a lower
    // hangover threshold (hysteresis) so we don't chatter around the edge and
    // actually detect the pause.
    //
    // Levels are on the RMS of a 2048-sample frame (~43ms). Normal speech at a
    // conversational distance with autoGainControl is around 0.02–0.08 RMS; the
    // old absFloor=0.012 + noise*2.2 made Zenith only pick up loud, close speech.
    const absFloor = 0.004;
    const isAssistantSpeaking = liveStreaming || isSpeakingState();
    // During assistant speech, speech onset floor is raised slightly to prevent
    // acoustic speaker bleed from false-triggering, while enabling natural voice barge-in.
    const effectiveFloor = isAssistantSpeaking ? 0.016 : absFloor;
    const onThresh = Math.max(effectiveFloor, noise * (isAssistantSpeaking ? 2.2 : 1.6));
    const offThresh = Math.max(absFloor * 0.5, noise * 1.05);
    const speechNow = rms > (vad.speech ? offThresh : onThresh);

    // Paused OR while we already have a speech chunk in flight: hold detection
    // state but don't stack utterances. Only voicePaused truly halts.
    if (voicePaused || (processingSpeech && !vad.speech)) {
      vad._onsetMs = (voicePaused || processingSpeech) ? 0 : vad._onsetMs;
      return;
    }

    // Brief settling delay right after audio ends to absorb room reverberation
    if (!vad.speech && !isAssistantSpeaking && liveReplyEnd && (t - liveReplyEnd) < 250) {
      vad._onsetMs = 0;
      return;
    }

    if (speechNow && vad.speech) {
      vad.silenceStartMs = 0;
      if (t - vad.speechStartMs > cfg.max_utterance_ms) {
        // long monologue — roll over to a fresh utterance
        vad.speech = false;
        finishUtteranceNow();
      }
    } else if (speechNow && !vad.speech) {
      // speech onset
      if (!vad._onsetMs) vad._onsetMs = t;
      if (t - vad._onsetMs > cfg.min_speech_ms) {
        vad.speech = true;
        vad.speechStartMs = t;
        vad._onsetMs = 0;
        stopAssistantSpeech(); // barge-in (stops any playing reply and resets live session)
        $("v-status").textContent = "voice · listening…";
        setVoiceState("listening");
        startMediaRecorder();
      }
    } else if (!speechNow && vad.speech) {
      if (!vad.silenceStartMs) vad.silenceStartMs = t;
      if (t - vad.silenceStartMs > cfg.silence_ms) {
        vad.speech = false;
        vad.silenceStartMs = 0;
        // Live: tell the model the user's audio turn ended so it finalizes the
        // ASR and starts answering immediately (the client-side VAD is the
        // end-of-speech signal — hybrid VAD, no server silence wait).
        finishUtteranceNow();
      }
    } else if (!speechNow && !vad.speech) {
      vad._onsetMs = 0;
    }
  }

  function finishUtteranceNow() {
    stopMediaRecorder();
    // Live mode: the end-turn signal already went out over /ws/live and the
    // model is answering. Nothing more to transcribe.
    if (useLiveStreaming && !liveWsRefused && liveWs && liveWs.readyState === WebSocket.OPEN) {
      processingSpeech = false;
      refreshVoiceStatus();
      return;
    }
    processingSpeech = true;
    // Classic mode: wait for the final ondataavailable chunk (stop() is async)
    // so the whole utterance reaches Groq, then transcribe.
    setTimeout(() => { if (processingSpeech) sendRecordedAudio(); }, 120);
  }

  function stopAssistantSpeech() {
    stopLivePlayback();
    try {
      if (liveWs && liveWs.readyState === WebSocket.OPEN) {
        liveWs.send(JSON.stringify({ type: "barge_in" }));
      }
    } catch {}
    try {
      if (window.zenithAudio) { window.zenithAudio.pause(); window.zenithAudio = null; }
    } catch {}
    try { window.speechSynthesis.cancel(); } catch {}
  }

  async function ensureMic() {
    if (micReady && micStream && micStream.active) return;
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      micReady = false;
      throw new Error("no-media");
    }
    // echoCancellation + noiseSuppression keep Zenith's own voice out of the
    // VAD (so it doesn't self-trigger) while still letting you barge in.
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    micReady = true;
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      audioCtx.createMediaStreamSource(micStream).connect(analyser);
    }
    // Calibrate the noise floor over ~600ms before arming VAD, so ambient
    // room noise is measured and speech is detected relative to it.
    vad._noise = 0;
    vad._calibUntil = performance.now() + 600;
    vad._calibSum = 0;
    vad._calibN = 0;
    // Re-arm VAD before we draw so the first utterance can start immediately.
    vad.enabled = true;
  }

  async function openVoice() {
    const mod = $("vmod");
    if (!mod) return;
    mod.classList.add("open");
    const vBtn = $("voice-btn");
    if (vBtn) vBtn.classList.add("active");
    $("v-text").textContent = "keep talking — Zenith will listen.";
    // Opening the voice layer is a fresh start: give Live streaming another
    // chance even if a previous session's refusals tripped the guard.
    liveWsRefused = false;
    refreshVoiceStatus();

    // Silence-detection state lives in vadFrame (on the orb rAF loop).
    try {
      await ensureMic();
    } catch (e) {
      console.warn("Microphone access error:", e);
      micReady = false;
      micStream = null;
      refreshVoiceStatus();
      return;
    }
    voicePaused = false;
    refreshVoiceStatus();
    drawOrb();
    // Continuous listening: the rolling MediaRecorder (or Live session) starts
    // up front and runs the whole session, so speech onset is never clipped
    // (pre-roll ring). In Live mode this also opens /ws/live so PCM is already
    // flowing when the user starts talking.
    startMediaRecorder();
  }

  function closeVoice() {
    const mod = $("vmod");
    if (mod) mod.classList.remove("open");
    const vBtn = $("voice-btn");
    if (vBtn) vBtn.classList.remove("active");

    vad.enabled = false;
    vad.speech = false;
    voicePaused = false;
    const st = $("v-status");
    if (st) st.textContent = "voice";

    micReady = false;
    isListening = false;
    if (speechRecognizer) { try { speechRecognizer.stop(); } catch {} speechRecognizer = null; }
    stopMediaRecorder();
    mediaRecorder = null;
    audioChunks = [];
    // End the persistent Gemini Live session (if one is open) before tearing
    // down the mic — it may still be buffering/streaming the last utterance.
    shutdownLive(true);
    if (micStream) { micStream.getTracks().forEach((t) => t.stop()); micStream = null; }
    if (audioCtx) { try { audioCtx.close(); } catch {} audioCtx = null; }
    liveAudioCtx = null;
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (orbAnim) { cancelAnimationFrame(orbAnim); orbAnim = null; }
  }

  window.zenithAudio = null;

  function speak(text, onDone) {
    if (!text) {
      if (onDone) onDone();
      return;
    }
    onDone = onDone || function () {};

    // Spoken replies off (G) → finish the turn silently but let the flow end.
    if (zenithVoiceSpoken === false) {
      onDone();
      return;
    }

    let spokenText = text
      .replace(/```[\s\S]*?```/g, " I have generated the code on your screen. ")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/(?:https?|ftp):\/\/[\n\S]+/g, '')
      .replace(/[*_#~|<=>]/g, " ")
      .replace(/\s+/g, " ")
      .trim();

    if (!spokenText) {
      onDone();
      return;
    }

    if (spokenText.length > 350) {
      spokenText = spokenText.slice(0, 340) + ". The full result is available on screen.";
    }

    $("v-status").textContent = "voice · speaking…";
    $("v-text").textContent = `“${spokenText}”`;
    setVoiceState("idle");

    // Server streaming: fewer round-trips, low latency. WebSpeech is the fallback.
    if (useStreamingTTS && navigator.mediaDevices && window.fetch) {
      playStreamedTTS(spokenText, onDone);
      return;
    }

    try {
      if (window.zenithAudio) {
        try { window.zenithAudio.pause(); } catch {}
      }
      const audioUrl = `/api/tts?text=${encodeURIComponent(spokenText)}`;
      window.zenithAudio = new Audio(audioUrl);
      window.zenithAudio.volume = 0.95;

      window.zenithAudio.onended = () => {
        $("v-text").textContent = "keep talking — Zenith will listen.";
        setVoiceState("idle");
        liveReplyEnd = 0;  // reply done — VAD re-arms
        if (voiceOpen()) refreshVoiceStatus();
        onDone();
      };

      window.zenithAudio.onerror = () => {
        liveReplyEnd = 0;
        speakWebSpeech(spokenText, onDone);
      };

      // Echo-mute while Zenith speaks (one-shot path)
      liveReplyEnd = performance.now() + Math.max(400, (window.zenithAudio.duration || 2) * 1000);
      const playPromise = window.zenithAudio.play();
      if (playPromise !== undefined) {
        playPromise.catch(() => {
          liveReplyEnd = 0;
          speakWebSpeech(spokenText, onDone);
        });
      }
      return;
    } catch (e) {
      console.warn("Server TTS play failed, using WebSpeech API:", e);
    }
    speakWebSpeech(spokenText, onDone);
  }

  async function playStreamedTTS(text, onDone) {
    try {
      const resp = await fetch(`/api/tts?stream=1&text=${encodeURIComponent(text)}`);
      if (!resp.ok) throw new Error("tts status " + resp.status);
      const ct = resp.headers.get("content-type") || "";
      if (ct.includes("json")) {
        const d = await resp.json();
        if (d.status === "error") { speakWebSpeech(text, onDone); return; }
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      stopAssistantSpeech();
      const audio = new Audio(url);
      window.zenithAudio = audio;
      audio.volume = 0.95;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        $("v-text").textContent = "keep talking — Zenith will listen.";
        setVoiceState("idle");
        liveReplyEnd = 0;  // reply done — VAD re-arms
        if (voiceOpen()) refreshVoiceStatus();
        onDone();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        liveReplyEnd = 0;
        speakWebSpeech(text, onDone);
      };
      // Echo-mute while Zenith speaks (streamed path)
      liveReplyEnd = performance.now() + Math.max(400, (audio.duration || 2) * 1000);
      await audio.play().catch(() => {
        URL.revokeObjectURL(url);
        liveReplyEnd = 0;
        speakWebSpeech(text, onDone);
      });
    } catch (e) {
      console.warn("Streamed TTS failed:", e);
      speakWebSpeech(text, onDone);
    }
  }

  /* Play Gemini-Live native audio (a done event). */
  function playLiveAudio(b64, model, mime) {
    try {
      const rawB64 = b64.includes("%") ? decodeURIComponent(b64) : b64;
      const binary = atob(rawB64);
      const audioBytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) audioBytes[i] = binary.charCodeAt(i);
      const blob = new Blob([audioBytes], { type: mime || "audio/wav" }); // Live native-audio container
      const url = URL.createObjectURL(blob);
      stopAssistantSpeech();
      const audio = new Audio(url);
      window.zenithAudio = audio;
      audio.volume = 0.95;
      audio.onended = () => {
        URL.revokeObjectURL(url);
        $("v-text").textContent = "keep talking — Zenith will listen.";
        setVoiceState("idle");
        liveReplyEnd = 0;  // reply done — VAD can re-arm now
        if (voiceOpen()) refreshVoiceStatus();
        onVoiceTurnDone();
      };
      audio.onerror = () => {
        URL.revokeObjectURL(url);
        liveReplyEnd = 0;
        onVoiceTurnDone();
      };
      // Duration-aware echo mute: keep VAD muted for the whole reply so Zenith's
      // own voice can't re-trigger a new utterance while she's still talking.
      liveReplyEnd = performance.now() + Math.max(400, (audio.duration || 2) * 1000);
      audio.play();
    } catch (e) {
      console.warn("Live audio play failed:", e);
      liveReplyEnd = 0;
      onVoiceTurnDone();
    }
  }

  function speakWebSpeech(spokenText, onDone) {
    if (!window.speechSynthesis) { if (onDone) onDone(); return; }
    try {
      window.speechSynthesis.cancel();
      if (window.speechSynthesis.resume) window.speechSynthesis.resume();
      const u = new SpeechSynthesisUtterance(spokenText);
      if (selectedFemaleVoice) u.voice = selectedFemaleVoice;
      u.pitch = 1.08; u.rate = 0.95; u.volume = 0.95;

      // Echo-mute for the duration (approximate: 14 chars/sec).
      liveReplyEnd = performance.now() + Math.max(400, spokenText.length / 14 * 1000);
      u.onend = () => {
        liveReplyEnd = 0;
        setVoiceState("idle");
        if (voiceOpen()) refreshVoiceStatus();
        if (onDone) onDone();
      };
      window.speechSynthesis.speak(u);
    } catch {
      liveReplyEnd = 0;
      if (onDone) onDone();
    }
  }

  // ONE consistent orb: a calm warm-glow sphere that always renders, pulses
// gently when idle, brightens with captured voice, and shows a soft star only
// during speech. No separate "two orbs" state — it is always the same orb.
  function drawOrb() {
    const cv = $("orb-canvas");
    if (!cv) return;
    if (!voiceOpen()) {
      if (orbAnim) { cancelAnimationFrame(orbAnim); orbAnim = null; }
      return;
    }
    const ctx = cv.getContext("2d");
    const d = analyser ? new Uint8Array(analyser.frequencyBinCount) : new Uint8Array(32);
    let phase = 0;
    (function frame() {
      if (!voiceOpen()) {
        if (orbAnim) { cancelAnimationFrame(orbAnim); orbAnim = null; }
        return;
      }
      orbAnim = requestAnimationFrame(frame);
      const isSpeaking = liveStreaming || isSpeakingState();
      const activeAnalyser = (isSpeaking && liveAnalyser) ? liveAnalyser : analyser;
      if (activeAnalyser) activeAnalyser.getByteFrequencyData(d);
      let sum = 0;
      for (let i = 0; i < d.length; i++) sum += d[i];
      const t = sum / d.length;
      volume += (t - volume) * 0.14;

      // Voice-activity detection shares the frame loop.
      vadFrame(performance.now());
      // Gentle idle breathing so the orb stays alive (and consistent).
      if (!vad.speech && !isSpeaking && !processingSpeech && voicePaused === false) {
        volume *= 1 - 0.015;
      }

      ctx.clearRect(0, 0, cv.width, cv.height);
      const cx = cv.width / 2, cy = cv.height / 2;
      volume *= 0.94;
      const r = 44 + Math.min(28, volume * 0.4);
      phase += 0.02;

      // Warm violet glow — always drawn, the orb's body.
      const lg = ctx.createRadialGradient(cx, cy, r * 0.25, cx, cy, r * 1.9);
      lg.addColorStop(0, "rgba(124,111,247,0.6)");
      lg.addColorStop(0.45, "rgba(138,126,255,0.28)");
      lg.addColorStop(1, "rgba(108,99,247,0)");
      ctx.fillStyle = lg;
      ctx.beginPath(); ctx.arc(cx, cy, r * 1.9, 0, Math.PI * 2); ctx.fill();

      // Inner sphere (calm core).
      ctx.beginPath(); ctx.arc(cx, cy, r * 0.42, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(124,111,247,0.45)";
      ctx.shadowColor = "rgba(124,111,247,0.55)";
      ctx.shadowBlur = 16 + ((vad.speech || isSpeaking) ? volume * 0.6 : 8);
      ctx.fill();
      ctx.shadowBlur = 0;

      // Dynamic harmonic ripples while user speaks OR Zenith speaks
      if ((vad.speech || isSpeaking) && activeAnalyser) {
        ctx.save();
        ctx.translate(cx, cy);
        ctx.beginPath();
        const rays = isSpeaking ? 18 : 14;
        for (let i = 0; i < rays; i++) {
          const an = (i / rays) * Math.PI * 2;
          const di = (d[i % d.length] / 255) * (isSpeaking ? 16 : 14) * Math.sin(phase + i);
          const rr = r + 10 + di;
          const x = Math.cos(an) * rr, y = Math.sin(an) * rr;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.closePath();
        ctx.fillStyle = isSpeaking ? "rgba(168,140,255,0.4)" : "rgba(138,126,255,0.35)";
        ctx.fill();
        ctx.restore();
      }
    })();
  }

  // Initialize attachment handlers
  initAttachmentHandlers();

  // ── God's Eye View Fullscreen Handler ──
  window.toggleGevFullscreen = function(btn) {
    const wrapper = btn ? btn.closest('.gev-embed-wrapper') : null;
    if (!wrapper) return;
    const isFull = wrapper.classList.toggle('fullscreen');
    const label = btn.querySelector('.gev-btn-label');
    if (label) {
      label.textContent = isFull ? 'Exit Full Screen' : 'Full Screen';
    }
    const icon = btn.querySelector('.gev-btn-icon');
    if (icon) {
      icon.innerHTML = isFull
        ? '<path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>'
        : '<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>';
    }
    if (isFull) {
      document.body.classList.add('gev-fullscreen-active');
    } else {
      document.body.classList.remove('gev-fullscreen-active');
    }
  };

  window.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      const active = document.querySelector('.gev-embed-wrapper.fullscreen');
      if (active) {
        const btn = active.querySelector('.gev-fullscreen-btn');
        if (btn) window.toggleGevFullscreen(btn);
        else active.classList.remove('fullscreen');
      }
      const ctxDrawer = document.getElementById('context-drawer');
      if (ctxDrawer && ctxDrawer.style.display !== 'none') {
        ctxDrawer.style.display = 'none';
        const ctxBtn = document.getElementById('context-btn');
        if (ctxBtn) ctxBtn.classList.remove('active');
      }
    }
  });
})();
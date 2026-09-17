"""Zenith — Setup & Secrets Management Engine.

Provides catalog definitions for all secrets and configuration settings,
methods to test API keys (e.g. Gemini AI Studio), safe masked config exports,
and robust .env file generation and reloading.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx

from .config import PROJECT_ROOT, settings

log = logging.getLogger("zenith.setup")


# ── Configuration Catalog Definition ──────────────────────────────────────────
# Every capability in Zenith maps to one of these entries.

SECRETS_CATALOG = [
    # ── Category 1: AI Brain (Core LLM) ──────────────────────────────────────
    {
        "key": "GEMINI_API_KEY",
        "label": "Google Gemini API Key",
        "category": "brain",
        "category_label": "AI Brain & Intelligence",
        "category_icon": "brain",
        "required": True,
        "is_secret": True,
        "placeholder": "AIzaSy...",
        "description": "The central reasoning engine for Zenith. Powers conversational intelligence, tool selection, reasoning, and autonomous actions.",
        "where_to_get_url": "https://aistudio.google.com/apikey",
        "where_to_get_label": "Google AI Studio",
        "guide_steps": [
            "Visit https://aistudio.google.com/apikey and sign in with your Google account.",
            "Click '+ Create API Key' (choose or create a Google Cloud project).",
            "Copy the key (starts with 'AIzaSy...') and paste it here.",
            "The free tier includes generous rate limits for Gemini 3.5 Flash and Gemini 3.1 Flash Lite."
        ],
    },
    {
        "key": "FALLBACK_API_KEY",
        "label": "Fallback Provider API Key",
        "category": "brain",
        "category_label": "AI Brain & Intelligence",
        "category_icon": "brain",
        "required": False,
        "is_secret": True,
        "placeholder": "sk-...",
        "description": "Backup OpenAI-compatible API key (DeepSeek, OpenAI, Groq, OpenRouter) used if Gemini hits rate limits (429) or quota exhaustion.",
        "where_to_get_url": "https://platform.deepseek.com/api_keys",
        "where_to_get_label": "DeepSeek Platform (or OpenAI / OpenRouter)",
        "guide_steps": [
            "Get an API key from DeepSeek (https://platform.deepseek.com), OpenAI (https://platform.openai.com), or OpenRouter (https://openrouter.ai).",
            "Zenith will automatically route requests here if Gemini experiences high load or quota limits."
        ],
    },
    {
        "key": "FALLBACK_ENDPOINT",
        "label": "Fallback Endpoint URL",
        "category": "brain",
        "category_label": "AI Brain & Intelligence",
        "category_icon": "brain",
        "required": False,
        "is_secret": False,
        "default": "https://api.deepseek.com/v1/chat/completions",
        "placeholder": "https://api.deepseek.com/v1/chat/completions",
        "description": "The full chat completions URL for the fallback provider.",
        "where_to_get_url": "https://platform.deepseek.com",
        "where_to_get_label": "Provider Docs",
        "guide_steps": [
            "For DeepSeek: https://api.deepseek.com/v1/chat/completions",
            "For OpenAI: https://api.openai.com/v1/chat/completions",
            "For OpenRouter: https://openrouter.ai/api/v1/chat/completions",
        ],
    },
    {
        "key": "FALLBACK_MODEL",
        "label": "Fallback Model ID",
        "category": "brain",
        "category_label": "AI Brain & Intelligence",
        "category_icon": "brain",
        "field_type": "select",
        "options": [
            {"value": "deepseek-chat", "label": "DeepSeek Chat (deepseek-chat)"},
            {"value": "gpt-4o-mini", "label": "OpenAI GPT-4o Mini (gpt-4o-mini)"},
            {"value": "deepseek-v4-flash-0731", "label": "DeepSeek V4 Flash"},
            {"value": "meta-llama/llama-3.3-70b-instruct", "label": "Llama 3.3 70B (OpenRouter)"},
        ],
        "required": False,
        "is_secret": False,
        "default": "deepseek-chat",
        "placeholder": "deepseek-chat",
        "description": "Model identifier for the fallback provider (e.g. deepseek-chat, gpt-4o-mini, etc.).",
        "where_to_get_url": "https://platform.deepseek.com",
        "where_to_get_label": "Provider Models",
        "guide_steps": [
            "Enter or select the model string supported by your fallback provider.",
        ],
    },
    {
        "key": "WORKER_URL",
        "label": "Antigravity Coding Worker Endpoint",
        "category": "ai",
        "category_label": "AI Brain & Intelligence",
        "category_icon": "brain",
        "required": False,
        "is_secret": False,
        "default": "http://host.docker.internal:8022",
        "placeholder": "http://host.docker.internal:8022",
        "description": "Local REST seam for delegating complex engineering, file manipulation, and coding tasks to the Google Antigravity CLI (agy).",
        "where_to_get_url": "https://antigravity.google/docs/cli",
        "where_to_get_label": "Antigravity CLI Documentation",
        "guide_steps": [
            "Inside Docker, Zenith accesses the host worker via 'http://host.docker.internal:8022'.",
            "On bare metal without Docker, use 'http://127.0.0.1:8022'.",
            "Run './scripts/setup-worker.sh' to bootstrap the worker daemon.",
        ],
    },

    # ── Category 2: Personalization & Profile ─────────────────────────────────
    {
        "key": "USER_NAME",
        "label": "Your Name / Preferred Name",
        "category": "profile",
        "category_label": "User Profile & Identity",
        "category_icon": "user",
        "required": True,
        "is_secret": False,
        "default": "Friend",
        "placeholder": "e.g. Alex, Sarah, Jordan...",
        "description": "How Zenith will address you warmly in conversation, greetings, and briefings.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Type your first name or preferred nickname.",
            "Zenith personalizes its persona, tone, and memory store around you."
        ],
    },
    {
        "key": "USER_EMAIL",
        "label": "Your Primary Email Address",
        "category": "profile",
        "category_label": "User Profile & Identity",
        "category_icon": "user",
        "required": False,
        "is_secret": False,
        "placeholder": "you@example.com",
        "description": "Your email for receiving notifications, generated slides/documents, and proactive reminder digests.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Enter the email where you want to receive files, presentations, and reminders."
        ],
    },
    {
        "key": "USER_TIMEZONE",
        "label": "Your Timezone",
        "category": "profile",
        "category_label": "User Profile & Identity",
        "category_icon": "user",
        "field_type": "timezone",
        "required": False,
        "is_secret": False,
        "default": "Asia/Kolkata",
        "placeholder": "e.g. Asia/Kolkata, America/New_York, Europe/London",
        "description": "Ensures time-appropriate greetings, scheduling, and calendar alignment.",
        "where_to_get_url": "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones",
        "where_to_get_label": "IANA Timezones",
        "guide_steps": [
            "Click 'Auto-detect' to automatically set to your local browser timezone, or enter standard IANA strings."
        ],
    },
    {
        "key": "USER_BIO",
        "label": "About You / Your Interests & Goals",
        "category": "profile",
        "category_label": "User Profile & Identity",
        "category_icon": "user",
        "field_type": "textarea",
        "required": False,
        "is_secret": False,
        "placeholder": "e.g. Software engineer building web apps, tech enthusiast, researcher...",
        "description": "Context about who you are and what you work on. Zenith weaves this into memory and assists you accordingly.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Share what you do or your current focus so Zenith can tailor recommendations and tool usage to you."
        ],
    },
    {
        "key": "USER_BIRTHDAY",
        "label": "Birthday",
        "category": "profile",
        "category_label": "User Profile & Identity",
        "category_icon": "calendar",
        "field_type": "text",
        "required": False,
        "is_secret": False,
        "placeholder": "e.g. October 14, 2004 or 2004-10-14",
        "description": "Your birthday so Zenith can celebrate and remember milestones.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Enter your birthday in any recognizable format."
        ],
    },
    {
        "key": "USER_HOBBIES",
        "label": "Hobbies & Interests",
        "category": "profile",
        "category_label": "User Profile & Identity",
        "category_icon": "sparkles",
        "field_type": "text",
        "required": False,
        "is_secret": False,
        "placeholder": "e.g. Coding, homelab tinkering, photography, gaming, sci-fi",
        "description": "Your hobbies, passions, and favorite topics for personalized suggestions and conversations.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Enter hobbies separated by commas or short phrases."
        ],
    },

    # ── Category 3: Voice & Speech ────────────────────────────────────────────
    {
        "key": "GROQ_API_KEY",
        "label": "Groq Whisper API Key",
        "category": "voice",
        "category_label": "Voice & Live Audio",
        "category_icon": "mic",
        "required": False,
        "is_secret": True,
        "placeholder": "gsk_...",
        "description": "Enables ultra-fast, real-time Whisper speech-to-text (whisper-large-v3-turbo) for hands-free live conversation.",
        "where_to_get_url": "https://console.groq.com/keys",
        "where_to_get_label": "Groq Cloud Console",
        "guide_steps": [
            "Go to https://console.groq.com and sign up or log in (free tier provided).",
            "Go to 'API Keys' in the sidebar.",
            "Click 'Create API Key', give it a name, and copy the key (starts with 'gsk_').",
            "If omitted, Zenith will fall back to browser speech recognition."
        ],
    },
    {
        "key": "LIVE_VOICE_ENABLED",
        "label": "Gemini Live Native Audio Voice",
        "category": "voice",
        "category_label": "Voice & Live Audio",
        "category_icon": "mic",
        "field_type": "switch",
        "required": False,
        "is_secret": False,
        "default": "yes",
        "description": "Bidirectional native speech streaming using Gemini Live WebSockets directly over raw PCM audio.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Enable for Gemini Live bidirectional voice streaming.",
            "Disable to use the Groq Whisper STT + Edge TTS pipeline."
        ],
    },
    {
        "key": "EDGE_VOICE",
        "label": "Neural Spoken Voice",
        "category": "voice",
        "category_label": "Voice & Live Audio",
        "category_icon": "mic",
        "field_type": "select",
        "options": [
            {"value": "en-IN-NeerjaNeural", "label": "en-IN-NeerjaNeural (Indian English · Warm & Calm) ★ Default"},
            {"value": "en-US-AriaNeural", "label": "en-US-AriaNeural (US English · Conversational)"},
            {"value": "en-US-GuyNeural", "label": "en-US-GuyNeural (US English · Deep & Calm Male)"},
            {"value": "en-US-JennyNeural", "label": "en-US-JennyNeural (US English · Expressive Female)"},
            {"value": "en-GB-SoniaNeural", "label": "en-GB-SoniaNeural (British English · Clear & Professional)"},
            {"value": "en-AU-NatashaNeural", "label": "en-AU-NatashaNeural (Australian English · Friendly)"},
        ],
        "required": False,
        "is_secret": False,
        "default": "en-IN-NeerjaNeural",
        "placeholder": "en-IN-NeerjaNeural",
        "description": "Natural neural voice for spoken replies. 100% free with no API key needed.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Select your preferred neural speaking accent and tone."
        ],
    },

    # ── Category 4: Email & Communication ─────────────────────────────────────
    {
        "key": "RESEND_API_KEY",
        "label": "Resend API Key",
        "category": "email",
        "category_label": "Email & Communication",
        "category_icon": "mail",
        "required": False,
        "is_secret": True,
        "placeholder": "re_...",
        "description": "Used by Zenith to autonomously send generated presentations (.pptx), documents (.pdf/.docx), research briefings, and reminder emails.",
        "where_to_get_url": "https://resend.com/api-keys",
        "where_to_get_label": "Resend Dashboard",
        "guide_steps": [
            "Go to https://resend.com and sign up for a free account (includes 3,000 free emails/month).",
            "Go to 'API Keys' -> 'Create API Key'.",
            "Copy the key starting with 're_'."
        ],
    },
    {
        "key": "RESEND_FROM",
        "label": "Resend Sender Address",
        "category": "email",
        "category_label": "Email & Communication",
        "category_icon": "mail",
        "required": False,
        "is_secret": False,
        "default": "Zenith <onboarding@resend.dev>",
        "placeholder": "Zenith <onboarding@resend.dev> or Zenith <zenith@yourdomain.com>",
        "description": "The sender name and email shown in the From line of sent emails.",
        "where_to_get_url": "https://resend.com/domains",
        "where_to_get_label": "Resend Domains",
        "guide_steps": [
            "For quick testing without domain verification, use 'Zenith <onboarding@resend.dev>'.",
            "To send from your custom domain, verify your domain in Resend and enter your email here."
        ],
    },
    {
        "key": "GMAIL_USER",
        "label": "Gmail Username (for Inbox Reading)",
        "category": "email",
        "category_label": "Email & Communication",
        "category_icon": "mail",
        "required": False,
        "is_secret": False,
        "placeholder": "you@gmail.com",
        "description": "Your Gmail address so Zenith can check incoming mail, summarize unread threads, and search your inbox.",
        "where_to_get_url": "https://gmail.com",
        "where_to_get_label": "Gmail",
        "guide_steps": [
            "Enter your full Gmail or Google Workspace address."
        ],
    },
    {
        "key": "GMAIL_APP_PASSWORD",
        "label": "Gmail App Password",
        "category": "email",
        "category_label": "Email & Communication",
        "category_icon": "mail",
        "required": False,
        "is_secret": True,
        "placeholder": "16-character app password (e.g. abcd efgh ijkl mnop)",
        "description": "Dedicated Google App Password allowing Zenith to read email via secure IMAP.",
        "where_to_get_url": "https://myaccount.google.com/apppasswords",
        "where_to_get_label": "Google Account App Passwords",
        "guide_steps": [
            "Go to https://myaccount.google.com/security and verify 2-Step Verification is turned ON.",
            "Visit https://myaccount.google.com/apppasswords.",
            "Create a new App Password named 'Zenith'.",
            "Copy the 16-character code and paste it here."
        ],
    },

    # ── Category 5: Maps & Calendar ───────────────────────────────────────────
    {
        "key": "GOOGLE_MAPS_API_KEY",
        "label": "Google Maps Platform API Key",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": True,
        "placeholder": "AIzaSy...",
        "description": "Unlocks live interactive Google Maps embeds in chat, driving/transit directions, commute times, and places/business searches.",
        "where_to_get_url": "https://console.cloud.google.com/google/maps-apis/credentials",
        "where_to_get_label": "Google Cloud Console",
        "guide_steps": [
            "Visit Google Cloud Console -> APIs & Services -> Enable APIs.",
            "Enable: Maps Embed API, Places API, Directions API, and Distance Matrix API.",
            "Go to Credentials -> 'Create Credentials' -> 'API Key'.",
            "Copy the key and paste it here."
        ],
    },
    {
        "key": "GOOGLE_CLIENT_ID",
        "label": "Google Calendar Client ID",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": False,
        "placeholder": "...apps.googleusercontent.com",
        "description": "OAuth 2.0 Client ID for Google Calendar event management.",
        "where_to_get_url": "https://console.cloud.google.com/apis/credentials",
        "where_to_get_label": "Google Cloud Credentials",
        "guide_steps": [
            "In Google Cloud Console -> Credentials -> Create Credentials -> OAuth Client ID.",
            "Select Web Application, add authorized redirect URIs, and copy the Client ID."
        ],
    },
    {
        "key": "GOOGLE_CLIENT_SECRET",
        "label": "Google Calendar Client Secret",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": True,
        "placeholder": "GOCSPX-...",
        "description": "OAuth 2.0 Client Secret for Google Calendar.",
        "where_to_get_url": "https://console.cloud.google.com/apis/credentials",
        "where_to_get_label": "Google Cloud Credentials",
        "guide_steps": [
            "Copy the Client Secret from the created OAuth Client."
        ],
    },
    {
        "key": "GOOGLE_REFRESH_TOKEN",
        "label": "Google Calendar Refresh Token",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": True,
        "placeholder": "1//0...",
        "description": "Long-lived refresh token obtained after granting calendar access.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Can be generated using 'python scripts/google_calendar_auth.py' after providing Client ID and Secret."
        ],
    },
    {
        "key": "CESIUM_ION_TOKEN",
        "label": "Cesium Ion Access Token (God's Eye View)",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": True,
        "placeholder": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "description": "Unlocks photorealistic 3D terrain, high-res satellite imagery, and 3D buildings in God's Eye View.",
        "where_to_get_url": "https://ion.cesium.com/tokens",
        "where_to_get_label": "Cesium Ion Tokens",
        "guide_steps": [
            "Sign up or log in at Cesium Ion (https://ion.cesium.com).",
            "Go to 'Access Tokens' and copy your default token (or create one with assets:read scope).",
            "Paste the token here to enable photoreal 3D terrain in God's Eye View."
        ],
    },
    {
        "key": "GEV_ENABLED",
        "label": "God's Eye View 3D Globe Enabled",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": False,
        "placeholder": "yes",
        "description": "Enable real-time 3D God's Eye View spy satellite simulator embeds in Zenith chat.",
        "where_to_get_url": "https://github.com/bilawalsidhu/gods-eye-view",
        "where_to_get_label": "God's Eye View Repository",
        "guide_steps": [
            "Set to 'yes' (or 'true') to enable 3D globe embeds, or 'no' to disable."
        ],
    },
    {
        "key": "GEV_PORT",
        "label": "God's Eye View Server Port",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": False,
        "placeholder": "4173",
        "description": "Local port for the God's Eye View server (default 4173).",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Default is 4173. Change if port conflicts with other local services."
        ],
    },
    {
        "key": "GEV_PUBLIC_URL",
        "label": "God's Eye View Public URL Override",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": False,
        "placeholder": "https://gev.yourdomain.com",
        "description": "Optional custom public URL for God's Eye View when hosted behind a reverse proxy or tunnel.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Leave blank to use default local routing or reverse proxy."
        ],
    },
    {
        "key": "OPENSKY_CLIENT_ID",
        "label": "OpenSky Network Username (Live Aircraft)",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": False,
        "placeholder": "opensky_username",
        "description": "Enables live ADS-B commercial flight tracking and high-frequency aircraft telemetry in God's Eye View.",
        "where_to_get_url": "https://opensky-network.org",
        "where_to_get_label": "OpenSky Network",
        "guide_steps": [
            "Create a free account at opensky-network.org.",
            "Enter your OpenSky username here."
        ],
    },
    {
        "key": "OPENSKY_CLIENT_SECRET",
        "label": "OpenSky Network Password / Secret",
        "category": "maps_calendar",
        "category_label": "Maps & Calendar",
        "category_icon": "map",
        "required": False,
        "is_secret": True,
        "placeholder": "opensky_password",
        "description": "Password or API secret for OpenSky Network live aircraft tracking.",
        "where_to_get_url": "https://opensky-network.org",
        "where_to_get_label": "OpenSky Network",
        "guide_steps": [
            "Enter your OpenSky Network account password."
        ],
    },

    # ── Category 6: Cloud & Developer Tools ───────────────────────────────────
    {
        "key": "CLOUDFLARE_API_TOKEN",
        "label": "Cloudflare API Token",
        "category": "cloud",
        "category_label": "Cloud & Web Services",
        "category_icon": "cloud",
        "required": False,
        "is_secret": True,
        "placeholder": "cfat_... or cfut_...",
        "description": "Enables Zenith to autonomously manage DNS records, check tunnel status, and configure email routing.",
        "where_to_get_url": "https://dash.cloudflare.com/profile/api-tokens",
        "where_to_get_label": "Cloudflare API Tokens",
        "guide_steps": [
            "Go to Cloudflare Dashboard -> My Profile -> API Tokens.",
            "Click 'Create Token' -> Use 'Edit zone DNS' template.",
            "Choose your Zone resources and create the token."
        ],
    },
    {
        "key": "CLOUDFLARE_ZONE",
        "label": "Cloudflare Zone (Domain)",
        "category": "cloud",
        "category_label": "Cloud & Web Services",
        "category_icon": "cloud",
        "required": False,
        "is_secret": False,
        "placeholder": "yourdomain.com",
        "description": "Your root domain name managed on Cloudflare.",
        "where_to_get_url": "https://dash.cloudflare.com",
        "where_to_get_label": "Cloudflare Dashboard",
        "guide_steps": [
            "Enter the domain name you manage in Cloudflare (e.g. example.com)."
        ],
    },
    {
        "key": "VERCEL_TOKEN",
        "label": "Vercel API Token",
        "category": "cloud",
        "category_label": "Cloud & Web Services",
        "category_icon": "cloud",
        "required": False,
        "is_secret": True,
        "placeholder": "...",
        "description": "Allows Zenith to inspect deployments, trigger project builds, and check preview domains on Vercel.",
        "where_to_get_url": "https://vercel.com/account/tokens",
        "where_to_get_label": "Vercel Account Settings",
        "guide_steps": [
            "Go to Vercel Dashboard -> Account Settings -> Tokens.",
            "Create a new token with appropriate scope and paste it here."
        ],
    },
    {
        "key": "HACKCLUB_CDN_KEY",
        "label": "Hack Club CDN Key",
        "category": "cloud",
        "category_label": "Cloud & Web Services",
        "category_icon": "cloud",
        "required": False,
        "is_secret": True,
        "placeholder": "...",
        "description": "Enables instant public hosting for generated images, documents, and assets at cdn.hackclub.com.",
        "where_to_get_url": "https://cdn.hackclub.com",
        "where_to_get_label": "Hack Club CDN",
        "guide_steps": [
            "Get your API key from https://cdn.hackclub.com to enable public asset uploads."
        ],
    },
    {
        "key": "GITHUB_USER",
        "label": "GitHub Username / Organization",
        "category": "cloud",
        "category_label": "Cloud & Web Services",
        "category_icon": "cloud",
        "required": False,
        "is_secret": False,
        "placeholder": "e.g. your-github-handle",
        "description": "Default GitHub username or organization for listing repos, opening issues, and creating branches.",
        "where_to_get_url": "https://github.com/settings/profile",
        "where_to_get_label": "GitHub Profile",
        "guide_steps": [
            "Enter your personal GitHub username or default organization name."
        ],
    },
    {
        "key": "GITHUB_TOKEN",
        "label": "GitHub Personal Access Token (PAT)",
        "category": "cloud",
        "category_label": "Cloud & Web Services",
        "category_icon": "cloud",
        "required": False,
        "is_secret": True,
        "placeholder": "ghp_... or github_pat_...",
        "description": "Personal access token with repo scope for automated git actions and PR management.",
        "where_to_get_url": "https://github.com/settings/tokens",
        "where_to_get_label": "GitHub Personal Access Tokens",
        "guide_steps": [
            "Go to GitHub -> Settings -> Developer Settings -> Personal Access Tokens -> Tokens (classic).",
            "Generate new token with 'repo' and 'read:user' permissions, and paste it here."
        ],
    },

    # ── Category 7: Homelab & Smart Home ──────────────────────────────────────
    {
        "key": "HOME_ASSISTANT_URL",
        "label": "Home Assistant Instance URL",
        "category": "smart_home",
        "category_label": "Smart Home & Homelab",
        "category_icon": "home",
        "required": False,
        "is_secret": False,
        "default": "http://172.17.0.1:8123",
        "placeholder": "http://homeassistant.local:8123 or IP:8123",
        "description": "The base URL for your local Home Assistant installation.",
        "where_to_get_url": "https://www.home-assistant.io",
        "where_to_get_label": "Home Assistant Docs",
        "guide_steps": [
            "Enter your local Home Assistant URL (e.g. http://192.168.1.100:8123 or http://homeassistant.local:8123)."
        ],
    },
    {
        "key": "HOME_ASSISTANT_TOKEN",
        "label": "Home Assistant Long-Lived Access Token",
        "category": "smart_home",
        "category_label": "Smart Home & Homelab",
        "category_icon": "home",
        "required": False,
        "is_secret": True,
        "placeholder": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
        "description": "Allows Zenith to control smart lights, switches, AC, fans, thermostats, and query telemetry.",
        "where_to_get_url": "",
        "where_to_get_label": "Home Assistant Profile",
        "guide_steps": [
            "In Home Assistant, click your Profile icon at bottom-left.",
            "Scroll down to 'Long-Lived Access Tokens'.",
            "Click 'Create Token', name it 'Zenith', and copy the full JWT string."
        ],
    },
    {
        "key": "SONARR_API_KEY",
        "label": "Sonarr API Key",
        "category": "smart_home",
        "category_label": "Smart Home & Homelab",
        "category_icon": "home",
        "required": False,
        "is_secret": True,
        "placeholder": "...",
        "description": "For TV series automation and queue monitoring via Sonarr.",
        "where_to_get_url": "",
        "where_to_get_label": "Sonarr Settings -> General",
        "guide_steps": [
            "Found in Sonarr under Settings -> General -> Security -> API Key."
        ],
    },
    {
        "key": "RADARR_API_KEY",
        "label": "Radarr API Key",
        "category": "smart_home",
        "category_label": "Smart Home & Homelab",
        "category_icon": "home",
        "required": False,
        "is_secret": True,
        "placeholder": "...",
        "description": "For movie automation and download management via Radarr.",
        "where_to_get_url": "",
        "where_to_get_label": "Radarr Settings -> General",
        "guide_steps": [
            "Found in Radarr under Settings -> General -> Security -> API Key."
        ],
    },

    # ── Category 8: Permissions & Security ────────────────────────────────────
    {
        "key": "ALLOW_SHELL",
        "label": "Allow Host Shell Execution",
        "category": "security",
        "category_label": "Security & Permissions",
        "category_icon": "shield",
        "field_type": "switch",
        "required": False,
        "is_secret": False,
        "default": "no",
        "description": "Safety switch for running arbitrary shell commands. Keep disabled unless explicitly needed.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Enable only if you want Zenith to run arbitrary terminal shell commands on your host system."
        ],
    },
    {
        "key": "ALLOW_DOCKER",
        "label": "Allow Docker Container Management",
        "category": "security",
        "category_label": "Security & Permissions",
        "category_icon": "shield",
        "field_type": "switch",
        "required": False,
        "is_secret": False,
        "default": "yes",
        "description": "Allows Zenith to inspect container health, restart guarded containers, and monitor homelab vitals.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "Enable if running with the Docker socket (/var/run/docker.sock) mounted."
        ],
    },

    # ── Category 9: Art & Design Integrations ────────────────────────────────
    {
        "key": "FIGMA_CLIENT_ID",
        "label": "Figma OAuth Client ID",
        "category": "art_design",
        "category_label": "Art & Design",
        "category_icon": "palette",
        "required": False,
        "is_secret": False,
        "placeholder": "e.g. abc123def456...",
        "description": "Client ID for your Figma OAuth app. Enables Zenith to connect to Figma for reading designs, exporting assets, and AI-assisted design creation.",
        "where_to_get_url": "https://www.figma.com/developers/apps",
        "where_to_get_label": "Figma Developer Apps",
        "guide_steps": [
            "Go to https://www.figma.com/developers/apps and click 'Create a new app'.",
            "Select your team/organization, name it 'Zenith', and click Create.",
            "Copy the Client ID shown on the app page.",
            "Set the Redirect URL to: http://localhost:8005/api/integrations/figma/callback",
            "Select scopes: current_user:read, file_content:read.",
        ],
    },
    {
        "key": "FIGMA_CLIENT_SECRET",
        "label": "Figma OAuth Client Secret",
        "category": "art_design",
        "category_label": "Art & Design",
        "category_icon": "palette",
        "required": False,
        "is_secret": True,
        "placeholder": "Secret from Figma Developer Apps",
        "description": "Client secret for Figma OAuth token exchange. Stored securely and never sent to the browser.",
        "where_to_get_url": "https://www.figma.com/developers/apps",
        "where_to_get_label": "Figma Developer Apps",
        "guide_steps": [
            "The Client Secret is shown once when you first create your Figma OAuth app.",
            "If you lost it, you can regenerate it in your app settings.",
        ],
    },
    {
        "key": "FIGMA_REDIRECT_URI",
        "label": "Figma Redirect URI",
        "category": "art_design",
        "category_label": "Art & Design",
        "category_icon": "palette",
        "required": False,
        "is_secret": False,
        "default": "http://localhost:8005/api/integrations/figma/callback",
        "placeholder": "http://localhost:8005/api/integrations/figma/callback",
        "description": "The OAuth callback URL registered with your Figma app. Must match exactly.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "For local development: http://localhost:8005/api/integrations/figma/callback",
            "For production: https://yourdomain.com/api/integrations/figma/callback",
            "This must match the redirect URL registered in your Figma OAuth app.",
        ],
    },
    {
        "key": "CANVA_CLIENT_ID",
        "label": "Canva Connect Client ID",
        "category": "art_design",
        "category_label": "Art & Design",
        "category_icon": "palette",
        "required": False,
        "is_secret": False,
        "placeholder": "e.g. OC-AZBc2...",
        "description": "Client ID for your Canva Connect integration. Enables Zenith to create, list, and export Canva designs via AI.",
        "where_to_get_url": "https://www.canva.com/developers/integrations",
        "where_to_get_label": "Canva Developer Portal",
        "guide_steps": [
            "Go to https://www.canva.com/developers/integrations and create a new integration.",
            "Set a name and generate a client secret.",
            "Set scopes: design:content:read, design:meta:read, profile:read.",
            "Set the Redirect URL to: http://localhost:8005/api/integrations/canva/callback",
            "Copy the Client ID.",
        ],
    },
    {
        "key": "CANVA_CLIENT_SECRET",
        "label": "Canva Connect Client Secret",
        "category": "art_design",
        "category_label": "Art & Design",
        "category_icon": "palette",
        "required": False,
        "is_secret": True,
        "placeholder": "Secret from Canva Developer Portal",
        "description": "Client secret for Canva OAuth token exchange. Used server-side only.",
        "where_to_get_url": "https://www.canva.com/developers/integrations",
        "where_to_get_label": "Canva Developer Portal",
        "guide_steps": [
            "Generated when you create your integration in the Canva Developer Portal.",
            "Store it securely — it's shown only once.",
        ],
    },
    {
        "key": "CANVA_REDIRECT_URI",
        "label": "Canva Redirect URI",
        "category": "art_design",
        "category_label": "Art & Design",
        "category_icon": "palette",
        "required": False,
        "is_secret": False,
        "default": "http://localhost:8005/api/integrations/canva/callback",
        "placeholder": "http://localhost:8005/api/integrations/canva/callback",
        "description": "The OAuth callback URL for Canva. Must match the URL registered in your integration.",
        "where_to_get_url": "",
        "where_to_get_label": "",
        "guide_steps": [
            "For local development: http://localhost:8005/api/integrations/canva/callback",
            "For production: https://yourdomain.com/api/integrations/canva/callback",
        ],
    },
]


def mask_secret(val: str) -> str:
    """Mask sensitive keys for safe display in UI."""
    if not val:
        return ""
    clean = str(val).strip()
    if len(clean) <= 8:
        return "•" * len(clean)
    return f"{clean[:5]}...{clean[-4:]}"


def get_status() -> dict[str, Any]:
    """Check whether Zenith has been onboarded/configured."""
    has_gemini = bool(settings.gemini_api_key and str(settings.gemini_api_key).strip())
    completed = bool(has_gemini and (settings.setup_completed or (os.getenv("ZENITH_SETUP_COMPLETED", "")).lower() in {"1", "true", "yes"}))
    return {
        "setup_completed": completed,
        "has_gemini_key": has_gemini,
        "user_name": settings.user_name or "Friend",
        "auth_mode": settings.auth_mode,
    }


def get_catalog_with_values() -> list[dict[str, Any]]:
    """Return catalog populated with current values, masked for secrets."""
    results = []
    for item in SECRETS_CATALOG:
        k = item["key"]
        curr_raw = os.getenv(k, "").strip()
        is_set = bool(curr_raw)

        entry = dict(item)
        entry["is_set"] = is_set
        if item["is_secret"]:
            entry["current_display"] = mask_secret(curr_raw)
            entry["value"] = ""  # Never return raw secrets to client
        else:
            entry["current_display"] = curr_raw or item.get("default", "")
            entry["value"] = curr_raw or item.get("default", "")

        results.append(entry)
    return results


def get_setup_summary_text(category: str = "") -> str:
    """Generate a clean, structured text report of configured vs unconfigured integrations for Zenith to assist with."""
    catalog = get_catalog_with_values()
    if category:
        catalog = [item for item in catalog if item.get("category", "").lower() == category.lower()]

    categories: dict[str, list[dict]] = {}
    for item in catalog:
        cat_lbl = item.get("category_label", "Other")
        categories.setdefault(cat_lbl, []).append(item)

    configured_count = sum(1 for item in catalog if item["is_set"])
    total_count = len(catalog)

    name = settings.user_name or "Friend"
    lines = [
        f"# Zenith Setup & Integration Catalog ({configured_count}/{total_count} Configured)",
        f"Goal: Help {name} connect more services, tools, and secrets step-by-step without feeling overwhelmed.\n",
    ]

    for cat_lbl, items in categories.items():
        lines.append(f"### {cat_lbl}")
        for it in items:
            key = it["key"]
            lbl = it["label"]
            is_set = it["is_set"]
            disp = it["current_display"]
            url = it.get("where_to_get_url", "")
            desc = it.get("description", "")
            if is_set:
                lines.append(f"- **✓ {key}** ({lbl}): Configured (`{disp}`)")
            else:
                extra = f" | Where to get: {url}" if url else ""
                lines.append(f"- **• {key}** ({lbl}): *Not configured* — {desc}{extra}")
        lines.append("")

    return "\n".join(lines).strip()


async def test_gemini_api_key(api_key: str) -> dict[str, Any]:
    """Test a candidate Gemini API key directly against Google AI Studio API."""
    key = str(api_key).strip()
    if not key:
        return {"valid": False, "error": "API key cannot be empty."}

    # If OAuth AQ./ya29. token, handle differently if needed; standard API keys start with AIza
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
    headers = {"Content-Type": "application/json"}
    if key.startswith("AQ.") or key.startswith("ya29."):
        headers["Authorization"] = f"Bearer {key}"
        url = "https://generativelanguage.googleapis.com/v1beta/models"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "").replace("models/", "") for m in data.get("models", [])]
                flash_found = any("flash" in m.lower() for m in models)
                return {
                    "valid": True,
                    "message": "Key verified! Connected to Google AI Studio successfully.",
                    "models_count": len(models),
                    "supports_flash": flash_found,
                }
            else:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = err_json.get("error", {}).get("message", err_text)
                except Exception:
                    pass
                return {
                    "valid": False,
                    "error": f"Google API returned HTTP {resp.status_code}: {err_text}",
                }
    except httpx.TimeoutException:
        return {"valid": False, "error": "Connection to Google AI Studio timed out. Check your network."}
    except Exception as exc:
        return {"valid": False, "error": f"Verification failed: {exc}"}


def save_configuration(updates: dict[str, str]) -> dict[str, Any]:
    """Write or update configuration in the project .env file and trigger runtime reload."""
    env_path = PROJECT_ROOT / ".env"
    example_path = PROJECT_ROOT / ".env.example"

    # Read existing .env if present, otherwise read .env.example as baseline
    existing_lines: list[str] = []
    if env_path.is_file():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()
    elif example_path.is_file():
        existing_lines = example_path.read_text(encoding="utf-8").splitlines()

    # Build map of key -> (line_index, existing_val)
    line_indices: dict[str, int] = {}
    key_regex = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")

    for idx, line in enumerate(existing_lines):
        m = key_regex.match(line)
        if m:
            key_name = m.group(1)
            line_indices[key_name] = idx

    # Apply updates
    # Mark setup completed
    updates["ZENITH_SETUP_COMPLETED"] = "true"

    for k, v in updates.items():
        if isinstance(v, bool):
            val_str = "yes" if v else "no"
        else:
            val_str = str(v).strip()
            if k in {"LIVE_VOICE_ENABLED", "FALLBACK_PREFER", "ALLOW_SHELL", "ALLOW_DOCKER", "ALLOW_GITHUB", "ALLOW_SYSTEM"}:
                if val_str.lower() in {"true", "yes", "on", "1"}:
                    val_str = "yes"
                elif val_str.lower() in {"false", "no", "off", "0"}:
                    val_str = "no"
        # Quote values containing spaces or quotes
        if "\n" in val_str:
            continue
        formatted_val = f'"{val_str}"' if (" " in val_str or "#" in val_str) else val_str
        new_line = f"{k}={formatted_val}"

        if k in line_indices:
            existing_lines[line_indices[k]] = new_line
        else:
            existing_lines.append(new_line)
            line_indices[k] = len(existing_lines) - 1

    # Write back to .env
    new_content = "\n".join(existing_lines) + "\n"
    env_path.write_text(new_content, encoding="utf-8")
    log.info("Saved updated configuration to %s", env_path)

    # Sync updates directly to process environment
    for k, v in updates.items():
        if isinstance(v, bool):
            os.environ[k] = "true" if v else "false"
        else:
            os.environ[k] = str(v).strip()

    # Reload runtime settings in memory
    settings.reload()

    # Update memory store with user info if provided
    user_name = updates.get("USER_NAME")
    user_bio = updates.get("USER_BIO")
    user_email = updates.get("USER_EMAIL")
    user_birthday = updates.get("USER_BIRTHDAY")
    user_hobbies = updates.get("USER_HOBBIES")
    if user_name or user_bio or user_email or user_birthday or user_hobbies:
        try:
            from ..memory import store
            store.init_db()
            with store._connect() as conn:
                if user_name:
                    conn.execute("INSERT OR REPLACE INTO memories (category, key, value) VALUES ('user', 'name', ?)", (user_name,))
                if user_bio:
                    conn.execute("INSERT OR REPLACE INTO memories (category, key, value) VALUES ('user', 'bio', ?)", (user_bio,))
                if user_email:
                    conn.execute("INSERT OR REPLACE INTO memories (category, key, value) VALUES ('user', 'email', ?)", (user_email,))
                if user_birthday:
                    conn.execute("INSERT OR REPLACE INTO memories (category, key, value) VALUES ('user', 'birthday', ?)", (user_birthday,))
                if user_hobbies:
                    conn.execute("INSERT OR REPLACE INTO memories (category, key, value) VALUES ('user', 'hobbies', ?)", (user_hobbies,))
                conn.commit()
        except Exception as e:
            log.warning("Could not update user facts in memory store: %s", e)

    return {
        "success": True,
        "message": "Configuration saved successfully. Zenith is ready!",
        "setup_completed": True,
        "user_name": settings.user_name,
    }


async def summarize_and_store_profile(
    name: str,
    birthday: str = "",
    hobbies: str = "",
    bio: str = "",
) -> dict[str, Any]:
    """Summarize user profile info using Gemini / Provider and store facts and graph relations in Zenith memory."""
    import json
    from ..memory import store
    from . import provider

    store.init_db()

    updates: dict[str, str] = {}
    if name:
        updates["USER_NAME"] = name
    if birthday:
        updates["USER_BIRTHDAY"] = birthday
    if hobbies:
        updates["USER_HOBBIES"] = hobbies
    if bio:
        updates["USER_BIO"] = bio

    # Save to .env and reload runtime settings
    if updates:
        save_configuration(updates)

    # Baseline facts in memory
    target_name = name or settings.user_name or "Friend"
    store.save_memory("user", "name", target_name)
    if birthday:
        store.save_memory("user", "birthday", birthday)
    if hobbies:
        store.save_memory("user", "hobbies", hobbies)
    if bio:
        store.save_memory("user", "bio", bio)

    # Split hobbies into individual relations
    if hobbies:
        for item in re.split(r"[,;•\n]+", hobbies):
            item = item.strip()
            if item:
                store.add_relation(target_name, "interested_in", item, weight=1.0)

    summary_text = ""
    extracted_facts: list[dict[str, str]] = []

    # If any profile details are provided, summarize via LLM
    profile_has_info = bool(birthday or hobbies or bio)
    if profile_has_info:
        system_instruction = (
            "You are Zenith, an autonomous personal AI companion. "
            "You are learning about your companion for the first time during onboarding. "
            "Extract structured knowledge so you always remember who they are."
        )
        prompt = f"""The user just introduced themselves during onboarding:
- Name: {target_name}
- Birthday: {birthday or 'Not specified'}
- Hobbies & Interests: {hobbies or 'Not specified'}
- About / Bio: {bio or 'Not specified'}

Analyze this profile. Return a JSON object with:
1. "summary": A warm, natural 1-2 sentence understanding of who {target_name} is, what drives them, and how you should speak to them.
2. "facts": An array of key memory items, each with:
   - "category": one of "user", "preferences", "hobbies", "milestones", "projects"
   - "key": short identifier (e.g. "birthday", "primary_hobby", "current_focus", "personality_vibe")
   - "value": concise fact description
3. "relations": An array of knowledge graph connections, each with:
   - "source": "{target_name}"
   - "rel": relationship verb (e.g. "enjoys", "works_on", "passionate_about", "born_on")
   - "target": target entity (e.g. "Photography", "Rust", "October 14")

Return ONLY valid JSON with keys "summary", "facts", "relations". No markdown formatting or explanation outside JSON."""

        try:
            resp_text = await provider.chat_once(
                tier="fast",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=600,
            )

            # Strip possible markdown code fence
            clean_json = resp_text.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```[a-zA-Z]*\n?", "", clean_json)
                clean_json = re.sub(r"\n?```$", "", clean_json).strip()

            data = json.loads(clean_json)
            summary_text = data.get("summary", "")
            if summary_text:
                store.save_memory("user", "profile_summary", summary_text)

            facts = data.get("facts", [])
            if isinstance(facts, list):
                for f in facts:
                    if isinstance(f, dict) and "key" in f and "value" in f:
                        cat = str(f.get("category", "user"))
                        k = str(f["key"])
                        v = str(f["value"])
                        store.save_memory(cat, k, v)
                        extracted_facts.append({"category": cat, "key": k, "value": v})

            relations = data.get("relations", [])
            if isinstance(relations, list):
                for r in relations:
                    if isinstance(r, dict) and "source" in r and "rel" in r and "target" in r:
                        store.add_relation(str(r["source"]), str(r["rel"]), str(r["target"]), weight=1.0)

            log.info("Profile summarized via LLM for %s: %s facts extracted", target_name, len(extracted_facts))
        except Exception as e:
            log.warning("LLM profile summarization failed (falling back to direct storage): %s", e)
            if not summary_text:
                parts = []
                if bio:
                    parts.append(bio)
                if hobbies:
                    parts.append(f"Passionate about {hobbies}.")
                summary_text = " ".join(parts) or f"{target_name} is getting started with Zenith."
                store.save_memory("user", "profile_summary", summary_text)

    return {
        "success": True,
        "name": target_name,
        "summary": summary_text,
        "facts_stored": len(extracted_facts) + 4,
    }

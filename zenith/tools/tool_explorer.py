"""Tool catalog exploration and configuration introspection engine.

Provides full transparency into:
- All available tools Zenith can invoke across all 8 capability domains.
- Tool schemas, parameters, and descriptions.
- What tools and integrations can be configured, which API keys or credentials configure them,
  where to obtain them, and their live configuration status.
"""
from __future__ import annotations

import json
from typing import Any

from ..core import setup
from ..core.config import settings

TOOL_CATEGORIES = {
    "operating_layer": {
        "label": "🛡️ Sovereign Operating Layer & Vision",
        "prefixes": ("screen_observe", "activity_", "mem0_", "camera_capture",
                     "vision_detect", "privacy_control", "get_unified_context",
                     "browser_autonomous_goal"),
    },
    "system_shell": {
        "label": "🖥️ System, Shell & Execution",
        "prefixes": ("shell", "get_command_history", "get_system_info", "system_status",
                     "disk_usage", "memory_usage", "cpu_usage", "top_processes",
                     "read_file", "write_file", "list_dir", "time_now", "port_inspector",
                     "ping_check", "endpoint_health", "systemd_status", "systemd_control"),
    },
    "developer_git": {
        "label": "💻 Developer, Git & Cloud",
        "prefixes": ("git_", "gh_", "docker_", "mc_", "n8n_", "vercel_", "tunnel_",
                     "cf_", "r2_", "http_request", "dns_lookup", "agent"),
    },
    "web_browser": {
        "label": "🌐 Web, Browser & Search",
        "prefixes": ("web_search", "read_url", "browser", "web_extract_data",
                     "deep_research", "youtube_"),
    },
    "multimedia_design": {
        "label": "🎨 Multimedia, Documents & Design",
        "prefixes": ("generate_", "edit_presentation", "preview_presentation", "list_design_themes",
                     "list_pptx", "fetch_stock_photo", "search_presentation_photos",
                     "analyze_file", "read_presentation", "read_spreadsheet", "analyze_image", "edit_image", "modify_file", "delete_generated_file",
                     "list_generated_files", "cdn_", "figma_", "canva_", "design_"),
    },
    "smart_home_homelab": {
        "label": "🏠 Smart Home & Homelab",
        "prefixes": ("ha_", "jellyfin_", "media_", "torrent_control", "homelab_overview"),
    },
    "communication": {
        "label": "✉️ Communication & Productivity",
        "prefixes": ("email_", "mailbox_", "calendar", "notes", "todo", "maps_", "gods_eye_view"),
    },
    "ai_memory": {
        "label": "🧠 AI Memory & Knowledge Graph",
        "prefixes": ("memory", "graph"),
    },
    "configuration": {
        "label": "⚙️ Configuration & Personalization",
        "prefixes": ("get_setup_status", "setup_secret", "get_configurable_tools",
                     "get_available_tools", "update_user_profile", "ui_customize_theme",
                     "ui_inspect", "ui_reset_theme", "switch_mode", "get_mode", "zenith_docs"),
    },
}


def _classify_tool(name: str) -> str:
    for cat_id, cat_info in TOOL_CATEGORIES.items():
        for prefix in cat_info["prefixes"]:
            if name == prefix or name.startswith(prefix):
                return cat_id
    return "other"


def get_available_tools(category: str = "", query: str = "") -> str:
    """Explore and list tools available in Zenith.

    Args:
        category: Optional category filter ('operating_layer', 'system_shell', 'developer_git',
                  'web_browser', 'multimedia_design', 'smart_home_homelab', 'communication',
                  'ai_memory', 'configuration').
        query: Optional search term to filter tools by name or description.
    """
    from ..core import tools as tool_reg

    all_tools = tool_reg.TOOLS
    matched_tools: dict[str, dict[str, Any]] = {}

    cat_filter = category.strip().lower()
    q_filter = query.strip().lower()

    for name, t in all_tools.items():
        if t.get("hidden_from_catalog"):
            continue

        tool_cat = _classify_tool(name)
        if cat_filter and cat_filter not in tool_cat and cat_filter not in TOOL_CATEGORIES.get(tool_cat, {}).get("label", "").lower():
            continue

        desc = t.get("description", "")
        if q_filter:
            if q_filter not in name.lower() and q_filter not in desc.lower():
                continue

        matched_tools[name] = t

    if not matched_tools:
        return f"No tools found matching category='{category}' and query='{query}'."

    grouped: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for name, t in matched_tools.items():
        cat = _classify_tool(name)
        grouped.setdefault(cat, []).append((name, t))

    total = len(matched_tools)
    lines = [f"# Zenith Tools Catalog ({total} tools available)\n"]

    for cat_id, items in grouped.items():
        cat_meta = TOOL_CATEGORIES.get(cat_id, {"label": "📦 Other Tools"})
        lines.append(f"## {cat_meta['label']} ({len(items)} tools)")
        for name, t in sorted(items, key=lambda x: x[0]):
            desc = t.get("description", "").split("\n")[0]
            params = t.get("parameters", {}).get("properties", {})
            param_names = [f"{p}*" if p in t.get("parameters", {}).get("required", []) else p for p in params.keys()]
            param_str = f"({', '.join(param_names)})" if param_names else "()"
            lines.append(f"- **`{name}{param_str}`**: {desc}")
        lines.append("")

    return "\n".join(lines).strip()


def get_configurable_tools() -> str:
    """List all integrations, credentials, and settings that can be configured in Zenith.

    Explains which tools each configuration unlocks, whether credentials are set,
    and how to configure them on the fly.
    """
    catalog = setup.get_catalog_with_values()
    by_category: dict[str, list[dict[str, Any]]] = {}

    for item in catalog:
        cat_lbl = item.get("category_label", "General Settings")
        by_category.setdefault(cat_lbl, []).append(item)

    configured_count = sum(1 for item in catalog if item.get("is_set"))
    total_count = len(catalog)

    lines = [
        f"# 🛠️ Zenith Configurable Integrations & Tools Catalog",
        f"Status: **{configured_count} of {total_count}** configuration items configured.\n",
        "Zenith can configure any missing credential or setting on the fly using:",
        "- `setup_secret(key, value)` — Store API keys, tokens, or configuration strings safely in `.env`.",
        "- `update_user_profile(name, email, timezone, bio)` — Update user identity and preferences.",
        "- `ui_customize_theme(accent_color, font, custom_css)` — Live-customize UI appearance.\n",
    ]

    TOOL_MAPPING = {
        "GEMINI_API_KEY": "Required for all autonomous AI thinking, multi-turn reasoning, and conversational agent execution.",
        "FALLBACK_API_KEY": "Unlocks fallback LLM failover (DeepSeek / OpenAI / OpenRouter) if Gemini rate limits occur.",
        "ALLOW_SHELL": "Enables the `shell` command runner across Linux, macOS, and Windows.",
        "RESEND_API_KEY": "Enables outbound email sending (`email_send`, `email_reminder`, `email_draft`).",
        "GMAIL_APP_PASSWORD": "Enables reading and searching user emails (`email_search`, `email_read`).",
        "GROQ_API_KEY": "Unlocks ultra-fast Groq Whisper speech-to-text for live voice chats.",
        "GOOGLE_MAPS_API_KEY": "Enables interactive Google Maps embeds, directions, place search, and commute times (`maps_*`).",
        "CESIUM_ION_TOKEN": "Enables photorealistic 3D terrain, high-res satellite imagery, and 3D buildings in God's Eye View (`gods_eye_view`).",
        "GEV_ENABLED": "Toggles God's Eye View 3D spy satellite simulator embeds in chat (`gods_eye_view`).",
        "OPENSKY_CLIENT_ID": "Enables live ADS-B commercial flight tracking and telemetry in God's Eye View.",
        "OPENSKY_CLIENT_SECRET": "Password/secret for high-frequency live flight telemetry in God's Eye View.",
        "GITHUB_TOKEN": "Enables GitHub Pro tools (`gh_create_pr`, `gh_code_review`, `gh_list_repos`, `gh_create_issue`, etc.).",
        "HOME_ASSISTANT_TOKEN": "Enables Home Assistant smart home control (`ha_ac`, `ha_fan`, `ha_soundbar`, `ha_smart_plug`, `ha_overview`).",
        "JELLYFIN_API_KEY": "Enables homelab media streaming search and status (`jellyfin_search`, `jellyfin_status`).",
        "CLOUDFLARE_API_TOKEN": "Enables Cloudflare Tunnels management (`tunnel_status`, `tunnel_add_route`) and DNS records (`cf_dns_*`).",
        "R2_ACCESS_KEY_ID": "Enables Cloudflare R2 bucket object storage (`r2_get`, `r2_put`, `r2_delete`, `r2_buckets`).",
        "VERCEL_TOKEN": "Enables deploying web apps and services to Vercel (`vercel_deploy`, `vercel_projects`).",
        "HACKCLUB_CDN_KEY": "Enables uploading generated files to public CDN (`cdn_upload`).",
        "FIGMA_ACCESS_TOKEN": "Enables Figma design inspection and asset extraction (`figma_*`).",
        "CANVA_API_KEY": "Enables Canva design creation and export (`canva_*`).",
        "OPENWEATHER_API_KEY": "Enables current weather and forecasts for any city (`get_weather`).",
    }

    for cat_lbl, items in by_category.items():
        lines.append(f"### {cat_lbl}")
        for it in items:
            key = it["key"]
            lbl = it["label"]
            is_set = it.get("is_set", False)
            disp = it.get("current_display", "")
            url = it.get("where_to_get_url", "")
            desc = it.get("description", "")
            tool_effect = TOOL_MAPPING.get(key, "")

            status_icon = "✅" if is_set else "⭕"
            status_text = f"Configured (`{disp}`)" if is_set else "*Not configured*"
            lines.append(f"- **{status_icon} `{key}`** — {lbl}: {status_text}")
            if tool_effect:
                lines.append(f"  - **Capabilities unlocked**: {tool_effect}")
            else:
                lines.append(f"  - **Purpose**: {desc}")
            if not is_set and url:
                lines.append(f"  - **Where to get**: [{it.get('where_to_get_label') or 'Portal'}]({url})")
        lines.append("")

    return "\n".join(lines).strip()

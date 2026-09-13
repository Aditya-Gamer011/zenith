# Zenith · Complete Tools & Capabilities Reference

Zenith includes over 60 built-in tools organized across 12 functional domains. The Orchestrator automatically selects, chains, and executes these tools based on the user's intent.

---

## 1. Core System, Knowledge & Productivity

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `time_now` | *(none)* | Returns the current wall-clock date and time in the configured timezone. Always call this instead of guessing timestamps. |
| `zenith_docs` | `topic` (string) | Look up Zenith's internal architecture, deployment guides, agent manuals, or tool specifications. |
| `memory` | `action` ("save" \| "recall" \| "all"), `key`, `value` | Persistently store or retrieve long-term facts, preferences, and system parameters in SQLite. |
| `graph` | `query` (string) | Search the knowledge graph (entities and relational triplets) for connected concepts. |
| `notes` | `action` ("create" \| "list" \| "get" \| "delete"), `title`, `text` | Manage personal notes. |
| `todo` | `action` ("add" \| "list" \| "done" \| "delete"), `title` | Manage task items and checklists. |
| `calendar` | `action` ("add" \| "list" \| "delete"), `text`, `when`, `event_id` | Add, list, or remove events on the user's calendar with natural language parsing (e.g., "tomorrow 4pm"). |
| `reminders` | `text`, `when` | Creates a calendar reminder event and schedules proactive alerting. |
| `email_reminder`| `text`, `when` | Sends an email notification to the user's configured email address for scheduled reminders. |

---

## 2. Web Search, Research & HTTP Utilities

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `web_search` | `query` (string), `num_results` (int) | Query the web for current news, documentation, and real-time information. |
| `read_url` | `url` (string) | Fetch and extract clean, readable text content from any public web page or article. |
| `deep_research` | `topic` (string), `max_depth` (int) | Execute multi-query synthesis across web sources, summarizing technical tradeoffs and citations. |
| `get_weather` | `city` (string) | Retrieve live meteorological reports and forecasts via OpenWeatherMap. |
| `dns_lookup` | `domain` (string), `record_type` (A, AAAA, CNAME, MX, TXT) | Query DNS resolution and verify records. |
| `http_request` | `url` (string), `method` ("GET" \| "POST" \| "PUT" \| "DELETE"), `headers`, `body` | Send HTTP requests to test REST/GraphQL APIs and web services. |
| `web_screenshot_full` | `url` (string) | Capture a full-page rendered screenshot of a website. |
| `web_extract_data` | `url` (string), `target` ("emails" \| "links" \| "headings" \| "images") | Extract structured data elements from web pages. |

---

## 3. Browser Automation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `browser` | `url` (string) | Open a URL using a headless browser and extract rendered DOM text and page title. |
| `browser_screenshot` | `url` (string), `output_path` (string) | Render a webpage with headless Chromium and capture a viewport screenshot. |
| `browser_click` | `selector` (string) | Click an interactive element matching a CSS selector on an active browser session. |
| `browser_type` | `selector` (string), `text` (string), `submit` (bool) | Fill an input field and optionally submit the form. |

---

## 4. Document, Presentation & Chart Generation

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `generate_pdf` | `filename`, `content` (Markdown), `title` | Generate a professional PDF document. By default writes thorough, multi-page documents (1,200–2,000+ words) with headers, tables, and structured sections. |
| `generate_docx` | `filename`, `content` (Markdown), `title` | Generate a Microsoft Word (`.docx`) document with formatted headings, lists, and tables. |
| `generate_xlsx` | `filename`, `data` (CSV/pipe formatted), `sheet_name` | Create a Microsoft Excel spreadsheet with structured columns and headers. |
| `generate_pptx` | `title`, `slides` (array), `theme`, `transition`, `author` | Generate a comprehensive PowerPoint (`.pptx`) deck (typically 6–8 slides) with themes (`executive_dark`, `cyberpunk_neon`, `corporate_light`, `emerald_forest`, `sunset_warm`, `midnight_violet`), layout primitives (`photo_hero`, `stat_hero`, `timeline`, `cards_grid`), and embedded web photos. |
| `generate_chart` | `title`, `chart_type` ("bar" \| "line" \| "pie" \| "doughnut"), `labels`, `values` | Render high-resolution visual charts as PNG images for inclusion in chat or exports. |
| `analyze_file` | `file_path` (string) | Extract text, tables, or source code from user-uploaded documents (PDF, DOCX, CSV, TXT, PY, JS). |
| `modify_file` | `file_path` (string), `new_content` (string) | Update and re-export modified document content. |
| `analyze_image` | `image_path` (string) | Run multimodal vision inspection, OCR, and diagram analysis on user-uploaded images or screenshots. |
| `edit_image` | `image_path` (string), `action` ("resize" \| "crop" \| "rotate" \| "convert" \| "watermark" \| "blur") | Manipulate images and export transformed assets. |
| `fetch_stock_photo`| `query` (string) | Search high-resolution stock photography (Unsplash, Pexels, Pixabay, Wikimedia) and download locally. |
| `cdn_upload` | `file_path` (string) | Upload a local asset to a public CDN and return a shareable public URL. |

---

## 5. Developer Tools & GitHub Suite

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `gh_whoami` | *(none)* | Verify active GitHub CLI authentication status and user identity. |
| `gh_list_repos` | `owner` (string, optional), `limit` (int) | List public and private repositories for a user or organization. |
| `gh_repo_status`| `owner` (string), `repo` (string) | Inspect repo metadata, default branch, stars, and recent commits. |
| `gh_issues` | `owner` (string), `repo` (string), `state` ("open" \| "closed") | List issues for a repository. |
| `gh_pulls` | `owner` (string), `repo` (string), `state` ("open" \| "closed") | List pull requests for a repository. |
| `gh_create_issue`| `owner`, `repo`, `title`, `body` | Create a new GitHub issue. |
| `gh_create_repo` | `name`, `private` (bool), `description` | Initialize a new GitHub repository under the user's account. |
| `gh_create_pr` | `title`, `body`, `base`, `head` | Generate and submit a Pull Request with an automated summary of commits and diffs. |
| `gh_code_review`| `diff` (string, optional) | Perform an automated AI code review on the current git diff, pointing out edge cases, security issues, and performance optimizations. |
| `gh_release_create`| `tag`, `title`, `notes`, `asset_paths` | Publish a GitHub release with optional compiled build assets. |
| `git_status` | `repo_path` (string, optional) | Inspect untracked files, staged changes, and current branch status. |
| `git_diff` | `repo_path` (string, optional), `staged` (bool) | Review working directory or staged code diffs. |
| `git_commit` | `message` (string), `all` (bool) | Commit changes with a clean, descriptive message. |
| `git_push` | `remote` (string), `branch` (string) | Push committed branches to a remote Git repository. |

---

## 6. Host Shell & Container Management

> **Safety Notice**: `shell` commands are gated by the `ALLOW_SHELL` environment variable in `.env`. Destructive commands require explicit human confirmation.

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `shell` | `command` (string), `cwd` (string, optional), `timeout` (int, default 60), `shell_type` ("auto" \| "bash" \| "zsh" \| "powershell" \| "cmd") | Cross-platform shell command execution (Linux, macOS, Windows). Supports stateful `cd` navigation, directory tracking, exit code reporting, and command history logging. |
| `get_command_history` | `limit` (int, default 10) | Inspect recent commands executed in the current session, their exit codes, durations, and output previews. |
| `get_system_info` | `detail_level` ("summary" \| "full") | Introspect what machine/server/container Zenith is running on (OS, kernel, CPU, RAM, disk, network, and environment type: Docker, WSL2, Raspberry Pi, Cloud VM, or Bare Metal). |
| `system_status` | *(none)* | Cross-platform host vitals (Linux/macOS/Windows): CPU load averages, memory usage, uptime, and disk usage. |
| `disk_usage` | *(none)* | View cross-platform disk usage tables across root and workspace volumes. |
| `memory_usage` | *(none)* | Inspect RAM consumption, available memory, and swap memory. |
| `top_processes` | `limit` (int) | List top processes sorted by CPU and memory consumption. |
| `docker_list` | *(none)* | List all running and stopped Docker containers on the host. |
| `docker_table` | *(none)* | Return a compact table of container names, images, status, and ports. |
| `docker_status` | `container_name` (string) | Inspect health, uptime, restart counts, and status of a specific container. |
| `docker_logs` | `container_name` (string), `tail` (int) | Tail recent logs from a container for troubleshooting. |
| `docker_start` | `container_name` (string) | Start a stopped container. |
| `docker_stop` | `container_name` (string) | Stop a running container. |
| `docker_restart` | `container_name` (string) | Restart a container safely. |

---

## 7. Homelab & Media Stack Control

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `homelab_overview` | *(none)* | Comprehensive scan of homelab services, container statuses, and system storage. |
| `media_search` | `query` (string), `media_type` ("movie" \| "tv") | Search for movies and TV series across media catalog engines. |
| `media_add` | `tmdb_id` (int), `media_type` ("movie" \| "tv") | Send a media request to automated download services (Radarr / Sonarr). |
| `media_queue` | *(none)* | Check active download queues, progress percentages, and estimated completion times. |
| `torrent_control` | `action` ("pause" \| "resume" \| "list"), `torrent_hash` | Control active BitTorrent client downloads. |
| `tunnel_status` | *(none)* | Check Cloudflare Tunnel ingress routes, active subdomains, and connectivity. |
| `tunnel_add_route` | `subdomain` (string), `local_port` (int) | Add a new public ingress route to Cloudflare Tunnel and reload configuration. |
| `caddy_status` | *(none)* | Inspect Caddy reverse proxy running status and configured reverse routes. |
| `caddy_reload` | *(none)* | Reload the Caddy configuration file without dropping active connections. |
| `jellyfin_status` | *(none)* | Check media server container availability and active streaming sessions. |
| `jellyfin_now_playing` | *(none)* | List current active video playback sessions, users, and media titles. |
| `n8n_list_workflows` | *(none)* | Inspect automated workflows configured in the local n8n automation engine. |
| `n8n_trigger_webhook` | `webhook_path` (string), `payload` (object) | Dispatch a payload to trigger an automated n8n workflow. |

---

## 8. Smart Home & Home Assistant

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `ha_overview` | *(none)* | Fetch a live overview of connected smart home devices, lights, climate entities, and switches. |
| `ha_entity` | `action` ("call" \| "state"), `domain`, `service`, `entity_id` | Call any Home Assistant domain service or query entity state. |
| `ha_switch` | `action` ("on" \| "off" \| "toggle" \| "status"), `entity_id` | Toggle or query the status of a power switch or smart plug. |
| `ha_ac` | `action` ("on" \| "off" \| "toggle" \| "status") | Control air conditioning units. |
| `ha_soundbar` | `action` ("on" \| "off" \| "toggle" \| "status") | Control audio soundbar power and status. |
| `ha_fan` | `action` ("on" \| "off" \| "speed"), `entity_id`, `percentage` | Control smart fans and set speed percentages. |
| `ha_smart_plug` | `action` ("on" \| "off" \| "telemetry") | Read real-time electrical telemetry (voltage, power in Watts, energy in kWh) from smart plugs. |

---

## 9. Google Maps, Navigation & Embeds

> **Interactive Embed Note**: When responding to places, cafes, or route queries, the frontend automatically renders the Google Maps iframe widget returned by these tools.

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `maps_search` | `query` (string), `location` (optional) | Search for points of interest, restaurants, landmarks, or addresses. |
| `maps_directions` | `origin` (string), `destination` (string), `mode` ("driving" \| "walking" \| "transit" \| "bicycling") | Get step-by-step turn directions, distance, and duration. |
| `maps_commute` | `origin` (string), `destinations` (list) | Calculate commute times and traffic delays across multiple destination targets. |
| `maps_geocode` | `address` (string) | Convert human addresses to latitude/longitude coordinates. |
| `maps_embed` | `mode` ("place" \| "directions" \| "view"), `params` | Generate an interactive Google Maps iframe embed code for chat display. |

---

## 10. Email Gateway & Messaging

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `email_search` | `query` (string), `limit` (int) | Search connected mailboxes for relevant emails by sender, subject, or keywords. |
| `email_read` | `uid` (string) | Retrieve and read full email headers and body text. |
| `email_send` | `to`, `subject`, `body`, `attachment_path`, `attachment_paths` | Send an email via Resend or SMTP. Supports attaching generated files (PDF, DOCX, PPTX) directly. |
| `mailbox_create` | *(none)* | Generate a temporary disposable inbox for one-time verification links or registrations. |

---

## 11. UI Customization & Secrets Management

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `ui_customize_theme` | `accent_color` (hex), `font` (string), `custom_css` (string) | Dynamically update the web interface's visual styling, colors, and typography live without reloading. |
| `ui_reset_theme` | *(none)* | Reset all custom UI styles back to the default monochrome matte theme. |
| `get_setup_status` | `category` (string, optional) | Inspect which credentials and integrations are currently configured vs unconfigured. |
| `get_available_tools` | `category` (string, optional), `query` (string, optional) | Self-introspect all 160+ tools, schemas, parameters, and categories Zenith can invoke. |
| `get_configurable_tools` | *(none)* | List all configurable integrations, credentials, and settings with guide links and configuration state. |
| `setup_secret` | `key` (string), `value` (string) | Save an API key or configuration secret securely to `.env` and immediately reload server settings. |
| `update_user_profile`| `name`, `email`, `timezone`, `bio` | Update user personal details and seed them into the persistent memory store. |

---

## 12. Antigravity Autonomous Coding Worker

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `agent_submit` | `task` (string), `workspace` (string), `requirements` (string) | Delegate a complex software engineering or multi-file coding task to the background Antigravity worker. |
| `agent_status` | `task_id` (string) | Poll the current execution state (`QUEUED`, `RUNNING`, `DONE`, `FAILED`) of an engineering task. |
| `agent_output` | `task_id` (string) | Fetch the live console log output from a running worker agent. |
| `agent_artifacts` | `task_id` (string) | List files, test reports, and deliverables created by the worker agent. |
| `agent_followup` | `task_id` (string), `message` (string) | Send new instructions or feedback into an ongoing worker task. |
| `agent_cancel` | `task_id` (string) | Terminate an active worker task cleanly. |

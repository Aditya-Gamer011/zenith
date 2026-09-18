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
| `read_presentation` | `file_path` (string), `max_slides` (int, default 50) | Read, parse, and analyze PowerPoint presentations (`.pptx`), extracting slide titles, bullet points, structured tables, and speaker notes. |
| `read_spreadsheet` | `file_path` (string), `sheet_name` (string, optional), `max_rows` (int, default 100), `max_cols` (int, default 20) | Read, parse, and format Excel workbooks (`.xlsx`, `.xlsm`) or CSV/TSV spreadsheets as clean Markdown tables with row/column counts. |
| `analyze_file` | `file_path` (string) | Extract text, tables, or source code from user-uploaded documents (PPTX, XLSX, CSV, PDF, DOCX, JSON, TXT, code files). |
| `modify_file` | `file_path` (string), `new_content` (string) | Update and re-export modified document content. |
| `analyze_image` | `image_path` (string) | Run multimodal vision inspection, OCR, and diagram analysis on user-uploaded images or screenshots. |
| `edit_image` | `image_path` (string), `action` ("resize" \| "crop" \| "rotate" \| "convert" \| "watermark" \| "blur") | Manipulate images and export transformed assets. |
| `fetch_stock_photo`| `query` (string) | Search high-resolution stock photography (Unsplash, Pexels, Pixabay, Wikimedia) and download locally. |
| `cdn_upload` | `file_path` (string) | Upload a local asset to a public CDN and return a shareable public URL. |


---

## 4.1. Media Studio & Audio/Video Engineering

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `media_info` | `file_path` (string) | Comprehensive technical metadata inspection via `ffprobe` (codecs, bitrate, sample rate, channels, resolution, FPS, duration). |
| `convert_media` | `input_path` (string), `output_format` ("mp3" \| "wav" \| "aac" \| "flac" \| "mp4" \| "webm" \| "gif"), `quality` ("high" \| "medium" \| "low") | Audio and video transcoding with optimized encoding presets. |
| `trim_media` | `input_path` (string), `start_time` (string), `duration` (string), `end_time` (string) | Precision trimming and cutting of audio and video clips. |
| `extract_frames`| `video_path` (string), `timestamp` (string), `count` (int), `output_format` ("jpg" \| "png") | Snapshot high-resolution video frames and thumbnails at specific timestamps. |
| `merge_audio_video` | `video_path` (string), `audio_path` (string), `replace_audio` (bool) | Combine voiceovers, soundtracks, or background music with video footage. |
| `compress_media` | `input_path` (string), `target_size_mb` (float, default 10.0) | Smart compression targeting file size limits (e.g. Discord 25MB, email attachments). |
| `text_to_speech` | `text` (string), `voice` (string), `speed` (string) | Studio-quality neural speech synthesis (MP3) via Edge TTS with human voices across global accents. |
| `download_web_audio` | `url` (string) | Download and extract clean 192kbps MP3 audio from YouTube, SoundCloud, Twitter/X, and web URLs. |
| `download_web_video` | `url` (string), `max_resolution` ("720" \| "1080") | Download video clips from supported web platforms capped at target resolution. |
| `web_media_info` | `url` (string) | Remote video/audio inspection without downloading (title, channel, views, chapters, duration). |
| `create_collage` | `image_paths` (array), `layout` ("auto" \| "2x2" \| "1x2" \| "1x3" \| "3x2"), `spacing` (int), `bg_color` (string) | Generate aesthetic photo grids and collages. |
| `generate_meme` | `image_path` (string), `top_text` (string), `bottom_text` (string), `style` ("impact") | Generate internet memes with bold outlined text. |
| `extract_palette` | `image_path` (string), `num_colors` (int, default 5) | Extract dominant color palette from images with visual hex swatches and RGB codes. |
| `create_animated_gif` | `image_paths` (array), `duration_ms` (int), `loop` (int) | Create animated GIFs from ordered image sequences with custom frame delays. |
| `create_audiogram` | `audio_path` (string), `background_image` (string), `title` (string), `artist_or_host` (string), `wave_color` (string), `style` ("wave" \| "p2p" \| "cline") | Turn speech voiceovers, podcasts, and music into animated waveform MP4 videos with custom branded cards. |
| `create_slideshow` | `image_paths` (array), `audio_path` (string), `duration_per_slide` (float), `resolution` (string) | Assemble multiple images into high-definition MP4 video reels with optional background audio narration. |
| `normalize_audio` | `input_path` (string), `target_lufs` (float, default -14.0) | Standardize audio loudness to streaming and broadcast standards (-14 LUFS) using FFmpeg EBU R128 loudnorm. |
| `overlay_media` | `base_media_path` (string), `overlay_path` (string), `position` ("bottom_right" \| "bottom_left" \| "top_right" \| "top_left" \| "center"), `scale` (float) | Watermark videos or images with logos, badges, or picture-in-picture media overlays. |
| `apply_image_filter` | `image_path` (string), `filter_name` ("cinematic" \| "vintage" \| "noir" \| "cyberpunk" \| "vibrant" \| "dramatic"), `intensity` (float) | Apply photographic aesthetic filters and cinematic color grading to images. |
| `burn_subtitles` | `video_path` (string), `subtitles_srt_or_path` (string), `font_size` (int), `primary_color` (string) | Burn hardcoded, styled subtitles into videos from an SRT file or raw text string. |

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

## 5.1. Autonomous SWE Coding Engine (Codex/Devin Tier)

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `repo_map` | `repo_path` (string), `max_depth` (int, default 4), `max_tokens` (int, default 3500) | Generates a compact AST-aware repository skeleton highlighting classes, functions, methods, signatures, and docstrings without reading raw source files. |
| `find_symbol` | `symbol_name` (string), `repo_path` (string), `exact` (bool, default False) | Instant symbol definition locator across Python, JS/TS, Go, and Rust files. Returns file path, line number, signature, and docstring. |
| `find_references` | `symbol_name` (string), `repo_path` (string), `max_results` (int, default 50) | Cross-repository symbol call site auditor. Locates function/class callers, instantiations, and imports with line numbers and code snippets. |
| `apply_patch` | `path` (string), `target_chunk` (string), `replacement_chunk` (string), `patch_diff` (string) | Surgical search-and-replace / unified diff applicator. Automatically runs AST/syntax validation (`compile`/`ast.parse`) before writing, creates atomic rollback checkpoints, and checks change minimization. |
| `apply_patch_transaction` | `patches` (array of patch dicts), `repo_path` (string) | Atomic multi-file patch transaction. Pre-validates syntax across all modified files before writing; automatically rolls back all changes if any chunk fails. |
| `rollback_patch` | `checkpoint_id` (string, optional), `file_path` (string, optional) | Restores files from atomic pre-patch checkpoints in `.zenith_checkpoints` if a change caused regressions. |
| `lint_code` | `file_path` (string), `repo_path` (string) | Lightweight AST static analysis detecting syntax errors, duplicate function definitions, mutable defaults, and bare except handlers. |
| `run_tests` | `test_target` (string), `test_framework` ("auto" \| "pytest" \| "npm" \| "cargo" \| "go"), `timeout` (int) | Specialized SWE test runner with failure isolation and log compaction. Extracts failing test names, exact tracebacks, and root-cause categories (`SYNTAX_ERROR`, `IMPORT_ERROR`, `ASSERTION_FAILURE`, `TYPE_ERROR`). |
| `inspect_diff` | `repo_path` (string), `staged_only` (bool), `file_path` (string) | Change minimization audit and safety gate. Reports `+` and `-` line churn, warns against large deletions or comment stripping, and encloses diffs in anti-injection tags. |
| `swe_status` | *(none)* | Reports active SWE task state machine phase (INVESTIGATION -> PLANNING -> PATCHING -> TESTING -> VERIFIED) and edit thrashing detector metrics. |

---

## 5.2. Repository Intelligence & Hierarchical Code Comprehension

| Tool | Parameters | Description |
| :--- | :--- | :--- |
| `analyze_dependency_graph` | `target` (string, optional), `repo_path` (string, optional) | Traces architectural tiers: `API Endpoint -> Service -> Repository -> Database Table`. Computes blast radius and risk level (`HIGH`, `MEDIUM`, `LOW`) when modifying a component. |
| `call_graph` | `function_name` (string), `repo_path` (string, optional), `direction` ("incoming" \| "outgoing", default "incoming"), `max_depth` (int, default 4) | Static call graph and execution path reachability engine. Traces which callers and execution chains reach a function (reverse call graph). |
| `map_tests` | `target` (string), `repo_path` (string, optional) | Automatically maps modified functions, classes, or files to covering test files and test cases. Generates targeted verification commands (e.g. `pytest tests/test_auth.py -k test_get_user`). |
| `semantic_code_search` | `query` (string), `repo_path` (string, optional), `max_results` (int, default 8) | Natural-language conceptual search across docstrings, comments, endpoints, and symbol names with concept synonym expansion (e.g., "Where is authentication handled?"). |
| `analyze_architecture` | `repo_path` (string, optional) | Automatically constructs and maintains high-level system architecture: entry points, core services, database models, APIs, and dependencies. |
| `get_hierarchical_context`| `task_query` (string), `subsystem` (string, optional), `depth` ("auto" \| "0" \| "1" \| "2" \| "3"), `repo_path` (string, optional) | Progressive disclosure context retriever: Tier 0 (Project Memory) -> Tier 1 (Subsystem Scope) -> Tier 2 (Symbol & Interface Skeleton) -> Tier 3 (Deep Verification & Call Paths). Prevents prompt saturation. |

---


## 6. Host Shell & Container Management

> **Sovereign Sandbox & Safety Policy**: Zenith operates under the Sovereign Sandbox policy. While Zenith executes developer workflows autonomously anywhere across the workspace with zero user friction (no annoying review modals), sensitive user credentials (`~/.ssh`, `~/.aws`, `~/.gnupg`, browser cookies, `/etc/shadow`) and catastrophic commands (`rm -rf /`, fork bombs, disk formats) are strictly prohibited and isolated by policy. API tokens and credentials are automatically redacted in outputs.

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

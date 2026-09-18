"""Cross-platform Host Path Resolver & Operating System Environment Awareness.

Provides zero-hardcoding resolution of user directories across Linux, macOS, and Windows:
- Home (~)
- Desktop
- Downloads
- Documents
- Pictures
- Videos / Movies
- Music
- Active Workspace
- System Root & Temp

Handles dual runtimes:
1. Native Host Mode (bare metal Python on Linux, macOS, Windows).
2. Containerized Mode (Docker / Podman):
   - Dynamically discovers real host paths via the host worker daemon (port 8022).
   - Falls back to host environment variables (HOST_USER, HOST_HOME, USER, HOME, USERPROFILE).
   - Translates descriptive paths ("on my desktop", "~/Desktop", "downloads") to real host paths.
"""
from __future__ import annotations

import getpass
import json
import logging
import os
import platform
import re
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("zenith.host_paths")

_CACHED_HOST_PATHS: dict[str, Any] | None = None
_LAST_CACHE_TIME: float = 0.0
_CACHE_TTL: float = 30.0  # refresh every 30s


def clear_host_paths_cache() -> None:
    """Clear cached host paths (useful for testing or dynamic environment reloads)."""
    global _CACHED_HOST_PATHS, _LAST_CACHE_TIME
    _CACHED_HOST_PATHS = None
    _LAST_CACHE_TIME = 0.0


def is_container() -> bool:
    """Detect if current process is running inside a Docker/Podman container."""
    if os.getenv("IS_CONTAINER") in ("1", "true", "yes"):
        return True
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            content = cgroup.read_text(errors="replace")
            if "docker" in content or "containerd" in content or "lxc" in content:
                return True
    except Exception:
        pass
    return False


def _get_worker_url() -> str:
    """Resolve worker URL (prefers host.docker.internal when containerized)."""
    env_url = os.getenv("WORKER_URL", "").rstrip("/")
    if env_url:
        return env_url
    if is_container():
        # Inside Docker on Linux/Mac/Windows
        gw = os.getenv("HOST_GATEWAY", "")
        if gw:
            return f"http://{gw}:8022"
        return "http://host.docker.internal:8022"
    return "http://127.0.0.1:8022"


def _read_linux_xdg_user_dirs(home_dir: Path) -> dict[str, str]:
    """Parse ~/.config/user-dirs.dirs on Linux if present."""
    xdg_file = home_dir / ".config" / "user-dirs.dirs"
    dirs: dict[str, str] = {}
    if not xdg_file.is_file():
        return dirs
    try:
        for line in xdg_file.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"')
                # Replace $HOME or ${HOME}
                v = v.replace("$HOME", str(home_dir)).replace("${HOME}", str(home_dir))
                dirs[k] = v
    except Exception as exc:
        log.debug("Failed reading user-dirs.dirs: %s", exc)
    return dirs


def resolve_native_host_paths() -> dict[str, Any]:
    """Inspect the local operating system and return resolved standard paths."""
    sys_name = platform.system().lower()
    if "darwin" in sys_name:
        os_family = "darwin"
    elif "windows" in sys_name or os.name == "nt":
        os_family = "windows"
    else:
        os_family = "linux"

    # Username
    try:
        username = getpass.getuser()
    except Exception:
        username = os.getenv("USER") or os.getenv("USERNAME") or "user"

    # Home directory
    home_str = os.getenv("HOME") or os.getenv("USERPROFILE") or str(Path.home())
    home = Path(home_str).expanduser().resolve()

    # Standard directories
    if os_family == "linux":
        xdg = _read_linux_xdg_user_dirs(home)
        desktop = Path(xdg.get("XDG_DESKTOP_DIR", str(home / "Desktop"))).resolve()
        downloads = Path(xdg.get("XDG_DOWNLOAD_DIR", str(home / "Downloads"))).resolve()
        documents = Path(xdg.get("XDG_DOCUMENTS_DIR", str(home / "Documents"))).resolve()
        pictures = Path(xdg.get("XDG_PICTURES_DIR", str(home / "Pictures"))).resolve()
        videos = Path(xdg.get("XDG_VIDEOS_DIR", str(home / "Videos"))).resolve()
        music = Path(xdg.get("XDG_MUSIC_DIR", str(home / "Music"))).resolve()
        root = "/"
    elif os_family == "darwin":
        desktop = (home / "Desktop").resolve()
        downloads = (home / "Downloads").resolve()
        documents = (home / "Documents").resolve()
        pictures = (home / "Pictures").resolve()
        videos = (home / "Movies").resolve() if (home / "Movies").exists() else (home / "Videos").resolve()
        music = (home / "Music").resolve()
        root = "/"
    else:  # windows
        desktop = (home / "Desktop").resolve()
        downloads = (home / "Downloads").resolve()
        documents = (home / "Documents").resolve()
        pictures = (home / "Pictures").resolve()
        videos = (home / "Videos").resolve()
        music = (home / "Music").resolve()
        root = os.getenv("SystemDrive", "C:") + "\\"

    # Workspace directory
    try:
        from ..core.config import settings
        workspace = str(settings.workspace_dir.resolve())
    except Exception:
        workspace = str(Path.cwd().resolve())

    return {
        "os_family": os_family,
        "username": username,
        "home": str(home),
        "desktop": str(desktop),
        "downloads": str(downloads),
        "documents": str(documents),
        "pictures": str(pictures),
        "videos": str(videos),
        "music": str(music),
        "workspace": workspace,
        "temp": tempfile.gettempdir(),
        "root": root,
        "is_container": False,
    }


def query_worker_host_paths(timeout: float = 1.5) -> dict[str, Any] | None:
    """Fetch authoritative host paths from the background Antigravity worker on the host."""
    url = f"{_get_worker_url()}/host/paths"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Zenith-Core"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "ok":
                    return data
    except Exception as exc:
        log.debug("Worker host paths query error (%s): %s", url, exc)
    return None


def get_host_paths(force_refresh: bool = False) -> dict[str, Any]:
    """Get the full dictionary of host system paths, handling container and native modes."""
    global _CACHED_HOST_PATHS, _LAST_CACHE_TIME
    import time

    now = time.time()
    if not force_refresh and _CACHED_HOST_PATHS and (now - _LAST_CACHE_TIME) < _CACHE_TTL:
        return _CACHED_HOST_PATHS

    container = is_container()
    if container:
        # Try worker query first
        worker_paths = query_worker_host_paths()
        if worker_paths:
            worker_paths["is_container"] = True
            _CACHED_HOST_PATHS = worker_paths
            _LAST_CACHE_TIME = now
            return worker_paths

        # Fallback to container environment variables passed by docker-compose
        host_user = os.getenv("HOST_USER") or os.getenv("USER") or ""
        host_home = os.getenv("HOST_HOME") or os.getenv("HOME") or ""
        host_os = os.getenv("HOST_OS") or "linux"

        # If HOST_HOME was provided and is not /home/zenith (the container user)
        if host_home and host_home != "/home/zenith":
            hp = Path(host_home)
            is_win = "\\" in host_home or (len(host_home) >= 2 and host_home[1] == ":")
            os_family = "windows" if is_win else ("darwin" if host_home.startswith("/Users") else "linux")
            if not host_user:
                host_user = hp.name

            desktop = str(hp / "Desktop")
            downloads = str(hp / "Downloads")
            documents = str(hp / "Documents")
            pictures = str(hp / "Pictures")
            videos = str(hp / ("Movies" if os_family == "darwin" else "Videos"))
            music = str(hp / "Music")
            root = "C:\\" if os_family == "windows" else "/"

            res = {
                "os_family": os_family,
                "username": host_user,
                "home": str(hp),
                "desktop": desktop,
                "downloads": downloads,
                "documents": documents,
                "pictures": pictures,
                "videos": videos,
                "music": music,
                "workspace": os.getenv("ZENITH_WORKSPACE") or "/app",
                "temp": "/tmp",
                "root": root,
                "is_container": True,
            }
            _CACHED_HOST_PATHS = res
            _LAST_CACHE_TIME = now
            return res

    # Native mode fallback
    res = resolve_native_host_paths()
    res["is_container"] = container
    _CACHED_HOST_PATHS = res
    _LAST_CACHE_TIME = now
    return res


def resolve_host_path(path_str: str) -> str:
    """Map user-supplied, relative, or symbolic path representations to absolute host paths.

    Examples:
    - "~/Desktop/foo" -> "/home/username/Desktop/foo" (or Windows/macOS equivalent)
    - "desktop" / "Desktop" -> "/home/username/Desktop"
    - "downloads" / "Downloads" -> "/home/username/Downloads"
    - "documents" / "Documents" -> "/home/username/Documents"
    - "pictures" / "Pictures" -> "/home/username/Pictures"
    - "videos" / "Videos" -> "/home/username/Videos"
    - "music" / "Music" -> "/home/username/Music"
    - "~" -> "/home/username"
    """
    if not path_str or not path_str.strip():
        return ""

    raw = path_str.strip().strip("'").strip('"')
    hp = get_host_paths()
    home = hp.get("home", "")
    desktop = hp.get("desktop", "")
    downloads = hp.get("downloads", "")
    documents = hp.get("documents", "")
    pictures = hp.get("pictures", "")
    videos = hp.get("videos", "")
    music = hp.get("music", "")

    low = raw.lower()

    # Exact directory keywords
    if low in ("desktop", "desktop/"):
        return desktop
    if low in ("downloads", "downloads/"):
        return downloads
    if low in ("documents", "docs", "documents/"):
        return documents
    if low in ("pictures", "photos", "pictures/"):
        return pictures
    if low in ("videos", "movies", "videos/"):
        return videos
    if low in ("music", "music/"):
        return music
    if low in ("~", "home", "$home", "%userprofile%"):
        return home

    # Relative to standard directories
    if low.startswith("desktop/") or low.startswith("desktop\\"):
        sub = raw[8:]
        sep = "\\" if hp.get("os_family") == "windows" else "/"
        return f"{desktop}{sep}{sub}"
    if low.startswith("downloads/") or low.startswith("downloads\\"):
        sub = raw[10:]
        sep = "\\" if hp.get("os_family") == "windows" else "/"
        return f"{downloads}{sep}{sub}"
    if low.startswith("documents/") or low.startswith("documents\\"):
        sub = raw[10:]
        sep = "\\" if hp.get("os_family") == "windows" else "/"
        return f"{documents}{sep}{sub}"
    if low.startswith("pictures/") or low.startswith("pictures\\"):
        sub = raw[9:]
        sep = "\\" if hp.get("os_family") == "windows" else "/"
        return f"{pictures}{sep}{sub}"
    if low.startswith("videos/") or low.startswith("videos\\") or low.startswith("movies/"):
        sub = raw.split("/", 1)[-1] if "/" in raw else raw.split("\\", 1)[-1]
        sep = "\\" if hp.get("os_family") == "windows" else "/"
        return f"{videos}{sep}{sub}"
    if low.startswith("music/") or low.startswith("music\\"):
        sub = raw[6:]
        sep = "\\" if hp.get("os_family") == "windows" else "/"
        return f"{music}{sep}{sub}"

    # ~ expansion
    if raw.startswith("~/") or raw.startswith("~\\"):
        sub = raw[2:]
        sep = "\\" if hp.get("os_family") == "windows" else "/"
        return f"{home}{sep}{sub}"

    # $HOME expansion
    if raw.startswith("$HOME/") or raw.startswith("${HOME}/"):
        sub = raw.split("/", 1)[1]
        sep = "\\" if hp.get("os_family") == "windows" else "/"
        return f"{home}{sep}{sub}"

    return raw


def format_host_paths_summary() -> str:
    """Format a clear, high-signal summary of all resolved host paths for system prompts."""
    hp = get_host_paths()
    os_fam = hp.get("os_family", "linux").title()
    user = hp.get("username", "user")
    is_cont = hp.get("is_container", False)
    mode_str = "Containerized (Docker Gateway Bridge)" if is_cont else "Native Host"

    lines = [
        f"### Host Machine & User File System Paths ({os_fam} — {mode_str})",
        f"- Host Username: `{user}`",
        f"- User Home (`~`): `{hp['home']}`",
        f"- Desktop: `{hp['desktop']}`",
        f"- Downloads: `{hp['downloads']}`",
        f"- Documents: `{hp['documents']}`",
        f"- Pictures: `{hp['pictures']}`",
        f"- Videos / Movies: `{hp['videos']}`",
        f"- Music: `{hp['music']}`",
        f"- Active Workspace: `{hp['workspace']}`",
        "",
        "CRITICAL FILE SYSTEM & HOST PATH DIRECTIVE:",
        f"1. When the user asks to create, modify, view, or delete files or folders on their Desktop, in Downloads, Documents, etc., ALWAYS target the exact host path (`{hp['desktop']}`, `{hp['downloads']}`, etc.).",
        "2. NEVER create user folders in container-internal paths like `/home/zenith`. All host file and folder operations MUST use the resolved host paths above.",
        f"3. Direct shell commands (`shell`) and file operations execute against the host machine.",
    ]
    return "\n".join(lines)


def is_host_path(path: Path | str) -> bool:
    """Check if a path targets the host file system rather than container-internal storage."""
    if not is_container():
        return True
    path_str = str(path).strip()
    if not path_str:
        return False
    # Container internal locations
    if path_str.startswith("/app") or path_str.startswith("/tmp") or path_str.startswith("/home/zenith"):
        return False

    hp = get_host_paths()
    home = hp.get("home", "")
    if home and (path_str == home or path_str.startswith(home + "/") or path_str.startswith(home + "\\")):
        return True
    for key in ("desktop", "downloads", "documents", "pictures", "videos", "music"):
        d = hp.get(key, "")
        if d and (path_str == d or path_str.startswith(d + "/") or path_str.startswith(d + "\\")):
            return True
    # If path starts with /home or Windows drive letter, it targets host
    if path_str.startswith("/home/") or (len(path_str) >= 2 and path_str[1] == ":") or path_str.startswith("/Users/"):
        return True
    return False


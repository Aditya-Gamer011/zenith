"""Host, server, and operating system introspection engine.

Provides cross-platform introspection across Linux, macOS (Darwin), and Windows:
- OS distribution, kernel, architecture, and platform string.
- Execution environment: Bare metal, Docker container, Podman, Kubernetes, WSL, Cloud VMs (AWS, GCP, Azure), Raspberry Pi.
- Host vitals: CPU cores & model, RAM total/used/free, Disk total/used/free, Uptime.
- Process runtime: Python version, virtualenv, user, home, workspace, PID.
- Cross-platform fallbacks for system_status, disk_usage, memory_usage, cpu_usage, top_processes.
"""
from __future__ import annotations

import getpass
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_PROCESS_START_TIME = time.time()


def get_os_family() -> str:
    """Returns 'linux', 'darwin', or 'windows'."""
    sys_name = platform.system().lower()
    if "darwin" in sys_name:
        return "darwin"
    if "windows" in sys_name:
        return "windows"
    return "linux"


def get_pretty_os_name() -> str:
    """Return friendly OS name and version."""
    family = get_os_family()
    if family == "windows":
        rel = platform.release()
        ver = platform.version()
        return f"Windows {rel} (Build {ver})"
    if family == "darwin":
        mac_ver, _, _ = platform.mac_ver()
        arch = platform.machine()
        chip = "Apple Silicon" if "arm" in arch.lower() else "Intel"
        return f"macOS {mac_ver or platform.release()} ({chip} {arch})"

    # Linux - try /etc/os-release
    try:
        os_release = Path("/etc/os-release")
        if os_release.exists():
            data = {}
            for line in os_release.read_text(errors="replace").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip().strip('"')
            if "PRETTY_NAME" in data:
                return f"{data['PRETTY_NAME']} ({platform.machine()})"
            if "NAME" in data:
                ver = data.get("VERSION", "")
                return f"{data['NAME']} {ver} ({platform.machine()})".strip()
    except Exception:
        pass

    return f"Linux {platform.release()} ({platform.machine()})"


def detect_environment_type() -> tuple[str, str, dict[str, bool]]:
    """Detect whether running in Docker, Podman, Kubernetes, WSL, Cloud VM, or Bare Metal.

    Returns:
        (env_id, friendly_description, flags)
    """
    flags = {
        "is_container": False,
        "is_wsl": False,
        "is_cloud": False,
        "is_k8s": False,
        "is_raspberry_pi": False,
    }

    # Kubernetes
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        flags["is_container"] = True
        flags["is_k8s"] = True
        return "kubernetes", "Kubernetes Pod Container", flags

    # Docker / Podman
    if Path("/.dockerenv").exists():
        flags["is_container"] = True
        return "docker", "Docker Container (Linux)", flags

    if Path("/run/.containerenv").exists():
        flags["is_container"] = True
        return "podman", "Podman Container (Linux)", flags

    try:
        cgroup = Path("/proc/1/cgroup")
        if cgroup.exists():
            content = cgroup.read_text(errors="replace")
            if "docker" in content or "containerd" in content:
                flags["is_container"] = True
                return "docker", "Docker Container (cgroups)", flags
            if "lxc" in content:
                flags["is_container"] = True
                return "lxc", "LXC Container", flags
    except Exception:
        pass

    # WSL (Windows Subsystem for Linux)
    if os.getenv("WSL_DISTRO_NAME") or os.getenv("WSL_INTEROP"):
        flags["is_wsl"] = True
        distro = os.getenv("WSL_DISTRO_NAME", "Linux")
        return "wsl", f"WSL2 Subsystem ({distro}) on Windows", flags

    try:
        proc_ver = Path("/proc/version")
        if proc_ver.exists():
            pv = proc_ver.read_text(errors="replace").lower()
            if "microsoft" in pv or "wsl" in pv:
                flags["is_wsl"] = True
                return "wsl", "WSL2 Subsystem on Windows", flags
    except Exception:
        pass

    # Raspberry Pi
    try:
        dt_model = Path("/proc/device-tree/model")
        if dt_model.exists():
            model = dt_model.read_text(errors="replace").strip("\x00\n ")
            if "Raspberry Pi" in model:
                flags["is_raspberry_pi"] = True
                return "raspberry_pi", f"Raspberry Pi Hardware ({model})", flags
    except Exception:
        pass

    # Cloud VM detection (AWS, GCP, Azure)
    try:
        dmi_sys = Path("/sys/class/dmi/id/sys_vendor")
        dmi_prod = Path("/sys/class/dmi/id/product_name")
        vendor = dmi_sys.read_text(errors="replace").lower() if dmi_sys.exists() else ""
        product = dmi_prod.read_text(errors="replace").lower() if dmi_prod.exists() else ""

        if "google" in vendor or "google" in product:
            flags["is_cloud"] = True
            return "gcp_vm", "Google Cloud Compute Engine VM", flags
        if "amazon" in vendor or "ec2" in product or Path("/sys/hypervisor/uuid").exists():
            flags["is_cloud"] = True
            return "aws_ec2", "AWS EC2 Cloud Instance", flags
        if "microsoft" in vendor and not flags["is_wsl"]:
            flags["is_cloud"] = True
            return "azure_vm", "Microsoft Azure Cloud VM", flags
        if "digitalocean" in vendor or "digitalocean" in product:
            flags["is_cloud"] = True
            return "digitalocean", "DigitalOcean Droplet VM", flags
        if "qemu" in vendor or "kvm" in vendor or "vmware" in vendor or "virtualbox" in vendor:
            return "virtual_machine", f"Virtual Machine ({vendor.strip().title() or product.strip()})", flags
    except Exception:
        pass

    family = get_os_family()
    if family == "windows":
        return "windows_host", "Native Windows Machine (Bare Metal / Host)", flags
    if family == "darwin":
        return "macos_host", "Native Apple Mac (Bare Metal / Host)", flags
    return "linux_host", "Native Linux Machine (Bare Metal / Host)", flags


def get_cpu_info() -> dict[str, Any]:
    """Get CPU cores, architecture, and model across Linux, macOS, and Windows."""
    cores = os.cpu_count() or 1
    model = platform.processor() or platform.machine()
    load_avg = None

    family = get_os_family()
    if family in ("linux", "darwin") and hasattr(os, "getloadavg"):
        try:
            load_avg = [round(x, 2) for x in os.getloadavg()]
        except Exception:
            pass

    if family == "linux":
        try:
            cpuinfo = Path("/proc/cpuinfo")
            if cpuinfo.exists():
                for line in cpuinfo.read_text(errors="replace").splitlines():
                    if "model name" in line:
                        model = line.split(":", 1)[1].strip()
                        break
        except Exception:
            pass
    elif family == "darwin":
        try:
            res = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                model = res.stdout.strip()
        except Exception:
            pass
    elif family == "windows":
        model = os.getenv("PROCESSOR_IDENTIFIER", model)

    return {
        "cores": cores,
        "model": model,
        "arch": platform.machine(),
        "load_avg": load_avg,
    }


def get_memory_info() -> dict[str, Any]:
    """Get system RAM total, available, and used percentage across OS."""
    family = get_os_family()
    total_b = 0
    avail_b = 0

    if family == "linux":
        try:
            meminfo = Path("/proc/meminfo").read_text(errors="replace")
            m_total = re.search(r"^MemTotal:\s+(\d+)", meminfo, re.M)
            m_avail = re.search(r"^MemAvailable:\s+(\d+)", meminfo, re.M)
            if m_total:
                total_b = int(m_total.group(1)) * 1024
            if m_avail:
                avail_b = int(m_avail.group(1)) * 1024
        except Exception:
            pass

    elif family == "darwin":
        try:
            res = subprocess.run(["sysctl", "-n", "hw.memsize"],
                                 capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip():
                total_b = int(res.stdout.strip())

            # vm_stat for free memory
            vm = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=3)
            if vm.returncode == 0:
                pagesize = 4096
                free_pages = 0
                inactive_pages = 0
                for line in vm.stdout.splitlines():
                    if "Pages free:" in line:
                        free_pages = int(line.split(":")[1].strip().rstrip("."))
                    elif "Pages inactive:" in line:
                        inactive_pages = int(line.split(":")[1].strip().rstrip("."))
                avail_b = (free_pages + inactive_pages) * pagesize
        except Exception:
            pass

    elif family == "windows":
        try:
            import ctypes

            class MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MemoryStatusEx()
            stat.dwLength = ctypes.sizeof(MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_b = stat.ullTotalPhys
                avail_b = stat.ullAvailPhys
        except Exception:
            pass

    if total_b == 0:
        # Fallback if OS-specific probe fails
        total_b = 8 * 1024 * 1024 * 1024  # default assumption
        avail_b = 4 * 1024 * 1024 * 1024

    used_b = max(0, total_b - avail_b)
    used_pct = round((used_b / total_b) * 100, 1) if total_b > 0 else 0

    return {
        "total_bytes": total_b,
        "available_bytes": avail_b,
        "used_bytes": used_b,
        "used_percent": used_pct,
        "total_gb": round(total_b / (1024 ** 3), 1),
        "available_gb": round(avail_b / (1024 ** 3), 1),
        "summary": f"{total_b / (1024**3):.1f} GB total, {avail_b / (1024**3):.1f} GB free ({used_pct:.0f}% used)",
    }


def get_disk_info(path: str | Path | None = None) -> dict[str, Any]:
    """Get disk space for root or specific path using standard shutil."""
    if not path:
        path = "/" if get_os_family() != "windows" else "C:\\"
    try:
        p = Path(path).resolve()
        usage = shutil.disk_usage(p)
        total_gb = round(usage.total / (1024 ** 3), 1)
        used_gb = round(usage.used / (1024 ** 3), 1)
        free_gb = round(usage.free / (1024 ** 3), 1)
        used_pct = round((usage.used / usage.total) * 100, 1) if usage.total > 0 else 0
        return {
            "path": str(p),
            "total_gb": total_gb,
            "used_gb": used_gb,
            "free_gb": free_gb,
            "used_percent": used_pct,
            "summary": f"{total_gb:.1f} GB total, {free_gb:.1f} GB free ({used_pct:.0f}% used) on {p}",
        }
    except Exception as exc:
        return {"path": str(path), "error": str(exc), "summary": f"Disk info unavailable: {exc}"}


def get_uptime_info() -> dict[str, Any]:
    """Get system and Zenith process uptime."""
    proc_uptime_sec = round(time.time() - _PROCESS_START_TIME, 1)
    sys_uptime_sec = proc_uptime_sec

    family = get_os_family()
    if family == "linux":
        try:
            up_str = Path("/proc/uptime").read_text().split()[0]
            sys_uptime_sec = round(float(up_str), 1)
        except Exception:
            pass
    elif family == "darwin":
        try:
            res = subprocess.run(["sysctl", "-n", "kern.boottime"],
                                 capture_output=True, text=True, timeout=3)
            # { sec = 1714123456, usec = ... }
            m = re.search(r"sec\s*=\s*(\d+)", res.stdout)
            if m:
                boot_sec = int(m.group(1))
                sys_uptime_sec = round(time.time() - boot_sec, 1)
        except Exception:
            pass
    elif family == "windows":
        try:
            import ctypes
            ms = ctypes.windll.kernel32.GetTickCount64()
            sys_uptime_sec = round(ms / 1000.0, 1)
        except Exception:
            pass

    def _fmt(sec: float) -> str:
        s = int(sec)
        days, rem = divmod(s, 86400)
        hours, rem = divmod(rem, 3600)
        mins, secs = divmod(rem, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        parts.append(f"{mins}m")
        if not days and not hours:
            parts.append(f"{secs}s")
        return " ".join(parts)

    return {
        "system_uptime_seconds": sys_uptime_sec,
        "system_uptime_human": _fmt(sys_uptime_sec),
        "zenith_uptime_seconds": proc_uptime_sec,
        "zenith_uptime_human": _fmt(proc_uptime_sec),
    }


def get_network_info() -> dict[str, Any]:
    """Get hostname and local IP addresses."""
    hostname = socket.gethostname()
    ips = []
    try:
        _, _, host_ips = socket.gethostbyname_ex(hostname)
        ips = [ip for ip in host_ips if not ip.startswith("127.")]
    except Exception:
        pass
    return {
        "hostname": hostname,
        "local_ips": ips or ["127.0.0.1"],
    }


def get_full_host_introspection() -> dict[str, Any]:
    """Comprehensive introspection of the host, container/server environment, hardware, and runtime."""
    from ..core.config import settings

    env_id, env_desc, env_flags = detect_environment_type()
    cpu = get_cpu_info()
    mem = get_memory_info()
    disk = get_disk_info(settings.workspace_dir if settings.workspace_dir.exists() else "/")
    uptime = get_uptime_info()
    net = get_network_info()
    os_name = get_pretty_os_name()
    family = get_os_family()

    # User & Shell
    try:
        user = getpass.getuser()
    except Exception:
        user = os.getenv("USER") or os.getenv("USERNAME") or "unknown"

    default_shell = "bash"
    if family == "windows":
        default_shell = "powershell" if shutil.which("powershell") or shutil.which("pwsh") else "cmd"
    elif family == "darwin":
        default_shell = "zsh"
    elif family == "linux":
        default_shell = "bash" if shutil.which("bash") else "sh"

    is_venv = hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)

    return {
        "os": {
            "family": family,
            "name": os_name,
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.machine(),
            "platform_string": platform.platform(),
        },
        "environment": {
            "id": env_id,
            "description": env_desc,
            "is_container": env_flags["is_container"],
            "is_wsl": env_flags["is_wsl"],
            "is_cloud": env_flags["is_cloud"],
            "is_k8s": env_flags["is_k8s"],
            "is_raspberry_pi": env_flags["is_raspberry_pi"],
        },
        "hardware": {
            "hostname": net["hostname"],
            "local_ips": net["local_ips"],
            "cpu_model": cpu["model"],
            "cpu_cores": cpu["cores"],
            "load_average": cpu["load_avg"],
            "memory": mem,
            "disk": disk,
            "uptime": uptime,
        },
        "runtime": {
            "user": user,
            "home_dir": str(Path.home()),
            "default_shell": default_shell,
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "is_virtualenv": is_venv,
            "virtualenv_path": sys.prefix if is_venv else None,
            "zenith_pid": os.getpid(),
            "workspace_dir": str(settings.workspace_dir),
            "zenith_mode": getattr(settings, "zenith_mode", "sovereign"),
            "allow_shell": settings.allow_shell,
        },
    }


def format_host_summary() -> str:
    """Concise 4-5 line summary for injection into Orchestrator system prompt."""
    data = get_full_host_introspection()
    os_info = data["os"]
    env_info = data["environment"]
    hw = data["hardware"]
    mem = hw["memory"]
    disk = hw["disk"]
    rt = data["runtime"]
    up = hw["uptime"]

    load_str = f" · Load: {', '.join(str(x) for x in hw['load_average'])}" if hw.get("load_average") else ""
    return (
        f"- OS: {os_info['name']} [{os_info['family']}]\n"
        f"- Environment: {env_info['description']}\n"
        f"- Hostname: {hw['hostname']} (IPs: {', '.join(hw['local_ips'])})\n"
        f"- Hardware: {hw['cpu_cores']} CPU cores ({hw['cpu_model']}) · RAM: {mem['summary']} · Disk: {disk['summary']}{load_str}\n"
        f"- Runtime: User '{rt['user']}' · Shell: {rt['default_shell']} · Python {rt['python_version']} (PID {rt['zenith_pid']}) · Uptime: {up['system_uptime_human']}"
    )


def format_host_details_markdown() -> str:
    """Rich markdown report of host inspection."""
    data = get_full_host_introspection()
    os_info = data["os"]
    env = data["environment"]
    hw = data["hardware"]
    mem = hw["memory"]
    disk = hw["disk"]
    up = hw["uptime"]
    rt = data["runtime"]

    load_txt = ", ".join(str(x) for x in hw["load_average"]) if hw.get("load_average") else "N/A"

    return f"""# 🖥️ Host & Server Environment Report

### 🌐 System & Architecture
- **Operating System**: {os_info['name']}
- **OS Family**: `{os_info['family']}`
- **Kernel Release**: {os_info['release']}
- **Architecture**: `{os_info['architecture']}`
- **Environment Type**: **{env['description']}** (Container: `{env['is_container']}`, WSL: `{env['is_wsl']}`, Cloud: `{env['is_cloud']}`)

### ⚙️ Hardware & Resources
- **Hostname**: `{hw['hostname']}`
- **Local Network IPs**: `{", ".join(hw['local_ips'])}`
- **CPU Processor**: {hw['cpu_model']} ({hw['cpu_cores']} logical cores)
- **System Load Average (1m, 5m, 15m)**: {load_txt}
- **RAM Memory**: {mem['summary']} ({mem['used_percent']}% used)
- **Primary Disk**: {disk['summary']}
- **System Uptime**: {up['system_uptime_human']}
- **Zenith Process Uptime**: {up['zenith_uptime_human']}

### 🐍 Process & Workspace Runtime
- **Current User**: `{rt['user']}` (Home: `{rt['home_dir']}`)
- **Default Shell**: `{rt['default_shell']}` (Shell Enabled: `{rt['allow_shell']}`)
- **Python Version**: {rt['python_version']} (`{rt['python_executable']}`)
- **Virtual Environment**: `{rt['virtualenv_path'] or 'None (System)'}`
- **Zenith Process PID**: `{rt['zenith_pid']}`
- **Workspace Directory**: `{rt['workspace_dir']}`
- **Operating Mode**: `{rt['zenith_mode']}`
"""


# ───────────────────────────────────────────────────────────── Cross-Platform Homelab Fallbacks ─────────

async def cross_platform_system_status() -> str:
    """Safe cross-platform host vitals: uptime, load, memory, disk."""
    try:
        mem = get_memory_info()
        disk = get_disk_info("/")
        up = get_uptime_info()
        cpu = get_cpu_info()
        load_str = ", ".join(str(x) for x in cpu["load_avg"]) if cpu.get("load_avg") else "N/A"
        return (
            f"uptime {up['system_uptime_human']} · load {load_str} · "
            f"mem {mem['used_percent']:.0f}% used ({mem['available_gb']:.1f} GiB free) · "
            f"disk {disk['summary']}"
        )
    except Exception as exc:
        return f"[system] {exc}"


async def cross_platform_disk_usage() -> str:
    """Safe cross-platform disk usage table."""
    try:
        from ..core.config import settings
        family = get_os_family()
        if family == "linux":
            # Native df if available
            try:
                res = subprocess.run(["df", "-h", "/", str(settings.workspace_dir)],
                                     capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    return res.stdout.strip()
            except Exception:
                pass

        # Cross-platform fallback via shutil
        root_info = get_disk_info("/" if family != "windows" else "C:\\")
        ws_info = get_disk_info(settings.workspace_dir)
        lines = [
            "Path                     Total       Used      Available  Use%",
            f"{root_info['path']:<24} {root_info.get('total_gb', 0):>6.1f}G {root_info.get('used_gb', 0):>6.1f}G {root_info.get('free_gb', 0):>9.1f}G  {root_info.get('used_percent', 0):>3.0f}%",
        ]
        if ws_info['path'] != root_info['path']:
            lines.append(
                f"{ws_info['path']:<24} {ws_info.get('total_gb', 0):>6.1f}G {ws_info.get('used_gb', 0):>6.1f}G {ws_info.get('free_gb', 0):>9.1f}G  {ws_info.get('used_percent', 0):>3.0f}%"
            )
        return "\n".join(lines)
    except Exception as exc:
        return f"[disk] {exc}"


async def cross_platform_memory_usage() -> str:
    """Safe cross-platform memory summary table."""
    try:
        family = get_os_family()
        if family == "linux":
            try:
                res = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    return res.stdout.strip()
            except Exception:
                pass

        mem = get_memory_info()
        return (
            f"Memory Summary:\n"
            f"  Total:     {mem['total_gb']:.1f} GiB\n"
            f"  Used:      {mem['used_bytes'] / (1024**3):.1f} GiB ({mem['used_percent']:.0f}%)\n"
            f"  Available: {mem['available_gb']:.1f} GiB"
        )
    except Exception as exc:
        return f"[memory] {exc}"


async def cross_platform_cpu_usage() -> str:
    """Safe cross-platform CPU usage report."""
    try:
        cpu = get_cpu_info()
        family = get_os_family()
        top_txt = ""

        if family in ("linux", "darwin"):
            try:
                res = subprocess.run("ps -eo pcpu,pmem,comm --sort=-pcpu | head -8",
                                     shell=True, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    top_txt = res.stdout.strip()
            except Exception:
                pass
        elif family == "windows":
            try:
                res = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    top_txt = "\n".join(res.stdout.splitlines()[:8])
            except Exception:
                pass

        load_str = ", ".join(str(x) for x in cpu["load_avg"]) if cpu.get("load_avg") else "N/A"
        return f"CPU: {cpu['model']} ({cpu['cores']} cores) · Load: {load_str}\n{top_txt}".strip()
    except Exception as exc:
        return f"[cpu] {exc}"


async def cross_platform_top_processes(limit: int = 8) -> str:
    """Safe cross-platform top processes list."""
    try:
        family = get_os_family()
        if family in ("linux", "darwin"):
            try:
                cmd = ["ps", "-eo", "pcpu,pmem,pid,comm", "--sort=-pcpu"] if family == "linux" else ["ps", "-arcxo", "%cpu,%mem,pid,command"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    lines = res.stdout.strip().splitlines()
                    return "\n".join(lines[: limit + 1])
            except Exception:
                pass
        elif family == "windows":
            try:
                res = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    lines = res.stdout.strip().splitlines()
                    return "\n".join(lines[: limit + 3])
            except Exception:
                pass

        return f"Top processes listing not available on this platform ({family})."
    except Exception as exc:
        return f"[ps] {exc}"

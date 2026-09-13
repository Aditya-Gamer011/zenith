"""Chart and Data Visualization Engine — generate graphs and charts.

Zenith can render data into visual charts (bar, line, pie, donut, scatter, area).
Supports both matplotlib (high-res PNG) and a pure-Python SVG fallback so
charts work out-of-the-box in any environment.

Charts are saved to static/screenshots/ for inline chat display, /tmp/zenith-files/
for file attachments, and can be uploaded to cdn.hackclub.com for public sharing.
"""
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path
from typing import Any, List, Dict, Optional, Union

import tempfile
from ..core.config import settings

_SCREENSHOTS_DIR = settings.screenshots_dir
_TMP_DIR = Path(tempfile.gettempdir()) / "zenith-files"


def _ensure_dirs():
    _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    _TMP_DIR.mkdir(parents=True, exist_ok=True)


async def generate_chart(
    title: str,
    chart_type: str = "bar",
    labels: Union[str, List[str]] = "",
    values: Union[str, List[float], List[List[float]]] = "",
    series_names: Union[str, List[str]] = "",
    x_label: str = "",
    y_label: str = "",
    upload_to_cdn: bool = False,
) -> str:
    """Generate a visual data chart (bar, line, pie, donut, scatter, area).

    labels: list of strings or comma-separated string e.g. ["Jan", "Feb", "Mar"]
    values: list of numbers or comma-separated string e.g. "10,20,30" or multiple series
    """
    _ensure_dirs()
    chart_type = chart_type.lower().strip()

    # Parse labels
    if isinstance(labels, str):
        label_list = [x.strip() for x in labels.split(",") if x.strip()]
    else:
        label_list = [str(x) for x in labels]

    # Parse values
    val_list: List[Any] = []
    if isinstance(values, str):
        # Could be pipe or comma separated
        parts = [x.strip() for x in values.split(",") if x.strip()]
        val_list = [_to_num(x) for x in parts]
    elif isinstance(values, list):
        val_list = [_to_num(x) for x in values]

    if not label_list and val_list:
        label_list = [f"Item {i+1}" for i in range(len(val_list))]
    elif not val_list and label_list:
        val_list = [1.0] * len(label_list)
    elif not label_list and not val_list:
        return "[charts] Error: Provide labels and values to plot."

    # Parse series_names
    if isinstance(series_names, str):
        s_names = [x.strip() for x in series_names.split(",") if x.strip()]
    else:
        s_names = [str(x) for x in series_names]

    ts = int(time.time())
    fname = f"chart_{ts}.png"
    out_img = _SCREENSHOTS_DIR / fname
    out_tmp = _TMP_DIR / fname

    # Try matplotlib first
    mpl_ok = False
    try:
        mpl_ok = _render_matplotlib(
            out_img, title, chart_type, label_list, val_list, s_names, x_label, y_label
        )
    except Exception as exc:
        mpl_ok = False

    if not mpl_ok:
        # Fallback to SVG rendering
        svg_fname = f"chart_{ts}.svg"
        out_svg = _SCREENSHOTS_DIR / svg_fname
        out_svg_tmp = _TMP_DIR / svg_fname
        _render_svg(
            out_svg, title, chart_type, label_list, val_list, s_names, x_label, y_label
        )
        # Copy to tmp
        out_svg_tmp.write_bytes(out_svg.read_bytes())

        rel_url = f"/static/screenshots/{svg_fname}"
        cdn_msg = ""
        if upload_to_cdn:
            from .cdn import cdn_upload
            cdn_res = await cdn_upload(str(out_svg))
            cdn_msg = f"\n  CDN: {cdn_res}"

        return (f"Chart generated (SVG):\n"
                f"  title: {title}\n"
                f"  path: {out_svg}\n"
                f"  embed: ![Chart: {title}]({rel_url}){cdn_msg}")

    # Copy PNG to tmp
    out_tmp.write_bytes(out_img.read_bytes())
    rel_url = f"/static/screenshots/{fname}"

    cdn_msg = ""
    if upload_to_cdn:
        from .cdn import cdn_upload
        cdn_res = await cdn_upload(str(out_img))
        cdn_msg = f"\n  CDN: {cdn_res}"

    return (f"Chart generated:\n"
            f"  title: {title}\n"
            f"  path: {out_img}\n"
            f"  embed: ![Chart: {title}]({rel_url}){cdn_msg}")


def _to_num(val: Any) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


# ── Matplotlib Renderer ──────────────────────────────────────────────────────

def _render_matplotlib(
    out_path: Path,
    title: str,
    chart_type: str,
    labels: List[str],
    values: List[Any],
    series_names: List[str],
    x_label: str,
    y_label: str,
) -> bool:
    import matplotlib
    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(9, 5), dpi=120)
    fig.patch.set_facecolor("#0f172a")
    ax.set_facecolor("#1e293b")

    colors = ["#38bdf8", "#818cf8", "#34d399", "#f43f5e", "#fbbf24", "#c084fc", "#38bdf8"]

    if chart_type in ("pie", "donut"):
        wedgeprops = {"width": 0.4} if chart_type == "donut" else {}
        ax.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            colors=colors[:len(values)],
            startangle=140,
            textprops={"color": "#e2e8f0", "fontsize": 10},
            wedgeprops=wedgeprops,
        )
    elif chart_type in ("line", "area"):
        ax.plot(labels, values, marker="o", linewidth=2.5, color="#38bdf8", label=series_names[0] if series_names else "")
        if chart_type == "area":
            ax.fill_between(range(len(labels)), values, color="#38bdf8", alpha=0.3)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha="right", color="#94a3b8")
    elif chart_type in ("scatter",):
        ax.scatter(range(len(values)), values, color="#818cf8", s=80)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha="right", color="#94a3b8")
    else:  # bar default
        bars = ax.bar(labels, values, color=colors[:len(values)], width=0.55, edgecolor="#0f172a")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=30, ha="right", color="#94a3b8")
        # Add value annotations on top of bars
        for bar in bars:
            height = bar.get_height()
            ax.annotate(
                f"{height:g}",
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, 3),
                textcoords="offset points",
                ha="center", va="bottom", color="#e2e8f0", fontsize=9
            )

    if title:
        ax.set_title(title, color="#f8fafc", fontsize=14, pad=15, fontweight="bold")
    if x_label and chart_type not in ("pie", "donut"):
        ax.set_xlabel(x_label, color="#94a3b8", fontsize=11)
    if y_label and chart_type not in ("pie", "donut"):
        ax.set_ylabel(y_label, color="#94a3b8", fontsize=11)

    ax.tick_params(colors="#94a3b8")
    for spine in ax.spines.values():
        spine.set_color("#334155")
    ax.grid(True, linestyle="--", alpha=0.2, color="#475569")

    plt.tight_layout()
    plt.savefig(out_path, facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)
    return True


# ── Pure-Python SVG Fallback ────────────────────────────────────────────────

def _render_svg(
    out_path: Path,
    title: str,
    chart_type: str,
    labels: List[str],
    values: List[Any],
    series_names: List[str],
    x_label: str,
    y_label: str,
) -> None:
    width, height = 700, 400
    colors = ["#38bdf8", "#818cf8", "#34d399", "#f43f5e", "#fbbf24", "#c084fc"]

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">',
        f'<rect width="{width}" height="{height}" fill="#0f172a" rx="12"/>',
        f'<text x="{width/2}" y="35" fill="#f8fafc" font-family="system-ui, sans-serif" font-size="18" font-weight="bold" text-anchor="middle">{title}</text>',
    ]

    n = len(values)
    max_val = max(values) if values and max(values) > 0 else 1.0

    if chart_type in ("bar", "default"):
        chart_left, chart_bottom, chart_width, chart_height = 80, 330, 560, 240
        bar_width = min(40, chart_width / (n * 1.5))
        gap = (chart_width - (n * bar_width)) / (n + 1)

        # Baseline
        svg.append(f'<line x1="{chart_left}" y1="{chart_bottom}" x2="{chart_left + chart_width}" y2="{chart_bottom}" stroke="#334155" stroke-width="2"/>')

        for i, (lbl, val) in enumerate(zip(labels, values)):
            x = chart_left + gap + i * (bar_width + gap)
            h = (val / max_val) * chart_height
            y = chart_bottom - h
            color = colors[i % len(colors)]
            svg.append(f'<rect x="{x}" y="{y}" width="{bar_width}" height="{h}" fill="{color}" rx="4"/>')
            svg.append(f'<text x="{x + bar_width/2}" y="{y - 8}" fill="#e2e8f0" font-family="sans-serif" font-size="11" text-anchor="middle">{val:g}</text>')
            svg.append(f'<text x="{x + bar_width/2}" y="{chart_bottom + 20}" fill="#94a3b8" font-family="sans-serif" font-size="11" text-anchor="middle">{lbl}</text>')

    elif chart_type in ("line", "area"):
        chart_left, chart_bottom, chart_width, chart_height = 80, 330, 560, 240
        points = []
        step = chart_width / max(n - 1, 1)

        for i, (lbl, val) in enumerate(zip(labels, values)):
            x = chart_left + i * step
            y = chart_bottom - (val / max_val) * chart_height
            points.append((x, y, lbl, val))

        pts_str = " ".join([f"{x},{y}" for x, y, _, _ in points])

        if chart_type == "area":
            area_pts = f"{chart_left},{chart_bottom} " + pts_str + f" {chart_left + chart_width},{chart_bottom}"
            svg.append(f'<polygon points="{area_pts}" fill="#38bdf8" fill-opacity="0.2"/>')

        svg.append(f'<polyline points="{pts_str}" fill="none" stroke="#38bdf8" stroke-width="3"/>')

        for x, y, lbl, val in points:
            svg.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#38bdf8"/>')
            svg.append(f'<text x="{x}" y="{y - 10}" fill="#e2e8f0" font-family="sans-serif" font-size="11" text-anchor="middle">{val:g}</text>')
            svg.append(f'<text x="{x}" y="{chart_bottom + 20}" fill="#94a3b8" font-family="sans-serif" font-size="11" text-anchor="middle">{lbl}</text>')

    svg.append('</svg>')
    out_path.write_text("\n".join(svg), encoding="utf-8")

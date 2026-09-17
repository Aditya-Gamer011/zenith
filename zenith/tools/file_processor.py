"""File & Image Processor Module — analyze, vision-inspect, edit, and convert user files and images.

Zenith can process user-uploaded files & images (PDFs, Word docs, Excel sheets, code, PNG, JPG, WEBP),
perform vision analysis, edit/transform images (resize, crop, grayscale, rotate, watermark),
and modify/re-export documents.
"""
from __future__ import annotations

import base64
import io
import json
import os
import time
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from ..core.config import settings

_UPLOADS_DIR = settings.static_dir / "uploads"
_TMP_DIR = Path(tempfile.gettempdir()) / "zenith-files"


def _ensure_dirs():
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    _TMP_DIR.mkdir(parents=True, exist_ok=True)


async def analyze_image(image_path: str, prompt: str = "") -> str:
    """Analyze and inspect an image file (PNG, JPG, WEBP, SVG, GIF).
    Provides image metadata, dimensions, color info, and AI vision description."""
    _ensure_dirs()
    p = Path(image_path).expanduser()
    if not p.is_file():
        # Try relative to uploads or tmp
        if (_UPLOADS_DIR / p.name).is_file():
            p = _UPLOADS_DIR / p.name
        elif (_TMP_DIR / p.name).is_file():
            p = _TMP_DIR / p.name
        else:
            return f"[file_processor] Image file not found: {image_path}"

    try:
        from PIL import Image

        with Image.open(p) as img:
            width, height = img.size
            fmt = img.format or p.suffix.lstrip(".").upper()
            mode = img.mode
            size_kb = p.stat().st_size / 1024

        info = f"📷 **Image Inspection**: `{p.name}`\n" \
               f"  - **Dimensions**: {width} x {height} px\n" \
               f"  - **Format**: {fmt}\n" \
               f"  - **Color Mode**: {mode}\n" \
               f"  - **File Size**: {size_kb:.1f} KB\n"

        # Vision pass using provider if prompt or general analysis is requested
        try:
            from ..core import provider
            image_bytes = p.read_bytes()
            b64_img = base64.b64encode(image_bytes).decode("ascii")

            sys_prompt = "You are a computer vision expert. Analyze this image thoroughly."
            user_msg = prompt or "Describe what is in this image, including text, objects, UI components, or diagrams."

            # Multimodal prompt structure
            vision_resp = await provider.chat_once(
                "standard",
                [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_msg},
                        {"type": "image_url", "image_url": {"url": f"data:image/{fmt.lower()};base64,{b64_img}"}}
                    ]}
                ],
                max_tokens=600,
            )
            if vision_resp:
                info += f"\n**AI Vision Analysis**:\n{vision_resp}"
        except Exception:
            pass

        rel_url = f"/static/uploads/{p.name}" if "uploads" in str(p) else f"/static/screenshots/{p.name}"
        info += f"\n\n![Image: {p.name}]({rel_url})"
        return info

    except Exception as exc:
        return f"[analyze_image error]: {exc}"


async def edit_image(
    image_path: str,
    action: str,
    width: int = 0,
    height: int = 0,
    angle: int = 0,
    target_format: str = "",
    watermark_text: str = "",
) -> str:
    """Edit, transform, or convert an image (actions: resize, grayscale, rotate, convert, watermark, blur, flip)."""
    _ensure_dirs()
    p = Path(image_path).expanduser()
    if not p.is_file():
        if (_UPLOADS_DIR / p.name).is_file():
            p = _UPLOADS_DIR / p.name
        elif (_TMP_DIR / p.name).is_file():
            p = _TMP_DIR / p.name
        else:
            return f"[edit_image] File not found: {image_path}"

    action = action.lower().strip()
    ts = int(time.time())
    ext = target_format.lower().lstrip(".") if target_format else p.suffix.lstrip(".").lower()
    if ext == "jpeg":
        ext = "jpg"

    out_name = f"edited_{p.stem}_{ts}.{ext}"
    out_path = _UPLOADS_DIR / out_name

    try:
        from PIL import Image, ImageOps, ImageEnhance, ImageDraw, ImageFont, ImageFilter

        with Image.open(p) as img:
            # Convert RGBA to RGB if saving as JPG
            if ext in ("jpg", "jpeg") and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")

            if action == "resize":
                if width > 0 and height > 0:
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                elif width > 0:
                    w_percent = width / float(img.size[0])
                    h_size = int(float(img.size[1]) * float(w_percent))
                    img = img.resize((width, h_size), Image.Resampling.LANCZOS)
                elif height > 0:
                    h_percent = height / float(img.size[1])
                    w_size = int(float(img.size[0]) * float(h_percent))
                    img = img.resize((w_size, height), Image.Resampling.LANCZOS)

            elif action in ("grayscale", "blackwhite", "bw"):
                img = ImageOps.grayscale(img)

            elif action == "rotate":
                deg = angle or 90
                img = img.rotate(-deg, expand=True)

            elif action in ("flip", "mirror"):
                img = ImageOps.mirror(img)

            elif action == "blur":
                img = img.filter(ImageFilter.BLUR)

            elif action == "watermark":
                draw = ImageDraw.Draw(img)
                text = watermark_text or "Zenith Assistant"
                w, h = img.size
                draw.text((w - 180, h - 40), text, fill=(255, 255, 255, 180))

            img.save(out_path)

        rel_url = f"/static/uploads/{out_name}"
        return (f"✅ Image edited ({action}):\n"
                f"  out: {out_path}\n"
                f"  embed: ![Edited Image: {out_name}]({rel_url})")

    except Exception as exc:
        return f"[edit_image error]: {exc}"


async def analyze_file(file_path: str) -> str:
    """Inspect and extract content/structure from PDFs, Word docs, Excel sheets, CSV, JSON, or code files."""
    p = Path(file_path).expanduser()
    if not p.is_file():
        if (_UPLOADS_DIR / p.name).is_file():
            p = _UPLOADS_DIR / p.name
        elif (_TMP_DIR / p.name).is_file():
            p = _TMP_DIR / p.name
        else:
            return f"[analyze_file] File not found: {file_path}"

    suffix = p.suffix.lower()
    size_kb = p.stat().st_size / 1024

    # 1. PDF Analysis
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(p)
            num_pages = len(reader.pages)
            extracted_text = []
            for i, page in enumerate(reader.pages[:5]):
                txt = page.extract_text()
                if txt and txt.strip():
                    extracted_text.append(f"--- Page {i+1} ---\n{txt.strip()[:600]}")
            preview = "\n\n".join(extracted_text) if extracted_text else "No extractable text found (scanned or image PDF)."
            return (f"📄 **PDF Document**: `{p.name}` ({size_kb:.1f} KB)\n"
                    f"**Total Pages**: {num_pages}\n"
                    f"**Preview (First {min(num_pages, 5)} Pages)**:\n```\n{preview[:2000]}\n```")
        except Exception as exc:
            return f"[pdf analyze error]: {exc}"

    # 2. Word Document (.docx) Analysis
    elif suffix == ".docx":
        try:
            from docx import Document
            doc = Document(p)
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            preview = "\n".join(paragraphs[:10])
            return (f"📝 **Word Document**: `{p.name}` ({size_kb:.1f} KB)\n"
                    f"**Paragraphs**: {len(paragraphs)}\n"
                    f"**Preview**:\n```\n{preview[:1500]}\n```")
        except Exception as exc:
            return f"[docx analyze error]: {exc}"

    # 3. Excel Spreadsheet (.xlsx) Analysis
    elif suffix == ".xlsx":
        try:
            from openpyxl import load_workbook
            wb = load_workbook(p, data_only=True)
            sheets = wb.sheetnames
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            headers = [str(c) for c in rows[0]] if rows else []
            return (f"📊 **Excel Spreadsheet**: `{p.name}` ({size_kb:.1f} KB)\n"
                    f"**Sheets**: {', '.join(sheets)}\n"
                    f"**Rows**: {len(rows)}\n"
                    f"**Headers**: {', '.join(headers[:8])}")
        except Exception as exc:
            return f"[xlsx analyze error]: {exc}"

    # 4. Text / Code / CSV / JSON Analysis
    else:
        try:
            text = p.read_text(errors="replace")
            lines = text.splitlines()
            return (f"💻 **File**: `{p.name}` ({size_kb:.1f} KB)\n"
                    f"**Total Lines**: {len(lines)}\n"
                    f"**Preview**:\n```\n{text[:2000]}\n```")
        except Exception as exc:
            return f"[file analyze error]: {exc}"


async def modify_file(file_path: str, new_content: str, output_filename: str = "", in_place: bool = False) -> str:
    """Modify or re-export an existing file with new content or changes.

    If in_place=True (or if the file is a project/workspace file and no output_filename is provided),
    the file is modified directly in place with syntax validation and rollback backup.
    Otherwise, a modified copy is exported to the temporary uploads/downloads staging area.
    """
    p = Path(file_path).expanduser()
    if not p.is_file():
        # Check relative to workspace or uploads or tmp
        ws_candidate = (settings.workspace_dir / p).resolve() if settings.workspace_dir.exists() else None
        if ws_candidate and ws_candidate.is_file():
            p = ws_candidate
        elif (_UPLOADS_DIR / p.name).is_file():
            p = _UPLOADS_DIR / p.name
        elif (_TMP_DIR / p.name).is_file():
            p = _TMP_DIR / p.name
        else:
            return f"[modify_file] File not found: {file_path}"

    # Determine if in-place modification should be performed
    is_in_place = in_place or (not output_filename and not str(p).startswith(str(_TMP_DIR)) and not str(p).startswith(str(_UPLOADS_DIR)))

    if is_in_place:
        from .swe_engine import _validate_syntax, _create_checkpoint
        valid, err = _validate_syntax(p, new_content)
        if not valid:
            return f"❌ [modify_file] Syntax validation failed: {err}"

        ws = settings.workspace_dir if settings.workspace_dir.exists() else Path.cwd()
        chk_id = _create_checkpoint(p, p.read_text(encoding="utf-8", errors="replace"), ws)
        try:
            p.write_text(new_content, encoding="utf-8")
            return f"✅ File modified in-place: `{p}` ({p.stat().st_size} bytes, checkpoint: `{chk_id}`)"
        except Exception as exc:
            return f"[modify_file error]: {exc}"

    out_name = output_filename or f"modified_{p.name}"
    out_path = _TMP_DIR / out_name

    try:
        out_path.write_text(new_content, encoding="utf-8")
        return f"✅ File modified & saved: `{out_path}` ({out_path.stat().st_size} bytes)"
    except Exception as exc:
        return f"[modify_file error]: {exc}"


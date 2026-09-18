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


def _resolve_file(file_path: str) -> Optional[Path]:
    """Resolve file path across workspace, uploads dir, temp dir, and filesystem."""
    _ensure_dirs()
    if not file_path:
        return None
    p = Path(file_path).expanduser()
    if p.is_file():
        return p
    # Try workspace directory if configured
    try:
        ws = getattr(settings, "workspace_dir", None)
        if ws and Path(ws).exists():
            candidate_ws = (Path(ws) / p).resolve()
            if candidate_ws.is_file():
                return candidate_ws
    except Exception:
        pass
    # Try relative to uploads dir or temp dir by filename
    if (_UPLOADS_DIR / p.name).is_file():
        return _UPLOADS_DIR / p.name
    if (_TMP_DIR / p.name).is_file():
        return _TMP_DIR / p.name
    # Try direct subpath under uploads or temp
    cand_up = _UPLOADS_DIR / file_path
    if cand_up.is_file():
        return cand_up
    cand_tmp = _TMP_DIR / file_path
    if cand_tmp.is_file():
        return cand_tmp
    return None


async def read_presentation(file_path: str, max_slides: int = 50) -> str:
    """Read, parse, and analyze a PowerPoint presentation (.pptx) extracting slide titles, bullet points, tables, and notes."""
    p = _resolve_file(file_path)
    if not p:
        return f"[read_presentation] Presentation file not found: {file_path}"

    suffix = p.suffix.lower()
    if suffix not in (".pptx", ".ppt"):
        return f"[read_presentation] Unsupported format '{suffix}'. Please provide a PowerPoint (.pptx) file."

    if suffix == ".ppt":
        return (f"⚠️ [read_presentation] `{p.name}` is in legacy binary .ppt format. "
                "Please save or convert it to modern .pptx to inspect its slides, tables, and notes.")

    try:
        from pptx import Presentation

        prs = Presentation(p)
        total_slides = len(prs.slides)
        size_kb = p.stat().st_size / 1024

        if total_slides == 0:
            return f"📊 **PowerPoint Presentation**: `{p.name}` ({size_kb:.1f} KB)\n*(Presentation contains 0 slides)*"

        limit = min(total_slides, max(1, max_slides))
        out = [f"📊 **PowerPoint Presentation**: `{p.name}` ({size_kb:.1f} KB, {total_slides} total slides)\n"]

        for idx, slide in enumerate(prs.slides):
            if idx >= limit:
                break
            slide_num = idx + 1

            # Extract title
            title = ""
            if slide.shapes.title and slide.shapes.title.text:
                title = slide.shapes.title.text.strip().replace("\n", " ")
            if not title:
                title = f"Slide {slide_num}"

            out.append(f"### Slide {slide_num}: {title}")

            content_lines = []
            for shape in slide.shapes:
                if shape == slide.shapes.title:
                    continue

                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        txt = para.text.strip()
                        if not txt or txt == title:
                            continue
                        indent = "  " * (para.level or 0)
                        content_lines.append(f"{indent}- {txt}")

                elif shape.has_table:
                    tbl = shape.table
                    content_lines.append("\n**Table:**")
                    table_rows = []
                    for r_idx, row in enumerate(tbl.rows):
                        cells = [cell.text.strip().replace("\n", " ").replace("|", "\\|") for cell in row.cells]
                        table_rows.append("| " + " | ".join(cells) + " |")
                        if r_idx == 0:
                            table_rows.append("| " + " | ".join(["---"] * max(1, len(cells))) + " |")
                    content_lines.append("\n".join(table_rows) + "\n")

            if content_lines:
                out.append("\n".join(content_lines))
            else:
                out.append("*(No text/table content — image, graphic, or layout slide)*")

            # Extract speaker notes if present
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text.strip()
                if notes:
                    out.append(f"> 🎙️ **Speaker Notes**: {notes}")

            out.append("")  # Spacing between slides

        if total_slides > limit:
            out.append(f"\n*(Truncated: showing first {limit} of {total_slides} slides. Specify max_slides to view more.)*")

        return "\n".join(out)

    except Exception as exc:
        return f"[read_presentation error]: {exc}"


async def read_spreadsheet(
    file_path: str,
    sheet_name: str = "",
    max_rows: int = 100,
    max_cols: int = 20,
) -> str:
    """Read, parse, and analyze an Excel spreadsheet (.xlsx, .xlsm) or CSV/TSV file with clean Markdown table formatting."""
    p = _resolve_file(file_path)
    if not p:
        return f"[read_spreadsheet] Spreadsheet file not found: {file_path}"

    suffix = p.suffix.lower()
    size_kb = p.stat().st_size / 1024

    # 1. CSV / TSV handling
    if suffix in (".csv", ".tsv"):
        try:
            import csv
            delim = "\t" if suffix == ".tsv" else ","
            text_content = p.read_text(encoding="utf-8", errors="replace")
            if suffix == ".csv":
                try:
                    sample = text_content[:4096]
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(sample, delimiters=",\t;|")
                    delim = dialect.delimiter
                except Exception:
                    delim = ","

            reader = list(csv.reader(text_content.splitlines(), delimiter=delim))
            while reader and not any(c.strip() for c in reader[-1]):
                reader.pop()

            if not reader:
                return f"📋 **CSV/TSV Spreadsheet**: `{p.name}` ({size_kb:.1f} KB)\n*(File is empty)*"

            total_rows = len(reader)
            total_cols = max(len(r) for r in reader) if reader else 0
            headers_raw = reader[0][:max_cols]
            headers = [h.strip().replace("|", "\\|") if h.strip() else f"Col {i+1}" for i, h in enumerate(headers_raw)]
            if not headers:
                headers = ["Col 1"]

            out = [
                f"📋 **CSV/TSV Spreadsheet**: `{p.name}` ({size_kb:.1f} KB)\n"
                f"**Total Rows**: {total_rows} | **Columns**: {total_cols}\n"
            ]
            out.append("| " + " | ".join(headers) + " |")
            out.append("| " + " | ".join(["---"] * len(headers)) + " |")

            limit = min(total_rows, max_rows)
            for row in reader[1:limit]:
                cells = [(c.strip().replace("\n", " ").replace("|", "\\|") if c else "") for c in row[:max_cols]]
                while len(cells) < len(headers):
                    cells.append("")
                out.append("| " + " | ".join(cells) + " |")

            if total_rows > limit:
                out.append(f"\n*(Showing first {limit} of {total_rows} rows. Increase max_rows to inspect more.)*")

            return "\n".join(out)
        except Exception as exc:
            return f"[read_spreadsheet CSV error]: {exc}"

    # 2. Excel handling
    if suffix not in (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"):
        return f"[read_spreadsheet] Unsupported format '{suffix}'. Please provide an Excel (.xlsx, .xlsm) or CSV file."

    if suffix == ".xls":
        return (f"⚠️ [read_spreadsheet] `{p.name}` is in legacy binary Excel .xls format. "
                "Please save or export as modern .xlsx for full sheet parsing and table formatting.")

    try:
        from openpyxl import load_workbook

        wb = load_workbook(p, data_only=True)
        sheet_names = wb.sheetnames
        if not sheet_names:
            return f"📊 **Excel Spreadsheet**: `{p.name}` ({size_kb:.1f} KB)\n*(Workbook contains no sheets)*"

        out = [f"📊 **Excel Spreadsheet**: `{p.name}` ({size_kb:.1f} KB)\n**Worksheets ({len(sheet_names)})**: {', '.join(sheet_names)}\n"]

        if sheet_name:
            if sheet_name not in wb:
                return (f"[read_spreadsheet] Sheet '{sheet_name}' not found in `{p.name}`. "
                        f"Available sheets: {', '.join(sheet_names)}")
            target_sheets = [sheet_name]
        else:
            target_sheets = sheet_names[:3]

        for s_idx, sname in enumerate(target_sheets):
            ws = wb[sname]
            raw_rows = list(ws.iter_rows(values_only=True))

            while raw_rows and not any(c is not None and str(c).strip() for c in raw_rows[-1]):
                raw_rows.pop()

            if not raw_rows:
                out.append(f"### Sheet: `{sname}`\n*(Empty worksheet)*\n")
                continue

            total_rows = len(raw_rows)
            first_row = raw_rows[0][:max_cols]
            headers = [str(c).strip().replace("|", "\\|") if c is not None and str(c).strip() else f"Col {i+1}" for i, c in enumerate(first_row)]
            if not headers:
                headers = ["Col 1"]

            out.append(f"### Sheet: `{sname}` ({total_rows} rows, {len(first_row)} columns)")
            out.append("| " + " | ".join(headers) + " |")
            out.append("| " + " | ".join(["---"] * len(headers)) + " |")

            limit = min(total_rows, max_rows if (sheet_name or s_idx == 0) else min(max_rows, 20))
            for row in raw_rows[1:limit]:
                cells = [str(c).strip().replace("\n", " ").replace("|", "\\|") if c is not None else "" for c in row[:max_cols]]
                while len(cells) < len(headers):
                    cells.append("")
                out.append("| " + " | ".join(cells) + " |")

            if total_rows > limit:
                out.append(f"\n*(Showing {limit} of {total_rows} rows in sheet `{sname}`)*\n")
            else:
                out.append("")

        return "\n".join(out)

    except Exception as exc:
        return f"[read_spreadsheet error]: {exc}"


async def analyze_file(file_path: str) -> str:
    """Inspect and extract content/structure from PowerPoint presentations, Excel sheets, PDFs, Word docs, CSV, JSON, or code files."""
    p = _resolve_file(file_path)
    if not p:
        return f"[analyze_file] File not found: {file_path}"

    suffix = p.suffix.lower()
    size_kb = p.stat().st_size / 1024

    # 1. PowerPoint Presentation (.pptx, .ppt)
    if suffix in (".pptx", ".ppt"):
        return await read_presentation(str(p), max_slides=10)

    # 2. Excel Spreadsheet (.xlsx, .xlsm, .xls) & CSV/TSV
    elif suffix in (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls", ".csv", ".tsv"):
        return await read_spreadsheet(str(p), max_rows=25)

    # 3. PDF Document
    elif suffix == ".pdf":
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

    # 4. Word Document (.docx)
    elif suffix == ".docx":
        try:
            from docx import Document
            doc = Document(p)
            paragraphs = [pr.text.strip() for pr in doc.paragraphs if pr.text.strip()]
            preview_paras = "\n".join(paragraphs[:10])
            
            table_previews = []
            for t_idx, tbl in enumerate(doc.tables[:3]):
                table_previews.append(f"\n**Table {t_idx + 1}** ({len(tbl.rows)} rows):")
                for row in tbl.rows[:5]:
                    row_txt = [c.text.strip().replace('\n', ' ') for c in row.cells]
                    table_previews.append("| " + " | ".join(row_txt) + " |")

            table_str = "\n".join(table_previews) if table_previews else ""
            return (f"📝 **Word Document**: `{p.name}` ({size_kb:.1f} KB)\n"
                    f"**Paragraphs**: {len(paragraphs)} | **Tables**: {len(doc.tables)}\n"
                    f"**Preview**:\n```\n{preview_paras[:1500]}\n```{table_str}")
        except Exception as exc:
            return f"[docx analyze error]: {exc}"

    # 5. JSON Document
    elif suffix == ".json":
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
            if isinstance(data, dict):
                keys_info = f"Keys ({len(data)}): {', '.join(list(data.keys())[:15])}"
            elif isinstance(data, list):
                keys_info = f"Array length: {len(data)} items"
            else:
                keys_info = f"Type: {type(data).__name__}"
            snippet = json.dumps(data, indent=2)[:1500]
            return (f"📋 **JSON File**: `{p.name}` ({size_kb:.1f} KB)\n"
                    f"**Structure**: {keys_info}\n"
                    f"**Preview**:\n```json\n{snippet}\n```")
        except Exception:
            pass

    # 6. Text / Code / Markdown / Generic File Analysis
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
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
    p = _resolve_file(file_path)
    if not p:
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


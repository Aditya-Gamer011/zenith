"""File generation — create Executive PDFs, Word docs, Excel spreadsheets, code, CSV, JSON.

Zenith can generate high-executive documents on-the-fly:
  - Rich PDF Reports: Executive Cover, Markdown Headings, Styled Tables, Code Blocks, Page X of Y footers, Stock Photos & Visual Charts.
  - Word (.docx): Professional Typography, Colored Heading Accents, Styled Tables, Callout Boxes, Stock Photo Embeds.
  - Excel (.xlsx): Executive Headers, Zebra Striping, Auto Number/Currency/Percent Formatting, Auto SUM Formulas, Gridlines & Column Auto-fit.
  - Code & Data Files: JSON, CSV, Python, JS, TS, HTML, Shell, etc.

Files land in /tmp/zenith-files/ and can be emailed or uploaded to Hack Club CDN.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, List, Dict, Optional

import tempfile

log = logging.getLogger("zenith.tools.filegen")

_OUTDIR = Path(tempfile.gettempdir()) / "zenith-files"
_OUTDIR.mkdir(parents=True, exist_ok=True)


def _ensure_dir() -> None:
    _OUTDIR.mkdir(parents=True, exist_ok=True)


def _unique_name(filename: str) -> Path:
    """Return a collision-free path under _OUTDIR."""
    _ensure_dir()
    stem = Path(filename).stem
    suffix = Path(filename).suffix or ".txt"
    ts = int(time.time())
    return _OUTDIR / f"{stem}_{ts}{suffix}"


def _format_inline_markdown(text: str) -> str:
    """Convert inline markdown (**bold**, *italic*, `code`) to ReportLab XML tags."""
    # Escape XML special chars first (except tags we generate)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Bold
    text = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", text)
    # Italic
    text = re.sub(r"\*(.*?)\*", r"<i>\1</i>", text)
    # Code
    text = re.sub(r"`(.*?)`", r'<font name="Courier" color="#8B5CF6">\1</font>', text)
    return text


# ── PDF Engine ──────────────────────────────────────────────────────────────

async def generate_pdf(filename: str, content: str, title: str = "") -> str:
    """Generate an Executive PDF file from markdown text content. Returns the file path."""
    out = _unique_name(filename if filename.endswith(".pdf") else f"{filename}.pdf")
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm, inch
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable, KeepTogether
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
        from reportlab.lib.colors import HexColor
        from reportlab.pdfgen import canvas
        from zenith.tools.presentation import fetch_web_image

        class PageNumCanvas(canvas.Canvas):
            """Two-pass ReportLab canvas for running footer ('Page X of Y')."""
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.pages = []

            def showPage(self):
                self.pages.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                page_count = len(self.pages)
                for page in self.pages:
                    self.__dict__.update(page)
                    self.draw_footer(page_count)
                    super().showPage()
                super().save()

            def draw_footer(self, page_count):
                self.saveState()
                self.setFont("Helvetica", 9)
                self.setFillColor(HexColor("#64748B"))
                self.setStrokeColor(HexColor("#CBD5E1"))
                self.setLineWidth(0.5)
                self.line(54, 40, 541, 40)
                self.drawString(54, 26, "Zenith Intelligence Engine  •  Executive Report")
                self.drawRightString(541, 26, f"Page {self._pageNumber} of {page_count}")
                self.restoreState()

        doc = SimpleDocTemplate(
            str(out),
            pagesize=A4,
            leftMargin=1.9 * cm,
            rightMargin=1.9 * cm,
            topMargin=2.0 * cm,
            bottomMargin=2.2 * cm,
        )

        styles = getSampleStyleSheet()

        # Custom Executive Typography Styles
        title_style = ParagraphStyle(
            "DocTitle", parent=styles["Title"],
            fontName="Helvetica-Bold", fontSize=24, leading=28,
            textColor=HexColor("#0F172A"), alignment=TA_LEFT, spaceAfter=8
        )
        h1_style = ParagraphStyle(
            "DocH1", parent=styles["Heading1"],
            fontName="Helvetica-Bold", fontSize=16, leading=20,
            textColor=HexColor("#1E40AF"), spaceBefore=14, spaceAfter=6, keepWithNext=True
        )
        h2_style = ParagraphStyle(
            "DocH2", parent=styles["Heading2"],
            fontName="Helvetica-Bold", fontSize=13, leading=16,
            textColor=HexColor("#0F172A"), spaceBefore=10, spaceAfter=4, keepWithNext=True
        )
        h3_style = ParagraphStyle(
            "DocH3", parent=styles["Heading3"],
            fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=HexColor("#475569"), spaceBefore=8, spaceAfter=3, keepWithNext=True
        )
        body_style = ParagraphStyle(
            "DocBody", parent=styles["Normal"],
            fontName="Helvetica", fontSize=10, leading=14,
            textColor=HexColor("#334155"), alignment=TA_LEFT, spaceAfter=6
        )
        bullet_style = ParagraphStyle(
            "DocBullet", parent=body_style,
            leftIndent=15, bulletIndent=5, spaceAfter=3
        )
        code_style = ParagraphStyle(
            "DocCode", parent=styles["Normal"],
            fontName="Courier", fontSize=9, leading=12,
            textColor=HexColor("#0F172A"), backColor=HexColor("#F8FAFC"),
            borderColor=HexColor("#E2E8F0"), borderWidth=1, borderPadding=8,
            spaceBefore=6, spaceAfter=8
        )
        table_cell_style = ParagraphStyle(
            "TableCell", parent=body_style,
            fontSize=9, leading=12, textColor=HexColor("#1E293B"), spaceAfter=0
        )
        table_hdr_style = ParagraphStyle(
            "TableHdr", parent=body_style,
            fontName="Helvetica-Bold", fontSize=9, leading=12,
            textColor=HexColor("#FFFFFF"), spaceAfter=0
        )

        story = []

        # Executive Header Title Section
        doc_title = title or Path(filename).stem.replace("_", " ").title()
        story.append(Paragraph(doc_title, title_style))
        story.append(HRFlowable(width="100%", thickness=2, color=HexColor("#8B5CF6"), spaceBefore=2, spaceAfter=12))

        # Check if content references photos or if title suggests visual header
        header_img_query = ""
        lines = content.split("\n")
        for l in lines[:5]:
            if l.startswith("![") and "](" in l:
                m = re.search(r"\!\[.*?\]\((.*?)\)", l)
                if m:
                    header_img_query = m.group(1)
                    break

        if not header_img_query and len(lines) > 3:
            header_img_query = doc_title

        if header_img_query and not header_img_query.endswith((".pdf", ".doc", ".txt")):
            img_file = await fetch_web_image(header_img_query, index=0)
            if img_file and os.path.exists(img_file):
                try:
                    story.append(Image(img_file, width=6.8 * inch, height=3.0 * inch))
                    story.append(Spacer(1, 10))
                except Exception as iexc:
                    log.debug("PDF image embed skipped: %s", iexc)

        # Parse Markdown Content into Flowables
        in_code_block = False
        code_buffer = []
        table_buffer = []

        def flush_table_buffer(buf):
            if not buf:
                return None
            table_data = []
            for r_idx, line in enumerate(buf):
                cells = [c.strip() for c in line.strip("|").split("|")]
                # Skip markdown header separator line (|---|---|)
                if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                    continue
                row_cells = []
                for c in cells:
                    st = table_hdr_style if r_idx == 0 else table_cell_style
                    row_cells.append(Paragraph(_format_inline_markdown(c), st))
                if row_cells:
                    table_data.append(row_cells)

            if not table_data:
                return None

            t = Table(table_data, colWidths=None)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), HexColor('#1E293B')),
                ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#FFFFFF')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#CBD5E1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [HexColor('#FFFFFF'), HexColor('#F8FAFC')]),
            ]))
            return t

        for line in lines:
            stripped = line.strip()

            # Code Block Toggle
            if stripped.startswith("```"):
                if in_code_block:
                    code_text = "\n".join(code_buffer)
                    code_text = code_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    story.append(Paragraph(code_text.replace("\n", "<br/>"), code_style))
                    code_buffer = []
                    in_code_block = False
                else:
                    if table_buffer:
                        tb_elem = flush_table_buffer(table_buffer)
                        if tb_elem:
                            story.append(tb_elem)
                            story.append(Spacer(1, 8))
                        table_buffer = []
                    in_code_block = True
                continue

            if in_code_block:
                code_buffer.append(line)
                continue

            # Table lines
            if stripped.startswith("|") and stripped.endswith("|"):
                table_buffer.append(stripped)
                continue
            elif table_buffer:
                tb_elem = flush_table_buffer(table_buffer)
                if tb_elem:
                    story.append(tb_elem)
                    story.append(Spacer(1, 8))
                table_buffer = []

            if not stripped:
                story.append(Spacer(1, 4))
                continue

            # Headings
            if stripped.startswith("# "):
                story.append(Paragraph(_format_inline_markdown(stripped[2:]), h1_style))
            elif stripped.startswith("## "):
                story.append(Paragraph(_format_inline_markdown(stripped[3:]), h2_style))
            elif stripped.startswith("### "):
                story.append(Paragraph(_format_inline_markdown(stripped[4:]), h3_style))
            elif stripped.startswith("- ") or stripped.startswith("* "):
                story.append(Paragraph("• " + _format_inline_markdown(stripped[2:]), bullet_style))
            elif re.match(r"^\d+\.\s", stripped):
                story.append(Paragraph(_format_inline_markdown(stripped), bullet_style))
            elif stripped.startswith("> "):
                bq_style = ParagraphStyle(
                    "DocBQ", parent=body_style,
                    fontName="Helvetica-Oblique", leftIndent=20,
                    textColor=HexColor("#475569"), spaceBefore=4, spaceAfter=6
                )
                story.append(Paragraph(_format_inline_markdown(stripped[2:]), bq_style))
            elif stripped.startswith("![") and "](" in stripped:
                m = re.search(r"\!\[.*?\]\((.*?)\)", stripped)
                if m:
                    img_q = m.group(1)
                    img_f = await fetch_web_image(img_q, index=1)
                    if img_f and os.path.exists(img_f):
                        try:
                            story.append(Spacer(1, 6))
                            story.append(Image(img_f, width=6.5 * inch, height=3.2 * inch))
                            story.append(Spacer(1, 6))
                        except Exception:
                            pass
            else:
                story.append(Paragraph(_format_inline_markdown(stripped), body_style))

        if table_buffer:
            tb_elem = flush_table_buffer(table_buffer)
            if tb_elem:
                story.append(tb_elem)
            table_buffer = []

        doc.build(story, canvasmaker=PageNumCanvas)
        log.info("Generated Executive PDF Report: %s (%d bytes)", out, out.stat().st_size)
        return str(out)

    except ImportError:
        fallback = out.with_suffix(".txt")
        header = f"=== {title} ===\n\n" if title else ""
        fallback.write_text(header + content, errors="replace")
        return f"[reportlab fallback] Wrote text document: {fallback}"
    except Exception as exc:
        log.error("PDF generation error: %s", exc)
        return f"[filegen] PDF error: {exc}"


# ── Word (.docx) Engine ─────────────────────────────────────────────────────

async def generate_docx(filename: str, content: str, title: str = "") -> str:
    """Generate a high-executive Word (.docx) document from markdown text. Returns the file path."""
    out = _unique_name(filename if filename.endswith(".docx") else f"{filename}.docx")
    try:
        from docx import Document
        from docx.shared import Pt, Inches, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.enum.table import WD_TABLE_ALIGNMENT
        from docx.oxml import parse_xml, OxmlElement
        from docx.oxml.ns import nsdecls, qn
        from zenith.tools.presentation import fetch_web_image

        doc = Document()

        # Set 1-inch Margins
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)

        def set_cell_background(cell, fill_hex: str):
            shading_elm = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
            cell._tc.get_or_add_tcPr().append(shading_elm)

        # Executive Document Header
        doc_title = title or Path(filename).stem.replace("_", " ").title()
        p_title = doc.add_paragraph()
        run_title = p_title.add_run(doc_title)
        run_title.font.name = "Arial"
        run_title.font.size = Pt(24)
        run_title.font.bold = True
        run_title.font.color.rgb = RGBColor(15, 23, 42) # #0F172A
        p_title.space_after = Pt(4)

        # Subtitle / Author Tag
        p_sub = doc.add_paragraph()
        run_sub = p_sub.add_run("Executive Document  •  Zenith Intelligence Engine")
        run_sub.font.name = "Arial"
        run_sub.font.size = Pt(10)
        run_sub.font.color.rgb = RGBColor(139, 92, 246) # #8B5CF6
        p_sub.space_after = Pt(16)

        # Image Header Embed if available
        lines = content.split("\n")
        header_img_query = ""
        for line in lines[:5]:
            if line.startswith("![") and "](" in line:
                m = re.search(r"\!\[.*?\]\((.*?)\)", line)
                if m:
                    header_img_query = m.group(1)
                    break

        if not header_img_query:
            header_img_query = doc_title

        if header_img_query and not header_img_query.endswith((".pdf", ".doc", ".txt")):
            img_file = await fetch_web_image(header_img_query, index=0)
            if img_file and os.path.exists(img_file):
                try:
                    doc.add_picture(img_file, width=Inches(6.5))
                    doc.paragraphs[-1].space_after = Pt(14)
                except Exception as iexc:
                    log.debug("DOCX image embed skipped: %s", iexc)

        # Parse Content Blocks
        in_code_block = False
        code_buffer = []
        table_buffer = []

        def flush_docx_table(buf):
            if not buf:
                return
            table_data = []
            for r_idx, l in enumerate(buf):
                cells = [c.strip() for c in l.strip("|").split("|")]
                if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                    continue
                if cells:
                    table_data.append(cells)

            if not table_data:
                return

            rows_cnt = len(table_data)
            cols_cnt = max(len(r) for r in table_data)
            tbl = doc.add_table(rows=rows_cnt, cols=cols_cnt)
            tbl.alignment = WD_TABLE_ALIGNMENT.CENTER

            for r_i, row in enumerate(table_data):
                for c_i, cell_text in enumerate(row):
                    if c_i < cols_cnt:
                        cell = tbl.cell(r_i, c_i)
                        cell.text = cell_text
                        p = cell.paragraphs[0]
                        p.runs[0].font.size = Pt(9.5)
                        if r_i == 0:
                            set_cell_background(cell, "1E293B")
                            p.runs[0].font.bold = True
                            p.runs[0].font.color.rgb = RGBColor(255, 255, 255)
                        else:
                            if r_i % 2 == 0:
                                set_cell_background(cell, "F8FAFC")
                            p.runs[0].font.color.rgb = RGBColor(30, 41, 59)
            doc.add_paragraph().space_after = Pt(6)

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("```"):
                if in_code_block:
                    # Flush code box
                    tbl = doc.add_table(rows=1, cols=1)
                    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
                    cell = tbl.cell(0, 0)
                    set_cell_background(cell, "F1F5F9")
                    cell.text = "\n".join(code_buffer)
                    for p in cell.paragraphs:
                        for r in p.runs:
                            r.font.name = "Consolas"
                            r.font.size = Pt(9.5)
                            r.font.color.rgb = RGBColor(15, 23, 42)
                    code_buffer = []
                    in_code_block = False
                    doc.add_paragraph().space_after = Pt(8)
                else:
                    if table_buffer:
                        flush_docx_table(table_buffer)
                        table_buffer = []
                    in_code_block = True
                continue

            if in_code_block:
                code_buffer.append(line)
                continue

            if stripped.startswith("|") and stripped.endswith("|"):
                table_buffer.append(stripped)
                continue
            elif table_buffer:
                flush_docx_table(table_buffer)
                table_buffer = []

            if not stripped:
                continue

            if stripped.startswith("# "):
                h = doc.add_heading(stripped[2:], level=1)
                h.runs[0].font.name = "Arial"
                h.runs[0].font.color.rgb = RGBColor(30, 64, 175) # #1E40AF
                h.space_before = Pt(14)
                h.space_after = Pt(4)
            elif stripped.startswith("## "):
                h = doc.add_heading(stripped[3:], level=2)
                h.runs[0].font.name = "Arial"
                h.runs[0].font.color.rgb = RGBColor(15, 23, 42) # #0F172A
                h.space_before = Pt(10)
                h.space_after = Pt(3)
            elif stripped.startswith("### "):
                h = doc.add_heading(stripped[4:], level=3)
                h.runs[0].font.name = "Arial"
                h.runs[0].font.color.rgb = RGBColor(71, 85, 105) # #475569
                h.space_before = Pt(8)
                h.space_after = Pt(2)
            elif stripped.startswith("- ") or stripped.startswith("* "):
                p = doc.add_paragraph(stripped[2:], style="List Bullet")
                p.runs[0].font.size = Pt(10.5)
                p.runs[0].font.color.rgb = RGBColor(51, 65, 85)
                p.space_after = Pt(3)
            elif stripped.startswith("![") and "](" in stripped:
                m = re.search(r"\!\[.*?\]\((.*?)\)", stripped)
                if m:
                    img_f = await fetch_web_image(m.group(1), index=1)
                    if img_f and os.path.exists(img_f):
                        try:
                            doc.add_picture(img_f, width=Inches(6.0))
                            doc.paragraphs[-1].space_after = Pt(8)
                        except Exception:
                            pass
            else:
                p = doc.add_paragraph()
                run = p.add_run(stripped)
                run.font.name = "Arial"
                run.font.size = Pt(10.5)
                run.font.color.rgb = RGBColor(51, 65, 85)
                p.space_after = Pt(6)

        if table_buffer:
            flush_docx_table(table_buffer)
            table_buffer = []

        doc.save(str(out))
        log.info("Generated Executive Word Document: %s (%d bytes)", out, out.stat().st_size)
        return str(out)

    except ImportError:
        fallback = out.with_suffix(".txt")
        header = f"=== {title} ===\n\n" if title else ""
        fallback.write_text(header + content, errors="replace")
        return f"[python-docx fallback] Wrote text document: {fallback}"
    except Exception as exc:
        log.error("DOCX generation error: %s", exc)
        return f"[filegen] DOCX error: {exc}"


# ── Excel (.xlsx) Engine ───────────────────────────────────────────────────

async def generate_xlsx(filename: str, data: str, sheet_name: str = "Financial Overview") -> str:
    """Generate a high-executive Excel (.xlsx) spreadsheet with zebra striping, auto formats, formulas, and gridlines."""
    out = _unique_name(filename if filename.endswith(".xlsx") else f"{filename}.xlsx")

    # Parse rows from CSV, pipe-delimited, or markdown table text
    rows = []
    sep = "|" if "|" in data else ("," if "," in data else "\t")
    for line in data.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
        else:
            cells = [c.strip() for c in line.split(sep)]
        if cells and not all(re.match(r"^:?-+:?$", c) for c in cells if c):
            rows.append(cells)

    if not rows:
        return "[filegen] No data provided for spreadsheet generation."

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name[:31]

        # Enable Gridlines explicitly
        ws.views.sheetView[0].showGridLines = True

        # Executive Styling Tokens
        hdr_font = Font(name="Calibri", bold=True, size=11, color="FFFFFF")
        hdr_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid") # Dark Slate
        zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
        total_font = Font(name="Calibri", bold=True, size=11, color="0F172A")
        total_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")

        thin_border = Border(
            left=Side(style="thin", color="CBD5E1"),
            right=Side(style="thin", color="CBD5E1"),
            top=Side(style="thin", color="CBD5E1"),
            bottom=Side(style="thin", color="CBD5E1"),
        )
        total_border = Border(
            top=Side(style="thin", color="0F172A"),
            bottom=Side(style="double", color="0F172A"),
        )

        numeric_cols = set()

        for r_idx, row in enumerate(rows, 1):
            for c_idx, cell_val in enumerate(row, 1):
                typed_val, fmt = _auto_parse_value(cell_val)
                c = ws.cell(row=r_idx, column=c_idx, value=typed_val)
                c.border = thin_border
                c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="right" if isinstance(typed_val, (int, float)) else "left")

                if fmt:
                    c.number_format = fmt

                if r_idx == 1:
                    c.font = hdr_font
                    c.fill = hdr_fill
                    c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                else:
                    if r_idx % 2 == 0:
                        c.fill = zebra_fill
                    if isinstance(typed_val, (int, float)):
                        numeric_cols.add(c_idx)

        # Add Automatic Total / Summary Row if numeric columns exist and > 2 data rows
        if len(rows) > 3 and numeric_cols:
            tot_row_idx = len(rows) + 1
            ws.cell(row=tot_row_idx, column=1, value="Total / Summary").font = total_font
            ws.cell(row=tot_row_idx, column=1).border = total_border
            ws.cell(row=tot_row_idx, column=1).fill = total_fill

            for c_idx in range(1, max(len(r) for r in rows) + 1):
                cell = ws.cell(row=tot_row_idx, column=c_idx)
                cell.border = total_border
                cell.fill = total_fill
                if c_idx in numeric_cols:
                    col_let = get_column_letter(c_idx)
                    cell.value = f"=SUM({col_let}2:{col_let}{tot_row_idx - 1})"
                    cell.font = total_font
                    cell.alignment = Alignment(horizontal="right")

        # Auto-fit Column Widths
        for col in ws.columns:
            col_letter = get_column_letter(col[0].column)
            max_len = max((len(str(cell.value or "")) for cell in col), default=8)
            ws.column_dimensions[col_letter].width = min(max(max_len + 5, 12), 45)

        wb.save(str(out))
        log.info("Generated Executive Excel Spreadsheet: %s (%d rows)", out, len(rows))
        return str(out)

    except ImportError:
        fallback = out.with_suffix(".csv")
        lines = [sep.join(row) for row in rows]
        fallback.write_text("\n".join(lines), errors="replace")
        return f"[openpyxl fallback] Wrote CSV file: {fallback}"
    except Exception as exc:
        log.error("XLSX generation error: %s", exc)
        return f"[filegen] XLSX error: {exc}"


def _auto_parse_value(val: str) -> tuple[Any, str | None]:
    """Parse raw cell string into typed Python value and Excel format string."""
    val = val.strip()
    if not val:
        return "", None

    # Currency ($ or ₹)
    if re.match(r"^[\$₹]\s*[\d,]+(\.\d+)?$", val):
        clean = re.sub(r"[^\d.]", "", val)
        try:
            return float(clean), '"$"#,##0.00'
        except ValueError:
            pass

    # Percentage
    if val.endswith("%"):
        clean = val[:-1].strip()
        try:
            return float(clean) / 100.0, "0.0%"
        except ValueError:
            pass

    # Integer
    try:
        if "," in val and not "." in val:
            clean = val.replace(",", "")
            return int(clean), "#,##0"
        return int(val), None
    except ValueError:
        pass

    # Float
    try:
        clean = val.replace(",", "")
        return float(clean), "#,##0.00"
    except ValueError:
        pass

    return val, None


# ── Code & Data Files ───────────────────────────────────────────────────────

async def generate_code(filename: str, content: str) -> str:
    """Write a code or text file (any extension). Returns the file path."""
    out = _unique_name(filename)
    try:
        out.write_text(content, errors="replace")
        return f"File created: {out} ({out.stat().st_size} bytes)"
    except Exception as exc:
        return f"[filegen] Code file error: {exc}"


async def generate_csv(filename: str, data: str) -> str:
    """Write a CSV file from raw CSV text. Returns the file path."""
    out = _unique_name(filename if filename.endswith(".csv") else f"{filename}.csv")
    try:
        out.write_text(data, errors="replace")
        return f"CSV created: {out} ({out.stat().st_size} bytes)"
    except Exception as exc:
        return f"[filegen] CSV error: {exc}"


async def generate_json(filename: str, data: str) -> str:
    """Write a formatted JSON file. Data can be a JSON string or raw text."""
    out = _unique_name(filename if filename.endswith(".json") else f"{filename}.json")
    try:
        parsed = json.loads(data)
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        formatted = data

    try:
        out.write_text(formatted, errors="replace")
        return f"JSON file created: {out} ({out.stat().st_size} bytes)"
    except Exception as exc:
        return f"[filegen] JSON error: {exc}"


# ── Listing & Cleanup ──────────────────────────────────────────────────────

async def list_generated_files() -> str:
    """List all files in the zenith-files directory."""
    _ensure_dir()
    files = sorted(_OUTDIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return "No generated files."
    lines = []
    for f in files[:30]:
        size = f.stat().st_size
        if size > 1024 * 1024:
            sz = f"{size / 1024 / 1024:.1f} MB"
        elif size > 1024:
            sz = f"{size / 1024:.1f} KB"
        else:
            sz = f"{size} B"
        lines.append(f"  {f.name}  ({sz})")
    return "\n".join(lines)


async def delete_generated_file(filename: str) -> str:
    """Delete a generated file by name."""
    p = _OUTDIR / filename
    if not p.is_file():
        return f"[filegen] Not found: {filename}"
    try:
        p.unlink()
        return f"Deleted {filename}."
    except Exception as exc:
        return f"[filegen] Delete error: {exc}"

"""Deep Research Engine — autonomous multi-source web research & data synthesis.

Zenith can run deep research on any topic: query generation, concurrent multi-page
crawling, data extraction, auto-generating visual charts, and producing an
executive research report (with downloadable PDF / Markdown file).
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import List, Dict, Any

from .web import web_search, read_url
from .charts import generate_chart
from .filegen import generate_pdf, generate_docx


async def deep_research(
    topic: str,
    extra_queries: List[str] | None = None,
    pdf_files: List[str] | None = None,
    max_sources: int = 6,
    generate_report_pdf: bool = True,
    create_chart: bool = True,
) -> str:
    """Execute autonomous deep research on a topic across web sources and local PDF documents,
    extract structured findings, synthesize findings, generate visual charts if numerical
    data is present, and create a downloadable PDF report."""
    if not topic.strip():
        return "[deep_research] Topic is required."

    # ── Step 1: Formulate targeted queries ──────────────────────────────────
    queries = [topic]
    if extra_queries:
        for q in extra_queries:
            if q and q.strip() and q.strip() not in queries:
                queries.append(q.strip())
    if len(queries) == 1:
        queries.extend([
            f"{topic} latest developments analysis",
            f"{topic} key data statistics facts overview",
        ])

    # ── Step 2: Parse local/uploaded PDF files if provided ──────────────────
    pdf_context: List[str] = []
    if pdf_files:
        from pathlib import Path
        for pdf_p in pdf_files:
            p = Path(pdf_p).expanduser()
            if not p.is_file():
                p_upload = Path("/app/static/uploads") / Path(pdf_p).name
                if p_upload.is_file():
                    p = p_upload
            if p.is_file() and p.suffix.lower() == ".pdf":
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(p)
                    txts = []
                    for page in reader.pages[:8]:
                        t = page.extract_text()
                        if t and t.strip():
                            txts.append(t.strip())
                    if txts:
                        pdf_context.append(f"--- PDF DOCUMENT ({p.name}) ---\n" + "\n".join(txts)[:3500])
                except Exception as exc:
                    pdf_context.append(f"--- PDF ({p.name}) Error: {exc} ---")

    # ── Step 3: Run web search across queries ───────────────────────────────
    search_tasks = [web_search(q) for q in queries[:4]]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    urls: List[str] = []
    all_snippets: List[str] = []
    url_regex = re.compile(r"https?://[^\s\"'>]+")

    for res in search_results:
        if isinstance(res, str):
            all_snippets.append(res)
            found = url_regex.findall(res)
            for u in found:
                u_clean = u.rstrip(".,);]")
                if u_clean not in urls and not any(skip in u_clean for skip in ("duckduckgo.com", "google.com/search")):
                    urls.append(u_clean)

    # ── Step 4: Fetch top sources concurrently ──────────────────────────────
    target_urls = urls[:min(max_sources, 8)]
    page_texts: List[Dict[str, str]] = []

    if target_urls:
        read_tasks = [read_url(u) for u in target_urls]
        read_results = await asyncio.gather(*read_tasks, return_exceptions=True)
        for u, r in zip(target_urls, read_results):
            if isinstance(r, str) and not r.startswith("[error]") and len(r) > 100:
                page_texts.append({"url": u, "content": r[:3000]})

    # ── Step 5: Synthesize Findings ─────────────────────────────────────────
    combined_corpus = ""
    if pdf_context:
        combined_corpus += "\n\n".join(pdf_context) + "\n\n"
    combined_corpus += "\n\n".join([f"--- SOURCE: {p['url']} ---\n{p['content']}" for p in page_texts])
    if not combined_corpus.strip():
        combined_corpus = "\n".join(all_snippets[:5])

    synthesized_summary = ""
    try:
        from ..core import provider
        system_prompt = (
            "You are Zenith Senior Research Analyst. Produce a comprehensive, structured, executive "
            "synthesis of the provided web and document research. Use clear section headers, bullet points, "
            "and cite key facts or URLs."
        )
        user_prompt = (
            f"Topic: {topic}\n"
            f"Queries Executed: {', '.join(queries)}\n"
            f"PDF Documents Parsed: {len(pdf_context)}\n"
            f"Web Sources Crawled: {len(page_texts)}\n\n"
            f"RESEARCH CORPUS:\n{combined_corpus[:6000]}\n\n"
            f"Produce a structured executive markdown research briefing."
        )
        synthesized_summary = await provider.chat_once(
            "standard",
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1000,
        )
    except Exception:
        pass

    if not synthesized_summary:
        sources_summary = "\n\n".join(
            [f"--- SOURCE: {p['url']} ---\n{p['content'][:1200]}" for p in page_texts]
        ) or "\n".join(all_snippets[:5])
        synthesized_summary = (
            f"### Executive Summary\nSynthesized research across {len(queries)} queries, {len(target_urls)} web sources, "
            f"and {len(pdf_context)} documents regarding **{topic}**.\n\n"
            f"### Key Findings & Data\n{sources_summary[:2500]}"
        )

    # ── Step 6: Auto-generate chart if numerical data found ──────────────────
    chart_embed = ""
    if create_chart:
        chart_res = await _auto_extract_chart(topic, combined_corpus or synthesized_summary)
        if chart_res:
            chart_embed = f"\n\n### 📊 Visual Data Summary\n{chart_res}"

    # ── Step 7: Generate PDF Report File ─────────────────────────────────────
    pdf_msg = ""
    if generate_report_pdf:
        report_doc = f"""# DEEP RESEARCH BRIEFING: {topic.upper()}

{synthesized_summary}

## Sources Referenced
""" + "\n".join([f"- {u}" for u in target_urls])
        pdf_res = await generate_pdf(f"research_{topic[:20]}", report_doc, title=f"Research: {topic}")
        pdf_msg = f"\n\n📄 **Downloadable PDF Report**: `{pdf_res}`"

    doc_info = f", {len(pdf_context)} PDF files" if pdf_context else ""
    return (
        f"## 🔬 Deep Research Briefing: {topic}\n\n"
        f"**Queries Executed**: {', '.join(queries)}\n"
        f"**Sources Analyzed**: {len(page_texts)} web pages{doc_info} ({len(target_urls)} URLs searched)\n\n"
        f"{synthesized_summary[:1800]}\n"
        f"{chart_embed}"
        f"{pdf_msg}"
    )


async def _auto_extract_chart(topic: str, text: str) -> str:
    """Attempt to extract numbers & categories from research text to auto-render a chart."""
    # Look for category: number patterns (e.g. "Revenue: $15M", "Users: 5000", "2023: 85%")
    matches = re.findall(r"([A-Za-z0-9\s]{3,20})[:\s]+(\d+(?:\.\d+)?)\s*(%|\$|k|M|B|units|points)?", text)

    labels = []
    values = []

    seen = set()
    for cat, val, unit in matches:
        cat_clean = cat.strip()
        if cat_clean.lower() in ("http", "https", "page", "section", "figure", "table", "step"):
            continue
        if cat_clean not in seen and len(labels) < 6:
            try:
                v = float(val)
                if v > 0:
                    labels.append(cat_clean)
                    values.append(v)
                    seen.add(cat_clean)
            except ValueError:
                pass

    if len(labels) >= 2 and len(values) >= 2:
        return await generate_chart(
            title=f"Data Overview: {topic}",
            chart_type="bar",
            labels=labels,
            values=values,
        )

    return ""


async def research_synthesis(
    topic: str,
    extra_queries: List[str] | None = None,
    pdf_files: List[str] | None = None,
    max_sources: int = 6,
    generate_pdf_report: bool = True,
) -> str:
    """[Alias for 'deep_research'] Multi-query search aggregator, PDF parser & AI synthesis tool."""
    return await deep_research(
        topic=topic,
        extra_queries=extra_queries,
        pdf_files=pdf_files,
        max_sources=max_sources,
        generate_report_pdf=generate_pdf_report,
        create_chart=True,
    )


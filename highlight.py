"""Turn citations into highlighted document HTML.

Why this is simple and fast: the document the LLM saw was line-numbered with

    lines = docText.split("\\n")
    formatted = [f"{i+1}> {line}" for i, line in enumerate(lines)]

(see nlp_backend/.../doc_formatter/line_based_segment.py). So a citation
{"start": N, "end": M} is just a **1-based, inclusive line range** into
`docText.split("\\n")`. We map line numbers straight to list indices — no text
search, no fuzzy matching. O(cited lines) work, not O(document length).

Pipeline:
  items = [{idx, citations, color, accent}, ...]   # one per datapoint
  info  = build_highlight_model(text, items)        # per-line render model
  html  = render_doc_html(info)                      # escaped HTML

Anchors (scroll targets), rendered as empty <span id=...> inside a line:
  cite-{i}-{j}  -> first line of datapoint i's j-th citation  (a cite pill links here)
  dp-{i}        -> datapoint i's earliest cited line          (the 📍 locate link)
A line can host several anchors, so they are spans, not the line's own id.
"""
from __future__ import annotations

import html
from typing import Iterable, List, Optional


def _line_range(c: dict, n_lines: int) -> Optional[tuple]:
    """0-based inclusive (lo, hi) from one 1-based citation, clamped; None if invalid."""
    if not isinstance(c, dict):
        return None
    try:
        start = int(c["start"])
        end = int(c["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if end < start:                   # tolerate swapped bounds
        start, end = end, start
    lo = max(0, start - 1)            # 1-based -> 0-based
    hi = min(n_lines - 1, end - 1)
    return (lo, hi) if lo <= hi else None


def build_highlight_model(doc_text: str, items: Iterable[dict]) -> List[dict]:
    """Build a per-line render model from datapoint highlight `items`.

    Later items win the background color on overlap. Each citation places a
    `cite-{i}-{j}` anchor + its `L12–15` label on its first line; each datapoint
    places a `dp-{i}` anchor on its earliest cited line."""
    lines = doc_text.split("\n")
    n = len(lines)
    info = [{"text": ln, "color": None, "tags": [], "anchors": []} for ln in lines]
    for item in items:
        i = item.get("idx", 0)
        ns = item.get("ns", "")  # anchor namespace, e.g. "m-"/"b-" on the compare page
        color = item.get("color")
        accent = item.get("accent", color)
        earliest: Optional[int] = None
        for j, c in enumerate(item.get("citations") or []):
            rng = _line_range(c, n)
            if rng is None:
                continue
            lo, hi = rng
            for k in range(lo, hi + 1):
                info[k]["color"] = color
            s1, e1 = lo + 1, hi + 1
            label = f"L{s1}" if s1 == e1 else f"L{s1}–{e1}"
            info[lo]["tags"].append((label, accent))
            info[lo]["anchors"].append(f"cite-{ns}{i}-{j}")
            if earliest is None or lo < earliest:
                earliest = lo
        if earliest is not None:
            info[earliest]["anchors"].append(f"dp-{ns}{i}")
    return info


def render_doc_html(info: List[dict]) -> str:
    """One <div> per line: a right-aligned line-number gutter + the line text.
    Cited lines get a background, anchor span(s), the matching cite tag(s), and a
    left accent bar. Text is HTML-escaped so document content can't break markup."""
    out: List[str] = []
    for n, ln in enumerate(info, start=1):
        safe = html.escape(ln["text"]) if ln["text"] else "&nbsp;"
        anchors = "".join(f'<span class="cite-anchor" id="{a}"></span>' for a in ln["anchors"])
        tags = "".join(
            f'<span class="cite-tag" style="background:{c}">{html.escape(lbl)}</span>'
            for lbl, c in ln["tags"]
        )
        gutter = f'<span class="ln">{n}</span>'
        cls = "doc-line hl" if ln["color"] else "doc-line"
        style = f' style="background:{ln["color"]}"' if ln["color"] else ""
        out.append(
            f'<div class="{cls}"{style}>{gutter}'
            f'<span class="lt">{anchors}{tags}{safe}</span></div>'
        )
    return "".join(out)

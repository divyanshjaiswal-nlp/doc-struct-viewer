"""
An oncology-history summary beside the merged date-anchor index, in ONE standalone page.

The summary is prose written by L1; the right pane is the merged doc-to-struct output,
already collapsed to one entry per date. So the comparison this page draws is: for every
date the summary asserts, is there anything in the anchor index on that date?

Every date in the summary is marked, at whatever granularity it was written -- a year, a
year and month, or a full date. Each one is then looked up in the merged index, exactly
first and then by granularity, using the SAME cascade the doc-to-struct plate uses so the
two pages never disagree about what counts as a match.

A matched date carries a COLOUR, and its group in the merged index carries the same one, so
the pair is visible without clicking anything. The colour also runs across the clause the
date owns -- from the date up to the next date or the start of the next sentence -- which is
the text being compared against that date's entries. A date that reaches nothing is amber:
the summary asserts it and the index has nothing on that day.

Both panes are in one page because a click has to scroll the other pane, and a link in
Streamlit's own document cannot reach inside a components.html iframe.
"""
from __future__ import annotations

import html
import re

from date_text import find_dates
# `colour_for` is the palette the document plates cycle, reused so a colour means the same
# kind of thing across the app
from line_highlight import PAGE_CSS, PAGE_JS, colour_for, doc_open

EXTRA_CSS = """
/* ── the summary as prose ─────────────────────────────────────────────────── */
/* wider than half: it is paragraphs, and the right pane is short lines */
#summarypane { flex: 1 1 56%; }
.blk {
  margin: .6rem 0 .25rem; font-size: .62rem; font-weight: 700; opacity: .62;
  text-transform: uppercase; letter-spacing: .07em;
}
.prose {
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: .86rem; line-height: 1.68;
  white-space: pre-wrap; word-break: break-word;
}

/* ── the clause a date owns ───────────────────────────────────────────────── */
/* A faint wash of the date's own colour, so you can see how far its statement reaches
   without the prose becoming unreadable. box-decoration-break keeps the rounded ends on
   every line of a run that wraps, instead of only the first. */
.run {
  border-radius: .25rem; padding: .06rem 0;
  box-decoration-break: clone; -webkit-box-decoration-break: clone;
}
.run.miss { background: var(--miss-soft); }

/* ── the date itself ──────────────────────────────────────────────────────── */
/* A date with no key wears the same red the grounding judge's rejections wear elsewhere in
   the app -- it is the same kind of finding, and it must not be confused with a MATCHED
   date, whose colour comes from the palette. The palette's first entry is amber, so amber
   is not available to mean "unsupported" here. */
/* dark twice, for the same reason PAGE_CSS does it -- see the comment there */
:root { --miss-soft: rgba(200,45,45,.07); }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { --miss-soft: rgba(255,110,110,.09); }
}
:root[data-theme="dark"] { --miss-soft: rgba(255,110,110,.09); }
mark.dm {
  color: inherit; border-radius: 3px; padding: .02rem .22rem;
  box-decoration-break: clone; -webkit-box-decoration-break: clone;
}
/* matched: the fill and rule come inline, from the date's own colour */
mark.dm.hit { font-weight: 650; cursor: pointer; }
/* matched only at a coarser or finer granularity -- same date, different precision */
mark.dm.hit.near { font-weight: 400; }
/* nothing in the merged index on this date */
mark.dm.miss {
  background: var(--bad-bg); box-shadow: inset 0 -2px 0 var(--bad-rule);
  font-weight: 650;
}

/* ── the merged index ─────────────────────────────────────────────────────── */
/* a date a summary mention reached: its own colour, and clickable back to the mention */
.date.keyed {
  opacity: 1; cursor: pointer;
  padding: .18rem .45rem; border-left: 3px solid; border-radius: 0 .3rem .3rem 0;
}
.dp .doc {
  margin-top: .22rem; font-size: .64rem; opacity: .7;
  font-variant-numeric: tabular-nums;
}
"""

EXTRA_JS = """
function jumpToSummary(id) { jumpInto('summary', 'summarypane', id); }
"""

_RGBA = re.compile(r"rgba\(([^)]+)\)")

# where a date's clause ends: the start of the next sentence, or the next line. A period
# has to be followed by whitespace to count, which is what keeps `1.3` and `04-23-2024`
# from cutting a run short.
_BOUNDARY = re.compile(r"(?<=[.;])\s|\n")


def _tint(colour: str, alpha: float) -> str:
    """The same hue at a different weight.

    The palette gives one alpha, tuned for highlighting a line of a document. A whole clause
    of prose needs a much lighter wash than the date word sitting inside it.
    """
    match = _RGBA.match(colour)
    if not match:
        return colour
    red, green, blue = (part.strip() for part in match.group(1).split(",")[:3])
    return f"rgba({red},{green},{blue},{alpha})"


def _sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence, with the whitespace between them left out."""
    spans, cursor = [], 0

    for match in _BOUNDARY.finditer(text):
        spans.append((cursor, match.start()))
        cursor = match.end()

    spans.append((cursor, len(text)))
    return spans


def _runs(text: str, mentions: list) -> list[tuple[int, int]]:
    """
    (start, end) of the span each date colours -- its SENTENCE, not just itself.

    One date in a sentence takes the whole sentence. Several split it between them: each
    date takes the run-up from where the one before it ended, up to and including itself,
    and whatever trails the LAST date belongs to that date. So no part of a sentence
    carrying a date is left uncoloured, and where one date's statement stops and the next
    one's begins is visible.

        A cbsibc dibcn 09-08-2024, xibd icbic nhc eon 12-05-2025 oncjejcn.
        |------------ first ------|---------------- second ---------------|
    """
    runs = [(mention.start, mention.end) for mention in mentions]

    for start, end in _sentences(text):
        inside = [position for position, mention in enumerate(mentions)
                  if start <= mention.start < end]
        if not inside:
            continue

        for order, position in enumerate(inside):
            head = start if order == 0 else mentions[inside[order - 1]].end
            # never open a highlight on a space, or on the punctuation that closed the
            # previous date's clause -- `09-08-2024, xibd` starts the second run at `xibd`
            while head < len(text) and (text[head].isspace() or text[head] in ",;:-–"):
                head += 1
            tail = end if order == len(inside) - 1 else mentions[position].end
            runs[position] = (head, tail)

    return runs


def _coarser(mention_key: str, keys: set[str]) -> tuple[str | None, str | None]:
    """The nearest key ABOVE a mention -- `2025-07-28` reaching a `2025-07` key."""
    parts = mention_key.split("-")

    for size in range(len(parts) - 1, 0, -1):
        candidate = "-".join(parts[:size])
        if candidate in keys:
            return candidate, "month" if size == 2 else "year"

    return None, None


def _resolve(mentions: list, keys: set[str]) -> dict[str, tuple[list[str], str | None]]:
    """
    {mention key: (every merged key it covers, how it matched)}.

    A date written to less precision than the index covers EVERYTHING under it, not just the
    first one: `2019-06` takes both `2019-06-05` and `2019-06-23`, and a bare `2019` takes
    every key in that year. Anything else would leave the rest of a month looking unmatched
    when the summary did mention it.

    Only when nothing sits under the mention is the other direction tried -- a mention more
    precise than the index, `2025-07-28` reaching a `2025-07` key.
    """
    ordered = sorted(keys)
    resolved: dict[str, tuple[list[str], str | None]] = {}

    for mention in mentions:
        if mention.key in resolved:
            continue

        covered = [key for key in ordered
                   if key == mention.key or key.startswith(f"{mention.key}-")]

        if covered:
            resolved[mention.key] = (covered, "exact" if covered == [mention.key] else "covers")
        else:
            key, tier = _coarser(mention.key, keys)
            resolved[mention.key] = ([key], tier) if key else ([], None)

    return resolved


def _hint(mention_key: str, covered: list[str], tier: str | None) -> str:
    """The mark's tooltip -- why it is marked the way it is."""
    if not covered:
        return f"{mention_key} — no date key in the merged anchors"
    if tier == "exact":
        return f"{mention_key} — exact key in the merged anchors"
    if tier == "covers":
        if len(covered) == 1:
            return f"{mention_key} — covers {covered[0]}"
        return (f"{mention_key} — covers {len(covered)} keys, "
                f"{covered[0]} to {covered[-1]}")
    return f"nearest key: {covered[0]} (the index has this date only to the {tier})"


def _marked(text: str, mentions: list, resolved: dict, colours: dict, block: int,
            back: dict[str, str]) -> str:
    """The summary with each date's sentence washed in that date's colour, all else escaped."""
    runs = _runs(text, mentions)
    out, cursor = [], 0

    for position, mention in enumerate(mentions):
        run_start, run_end = runs[position]
        out.append(html.escape(text[cursor:run_start]))

        covered, tier = resolved[mention.key]
        dom_id = f"sum-{block}-{position}"
        hint = html.escape(_hint(mention.key, covered, tier), quote=True)

        if covered:
            # the heading of every key this mention covers jumps back to its FIRST mention
            back.setdefault(mention.key, dom_id)
            fill, accent = colours[mention.key]
            run_class, run_style = "run", f"background:{_tint(fill, .12)}"
            if tier == "exact":
                mark_class = "dm hit"
                mark_style = f"background:{fill};box-shadow:inset 0 -2px 0 {accent}"
            else:
                mark_class = "dm hit near"
                mark_style = (f"background:{_tint(fill, .18)};"
                              f"border-bottom:2px dashed {accent}")
            # the click lands on the earliest key it covers
            click = f' onclick="jumpToDate(\'{html.escape(covered[0], quote=True)}\')"'
        else:
            run_class, run_style = "run miss", ""
            mark_class, mark_style, click = "dm miss", "", ""

        style = f' style="{mark_style}"' if mark_style else ""
        mark = (f'<mark id="{dom_id}" class="{mark_class}" title="{hint}"{style}{click}>'
                f'{html.escape(mention.raw)}</mark>')

        # the sentence around the date: what leads up to it, then what trails it
        head = html.escape(text[run_start:mention.start])
        tail = html.escape(text[mention.end:run_end])

        run_style = f' style="{run_style}"' if run_style else ""
        out.append(f'<span class="{run_class}"{run_style}>{head}{mark}{tail}</span>')
        cursor = run_end

    out.append(html.escape(text[cursor:]))
    return "".join(out)


def _entry_html(entry: dict, style: str) -> str:
    """One merged entry: its text, and the document it came from when that is recorded.

    Type and date first, docId last -- the type is what tells you whether a date came off a
    progress note or a pathology report, which is usually the question.
    """
    parts = [html.escape(str(entry.get(key) or ""))
             for key in ("docType", "docDate", "docId") if entry.get(key)]
    doc = f'<div class="doc">{" &middot; ".join(parts)}</div>' if parts else ""
    return (f'<div class="dp" style="{style}">'
            f'<div class="t">{html.escape(str(entry.get("text") or ""))}</div>{doc}</div>')


def summary_anchor_page(blocks: list[tuple[str, str]], groups: list[dict],
                        dark: bool | None = None) -> tuple[str, dict]:
    """
    (standalone HTML page, what was found).

    `blocks` is [(label, summary text)] -- one per record, since an entity can hold more
    than one summary. `groups` is the merged index as
    [{key, label, entries: [{text, docId, docType, docDate}]}], already sorted.

    The returned dict carries the counts and the two lists worth reading outside the
    iframe: the summary dates that reached no key, and the keys no summary date reached.
    """
    keys = {group["key"] for group in groups}

    # resolved before anything is drawn: a colour belongs to a MENTION and is worn by every
    # key that mention covers, and what each one covers is only known once every block has
    # been scanned
    found = [(label, text, find_dates(text)) for label, text in blocks]
    resolved = _resolve([m for _, _, mentions in found for m in mentions], keys)

    # colours handed out in date order, so they run roughly in order down both panes
    colours = {key: colour_for(position)
               for position, key in enumerate(sorted(k for k, (covered, _) in resolved.items()
                                                     if covered))}

    # Which mention owns each merged key. The MOST PRECISE mention wins: where the summary
    # says both `2019` and `2019-06-05`, that key belongs to the one that names it, not to
    # the year that merely contains it.
    owner: dict[str, str] = {}
    for mention_key in sorted(resolved, key=lambda k: (-len(k), k)):
        for key in resolved[mention_key][0]:
            owner.setdefault(key, mention_key)

    back: dict[str, str] = {}
    left = []
    for block, (label, text, mentions) in enumerate(found):
        if len(found) > 1:
            left.append(f'<div class="blk">{html.escape(label)}</div>')
        left.append(f'<div class="prose">'
                    f'{_marked(text, mentions, resolved, colours, block, back)}</div>')

    # ── merged index ─────────────────────────────────────────────────────────
    right = []
    for group in groups:
        key = group["key"]
        mention_key = owner.get(key)
        colour = colours.get(mention_key) if mention_key else None

        if colour:
            fill, accent = colour
            heading = (f'<div class="date keyed" id="date-{html.escape(key, quote=True)}"'
                       f' style="background:{_tint(fill, .22)};border-left-color:{accent}"'
                       f' title="written as {html.escape(mention_key, quote=True)} in the summary"'
                       f' onclick="jumpToSummary(\'{back[mention_key]}\')">'
                       f'{html.escape(group["label"])}</div>')
            entry_style = f"border-color:{accent};background:{_tint(fill, .14)}"
        else:
            heading = (f'<div class="date" id="date-{html.escape(key, quote=True)}">'
                       f'{html.escape(group["label"])}</div>')
            entry_style = "border-color:rgba(128,128,128,.45)"

        right.append(heading)
        right += [_entry_html(entry, entry_style) for entry in group["entries"]]

    mentions_all = [(label, m) for label, _, mentions in found for m in mentions]
    tiers = [resolved[m.key][1] for _, m in mentions_all]
    entries = sum(len(group["entries"]) for group in groups)

    stats = {
        "mentions": len(mentions_all),
        "exact": sum(1 for tier in tiers if tier == "exact"),
        "near": sum(1 for tier in tiers if tier and tier != "exact"),
        "missing": sum(1 for tier in tiers if tier is None),
        "keys": len(groups),
        "entries": entries,
        "keys_hit": len(owner),
        # de-duplicated: the same unsupported date written four times is one gap
        "unmatched": sorted({(m.key, m.raw) for _, m in mentions_all
                             if not resolved[m.key][0]}),
        "unhit": [group["label"] for group in groups if group["key"] not in owner],
    }

    heading = f"{len(groups)} date(s) &middot; {entries} entr{'y' if entries == 1 else 'ies'}"
    page = (
        f"<!doctype html>{doc_open(dark)}<head><meta charset='utf-8'>"
        f"<style>{PAGE_CSS}{EXTRA_CSS}</style>"
        f"<script>{PAGE_JS}{EXTRA_JS}</script></head><body>"
        f'<div class="pane" id="summarypane" data-pane="summary">'
        f'<h4>Summary</h4>{"".join(left)}</div>'
        f'<div class="pane" id="eventspane" data-pane="events">'
        f'<h4>{heading}</h4>{"".join(right)}</div>'
        "</body></html>"
    )
    return page, stats

"""
The document and its date→events side by side, in ONE standalone HTML page.

Citations here are LINE RANGES -- `{"start": N, "end": M}`, 1-based and inclusive into
`docText.split("\\n")`, the same numbering the extractor was shown
(`line_based_segment.py`: `f"{i + 1}> {line}"`). So highlighting is exact: no text search,
no fuzzy matching, no "could not be located". That is the whole point of the citations.

Both panes live in the same page for one reason: a click has to scroll the document pane,
and a link in Streamlit's own document cannot reach an element inside a components.html
iframe. Keeping them together makes the jump a plain local scroll.

Neither pane scrolls the app: `body` is `overflow:hidden` and each pane owns its own
scrollbar. The jump sets `scrollTop` directly rather than calling scrollIntoView, which is
specified to scroll every scrollable ancestor -- including, across the iframe boundary,
the parent page.
"""
from __future__ import annotations

import html

# one colour per event, cycled; translucent so the line text stays readable in both themes
PALETTE: list[tuple[str, str]] = [
    ("rgba(255,196,0,.34)", "rgba(200,140,0,.95)"),
    ("rgba(120,170,255,.30)", "rgba(60,110,220,.95)"),
    ("rgba(110,215,150,.30)", "rgba(40,150,90,.95)"),
    ("rgba(255,140,170,.30)", "rgba(215,70,120,.95)"),
    ("rgba(190,150,255,.30)", "rgba(130,80,220,.95)"),
    ("rgba(255,170,90,.32)", "rgba(215,110,20,.95)"),
    ("rgba(105,215,215,.30)", "rgba(20,150,150,.95)"),
    ("rgba(205,205,110,.34)", "rgba(150,150,40,.95)"),
]

# Every colour that changes with the theme, in one place. Interpolated TWICE below -- see
# the comment there for why once is not enough.
_DARK_TOKENS = """
  --ink: #f0f1f3;
  --bad-rule: rgba(255,110,110,.55); --bad-bg: rgba(255,90,90,.13);
  --bad-ink: rgba(255,155,155,.95);
  --anchor-rule: rgba(150,190,255,.6); --anchor-bg: rgba(120,170,255,.18);
  --anchor-ink: rgba(160,195,255,.95);
"""

_CSS = """
:root {
  color-scheme: light dark;
  --ink: #17181a;
  --bad-rule: rgba(200,45,45,.55); --bad-bg: rgba(200,45,45,.10);
  --bad-ink: rgba(170,25,25,.95);
  --anchor-rule: rgba(60,110,220,.6); --anchor-bg: rgba(120,170,255,.16);
  --anchor-ink: rgba(40,90,200,.95);
}
/* Dark twice: once from the browser's own preference, once from the theme STAMPED on
   <html> by doc_open(). A component's iframe resolves prefers-color-scheme from the
   BROWSER, not from Streamlit's theme setting -- so with a dark app on a light OS the
   media query never fires, and this page paints near-black text onto the dark background
   showing through `background: transparent`. The stamp is the only signal that follows the
   app, and the media query is guarded so it cannot fight a light stamp. */
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { DARK_TOKENS } }
:root[data-theme="dark"] { DARK_TOKENS }

* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; background: transparent; color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .8rem; line-height: 1.5;
  display: flex; overflow: hidden; gap: .55rem;
}
/* the single-pane layout stacks its pill bar above one full-width pane */
body:has(> .bar) { flex-direction: column; gap: .35rem; }
.bar {
  flex: 0 0 auto; padding: .25rem 0 .35rem;
  border-bottom: 1px solid rgba(128,128,128,.28);
}

.pane {
  flex: 1 1 50%; min-width: 0; overflow-y: auto; overscroll-behavior: contain;
  border: 1px solid rgba(128,128,128,.28); border-radius: .5rem; padding: .5rem .6rem;
}
.pane h4 {
  margin: 0 0 .45rem; font-size: .64rem; font-weight: 700; opacity: .68;
  text-transform: uppercase; letter-spacing: .08em;
  position: sticky; top: -.5rem; padding: .4rem 0 .3rem;
  background: rgba(128,128,128,.10); backdrop-filter: blur(6px);
}

/* ── document ─────────────────────────────────────────────────────────────── */
.line { display: flex; gap: .55rem; scroll-margin-top: 2rem; }
.line .no {
  flex: 0 0 3.2ch; text-align: right; opacity: .35; user-select: none;
  font-variant-numeric: tabular-nums;
}
.line .tx { white-space: pre-wrap; word-break: break-word; flex: 1 1 auto; }
.line.hit .tx { border-radius: 3px; padding: 0 .25rem; }
/* lines behind an event the grounding judge rejected -- findable while scrolling the
   document, without touching the per-event fill colour that ties the two panes together */
.line.bad .tx { box-shadow: inset 0 -2px 0 var(--bad-rule); }

/* ── events ───────────────────────────────────────────────────────────────── */
.date { margin: .5rem 0 .3rem; font-weight: 700; font-size: .74rem; opacity: .88; }
.ev { border-left: 3px solid; padding: .3rem .5rem; margin: 0 0 .4rem; border-radius: 0 .35rem .35rem 0; }
.ev.bad { box-shadow: 0 0 0 1px var(--bad-rule); }
.ev .t { white-space: pre-wrap; word-break: break-word; }
.cites { margin-top: .25rem; }
.cite {
  display: inline-block; margin: .12rem .22rem 0 0; padding: .02rem .45rem;
  border: 1px solid; border-radius: 999px; font-size: .68rem;
  cursor: pointer; user-select: none;
}
.nocite { font-size: .68rem; opacity: .5; }

/* ── grounding verdict ────────────────────────────────────────────────────── */
.verdict {
  margin-top: .35rem; padding: .28rem .45rem; border-radius: .3rem;
  background: var(--bad-bg); border-left: 3px solid var(--bad-rule);
}
.verdict .tag {
  font-size: .6rem; font-weight: 700; letter-spacing: .07em;
  text-transform: uppercase; color: var(--bad-ink);
}
.verdict .why {
  margin-top: .18rem; font-size: .7rem; opacity: .88;
  white-space: pre-wrap; word-break: break-word;
}
.flag { color: var(--bad-ink); font-weight: 700; }

/* ── a column whose pane can be switched ──────────────────────────────────── */
.col { flex: 1 1 50%; min-width: 0; display: flex; flex-direction: column; gap: .35rem; }
.col > .pane { flex: 1 1 auto; }
.tabs { flex: 0 0 auto; display: flex; gap: .3rem; }
.tab {
  padding: .1rem .6rem; border: 1px solid rgba(128,128,128,.35); border-radius: 999px;
  font-size: .66rem; cursor: pointer; user-select: none; opacity: .55;
}
.tab.on { opacity: 1; font-weight: 700; background: rgba(128,128,128,.18); }
.hidden { display: none !important; }

/* ── doc-to-struct data points ────────────────────────────────────────────── */
.sec {
  margin: .55rem 0 .3rem; font-weight: 700; font-size: .66rem; opacity: .7;
  text-transform: uppercase; letter-spacing: .06em;
}
.dp { border-left: 3px solid; padding: .3rem .5rem; margin: 0 0 .4rem; border-radius: 0 .35rem .35rem 0; }
.dp .t { white-space: pre-wrap; word-break: break-word; }
.anchors { margin-top: .25rem; }
.anchor {
  display: inline-block; margin: .12rem .22rem 0 0; padding: .02rem .45rem;
  border: 1px solid rgba(128,128,128,.45); border-radius: .25rem; font-size: .66rem;
  font-variant-numeric: tabular-nums;
}
.noanchor { font-size: .66rem; opacity: .5; }

/* an anchor that matches a date key in the date-events output, and that key itself */
.anchor.hit {
  cursor: pointer; font-weight: 700;
  border-color: var(--anchor-rule); background: var(--anchor-bg); color: var(--anchor-ink);
}
/* matched at a coarser or finer granularity than the anchor was written */
.anchor.hit.near { font-weight: 400; border-style: dashed; }
.date.anchored {
  color: var(--anchor-ink); opacity: 1;
  border-left: 3px solid var(--anchor-rule); padding-left: .4rem;
}
"""

PAGE_CSS = _CSS.replace("DARK_TOKENS", _DARK_TOKENS)

PAGE_JS = """
function showPane(name) {
  var panes = document.querySelectorAll('[data-pane]');
  for (var i = 0; i < panes.length; i++) {
    panes[i].classList.toggle('hidden', panes[i].getAttribute('data-pane') !== name);
  }
  var tabs = document.querySelectorAll('[data-tab]');
  for (var j = 0; j < tabs.length; j++) {
    tabs[j].classList.toggle('on', tabs[j].getAttribute('data-tab') === name);
  }
}

function jumpInto(paneName, paneId, targetId) {
  var pane = document.getElementById(paneId);
  var target = document.getElementById(targetId);
  if (!pane || !target) return;
  // the pane may be the hidden half of a switchable column -- reveal it before measuring,
  // or every rect comes back zero and the scroll goes nowhere
  if (pane.classList.contains('hidden')) showPane(paneName);
  var t = target.getBoundingClientRect(), p = pane.getBoundingClientRect();
  pane.scrollTo({top: pane.scrollTop + (t.top - p.top) - (pane.clientHeight - t.height) / 2,
                 behavior: 'smooth'});
  target.animate([{filter: 'brightness(1.6)'}, {filter: 'none'}], {duration: 900});
}

function jumpTo(id)       { jumpInto('doc', 'docpane', id); }
function jumpToDate(key)  { jumpInto('events', 'eventspane', 'date-' + key); }
"""


def colour_for(index: int) -> tuple[str, str]:
    return PALETTE[index % len(PALETTE)]


def doc_open(dark: bool | None = None) -> str:
    """
    The `<html>` tag, with the APP's theme stamped on it when it is known.

    A component's iframe resolves `prefers-color-scheme` from the browser, so it does not
    see Streamlit's theme setting at all. `state.is_dark()` reads the active theme on the
    Python side and passes it here; `None` leaves the page on the media query, which is
    right for a browser whose preference matches.
    """
    if dark is None:
        return "<html>"
    return f'<html data-theme="{"dark" if dark else "light"}">'


def _spans(citations) -> list[tuple[int, int]]:
    """Well-formed (start, end) line ranges only; anything else is skipped."""
    out = []
    for citation in citations or []:
        if not isinstance(citation, dict):
            continue
        try:
            start, end = int(citation["start"]), int(citation["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if start >= 1 and end >= 1:
            out.append((min(start, end), max(start, end)))
    return out


def _render_lines(lines: list[str], events: list[dict],
                  anchors_on: bool = True) -> tuple[list[str], int]:
    """
    (one <div class="line"> per document line, how many events were located).

    `anchors_on=False` keeps the highlights but emits no jump anchors -- for a SECOND copy
    of the same document in one page. Two copies with the same anchor ids would make
    getElementById ambiguous, and every jump would land in whichever copy came first.
    """
    covering: dict[int, list[int]] = {}
    anchors: dict[int, list[str]] = {}
    flagged: set[int] = set()
    cited = 0

    for position, event in enumerate(events):
        spans = _spans(event.get("citations"))
        if spans:
            cited += 1
        for order, (start, end) in enumerate(spans):
            anchors.setdefault(start, []).append(f"cite-{position}-{order}")
            for number in range(start, min(end, len(lines)) + 1):
                covering.setdefault(number, []).append(position)
                if event.get("verdict"):
                    flagged.add(number)

    body = []
    for number, line in enumerate(lines, start=1):
        ids = "".join(f'<span id="{a}"></span>' for a in anchors.get(number, [])) if anchors_on else ""
        hits = covering.get(number)
        # innermost wins the fill; ties go to the first event, which keeps a line covered
        # by two events readable rather than muddy
        style = f' style="background:{colour_for(hits[0])[0]}"' if hits else ""
        classes = "line" + (" hit" if hits else "") + (" bad" if number in flagged else "")
        body.append(
            f'<div class="{classes}">'
            f'<span class="no">{ids}{number}</span>'
            f'<span class="tx"{style}>{html.escape(line) or "&nbsp;"}</span></div>'
        )

    return body, cited


# what the grounding judge's `unsupported` value means, spelled out
VERDICT_LABELS = {
    "event": "not written in the document",
    "date": "date misread",
    "both": "event and date unsupported",
}


def _verdict_html(verdict: dict | None) -> str:
    """The grounding judge's rejection, under the event it rejected."""
    if not verdict:
        return ""
    kind = str(verdict.get("unsupported") or "")
    label = VERDICT_LABELS.get(kind, kind or "flagged")
    reason = str(verdict.get("reason") or "")
    why = f'<div class="why">{html.escape(reason)}</div>' if reason else ""
    return (
        f'<div class="verdict"><span class="tag">&#9888; Judge: {html.escape(label)}</span>'
        f"{why}</div>"
    )


def document_only_page(doc_text: str, events: list[dict],
                       notes: list[str] | None = None,
                       dark: bool | None = None) -> tuple[str, int]:
    """
    One pane: the document with each event's CITED LINES highlighted, pills on top.

    The single-pane counterpart of document_events_page, for the L1 review page's date
    event tab where the events are already shown in the claim cards. Line ranges make this
    exact -- no text search, nothing "not located" unless the citation itself is missing.
    """
    lines = doc_text.split("\n")
    body, cited = _render_lines(lines, events)
    notes = notes or []

    pills = []
    for position, event in enumerate(events):
        spans = _spans(event.get("citations"))
        fill, accent = colour_for(position)
        label = notes[position] if position < len(notes) else f"{position + 1}"
        for order, (start, end) in enumerate(spans):
            span_text = f"{start}" if start == end else f"{start}&ndash;{end}"
            pills.append(
                f'<span class="cite" onclick="jumpTo(\'cite-{position}-{order}\')" '
                f'title="{html.escape(label)}" '
                f'style="background:{fill};border-color:{accent}">{span_text}</span>'
            )

    bar = f'<div class="bar">{"".join(pills)}</div>' if pills else ""
    return (
        f"<!doctype html>{doc_open(dark)}<head><meta charset='utf-8'>"
        f"<style>{PAGE_CSS}</style><script>{PAGE_JS}</script></head><body>"
        f'{bar}<div class="pane" id="docpane">{"".join(body)}</div>'
        "</body></html>"
    ), cited


def document_events_page(doc_text: str, events: list[dict],
                         raw_text: str | None = None,
                         dark: bool | None = None) -> tuple[str, int]:
    """
    (standalone HTML page, number of events that had at least one usable citation).

    `events` is [{date, text, citations, verdict?}] in display order; the list index picks
    the colour, so a colour means the same event in both panes. `verdict` is the grounding
    judge's rejection of that event, when it rejected it.

    `raw_text` is the document BEFORE the table pre-processing that `doc_text` has been
    through. Given one, the left side gains a tab to switch between them, so the dashes and
    stamped dates the model was shown can be compared against the note as it arrived. Both
    have the same line count, so the highlights land on the same lines in either.
    """
    lines = doc_text.split("\n")
    body, cited = _render_lines(lines, events)

    # ── events pane ──────────────────────────────────────────────────────────
    panel, last_date = [], None
    for position, event in enumerate(events):
        date = event.get("date") or ""
        if date != last_date:
            panel.append(f'<div class="date">{html.escape(date)}</div>')
            last_date = date

        fill, accent = colour_for(position)
        spans = _spans(event.get("citations"))
        pills = "".join(
            f'<span class="cite" onclick="jumpTo(\'cite-{position}-{order}\')" '
            f'style="background:{fill};border-color:{accent}">'
            f'{start}{"" if start == end else "&ndash;" + str(end)}</span>'
            for order, (start, end) in enumerate(spans)
        ) or '<span class="nocite">no citation</span>'

        verdict = event.get("verdict")
        panel.append(
            f'<div class="ev{" bad" if verdict else ""}" '
            f'style="border-color:{accent};background:{fill}">'
            f'<div class="t">{html.escape(str(event.get("text") or ""))}</div>'
            f'<div class="cites">{pills}</div>{_verdict_html(verdict)}</div>'
        )

    rejected = sum(1 for event in events if event.get("verdict"))
    heading = f"{len(events)} event(s)" + (
        f' &middot; <span class="flag">{rejected} flagged</span>' if rejected else ""
    )

    if raw_text is None or raw_text == doc_text:
        left = f'<div class="pane" id="docpane"><h4>Document</h4>{"".join(body)}</div>'
        right = f'<div class="pane"><h4>{heading}</h4>{"".join(panel)}</div>'
    else:
        # a second copy of the same document, so no anchors in it -- see _render_lines
        raw_body, _ = _render_lines(raw_text.split("\n"), events, anchors_on=False)
        left = (
            '<div class="col">'
            '<div class="tabs">'
            '<span class="tab on" data-tab="doc" onclick="showPane(\'doc\')">Document</span>'
            '<span class="tab" data-tab="raw" onclick="showPane(\'raw\')">Raw</span>'
            "</div>"
            f'<div class="pane" id="docpane" data-pane="doc">{"".join(body)}</div>'
            f'<div class="pane hidden" data-pane="raw">{"".join(raw_body)}</div>'
            "</div>"
        )
        # the hidden tab row keeps the right pane starting on the same line as the left
        right = (
            '<div class="col">'
            '<div class="tabs"><span class="tab" style="visibility:hidden">&nbsp;</span></div>'
            f'<div class="pane"><h4>{heading}</h4>{"".join(panel)}</div>'
            "</div>"
        )

    page = (
        f"<!doctype html>{doc_open(dark)}<head><meta charset='utf-8'>"
        f"<style>{PAGE_CSS}</style><script>{PAGE_JS}</script></head><body>"
        f"{left}{right}"
        "</body></html>"
    )
    return page, cited


def _match_date(anchor: str, keys: set[str]) -> tuple[str, str] | tuple[None, None]:
    """
    (the date key this anchor points at, how it matched) -- or (None, None).

    Tried in sequence, the same cascade the L1 judge uses: the key exactly as written, then
    the anchor's coarser forms, then a finer key sitting underneath it. So an anchor of
    `2025-07-28` reaches a `2025-07` key, and a `2025-07` anchor reaches the earliest
    `2025-07-..` key -- the granularities differ but the date is the same one.
    """
    if anchor in keys:
        return anchor, "exact"

    parts = anchor.split("-")
    for size in range(len(parts) - 1, 0, -1):
        coarser = "-".join(parts[:size])
        if coarser in keys:
            return coarser, "month" if size == 2 else "year"

    finer = sorted(key for key in keys if key.startswith(f"{anchor}-"))
    return (finer[0], "finer") if finer else (None, None)


def _events_panel(events: list[dict], anchored: frozenset[str] = frozenset()) -> str:
    """The date events as a read-only reference list, grouped by date.

    Each date heading carries an id so a data point's date anchor can scroll to it, and the
    headings in `anchored` are marked, so the dates the doc-to-struct output actually points
    at stand out from the ones it does not.

    The events' own line ranges are static chips: on this page the document's anchors belong
    to the data points, so an event's range has nothing to jump to.
    """
    panel, last_date = [], None

    for event in events:
        date = event.get("date") or ""
        if date != last_date:
            classes = "date anchored" if date in anchored else "date"
            panel.append(f'<div class="{classes}" id="date-{html.escape(date)}">'
                         f'{html.escape(date)}</div>')
            last_date = date

        chips = "".join(
            f'<span class="anchor">{start}{"" if start == end else "&ndash;" + str(end)}</span>'
            for start, end in _spans(event.get("citations"))
        ) or '<span class="noanchor">no citation</span>'

        panel.append(
            '<div class="dp" style="border-color:rgba(128,128,128,.45)">'
            f'<div class="t">{html.escape(str(event.get("text") or ""))}</div>'
            f'<div class="anchors">{chips}</div></div>'
        )

    return "".join(panel)


def document_struct_page(doc_text: str, events: list[dict], struct: dict,
                         dark: bool | None = None) -> tuple[str, int]:
    """
    (standalone HTML page, number of data points carrying a usable citation).

    Left column switches between the DOCUMENT and the DATE EVENTS; the right column holds
    the doc-to-struct output for the same document. `struct` is {section: [data_point, ...]}.

    The document's highlights and anchors belong to the DATA POINTS here, not to the date
    events -- the plate above already pairs the note with those, and colouring both sets at
    once makes neither readable. Clicking a data point's line range reveals the document
    pane before scrolling, so switching away never hides what you just asked to see.
    """
    flat = [(section, point)
            for section, points in struct.items() if isinstance(points, list)
            for point in points if isinstance(point, dict)]

    lines = doc_text.split("\n")
    body, cited = _render_lines(lines, [point for _, point in flat])

    # Resolve each anchor to a date key, exact first and then by granularity. A matched
    # anchor is clickable and its key is marked in the events pane; an anchor that reaches
    # no key at all stays a plain chip, which is itself the finding worth seeing.
    date_keys = {str(event.get("date") or "") for event in events}
    matches = {}
    for _, point in flat:
        for anchor in point.get("date_anchors") or []:
            anchor = str(anchor)
            if anchor not in matches:
                matches[anchor] = _match_date(anchor, date_keys)

    anchored = frozenset(key for key, _ in matches.values() if key)

    # ── data points, grouped by their section ────────────────────────────────
    panel, last_section = [], None
    for position, (section, point) in enumerate(flat):
        if section != last_section:
            panel.append(f'<div class="sec">{html.escape(section)}</div>')
            last_section = section

        fill, accent = colour_for(position)
        pills = "".join(
            f'<span class="cite" onclick="jumpTo(\'cite-{position}-{order}\')" '
            f'style="background:{fill};border-color:{accent}">'
            f'{start}{"" if start == end else "&ndash;" + str(end)}</span>'
            for order, (start, end) in enumerate(_spans(point.get("citations")))
        ) or '<span class="nocite">no citation</span>'

        chips = []
        for anchor in point.get("date_anchors") or []:
            anchor = html.escape(str(anchor))
            key, tier = matches.get(html.unescape(anchor), (None, None))
            if not key:
                chips.append(f'<span class="anchor" '
                             f'title="no date key in the date-events output">{anchor}</span>')
                continue
            near = "" if tier == "exact" else " near"
            hint = "exact date key" if tier == "exact" else f"nearest key: {key} ({tier})"
            chips.append(f'<span class="anchor hit{near}" '
                         f'onclick="jumpToDate(\'{html.escape(key)}\')" '
                         f'title="{hint}">{anchor}</span>')
        anchor_chips = "".join(chips) or '<span class="noanchor">no date anchor</span>'

        panel.append(
            f'<div class="dp" style="border-color:{accent};background:{fill}">'
            f'<div class="t">{html.escape(str(point.get("text") or ""))}</div>'
            f'<div class="cites">{pills}</div>'
            f'<div class="anchors">{anchor_chips}</div></div>'
        )

    return (
        f"<!doctype html>{doc_open(dark)}<head><meta charset='utf-8'>"
        f"<style>{PAGE_CSS}</style><script>{PAGE_JS}</script></head><body>"
        '<div class="col">'
        '<div class="tabs">'
        '<span class="tab on" data-tab="doc" onclick="showPane(\'doc\')">Document</span>'
        '<span class="tab" data-tab="events" onclick="showPane(\'events\')">Date events</span>'
        "</div>"
        f'<div class="pane" id="docpane" data-pane="doc">{"".join(body)}</div>'
        f'<div class="pane hidden" id="eventspane" data-pane="events">'
        f'{_events_panel(events, anchored)}</div>'
        "</div>"
        # the right column carries a hidden copy of the tab bar, so its pane starts on the
        # same line as the left one instead of riding up by the height of the tabs
        '<div class="col">'
        '<div class="tabs"><span class="tab" style="visibility:hidden">&nbsp;</span></div>'
        f'<div class="pane"><h4>{len(flat)} data point(s)</h4>{"".join(panel)}</div>'
        "</div>"
        "</body></html>"
    ), cited

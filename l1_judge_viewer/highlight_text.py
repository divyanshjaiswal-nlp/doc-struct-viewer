"""
Mark citation spans inside a document's raw text.

Not the same job as the repo's top-level highlight.py: that one treats a citation's
`start`/`end` as 1-based LINE numbers, because its pipeline fed the model a
line-numbered document. L1 citations come from format_citation() instead, carrying
character offsets (`startIdx`, `endIdx`) plus the verbatim `text`.

Locating a citation is tried cheapest-first, and each hit records HOW it was found so
the UI can say whether a highlight is trustworthy:

    offset      startIdx/endIdx, accepted only when the slice really is the citation
    exact       the citation text appears verbatim
    whitespace  appears once newlines/tabs/runs of spaces are collapsed and case is
                ignored -- by far the most common reason an "exact" search fails, since
                citations are assembled with single spaces while notes wrap and indent
    fuzzy       best partial alignment above FUZZY_FLOOR (rapidfuzz when installed,
                a word-anchored difflib search otherwise)
    approx      above LOOSE_FLOOR only -- the right REGION, not a match. Judge citations
                come from the date->events index, which is written *about* the document
                rather than quoted from it, so paraphrases land here. Drawn unfilled with
                a dotted rule so it can never read as "the citation appears here".
    prefix      the citation's opening run matched; the span is extended to its length

Anything still unfound is reported to the caller rather than quietly dropped.
"""
from __future__ import annotations

import html

# Similarity floor, 0-100. Judge citations come from the date->events index, which is
# LLM-written *about* the document rather than quoted from it, so they are often
# paraphrases -- the floor has to be lower than it would be for verbatim L1 citations.
FUZZY_FLOOR = 72.0
# Below the fuzzy floor but still the best region in the document. Measured paraphrases
# of the same sentence score 47-57, so this tier exists to point you at the right part of
# the note -- it is a navigation aid, drawn deliberately faint, never a claim of a match.
LOOSE_FLOOR = 45.0
PREFIX_CHARS = 60         # how much of the citation the prefix fallback anchors on
ANCHOR_WORDS = 4          # distinctive words the pure-python fuzzy search anchors on
MAX_ANCHOR_HITS = 25      # per word, so a common token cannot blow up the search

# One colour per citation, cycled. Translucent so the text stays readable in both
# themes; the accent is the same hue at full strength, for borders and pills.
PALETTE: list[tuple[str, str]] = [
    ("rgba(255,196,0,.38)", "rgba(200,140,0,.95)"),      # amber
    ("rgba(120,170,255,.34)", "rgba(60,110,220,.95)"),   # blue
    ("rgba(110,215,150,.34)", "rgba(40,150,90,.95)"),    # green
    ("rgba(255,140,170,.34)", "rgba(215,70,120,.95)"),   # pink
    ("rgba(190,150,255,.34)", "rgba(130,80,220,.95)"),   # violet
    ("rgba(255,170,90,.36)", "rgba(215,110,20,.95)"),    # orange
    ("rgba(105,215,215,.34)", "rgba(20,150,150,.95)"),   # teal
    ("rgba(205,205,110,.38)", "rgba(150,150,40,.95)"),   # olive
]


def colour_for(number: int) -> tuple[str, str]:
    """(background, accent) for a 1-based citation number."""
    return PALETTE[(number - 1) % len(PALETTE)]


# The page is rendered in an IFRAME (streamlit.components.v1.html), not inline.
#
# Inline HTML shares the app's document, so clicking an `#id` link made the browser
# scroll every scrollable ancestor needed to reveal the target -- including the window,
# which is why the whole page jumped. An iframe is its own scroll context: the jump stays
# inside it, and it always has a scrollbar of its own. The pills must therefore live in
# the iframe too, since a link in the parent document cannot reach an anchor inside one.
PAGE_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0; background: transparent; color: #17181a;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .82rem; line-height: 1.55;
  /* the document never scrolls -- .scroll does, so nothing can chain outward */
  display: flex; flex-direction: column; overflow: hidden;
}
@media (prefers-color-scheme: dark) { body { color: #e6e7e9; } }
.bar {
  flex: 0 0 auto; padding: .3rem 0 .4rem;
  background: rgba(128,128,128,.10);
  border-bottom: 1px solid rgba(128,128,128,.28);
}
/* flex:1 rather than a fixed height, so the pane fills whatever is left after the pill
   bar -- which wraps to two lines when a document has many citations */
.scroll {
  flex: 1 1 auto; overflow-y: auto; overscroll-behavior: contain;
  padding: .55rem .1rem 1.2rem;
}
.doc { white-space: pre-wrap; word-break: break-word; }
a.pill {
  display: inline-block; margin: 0 .22rem .18rem 0; padding: .05rem .5rem;
  border-radius: 999px; text-decoration: none; color: inherit; font-size: .74rem;
  cursor: pointer; user-select: none;
}
a.pill:hover { filter: brightness(1.15); }
span.anchor { display: inline-block; width: 0; }
"""

# Two things this script exists to avoid.
#
# href="#cite-N" does not work: components.html renders a `srcdoc` iframe, and a srcdoc
# document inherits the PARENT's base URL, so the fragment resolves against the Streamlit
# app's own URL and the iframe navigates there -- loading a copy of the whole app inside
# the panel.
#
# scrollIntoView does not work either: it is specified to scroll EVERY scrollable
# ancestor, and the containing-block chain runs through the iframe's owner element into
# the parent document -- so the app page scrolled as well, to bring the iframe into view.
#
# Setting scrollTop on the pane touches that one element and nothing else. Offsets come
# from getBoundingClientRect so the maths holds however the marks are nested.
PAGE_JS = """
function jumpTo(id) {
  var target = document.getElementById(id);
  var pane = document.querySelector('.scroll');
  if (!target || !pane) return;
  var t = target.getBoundingClientRect(), p = pane.getBoundingClientRect();
  var centred = (t.top - p.top) - (pane.clientHeight - t.height) / 2;
  pane.scrollTo({top: pane.scrollTop + centred, behavior: 'smooth'});
}
"""
# empty scroll target; needs a box of its own to honour scroll-margin
def pill_html(number: int, method: str, origin: str = "") -> str:
    """A jump link in the citation's own colour, so the pills act as the legend."""
    background, accent = colour_for(number)
    fill = "transparent" if method == "approx" else background
    tip = html.escape(f"{origin} · matched by {method}" if origin else f"matched by {method}")
    suffix = "" if method in EXACT_METHODS else ("&nbsp;≈" if method == "approx" else "&nbsp;~")
    return (
        f'<a class="pill" onclick="jumpTo(\'cite-{number}\')" title="{tip}" '
        f'style="border:1px solid {accent};background:{fill}">{number}{suffix}</a>'
    )

EXACT_METHODS = {"offset", "exact"}


def normalise(text: str) -> tuple[str, list[int]]:
    """
    Lowercased, whitespace-collapsed copy of `text` plus a map back to its own indices.

    index_map[i] is the position in the original of normalised character i, so a match
    found in the normalised copy can be reported as a span in the real text.
    """
    out: list[str] = []
    index_map: list[int] = []
    in_space = False

    for position, char in enumerate(text):
        if char.isspace():
            if not in_space and out:
                out.append(" ")
                index_map.append(position)
            in_space = True
        else:
            out.append(char.lower())
            index_map.append(position)
            in_space = False

    return "".join(out), index_map


def _span_from_norm(index_map: list[int], start: int, length: int) -> tuple[int, int] | None:
    """A span in the normalised copy -> a span in the original text."""
    if length <= 0 or start < 0 or start + length > len(index_map):
        return None
    return index_map[start], index_map[start + length - 1] + 1


def _fuzzy(
    needle: str, haystack: str, index_map: list[int]
) -> tuple[tuple[int, int], float] | None:
    """(span, score) for the best alignment of `needle` inside `haystack`, normalised."""
    try:
        from rapidfuzz.fuzz import partial_ratio_alignment
    except ModuleNotFoundError:
        return _fuzzy_pure(needle, haystack, index_map)

    alignment = partial_ratio_alignment(needle, haystack)
    if alignment is None:
        return None
    span = _span_from_norm(index_map, alignment.dest_start,
                           alignment.dest_end - alignment.dest_start)
    return (span, alignment.score) if span else None


def _fuzzy_pure(
    needle: str, haystack: str, index_map: list[int]
) -> tuple[tuple[int, int], float] | None:
    """
    Fuzzy search without rapidfuzz: anchor on the needle's most distinctive words, then
    score a needle-sized window around each hit with difflib.

    difflib over a whole document would be far too slow, so the anchors are what keep it
    cheap -- only a handful of windows are ever compared.
    """
    from difflib import SequenceMatcher

    words = sorted({w for w in needle.split() if len(w) >= 5}, key=len, reverse=True)
    if not words:
        return None

    reach = max(len(needle), 40)
    best: tuple[int, int] | None = None
    best_score = 0.0

    for word in words[:ANCHOR_WORDS]:
        cursor, hits = 0, 0
        while hits < MAX_ANCHOR_HITS:
            at = haystack.find(word, cursor)
            if at == -1:
                break
            cursor, hits = at + 1, hits + 1

            left = max(0, at - reach)
            window = haystack[left:min(len(haystack), at + reach)]
            matcher = SequenceMatcher(None, window, needle, autojunk=False)
            score = matcher.ratio() * 100
            if score <= best_score:
                continue

            blocks = [b for b in matcher.get_matching_blocks() if b.size]
            if blocks:
                best_score = score
                best = (left + blocks[0].a, left + blocks[-1].a + blocks[-1].size)

    if not best:
        return None
    span = _span_from_norm(index_map, best[0], best[1] - best[0])
    return (span, best_score) if span else None


def _locate(
    doc_text: str, hay: str, index_map: list[int], citation: dict
) -> tuple[int, int, str] | None:
    """One citation -> (start, end, method) in doc_text, or None if never found."""
    if not isinstance(citation, dict):
        return None

    text = (citation.get("text") or "").strip()
    start, end = citation.get("startIdx"), citation.get("endIdx")

    # 1. offsets, but only when the slice they point at really is this citation
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(doc_text):
        if not text or doc_text[start:end].strip() == text:
            return start, end, "offset"

    if not text:
        return None

    # 2. verbatim
    at = doc_text.find(text)
    if at != -1:
        return at, at + len(text), "exact"

    # 3. whitespace- and case-insensitive
    needle, _ = normalise(text)
    if not needle:
        return None

    at = hay.find(needle)
    if at != -1:
        span = _span_from_norm(index_map, at, len(needle))
        if span:
            return span[0], span[1], "whitespace"

    # 4. similarity -- two tiers, because a paraphrase can never clear the fuzzy floor
    hit = _fuzzy(needle, hay, index_map)
    if hit:
        (left, right), score = hit
        if score >= FUZZY_FLOOR:
            return left, right, "fuzzy"
        if score >= LOOSE_FLOOR:
            return left, right, "approx"

    # 5. anchor on the opening run, then extend to the citation's length
    prefix = needle[:PREFIX_CHARS]
    if len(prefix) >= 20:
        at = hay.find(prefix)
        if at != -1:
            span = _span_from_norm(index_map, at, min(len(needle), len(index_map) - at))
            if span:
                return span[0], span[1], "prefix"

    return None


def _segment_attrs(covering: list[tuple[int, int, int, str]]) -> str:
    """
    Style one elementary segment from the citations covering it.

    The SHORTEST covering span sets the background, so a narrow citation nested inside a
    wide one shows its own colour rather than being swallowed. When more than one covers
    the segment, the widest one is drawn as an inset border around it -- that pairing is
    what makes "which is long, which is short" readable at a glance. An approximate
    match (fuzzy / prefix) is underlined dashed so it stays distinguishable from a
    certain one.
    """
    inner = min(covering, key=lambda span: span[1] - span[0])
    background, accent = colour_for(inner[2])

    # `approx` is a region hint, not a match: no fill, just a dotted rule underneath, so
    # it can never be mistaken for the citation actually appearing here.
    if inner[3] == "approx":
        style = ("background:transparent;color:inherit;"
                 f"text-decoration:underline dotted {accent};text-underline-offset:3px;")
    else:
        style = f"background:{background};color:inherit;border-radius:3px;"
        if any(span[3] not in EXACT_METHODS for span in covering):
            style += f"text-decoration:underline dashed {accent};text-underline-offset:2px;"

    if len(covering) > 1:
        outer = max(covering, key=lambda span: span[1] - span[0])
        style += f"box-shadow:inset 0 0 0 1.5px {colour_for(outer[2])[1]};"

    label = ", ".join(f"{span[2]} ({span[3]})" for span in covering)
    return f'title="citation {label}" style="{style}"'


def document_page(doc_text: str, citations: list[dict],
                  notes: list[str] | None = None) -> tuple[str, list[tuple[int, str]]]:
    """
    A COMPLETE standalone HTML page for one document, plus [(citation number, method)].

    Meant for streamlit.components.v1.html -- see PAGE_CSS for why it is an iframe and
    not inline HTML. The sticky bar of jump pills is part of the page because a link in
    the parent document cannot reach an anchor inside an iframe.

    `notes[i]` is an optional label for citation i+1, used in the pill tooltips. Numbers
    are 1-based; anything absent from the returned list could not be located at all.
    """
    hay, index_map = normalise(doc_text)

    found = []
    for number, citation in enumerate(citations or [], start=1):
        hit = _locate(doc_text, hay, index_map, citation)
        if hit:
            found.append((hit[0], hit[1], number, hit[2]))

    # Nothing is dropped for overlapping: the text is split at every span boundary, so a
    # short citation sitting inside a long one stays visible as its own colour band.
    found.sort()
    edges = {0, len(doc_text)}
    for start, end, _, _ in found:
        edges.add(start)
        edges.add(end)
    points = sorted(edges)

    anchors_at: dict[int, list[int]] = {}
    for start, _, number, _ in found:
        anchors_at.setdefault(start, []).append(number)

    parts = []
    for left, right in zip(points, points[1:]):
        anchors = "".join(
            f'<span class="anchor" id="cite-{n}"></span>' for n in anchors_at.get(left, [])
        )
        chunk = html.escape(doc_text[left:right])

        covering = [span for span in found if span[0] <= left and right <= span[1]]
        if not covering:
            parts.append(anchors + chunk)
            continue

        parts.append(f"{anchors}<mark {_segment_attrs(covering)}>{chunk}</mark>")

    located = [(number, method) for _, _, number, method in found]
    notes = notes or []
    pills = " ".join(
        pill_html(number, method, notes[number - 1] if number <= len(notes) else "")
        for number, method in located
    )

    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<style>{PAGE_CSS}</style><script>{PAGE_JS}</script></head><body>"
        + (f'<div class="bar">{pills}</div>' if pills else "")
        + f'<div class="scroll"><div class="doc">{"".join(parts)}</div></div>'
        "</body></html>"
    )
    return page, located

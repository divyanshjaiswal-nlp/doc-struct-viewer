"""
Cosmetic layer for the viewer -- CSS plus the two small HTML builders that use it.

Everything here is purely visual. The Streamlit selectors are matched on `data-testid`
attributes, which are the most stable handles available, but if a future version renames
one the app keeps working and simply looks plainer.

Colour is only ever a translucent tint over the theme's own background, with
`color: inherit` -- the hue comes from the fill and border, never from the text, so a
chip or highlight reads correctly in light and dark without hardcoding ink.
"""
from __future__ import annotations

import html

CSS = """
<style>
/* ── page rhythm ─────────────────────────────────────────────────────────── */
.block-container { padding-top: 1.7rem; padding-bottom: 3rem; }
h1, h2, h3, h4, h5 { letter-spacing: -.012em; }

/* ── app header ──────────────────────────────────────────────────────────── */
.app-head {
  display: flex; align-items: baseline; gap: .6rem;
  margin: 0 0 .9rem; padding-bottom: .55rem;
  border-bottom: 1px solid rgba(128,128,128,.22);
}
.app-head .title { font-size: 1.02rem; font-weight: 700; letter-spacing: -.015em; }
.app-head .sub { font-size: .74rem; opacity: .55; }

/* ── section label: small caps with a hairline running to the edge ───────── */
.sec {
  display: flex; align-items: center; gap: .55rem;
  text-transform: uppercase; letter-spacing: .09em;
  font-size: .67rem; font-weight: 700; opacity: .58;
  margin: .15rem 0 .55rem;
}
.sec::after { content: ""; flex: 1; height: 1px; background: currentColor; opacity: .3; }

/* ── breadcrumb under the control row ────────────────────────────────────── */
.crumb { font-size: .74rem; opacity: .6; margin: -.35rem 0 1rem; }
.crumb b { font-weight: 600; opacity: .9; }
.crumb .path {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .7rem; opacity: .7;
}

/* ── record fields as a plain two-column table ───────────────────────────── */
table.fields { width: 100%; border-collapse: collapse; font-size: .84rem; margin: .1rem 0 .8rem; }
table.fields td {
  padding: .24rem .5rem .24rem 0; vertical-align: top;
  border-bottom: 1px solid rgba(128,128,128,.16);
}
table.fields td.k { width: 40%; font-weight: 600; opacity: .78; }
table.fields tr:last-child td { border-bottom: none; }

/* ── L1's own reasoning ──────────────────────────────────────────────────── */
/* Its own scroll pane, sized from the viewport so it reaches the bottom of the screen on
   a laptop and on a large monitor alike. The subtracted offset is roughly everything
   above it (header, control row, breadcrumb, tab bar); dvh is preferred where supported
   because mobile browsers shrink the visible area as toolbars appear.
   overscroll-behavior: contain is what stops the page taking over once this pane hits
   its end -- without it the scroll chains outward and the whole page moves. */
.l1reason {
  font-size: .92rem; line-height: 1.62;
  height: calc(100vh - 21rem);
  height: calc(100dvh - 21rem);
  min-height: 15rem;
  overflow-y: auto;
  overscroll-behavior: contain;
  border: 1px solid rgba(128,128,128,.22); border-radius: .5rem;
  padding: .6rem .7rem .2rem;
}
.l1reason .item { margin-bottom: .7rem; }
.l1reason .k {
  display: block; font-size: .62rem; font-weight: 700;
  text-transform: uppercase; letter-spacing: .07em; opacity: .55; margin-bottom: .15rem;
}
.l1reason .t {
  background: rgba(128,128,128,.07); border-left: 3px solid rgba(128,128,128,.35);
  border-radius: 0 .4rem .4rem 0; padding: .45rem .6rem; white-space: pre-wrap;
}

/* ── claim card: ONE html block, so nothing sits between its rows ────────── */
/* Built as a single element on purpose. Splitting it across st.markdown + st.html put a
   Streamlit element gap between Doc ID and Reasoning, and gave the two halves different
   font sizes. One block means one font size and margins we control. */
.claim {
  border: 1px solid rgba(128,128,128,.25); border-radius: .65rem;
  padding: .55rem .7rem .6rem; margin: 0 0 .5rem;
  font-size: .85rem; line-height: 1.55;
}
.claim .head { display: flex; align-items: center; gap: .5rem; margin-bottom: .3rem; }
.claim .role { font-weight: 650; font-size: .92rem; }
.claim .row { margin-top: .12rem; }
.claim .label { font-weight: 600; }
.claim .aside { opacity: .55; }
/* Values are tinted chips, not coloured text -- a fill with inherited ink reads
   correctly whichever theme is active, where a hardcoded text colour would not. */
.claim .v { padding: .02rem .36rem; border-radius: .3rem; background: rgba(128,128,128,.12); }
.claim .v.date { background: rgba(90,140,230,.20); }
.claim .v.doc  { background: rgba(150,110,220,.17); }
.claim .v.null { background: none; opacity: .5; font-style: italic; }

/* ── the Reasoning field: one label, two highlighted values ──────────────── */
.rblock { margin: .22rem 0 0; }
.rblock .line { margin-top: .2rem; }
.rblock mark {
  color: inherit; border-radius: 3px; padding: .04rem .3rem; white-space: pre-wrap;
  /* so a wrapped highlight gets rounded ends on every line, not just the first */
  box-decoration-break: clone; -webkit-box-decoration-break: clone;
}
/* the judge's own words */
.rblock mark.reason {
  background: rgba(120,170,255,.26); box-shadow: inset 0 -2px 0 rgba(70,120,220,.5);
}
/* the event text it matched -- same amber it wears in the document panel */
.rblock mark.quote {
  background: rgba(255,196,0,.38); box-shadow: inset 0 -2px 0 rgba(255,150,0,.55);
}

/* ── claim card ──────────────────────────────────────────────────────────── */
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: .65rem; }

/* ── widgets: smaller labels, tighter tabs and expanders ─────────────────── */
label[data-testid="stWidgetLabel"] p { font-size: .74rem; opacity: .75; }
button[data-baseweb="tab"] { padding-top: .35rem; padding-bottom: .35rem; }
div[data-testid="stExpander"] summary { font-size: .82rem; }
div[data-testid="stExpander"] summary p { font-size: .82rem; }

/* st.text carries quoted source material -- matched event text and citation text. It
   must stay readable, so it sits at body size with a left rule marking it as a quote
   rather than being shrunk into a caption. */
div[data-testid="stText"] {
  font-size: .88rem; line-height: 1.55;
  white-space: pre-wrap; word-break: break-word;
  background: rgba(128,128,128,.07);
  border-left: 3px solid rgba(128,128,128,.4);
  border-radius: 0 .4rem .4rem 0;
  padding: .5rem .7rem;
}
</style>
"""


def header(title: str, subtitle: str = "") -> str:
    """The slim app header rule."""
    sub = f'<span class="sub">{html.escape(subtitle)}</span>' if subtitle else ""
    return f'<div class="app-head"><span class="title">{html.escape(title)}</span>{sub}</div>'


def section(label: str) -> str:
    """An uppercase section label with a hairline to the right."""
    return f'<div class="sec">{html.escape(label)}</div>'


def field_table(rows: list[tuple[str, str]]) -> str:
    """The record's own fields as a two-column table -- one row per field, no headings."""
    if not rows:
        return ""
    body = "".join(
        f'<tr><td class="k">{html.escape(label)}</td><td>{html.escape(value)}</td></tr>'
        for label, value in rows
    )
    return f'<table class="fields"><tbody>{body}</tbody></table>'


def reason_items(items: list[tuple[str, str]]) -> str:
    """L1's reasoning, one labelled block per key of its reasoning map."""
    blocks = "".join(
        f'<div class="item"><span class="k">{html.escape(label)}</span>'
        f'<div class="t">{html.escape(text)}</div></div>'
        for label, text in items
    )
    return f'<div class="l1reason">{blocks}</div>'


def claim_card(role: str, fields: list[tuple[str, str, str]], reasoning: str = "",
               matched_text: str = "", aside: str = "") -> str:
    """
    One claim as a single HTML block: the role, then `Field: value` rows, then Reasoning.

    `fields` is [(label, value, kind)] where kind picks the chip tint: "date", "doc", or
    "" for plain. An empty value renders as a faint italic `null`, which matters -- a
    missing date is the thing being judged, so it must not look like a blank.

    Reasoning carries two values under one label: the judge's prose in blue and the event
    text it matched in amber, the same amber that text wears in the document panel. The
    tint is what distinguishes them, so neither needs its own heading.

    Rendered via st.html rather than st.markdown: the event text comes from the
    date->events index and carries markdown of its own, and st.markdown runs the markdown
    parser even with unsafe_allow_html on, so escaping alone would not protect it.
    """
    parts = [
        f'<div class="claim"><div class="head"><span class="role">{html.escape(role)}</span></div>'
    ]

    if aside:
        parts.append(f'<div class="row aside">{html.escape(aside)}</div>')

    for label, value, kind in fields:
        chip = (f'<span class="v {kind}">{html.escape(value)}</span>' if value
                else '<span class="v null">null</span>')
        parts.append(f'<div class="row"><span class="label">{html.escape(label)}:</span> {chip}</div>')

    if reasoning or matched_text:
        parts.append('<div class="rblock"><span class="label">Reasoning:</span>')
        if reasoning:
            parts.append(f'<div class="line"><mark class="reason">{html.escape(reasoning)}</mark></div>')
        if matched_text:
            parts.append(f'<div class="line"><mark class="quote">{html.escape(matched_text)}</mark></div>')
        parts.append("</div>")

    parts.append("</div>")
    return "".join(parts)


def crumb(patient_id: str, entity: str, record: str, path: str) -> str:
    """patient · entity · record · source file, on one quiet line."""
    return (
        '<div class="crumb">'
        f"<b>{html.escape(patient_id)}</b> &nbsp;·&nbsp; {html.escape(entity)}"
        f" &nbsp;·&nbsp; {html.escape(record)}"
        f' &nbsp;·&nbsp; <span class="path">{html.escape(path)}</span>'
        "</div>"
    )

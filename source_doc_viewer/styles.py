"""
Cosmetic layer for the source-document viewer -- CSS plus the small HTML builders
that use it. Same conventions as l1_judge_viewer/styles.py:

  * Streamlit selectors are matched on `data-testid`, the most stable handles
    available. If a future version renames one, the app keeps working and simply
    looks plainer.
  * Colour is only ever a translucent tint over the theme's own background, with
    `color: inherit` -- the hue comes from fill and border, never from the text. So
    every chip and plate reads correctly in dark and light without hardcoding ink,
    even though .streamlit/config.toml ships this app in dark.

The layout is two plates: the document on the left, its details on the right. The
details plate is deliberately the narrow one -- it holds short key/value rows, while
the document needs every pixel it can get.
"""
from __future__ import annotations

import html

CSS = """
<style>
/* ── page rhythm ─────────────────────────────────────────────────────────── */
.block-container { padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 100%; }
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
  margin: .15rem 0 .5rem;
}
.sec::after { content: ""; flex: 1; height: 1px; background: currentColor; opacity: .3; }

/* ── identity strip: patient · mrn · N documents ─────────────────────────── */
.strip {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: .2rem 1.1rem;
  margin: 0 0 .8rem;
}
.strip .cell { display: flex; align-items: baseline; gap: .38rem; }
.strip .k {
  font-size: .62rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .07em; opacity: .5;
}
.strip .v {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .8rem; font-weight: 600;
  padding: .04rem .38rem; border-radius: .32rem;
  background: rgba(128,128,128,.13);
}
.strip .v.plain { background: none; font-family: inherit; font-size: .82rem; }

/* ── chips: state, never colour-as-text ──────────────────────────────────── */
.chip {
  display: inline-block; font-size: .68rem; font-weight: 650;
  padding: .08rem .42rem; border-radius: .32rem;
  background: rgba(128,128,128,.14);
}
.chip.ok   { background: rgba(70,190,130,.22); }
.chip.warn { background: rgba(255,196,0,.26); }
.chip.bad  { background: rgba(240,90,90,.22); }
.chip.cool { background: rgba(90,140,230,.22); }

/* ── plates: the two bordered panels ─────────────────────────────────────── */
/* st.container(border=True) renders this wrapper. Styling it here rather than
   wrapping our own div means the plate can hold real Streamlit widgets. */
div[data-testid="stVerticalBlockBorderWrapper"] {
  border-radius: .7rem;
  border: 1px solid rgba(128,128,128,.22);
  background: rgba(128,128,128,.045);
}
/* Columns are flex items, and a flex item defaults to min-width:auto -- it refuses
   to shrink below its content. That is the other half of why long values escaped
   the details plate: the column itself was being pushed wider than its share.
   min-width: 0 lets it shrink to the ratio it was given. */
div[data-testid="stColumn"] { min-width: 0; }
div[data-testid="stColumn"] > div { min-width: 0; }
/* the plate's own title row */
.plate-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: .6rem; margin: 0 0 .55rem;
}
.plate-head .name {
  font-size: .67rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .09em; opacity: .58;
}

/* ── details: key/value rows, built to survive a narrow column ───────────── */
/* table-layout: fixed is what actually holds the plate to its column. Without it
   the browser sizes columns from content, so one long unbroken token -- a blob
   path, a hash, a uuid -- widens the table past its container and the text spills
   out of the plate. Fixed layout honours the declared widths and makes the wrap
   rules below the only way content can grow. */
table.fields {
  width: 100%; max-width: 100%; table-layout: fixed;
  border-collapse: collapse; font-size: .8rem; margin: .1rem 0 .2rem;
}
table.fields td {
  padding: .26rem .45rem .26rem 0; vertical-align: top;
  border-bottom: 1px solid rgba(128,128,128,.14);
}
table.fields td.k {
  width: 38%; font-weight: 600; opacity: .72;
  font-size: .72rem; text-transform: none;
  overflow-wrap: anywhere;
}
/* every value may break mid-token, not just the monospaced ones -- a long
   facility name or failure reason overflows just as readily as a blob path */
table.fields td.v { overflow-wrap: anywhere; }
/* ids, paths and hashes: monospace, and broken anywhere they have to be */
table.fields td.v.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .74rem; word-break: break-all;
}
table.fields td.v.none { opacity: .4; }
table.fields tr:last-child td { border-bottom: none; }

/* ── sidebar ─────────────────────────────────────────────────────────────── */
section[data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.2); }
div[data-testid="stSidebarUserContent"] { padding-top: 1.1rem; }
/* tighter vertical rhythm than the default, so the whole control set fits above
   the fold on a laptop */
div[data-testid="stSidebarUserContent"] div[data-testid="stVerticalBlock"] { gap: .5rem; }
div[data-testid="stSidebarUserContent"] .sec { margin-top: .5rem; }
/* the connection summary: three monospace lines that should read as one block */
.conn {
  font-size: .7rem; line-height: 1.65; opacity: .72;
  border-left: 2px solid rgba(128,128,128,.3);
  padding: .05rem 0 .05rem .55rem; margin: -.1rem 0 .25rem;
}
.conn b { font-weight: 600; opacity: .8; }
.conn code {
  font-size: .69rem; background: rgba(128,128,128,.13);
  padding: .02rem .26rem; border-radius: .26rem;
}
/* footer status line */
.envline { display: flex; flex-wrap: wrap; gap: .3rem; margin: .1rem 0 0; }

/* ── paper: the document's own surface ───────────────────────────────────── */
/* Clinical HTML and CDA are written for white paper: they set dark ink and leave
   the background alone, so on a dark page the text comes out black on near-black.
   A rendered document therefore gets an explicit white sheet with dark ink, whatever
   theme the app is in -- the plate around it stays dark, so it reads as paper on a
   desk. Source and hex views deliberately keep the dark theme: they are code, not
   documents, and they were already legible. */
.paper {
  background: #ffffff; color: #16191d;
  border: 1px solid rgba(128,128,128,.28); border-radius: .45rem;
  padding: .9rem 1.05rem;
  overflow: auto; overscroll-behavior: contain;
  font-size: .85rem; line-height: 1.58;
}
.paper pre {
  margin: 0; white-space: pre-wrap; word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .8rem; line-height: 1.5; color: inherit;
}
.paper a { color: #0b57d0; }
.paper table { border-collapse: collapse; max-width: 100%; }
.paper td, .paper th { border: 1px solid #d0d5dd; padding: .18rem .4rem; }
.paper h1, .paper h2, .paper h3, .paper h4 { color: #0b1220; margin: .6em 0 .3em; }
.paper img { max-width: 100%; height: auto; }

/* ── widgets: quieter labels, tighter tabs and expanders ─────────────────── */
label[data-testid="stWidgetLabel"] p { font-size: .72rem; opacity: .72; }
button[data-baseweb="tab"] { padding-top: .35rem; padding-bottom: .35rem; }
div[data-testid="stExpander"] summary { font-size: .78rem; }
div[data-testid="stExpander"] summary p { font-size: .78rem; }
div[data-testid="stExpander"] details {
  border-color: rgba(128,128,128,.2); border-radius: .5rem;
}
/* the document picker carries the whole list, so give it room to breathe */
div[data-testid="stSelectbox"] div[data-baseweb="select"] { font-size: .82rem; }

/* plain-text documents: readable body size, marked as quoted source material */
div[data-testid="stText"] {
  font-size: .84rem; line-height: 1.5;
  white-space: pre-wrap; word-break: break-word;
  background: rgba(128,128,128,.06);
  border-left: 3px solid rgba(128,128,128,.35);
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


def strip(cells: list[tuple[str, str, str]]) -> str:
    """
    The identity line above the plates: [(label, value, kind)] where kind is "mono"
    for ids or "plain" for prose. An empty value renders as a faint dash, so a
    missing MRN looks missing rather than looking like a layout bug.
    """
    parts = []
    for label, value, kind in cells:
        shown = html.escape(value) if value else "—"
        css = "v" if kind == "mono" else "v plain"
        parts.append(
            f'<span class="cell"><span class="k">{html.escape(label)}</span>'
            f'<span class="{css}">{shown}</span></span>'
        )
    return f'<div class="strip">{"".join(parts)}</div>'


def chip(text: str, kind: str = "") -> str:
    """A state pill. kind is "ok", "warn", "bad", "cool" or "" for neutral."""
    return f'<span class="chip {kind}">{html.escape(text)}</span>'


def plate_head(name: str, right: str = "") -> str:
    """A plate's title row: small-caps name on the left, chips on the right."""
    return (
        f'<div class="plate-head"><span class="name">{html.escape(name)}</span>'
        f"<span>{right}</span></div>"
    )


def field_table(rows: list[tuple[str, str, str]]) -> str:
    """
    Details as a two-column table: [(label, value, kind)] where kind is "mono" for
    ids, paths and hashes -- those get monospace and are allowed to break mid-token
    so the narrow plate never widens past its column.
    """
    if not rows:
        return ""
    body = []
    for label, value, kind in rows:
        if value:
            cls = f"v {kind}" if kind else "v"
            cell = f'<td class="{cls}">{html.escape(value)}</td>'
        else:
            cell = '<td class="v none">—</td>'
        body.append(f'<tr><td class="k">{html.escape(label)}</td>{cell}</tr>')
    return f'<table class="fields"><tbody>{"".join(body)}</tbody></table>'


def paper(inner_html: str, height: int = 0) -> str:
    """
    A white sheet for a rendered document. `inner_html` is inserted as-is, so the
    caller is responsible for escaping anything that came out of a document.
    """
    style = f' style="height:{int(height)}px"' if height else ""
    return f'<div class="paper"{style}>{inner_html}</div>'


def paper_text(text: str, height: int = 0) -> str:
    """A white sheet holding pre-formatted text, escaped."""
    return paper(f"<pre>{html.escape(text)}</pre>", height)


# Injected as the first thing in the HTML viewer's iframe. components.html sets the
# iframe's whole document from the string we pass, so this style block IS the page's
# base stylesheet. It comes first on purpose: the document's own rules then win on
# typography, while `!important` on the canvas keeps the sheet white even when a
# document sets a background of its own.
HTML_CANVAS = (
    "<style>"
    "html,body{background:#fff !important;margin:0;padding:16px 18px;}"
    "body{color:#16191d;"
    "font:14px/1.58 system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;}"
    "img{max-width:100%;height:auto}"
    "table{border-collapse:collapse;max-width:100%}"
    "td,th{border:1px solid #d0d5dd;padding:3px 6px}"
    "a{color:#0b57d0}"
    "h1,h2,h3,h4{color:#0b1220}"
    "</style>"
)


def conn_summary(tenant_id: str, dbname: str, schema: str) -> str:
    """
    The selected connection, as one quiet block. Never includes conninfo -- that
    string holds the password.
    """
    return (
        '<div class="conn">'
        f"tenant <code>{html.escape(tenant_id or '—')}</code><br>"
        f"db <code>{html.escape(dbname)}</code><br>"
        f"schema <code>{html.escape(schema)}</code>"
        "</div>"
    )

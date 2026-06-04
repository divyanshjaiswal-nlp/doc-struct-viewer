"""All visual theming in one place: the datapoint color palette + the CSS.

Edit here to restyle the app — no logic lives in this file. PALETTE/ACCENT are
paired: PALETTE is the soft highlight background painted onto cited lines, ACCENT
is the matching saturated color used for that datapoint's dot + cite tags, so a
card on the right and its highlighted lines on the left share a color.

Theming: colors are CSS variables defined for light, then overridden under
@media (prefers-color-scheme: dark). Streamlit's default theme follows the
browser/OS color scheme, so the app adapts automatically. The pastel highlight
backgrounds stay light in both themes, so highlighted line text is forced dark.
"""
from __future__ import annotations

# Soft backgrounds painted onto cited document lines (dark text stays readable).
PALETTE: list[str] = [
    "#FEF3C7", "#DBEAFE", "#DCFCE7", "#FCE7F3", "#EDE9FE", "#FFEDD5",
    "#CCFBF1", "#FEE2E2", "#E0E7FF", "#D1FAE5", "#FAE8FF", "#FEF9C3",
]
# Saturated partner color (datapoint dot / cite tag background).
ACCENT: list[str] = [
    "#F59E0B", "#3B82F6", "#22C55E", "#EC4899", "#8B5CF6", "#F97316",
    "#14B8A6", "#EF4444", "#6366F1", "#10B981", "#D946EF", "#EAB308",
]

CSS = """
<style>
/* ---- theme variables ---------------------------------------------------- */
:root {
  --surface:#ffffff; --surface-2:#f8fafc;
  --text:#0f172a; --text-muted:#475569; --text-faint:#94a3b8;
  --border:#e5e7eb; --border-soft:#e2e8f0;
  --doc-text:#1f2937; --gutter:#94a3b8; --gutter-hl:#475569; --sep:#cbd5e1;
  --kw-bg:#f1f5f9; --kw-fg:#0f172a;
  --src-bg:#eef2ff; --src-fg:#4338ca;
  --sec-bg:#f0fdf4; --sec-fg:#15803d;
  --scroll:#cbd5e1; --scroll-hover:#94a3b8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --surface:#1e293b; --surface-2:#0f172a;
    --text:#e5e7eb; --text-muted:#cbd5e1; --text-faint:#64748b;
    --border:#334155; --border-soft:#334155;
    --doc-text:#cbd5e1; --gutter:#64748b; --gutter-hl:#334155; --sep:#475569;
    --kw-bg:#334155; --kw-fg:#e5e7eb;
    --src-bg:#312e81; --src-fg:#c7d2fe;
    --sec-bg:#14532d; --sec-fg:#bbf7d0;
    --scroll:#475569; --scroll-hover:#64748b;
  }
}

/* ---- page chrome -------------------------------------------------------- */
html { scroll-behavior: smooth; }
.block-container { padding-top: 1.4rem; padding-bottom: 1rem; max-width: 100%; }
#MainMenu, footer { visibility: hidden; }

/* ---- breadcrumb header -------------------------------------------------- */
.crumb { color: var(--text-muted); font-size: .9rem; margin-bottom: .15rem; }
.crumb b { color: var(--text); }
.crumb .sep { color: var(--sep); margin: 0 .5rem; }
.badge { display:inline-block; font-size:.72rem; font-weight:700; color:#fff;
         background:#6366f1; border-radius:999px; padding:.1rem .55rem;
         margin-left:.4rem; vertical-align:middle; }

/* ---- panel headers ------------------------------------------------------ */
.panel-title { font-weight:800; font-size:.82rem; letter-spacing:.04em;
               text-transform:uppercase; color:var(--text-muted);
               display:flex; align-items:center; gap:.45rem; margin:.1rem 0 .5rem; }
.panel-title .count { font-weight:600; color:var(--text-faint);
                      text-transform:none; letter-spacing:0; }

/* ---- raw document panel (line number + text) ---------------------------- */
.doc-panel { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
             font-size: 12.5px; line-height: 1.55; color: var(--doc-text); }
.doc-line  { display:flex; align-items:flex-start;
             padding:.02rem .4rem; border-radius:4px; scroll-margin-top:.4rem; }
.doc-line .ln { flex:0 0 3em; text-align:right; margin-right:.7rem;
                color:var(--gutter); user-select:none; -webkit-user-select:none; }
.doc-line .lt { flex:1 1 auto; white-space:pre-wrap; word-break:break-word; }
.doc-line.hl { box-shadow: inset 3px 0 0 rgba(15,23,42,.30);
               padding:.12rem .4rem; margin:.05rem 0; color:#0f172a; }
.doc-line.hl .ln { color:var(--gutter-hl); }
.cite-anchor { scroll-margin-top: 12px; }
.cite-tag { display:inline-block; font-size:10px; font-weight:700; color:#fff;
            border-radius:5px; padding:0 .35rem; margin-right:.4rem; vertical-align:1px; }

/* ---- datapoint content (inside a bordered st.container) ----------------- */
.dp-head { margin-bottom:.3rem; }
.dp-jump, .dp-jump:hover, .dp-jump:visited, .dp-jump * { text-decoration:none !important; }
.dp-jump { font-size:.72rem; font-weight:700; color:var(--text-faint); cursor:pointer;
           display:inline-flex; align-items:center; gap:.4rem; }
.dp-jump:hover { color:var(--text-muted); }
.dp-dot { width:9px; height:9px; border-radius:50%; display:inline-block; }
.dp-jump .locate { opacity:.7; transition:opacity .12s; }
.dp-jump:hover .locate { opacity:1; }
.dp-text { color:var(--text); font-size:.9rem; line-height:1.55; }
.dp-row  { margin-top:.5rem; display:flex; flex-wrap:wrap; gap:.3rem; align-items:center; }
.dp-label{ font-size:.66rem; font-weight:700; letter-spacing:.03em;
           text-transform:uppercase; color:var(--text-faint); margin-right:.15rem; }
.cite-preview { font-size:.72rem; color:var(--text-muted); margin:.1rem 0 .2rem; }

.pill { font-size:.7rem; font-weight:600; padding:.13rem .5rem; border-radius:999px;
        border:1px solid transparent; white-space:nowrap; }
.pill.kw   { background:var(--kw-bg);  color:var(--kw-fg);  border-color:var(--border-soft); }
.pill.src  { background:var(--src-bg); color:var(--src-fg); }
.pill.sec  { background:var(--sec-bg); color:var(--sec-fg); }
.pill.cite { background:transparent; font-weight:700; }   /* color/border set inline per datapoint */
.cite-link, .cite-link:hover, .cite-link:visited { text-decoration:none !important; cursor:pointer; }
.cite-link:hover { filter:brightness(.9); }

/* ---- misc --------------------------------------------------------------- */
.empty { color:var(--text-faint); font-style:italic; padding:1.2rem .35rem; }
::-webkit-scrollbar { width:9px; height:9px; }
::-webkit-scrollbar-thumb { background:var(--scroll); border-radius:6px; }
::-webkit-scrollbar-thumb:hover { background:var(--scroll-hover); }
</style>
"""

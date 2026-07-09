"""Doc-Struct Viewer — browse doc-to-struct outputs, highlight citations, annotate.

Flow (each step is a dropdown):
    OUTPUT_DIR -> subfolder -> {patient}.json -> doc_id -> section
Left: the raw document, line-numbered, with the section's citations highlighted.
Right: one card per datapoint. Click "📍 locate" to scroll the document to its
first cited line. Each card has a comment box and a corrected-citation box that
save to the annotation CSV on Enter.

Run:  streamlit run app.py     (from inside this folder)
"""
from __future__ import annotations

import html
import os

import streamlit as st
from dotenv import load_dotenv

import annotations
import loader
from highlight import build_highlight_model, render_doc_html
from sections import (
    BASELINE_SECTION_KEYS,
    BASELINE_SECTION_LABELS,
    SECTION_KEYS,
    SECTION_LABELS,
)
from styles import ACCENT, CSS, PALETTE

load_dotenv()
st.set_page_config(page_title="Doc-Struct Viewer", page_icon="🩺", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

# Intercept cite/locate clicks: scroll the document panel to the cited line and,
# if that panel is off-screen (compare page), nudge the page to reveal it.
# st.iframe renders this string in a same-origin iframe (it auto-detects raw HTML),
# so the <script> still runs — the supported replacement for components.v1.html.
st.iframe(
    """
<script>
const pdoc = window.parent.document;
if (!pdoc.__citeScroll) {
  pdoc.__citeScroll = true;
  pdoc.addEventListener('click', function(e){
    const a = e.target.closest('a[href^="#cite-"], a[href^="#dp-"]');
    if (!a) return;
    e.preventDefault();
    const el = pdoc.getElementById(a.getAttribute('href').slice(1));
    if (!el) return;
    let c = el.parentElement;
    while (c && c !== pdoc.body) {
      const oy = getComputedStyle(c).overflowY;
      if ((oy === 'auto' || oy === 'scroll') && c.scrollHeight > c.clientHeight) break;
      c = c.parentElement;
    }
    if (!c || c === pdoc.body) { return; }
    c.scrollTo({top: c.scrollTop + el.getBoundingClientRect().top
                     - c.getBoundingClientRect().top - 12, behavior: 'smooth'});
    // If the doc panel itself is off-screen (compare page: doc sits below the
    // cards), scroll the page just enough to bring it into view. 'nearest'
    // makes this a no-op when the panel is already visible (viewer page).
    c.scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }, true);
}
</script>
""",
    height=1,  # st.iframe needs a positive int; 1px is effectively invisible
)

PANEL_H = 760  # height (px) of the two scrollable panels
HERE = os.path.dirname(os.path.abspath(__file__))


# --- small HTML render helpers ----------------------------------------------

def _pills(items, cls: str) -> str:
    """Render a list of strings as colored pills of one class."""
    return "".join(
        f'<span class="pill {cls}">{html.escape(str(x))}</span>'
        for x in (items or [])
        if str(x).strip()
    )


def _cite_pills(citations, accent: str, idx: int, ns: str = "") -> str:
    """Citation line ranges as clickable 'L12' / 'L12–15' links, tinted to the
    datapoint. Clicking pill j scrolls the document to that range's first line."""
    out = []
    for j, c in enumerate(citations or []):
        if not isinstance(c, dict):
            continue
        try:
            s, e = int(c["start"]), int(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        label = f"L{s}" if s == e else f"L{s}–{e}"
        out.append(
            f'<a class="pill cite cite-link" href="#cite-{ns}{idx}-{j}" '
            f'style="border-color:{accent};color:{accent}">{label}</a>'
        )
    return "".join(out)


def _card_inner(idx: int, dp: dict, accent: str, ns: str = "") -> str:
    """Read-only datapoint view (the editable widgets are added separately)."""
    text = html.escape(str(dp.get("text", ""))) or "<i>(no text)</i>"
    head = (
        f'<div class="dp-head"><a class="dp-jump" href="#dp-{ns}{idx}">'
        f'<span class="dp-dot" style="background:{accent}"></span>#{idx + 1}'
        f'<span class="locate">📍 locate</span></a></div>'
    )
    rows = ""
    kw = _pills(dp.get("keywords"), "kw")
    if kw:
        rows += f'<div class="dp-row"><span class="dp-label">keywords</span>{kw}</div>'
    cites = _cite_pills(dp.get("citations"), accent, idx, ns)
    if cites:
        rows += f'<div class="dp-row"><span class="dp-label">cites</span>{cites}</div>'
    src = _pills(dp.get("sources"), "src")
    sec = _pills((SECTION_LABELS.get(s, s) for s in dp.get("secondary_sections") or []), "sec")
    if src or sec:
        also = f'<span class="dp-label" style="margin-left:.35rem">also</span>{sec}' if sec else ""
        rows += f'<div class="dp-row">{src}{also}</div>'
    return f'{head}<div class="dp-text">{text}</div>{rows}'


def _section_count(response, key):
    """None = section absent from output (LLM missed it); else number of datapoints."""
    if not isinstance(response, dict) or key not in response:
        return None
    v = response.get(key)
    return len(v) if isinstance(v, list) else None


def _render_output_column(response, keys, labels, side: str, title: str,
                          ns: str, color_offset: int = 0) -> list[dict]:
    """One read-only output panel for the comparison page: a section dropdown
    (scoped to this side's section list) plus the datapoint cards. Returns the
    highlight `items` for the shared document panel; `ns` namespaces the scroll
    anchors so both sides can coexist, and `color_offset` staggers the palette
    so the two sides' highlights don't share colors."""
    counts = {k: _section_count(response, k) for k in keys}
    populated = sum(1 for k in keys if (counts[k] or 0) > 0)
    st.markdown(
        f'<div class="panel-title">{title} '
        f'<span class="count">· {populated}/{len(keys)} populated</span></div>',
        unsafe_allow_html=True,
    )
    if not isinstance(response, dict):
        st.warning("No structured output for this document.")
    default_idx = next((i for i, k in enumerate(keys) if (counts[k] or 0) > 0), 0)
    section = st.selectbox(
        "Section",
        keys,
        index=default_idx,
        format_func=lambda k: f"{labels[k]}  ·  "
        + ("—" if counts[k] is None else str(counts[k])),
        key=f"cmp_section_{side}",
        label_visibility="collapsed",
    )
    dps = response.get(section) if isinstance(response, dict) else None
    dps = dps if isinstance(dps, list) else []
    accents = [ACCENT[(color_offset + i) % len(ACCENT)] for i in range(len(dps))]
    items = [
        {"idx": i, "citations": dp.get("citations"), "ns": ns,
         "color": PALETTE[(color_offset + i) % len(PALETTE)], "accent": accents[i]}
        for i, dp in enumerate(dps)
    ]
    # No fixed-height scroll box here (unlike the Viewer): the cards flow at
    # their natural height, so the raw document starts right where the longer
    # column's cards end instead of after a tall half-empty panel.
    if not dps:
        st.markdown('<div class="empty">No datapoints in this section.</div>',
                    unsafe_allow_html=True)
    for i, dp in enumerate(dps):
        with st.container(border=True):
            st.markdown(_card_inner(i, dp, accents[i], ns),
                        unsafe_allow_html=True)
    return items


def _save_annotation(path, key, text, original_cites, ckey, zkey):
    """on_change callback: persist this datapoint's comment + corrected citation."""
    annotations.save_annotation(
        path, key,
        text=text,
        original_cites=original_cites,
        comment=st.session_state.get(ckey, ""),
        corrected_cites=st.session_state.get(zkey, ""),
    )


# --- page header: title + reload (no sidebar; everything lives on the page) --

# All paths are fixed on the server (set via .env). Reviewers only type a
# document id below — they never pick a run or a patient.
output_dir = os.environ.get("OUTPUT_DIR", "")
raw_dir = os.environ.get("RAW_DIR", "")
subfolder = os.environ.get("RUN_SUBFOLDER", "")      # the run/strategy folder to serve
doc_map_csv = os.environ.get("DOC_PATIENT_CSV", "")  # CSV index: doc_id -> patient_id
ann_path = os.environ.get("ANNOTATIONS_FILE", os.path.join(HERE, "annotations.csv"))

# Baseline run (for the "Compare vs baseline" page). Same layout as the main
# output: BASELINE_OUTPUT_DIR/BASELINE_RUN_SUBFOLDER/<patient_id>.json, indexed
# by its own doc->patient CSV (falls back to the main CSV if not set).
baseline_output_dir = os.environ.get("BASELINE_OUTPUT_DIR", "")
baseline_subfolder = os.environ.get("BASELINE_RUN_SUBFOLDER", "")
baseline_doc_map_csv = os.environ.get("BASELINE_DOC_PATIENT_CSV", doc_map_csv)

title_col, reload_col = st.columns([4, 1])
with title_col:
    st.markdown("## 🩺 Doc-Struct Viewer")
with reload_col:
    if st.button("↻ Reload from disk"):
        st.cache_data.clear()
        st.rerun()

# Server config must be present; reviewers can't fix this from the UI.
_missing = [name for name, val in (
    ("OUTPUT_DIR", output_dir),
    ("RUN_SUBFOLDER", subfolder),
    ("DOC_PATIENT_CSV", doc_map_csv),
) if not val]
if _missing:
    st.error("Missing server config: " + ", ".join(f"`{m}`" for m in _missing)
             + ". Set it in the server's `.env` file.")
    st.stop()

# --- top of page: the reviewer enters a document id to review ----------------
doc_col, page_col, _ = st.columns([1.2, 0.9, 1.1])
with doc_col:
    doc_id = st.text_input(
        "🔎 Document ID",
        key="doc_id_input",
        placeholder="Enter a document id…",
    ).strip()
with page_col:
    page = st.selectbox("Page", ["Viewer", "Compare vs baseline"], key="page_select")
if not doc_id:
    st.info("Enter a **Document ID** above to load its document.")
    st.stop()

# doc_id -> patient_id (via the index CSV) -> that patient's output file.
doc_map = loader.load_doc_patient_map(doc_map_csv)
if not doc_map:
    st.error(
        "The document index (`DOC_PATIENT_CSV`) is empty or unreadable — it needs a "
        "header row with `doc_id` and `patient_id` columns."
    )
    st.stop()
patient_id = doc_map.get(doc_id)
if not patient_id:
    st.error(f"Document id `{doc_id}` is not in the index.")
    st.stop()

try:
    output = loader.load_patient_output(output_dir, subfolder, patient_id)
except Exception as e:  # noqa: BLE001 - surface any read/parse error to the UI
    st.error(f"Failed to read the output file for patient `{patient_id}`: {e}")
    st.stop()

if doc_id not in output:
    st.error(
        f"Patient `{patient_id}` (from the index) has no document `{doc_id}` in their "
        "output file — the index and the outputs may be out of sync."
    )
    st.stop()

doc_ids = tuple(output.keys())
response = output.get(doc_id)

# --- comparison page: main output vs baseline output, side by side -----------
if page == "Compare vs baseline":
    _b_missing = [name for name, val in (
        ("BASELINE_OUTPUT_DIR", baseline_output_dir),
        ("BASELINE_RUN_SUBFOLDER", baseline_subfolder),
        ("BASELINE_DOC_PATIENT_CSV", baseline_doc_map_csv),
    ) if not val]
    if _b_missing:
        st.error("Missing baseline config: " + ", ".join(f"`{m}`" for m in _b_missing)
                 + ". Set it in the server's `.env` file.")
        st.stop()

    # Resolve the same doc id through the baseline's own index + output files.
    baseline_response = None
    baseline_error = ""
    baseline_map = loader.load_doc_patient_map(baseline_doc_map_csv)
    baseline_patient = baseline_map.get(doc_id)
    if not baseline_map:
        baseline_error = "The baseline document index is empty or unreadable."
    elif not baseline_patient:
        baseline_error = f"Document id `{doc_id}` is not in the baseline index."
    else:
        try:
            baseline_output = loader.load_patient_output(
                baseline_output_dir, baseline_subfolder, baseline_patient)
        except Exception as e:  # noqa: BLE001 - surface any read/parse error
            baseline_error = (f"Failed to read the baseline output for patient "
                              f"`{baseline_patient}`: {e}")
        else:
            if doc_id in baseline_output:
                baseline_response = baseline_output.get(doc_id)
            else:
                baseline_error = (f"Baseline patient `{baseline_patient}` has no "
                                  f"document `{doc_id}` in their output file.")

    crumb = (
        f'Doc <b>{html.escape(doc_id)}</b><span class="sep">·</span>'
        f'Main run <b>{html.escape(subfolder)}</b> (patient '
        f'<b>{html.escape(patient_id)}</b>)<span class="sep">vs</span>'
        f'Baseline run <b>{html.escape(baseline_subfolder)}</b>'
        + (f' (patient <b>{html.escape(baseline_patient)}</b>)' if baseline_patient else "")
    )
    st.markdown(f'<div class="crumb">{crumb}</div>', unsafe_allow_html=True)
    st.write("")

    main_col, base_col = st.columns(2, gap="medium")
    with main_col:
        main_items = _render_output_column(response, SECTION_KEYS, SECTION_LABELS,
                                           "main", "🧩 Main output", ns="m-")
    with base_col:
        if baseline_error:
            st.markdown(
                '<div class="panel-title">📐 Baseline output</div>',
                unsafe_allow_html=True,
            )
            st.error(baseline_error)
            base_items = []
        else:
            base_items = _render_output_column(
                baseline_response, BASELINE_SECTION_KEYS, BASELINE_SECTION_LABELS,
                "baseline", "📐 Baseline output", ns="b-",
                color_offset=len(PALETTE) // 2)

    # Full-width raw document below the two panels, with both sides' citations
    # highlighted (main = first palette half, baseline = second half).
    raw_docs = loader.load_raw_docs(raw_dir, patient_id, doc_ids) if raw_dir else {}
    raw_text = (raw_docs.get(doc_id) or {}).get("docText", "") or ""
    nlines = raw_text.count("\n") + 1 if raw_text else 0
    st.write("")
    st.markdown(
        f'<div class="panel-title">📄 Raw document '
        f'<span class="count">· {nlines} lines</span></div>',
        unsafe_allow_html=True,
    )
    with st.container(height=PANEL_H, border=True):
        if not raw_text:
            st.markdown(
                '<div class="empty">No raw document text found for this doc id '
                "in the raw folder.</div>",
                unsafe_allow_html=True,
            )
        else:
            info = build_highlight_model(raw_text, main_items + base_items)
            st.markdown(
                f'<div class="doc-panel">{render_doc_html(info)}</div>',
                unsafe_allow_html=True,
            )
    st.stop()

# Load the patient's raw docs once; picking the doc is just a dict lookup.
raw_docs = loader.load_raw_docs(raw_dir, patient_id, doc_ids) if raw_dir else {}
doc = raw_docs.get(doc_id) or {}
raw_text = doc.get("docText", "") or ""
ann = annotations.load_annotations(ann_path)  # uncached: reflects on_change writes

# --- breadcrumb header -------------------------------------------------------

populated = sum(1 for k in SECTION_KEYS if (_section_count(response, k) or 0) > 0)
crumb = (
    f'Run <b>{html.escape(subfolder)}</b><span class="sep">›</span>'
    f'Patient <b>{html.escape(patient_id)}</b><span class="sep">›</span>'
    f'Doc <b>{html.escape(doc_id)}</b>'
)
if doc.get("docDate"):
    crumb += f'<span class="sep">·</span>{html.escape(str(doc["docDate"]))}'
if doc.get("title"):
    crumb += f'<span class="sep">·</span>{html.escape(str(doc["title"]))}'
if doc.get("docType"):
    crumb += f'<span class="sep">·</span>{html.escape(str(doc["docType"]))}'
crumb += f'<span class="badge">{populated}/10 sections</span>'
st.markdown(f'<div class="crumb">{crumb}</div>', unsafe_allow_html=True)
st.write("")

# --- the two panels ----------------------------------------------------------
# Right is built first so the section selection (and thus the citation items) is
# known before we paint the document on the left.

left, right = st.columns([1.15, 1], gap="medium")

with right:
    counts = {k: _section_count(response, k) for k in SECTION_KEYS}
    default_idx = next((i for i, k in enumerate(SECTION_KEYS) if (counts[k] or 0) > 0), 0)

    st.markdown(
        f'<div class="panel-title">🧩 Structured output '
        f'<span class="count">· {populated} populated</span></div>',
        unsafe_allow_html=True,
    )
    if not isinstance(response, dict):
        st.warning("No structured output for this document (extraction may have failed).")

    section = st.selectbox(
        "Section",
        SECTION_KEYS,
        index=default_idx,
        format_func=lambda k: f"{SECTION_LABELS[k]}  ·  "
        + ("—" if counts[k] is None else str(counts[k])),
        label_visibility="collapsed",
    )

    dps = response.get(section) if isinstance(response, dict) else None
    dps = dps if isinstance(dps, list) else []
    colors = [PALETTE[i % len(PALETTE)] for i in range(len(dps))]
    accents = [ACCENT[i % len(ACCENT)] for i in range(len(dps))]

    # everything the left panel needs to paint + place scroll anchors
    items = [
        {"idx": i, "citations": dp.get("citations"),
         "color": colors[i], "accent": accents[i]}
        for i, dp in enumerate(dps)
    ]

    with st.container(height=PANEL_H, border=False):
        if not dps:
            st.markdown('<div class="empty">No datapoints in this section.</div>',
                        unsafe_allow_html=True)
        for i, dp in enumerate(dps):
            key = (subfolder, patient_id, doc_id, section, str(i))
            ckey = "cmt::" + "::".join(key)
            zkey = "cit::" + "::".join(key)
            orig_str = annotations.cites_to_str(dp.get("citations"))
            saved = ann.get(key, {})
            # seed widget state from the CSV once; later edits live in session_state
            st.session_state.setdefault(ckey, saved.get("comment", ""))
            st.session_state.setdefault(zkey, saved.get("corrected_cites", ""))

            with st.container(border=True):
                st.markdown(_card_inner(i, dp, accents[i]),
                            unsafe_allow_html=True)
                st.text_input(
                    "💬 Comment", key=ckey, placeholder="Comment if anything is wrong…",
                    on_change=_save_annotation,
                    args=(ann_path, key, str(dp.get("text", "")), orig_str, ckey, zkey),
                )
                st.text_input(
                    "✏️ Corrected citation", key=zkey,
                    placeholder=f"Fix citation, e.g. {orig_str or '12-15, 20'}",
                    on_change=_save_annotation,
                    args=(ann_path, key, str(dp.get("text", "")), orig_str, ckey, zkey),
                )
                typed = st.session_state.get(zkey, "")
                if typed.strip():
                    parsed = annotations.cites_to_str(annotations.parse_citations(typed))
                    st.markdown(
                        f'<div class="cite-preview">→ parsed: '
                        f'{parsed or "⚠ could not parse"}</div>',
                        unsafe_allow_html=True,
                    )

with left:
    nlines = raw_text.count("\n") + 1 if raw_text else 0
    st.markdown(
        f'<div class="panel-title">📄 Raw document '
        f'<span class="count">· {nlines} lines</span></div>',
        unsafe_allow_html=True,
    )
    with st.container(height=PANEL_H, border=True):
        if not raw_text:
            st.markdown(
                '<div class="empty">No raw document text found for this doc id '
                "in the raw folder.</div>",
                unsafe_allow_html=True,
            )
        else:
            info = build_highlight_model(raw_text, items)
            st.markdown(
                f'<div class="doc-panel">{render_doc_html(info)}</div>',
                unsafe_allow_html=True,
            )

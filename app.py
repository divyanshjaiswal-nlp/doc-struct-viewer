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
import streamlit.components.v1 as components
from dotenv import load_dotenv

import annotations
import loader
from highlight import build_highlight_model, render_doc_html
from sections import SECTION_KEYS, SECTION_LABELS
from styles import ACCENT, CSS, PALETTE

load_dotenv()
st.set_page_config(page_title="Doc-Struct Viewer", page_icon="🩺", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

# Intercept cite/locate clicks: scroll ONLY the document panel, never the page.
components.html(
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
  }, true);
}
</script>
""",
    height=0,
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


def _cite_pills(citations, accent: str, idx: int) -> str:
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
            f'<a class="pill cite cite-link" href="#cite-{idx}-{j}" '
            f'style="border-color:{accent};color:{accent}">{label}</a>'
        )
    return "".join(out)


def _card_inner(idx: int, dp: dict, accent: str) -> str:
    """Read-only datapoint view (the editable widgets are added separately)."""
    text = html.escape(str(dp.get("text", ""))) or "<i>(no text)</i>"
    head = (
        f'<div class="dp-head"><a class="dp-jump" href="#dp-{idx}">'
        f'<span class="dp-dot" style="background:{accent}"></span>#{idx + 1}'
        f'<span class="locate">📍 locate</span></a></div>'
    )
    rows = ""
    kw = _pills(dp.get("keywords"), "kw")
    if kw:
        rows += f'<div class="dp-row"><span class="dp-label">keywords</span>{kw}</div>'
    cites = _cite_pills(dp.get("citations"), accent, idx)
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


def _save_annotation(path, key, text, original_cites, ckey, zkey):
    """on_change callback: persist this datapoint's comment + corrected citation."""
    annotations.save_annotation(
        path, key,
        text=text,
        original_cites=original_cites,
        comment=st.session_state.get(ckey, ""),
        corrected_cites=st.session_state.get(zkey, ""),
    )


# --- sidebar: paths + navigation --------------------------------------------

with st.sidebar:
    st.markdown("## 🩺 Doc-Struct Viewer")
    output_dir = st.text_input("📁 Output folder", os.environ.get("OUTPUT_DIR", ""))
    raw_dir = st.text_input("📄 Raw documents folder", os.environ.get("RAW_DIR", ""))
    # Annotation CSV path comes from the env (ANNOTATIONS_FILE); not shown/editable in the UI.
    ann_path = os.environ.get("ANNOTATIONS_FILE", os.path.join(HERE, "annotations.csv"))
    if st.button("↻ Reload from disk", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
    st.divider()

if not output_dir:
    st.info("👈 Set the **Output folder** in the sidebar to begin.")
    st.stop()

subfolders = loader.list_subfolders(output_dir)
if not subfolders:
    st.error(f"No subfolders found in `{output_dir}`.")
    st.stop()

with st.sidebar:
    subfolder = st.selectbox("① Run / strategy", subfolders)
    patients = loader.list_patient_ids(output_dir, subfolder)
    if not patients:
        st.warning("No patient JSON files in this run.")
        st.stop()
    patient_id = st.selectbox("② Patient", patients)

try:
    output = loader.load_patient_output(output_dir, subfolder, patient_id)
except Exception as e:  # noqa: BLE001 - surface any read/parse error to the UI
    st.error(f"Failed to read patient file: {e}")
    st.stop()

doc_ids = tuple(output.keys())
if not doc_ids:
    st.warning("This patient file has no documents.")
    st.stop()

with st.sidebar:
    doc_id = st.selectbox(
        "③ Document",
        doc_ids,
        format_func=lambda d: ("" if isinstance(output.get(d), dict) else "⚠ ") + d,
    )

# Load the raw docs for this patient once; selecting a doc is a dict lookup.
raw_docs = loader.load_raw_docs(raw_dir, patient_id, doc_ids) if raw_dir else {}
doc = raw_docs.get(doc_id) or {}
raw_text = doc.get("docText", "") or ""
response = output.get(doc_id)
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
crumb += f'<span class="badge">{populated}/20 sections</span>'
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

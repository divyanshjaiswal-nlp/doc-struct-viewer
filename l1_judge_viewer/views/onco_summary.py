"""
An L1 oncology-history summary beside the merged doc-to-struct date anchors.

Left: the summary prose, with every date in it marked -- a year, a year and month, or a
full date, however it was written. Right: the merged anchor index, one group per date,
holding the data-point texts that anchor to it.

Each date in the summary is looked up in that index, exactly first and then by
granularity. A date that lands on a key is clickable and scrolls the index to it, and the
key scrolls back; a date that lands on nothing is marked amber -- the summary asserts it
and the index has nothing on that day.

`oncology_history_v3` has no entry in config.py and does not need one: the entity is found
here by the shape of its records (anything carrying a text `summary`), and every other key
on the record is ignored.

Paths: ONCO_L1_DIR and MERGED_ANCHOR_DIR, both editable in the "Paths" expander. Either
may be a directory or a single json file.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

VIEWER_ROOT = str(Path(__file__).resolve().parent.parent)
if VIEWER_ROOT not in sys.path:
    sys.path.insert(0, VIEWER_ROOT)

from loader import (ONCO_DIR_VARS, list_merged_files,  # noqa: E402
                    list_onco_patients, list_summary_entities, load_merged_anchors,
                    load_onco, merged_anchor_file, merged_anchor_groups, summary_blocks)
from state import is_dark, paths_expander, sticky     # noqa: E402
from styles import crumb, section                     # noqa: E402
from summary_view import summary_anchor_page          # noqa: E402

PANE_HEIGHT = 760

st.markdown(section("Oncology history summary vs merged date anchors"),
            unsafe_allow_html=True)

paths_expander(ONCO_DIR_VARS)

if not os.environ.get("ONCO_L1_DIR", "").strip():
    st.info("Set ONCO_L1_DIR above — the L1 run holding the summary entity. A folder per "
            "patient, a folder of `<patient_id>.json`, or one json file.")
    st.stop()

patients = list_onco_patients()
if not patients:
    st.warning("Nothing to read under ONCO_L1_DIR.")
    st.stop()

patient_col, entity_col = st.columns([2, 3])
patient_id = sticky(patient_col, "Patient", patients, key="onco_patient")

try:
    json_path, smd = load_onco(patient_id)
except Exception as exc:
    st.error(f"Failed to load the L1 output: {exc}")
    st.stop()

entities = list_summary_entities(smd)
if not entities:
    st.warning("No entity in this file carries a text `summary`.")
    with st.expander("What the file does hold", expanded=True):
        st.json({key: type(value).__name__ for key, value in smd.items()})
    st.stop()

entity_key = sticky(entity_col, "Entity", entities, key="onco_entity")
blocks = summary_blocks(smd[entity_key])

st.markdown(crumb(patient_id, entity_key, f"{len(blocks)} summary block(s)", json_path),
            unsafe_allow_html=True)

# ── the merged anchors ───────────────────────────────────────────────────────
if not os.environ.get("MERGED_ANCHOR_DIR", "").strip():
    st.info("Set MERGED_ANCHOR_DIR above — the merged doc-to-struct anchors, keyed by "
            "date. A directory of `<patient_id>.json`, or the merged file itself.")
    st.stop()

files = list_merged_files()
if not files:
    st.warning("No json under MERGED_ANCHOR_DIR.")
    st.stop()

merged_path = merged_anchor_file(patient_id)
if merged_path is None:
    # the merged file is assembled by hand, so its name need not carry the patient id
    by_name = {path.name: path for path in files}
    st.caption(f"No merged file named after `{patient_id}` — pick one.")
    merged_path = by_name[sticky(st, "Merged anchors file", list(by_name),
                                 key="onco_merged")]

path_col, order_col = st.columns([6, 1])
path_col.caption(f"Merged anchors: `{merged_path}`")
# the merged file's own key order is ignored either way -- it is re-sorted here, so a file
# written newest-first and one written oldest-first read the same
newest_first = order_col.checkbox("Newest first", key="onco_newest")

try:
    groups = merged_anchor_groups(load_merged_anchors(str(merged_path)), newest_first)
except Exception as exc:
    st.error(f"Failed to read {merged_path}: {exc}")
    st.stop()

if not groups:
    st.warning(
        "That file holds no date keys. Expected one of: `{date: [text, ...]}`, "
        "`{date: [{text, docId}, ...]}`, or `{docId: {date: [...]}}`, with dates as "
        "`YYYY`, `YYYY-MM` or `YYYY-MM-DD`."
    )
    st.stop()

# ── the comparison ───────────────────────────────────────────────────────────
page, stats = summary_anchor_page(blocks, groups, dark=is_dark())

st.caption(
    f"**{stats['mentions']}** date(s) written in the summary — "
    f"{stats['exact']} on an exact key, {stats['near']} covering keys beneath them or "
    f"reaching a coarser one, **{stats['missing']}** on nothing. "
    f"{stats['keys_hit']}/{stats['keys']} merged date(s) were reached. "
    "Each matched date has its own colour, worn by every key it covers on the right and "
    "washed across the sentence it owns — solid fill = an exact key, dashed underline = a "
    "partial date covering everything under it. Red = nothing in the index on that date."
)

# one iframe holding both panes: a click has to scroll the other pane, and a link in
# Streamlit's own document cannot reach inside a components.html iframe
components.html(page, height=PANE_HEIGHT, scrolling=False)

if stats["unmatched"]:
    with st.expander(f"{len(stats['unmatched'])} summary date(s) with no key"):
        for key, raw in stats["unmatched"]:
            st.caption(f"`{raw}`  →  {key}")

if stats["unhit"]:
    with st.expander(f"{len(stats['unhit'])} merged date(s) the summary never mentions"):
        st.caption("  ·  ".join(stats["unhit"]))

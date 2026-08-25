"""
Date → events for ONE document, before the merge.

Pick a patient and one of its documents; the document's text sits on the left with every
cited line highlighted, and its extracted events on the right. Clicking a citation's line
range scrolls the document pane to it.

This is the check on whether the extractor read an event from the right place. The merged
index cannot answer that -- it has already pooled the documents together.
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

from line_highlight import document_events_page, document_struct_page  # noqa: E402
from loader import (DATE_EVENTS_DIR_VARS, list_raw_patients,  # noqa: E402
                    load_doc, load_doc_struct, load_grounding,
                    load_raw_date_events, norm_event_text)
from state import is_dark, paths_expander, sticky     # noqa: E402
from styles import crumb, section                     # noqa: E402
from table_fill import fill_table_cells               # noqa: E402

PANE_HEIGHT = 720


def flatten(dates: dict, verdicts: dict[str, dict]) -> list[dict]:
    """{date: [event, ...]} -> [{date, text, citations, verdict?}], in date order.

    `verdicts` is the grounding judge's output for this document, keyed by normalised
    event text; only rejected events are in it, so most events come through untouched.
    Tolerates the old bare-string event shape, which simply has no citations.
    """
    events = []
    for date in sorted(dates):
        for event in dates[date] or []:
            if isinstance(event, str):
                text, citations = event, []
            elif isinstance(event, dict):
                text, citations = event.get("text") or "", event.get("citations") or []
            else:
                continue

            row = {"date": date, "text": text, "citations": citations}
            verdict = verdicts.get(norm_event_text(text))
            if verdict:
                row["verdict"] = verdict
            events.append(row)
    return events


st.markdown(section("Date → events, per document"), unsafe_allow_html=True)

paths_expander(DATE_EVENTS_DIR_VARS, optional=("PATIENT_DATA_DIR",))

if not os.environ.get("DATE_EVENTS_RAW_DIR", "").strip():
    st.info("Set DATE_EVENTS_RAW_DIR above — the un-merged extractor output: one file per "
            "patient, keyed by docId. Any grounding-judge results json sitting in the same "
            "directory is picked up automatically.")
    st.stop()

patients = list_raw_patients()
if not patients:
    st.warning("No patient files under DATE_EVENTS_RAW_DIR.")
    st.stop()

patient_col, doc_col = st.columns([2, 5])
patient_id = sticky(patient_col, "Patient", patients, key="raw_patient")

by_doc = load_raw_date_events(patient_id)
if not by_doc:
    st.warning(f"No usable date→events content for `{patient_id}`.")
    st.stop()

# label each document with its event count, and its type/date when we can read them
labels = {}
for doc_id, dates in by_doc.items():
    count = sum(len(v) for v in dates.values())
    meta = load_doc(patient_id, doc_id) or {}
    suffix = "".join(f"  ·  {meta[key]}" for key in ("docType", "docDate") if meta.get(key))
    labels[f"{doc_id}  ·  {count} event(s){suffix}"] = doc_id

doc_id = labels[sticky(doc_col, "Document", list(labels), key="raw_doc")]

# None when the grounding judge never saw this document; {} when it saw it and flagged
# nothing. The caption says which, so "clean" is never mistaken for "unchecked".
verdicts = load_grounding(patient_id, doc_id)
events = flatten(by_doc[doc_id], verdicts or {})

doc = load_doc(patient_id, doc_id)

# `doc_text` goes through the same blank-cell filling the extractor's formatter applies, so
# the document on screen is the document the model read. It changes cell contents only,
# never the number of lines, so every citation still points at the same line -- which is
# also why the raw version can be shown beside it under a tab.
raw_text = (doc or {}).get("docText") or ""
doc_text = fill_table_cells(raw_text)

st.markdown(
    crumb(patient_id, doc_id, f"{len(events)} event(s)",
          (doc or {}).get("docType") or "document text unavailable"),
    unsafe_allow_html=True,
)

if not doc_text:
    st.error(
        "No document text for this docId. Set PATIENT_DATA_DIR on the L1 review page — "
        "without the raw text there are no lines to highlight."
    )
    st.stop()

page, cited = document_events_page(doc_text, events, raw_text, dark=is_dark())
missing = len(events) - cited
if not events:
    st.caption("The extractor returned no events for this document.")
else:
    st.caption(
        f"{cited}/{len(events)} event(s) carry a line citation"
        + (f" · {missing} uncited — extracted before citations were added, or the extractor "
           "omitted them" if missing else "")
    )

if verdicts is None:
    st.caption("Grounding judge: not run on this document.")
else:
    rejected = sum(1 for event in events if event.get("verdict"))
    # a verdict lands on an event by its text; one that matches nothing is a verdict we
    # cannot show, so it is reported rather than silently dropped
    seen = {norm_event_text(event["text"]) for event in events}
    orphans = sum(1 for key in verdicts if key not in seen)

    if rejected:
        note = (f"Grounding judge: **{rejected}** of {len(events)} event(s) flagged — "
                "shown under the event on the right, with their lines underlined in the "
                "document.")
    elif not verdicts:
        note = "Grounding judge: every event in this document held up."
    else:
        note = "Grounding judge: nothing shown —"

    if orphans:
        note += (f" {orphans} verdict(s) could not be matched back to an event: the judge "
                 "altered the text it copied back, or the index was re-extracted after it "
                 "ran.")
    st.caption(note)

# one iframe holding BOTH panes: a citation click has to scroll the document pane, and a
# link in Streamlit's own document cannot reach inside a components.html iframe
components.html(page, height=PANE_HEIGHT, scrolling=False)

# ── the same document through doc-to-struct ──────────────────────────────────
struct = load_doc_struct(patient_id, doc_id)

st.markdown(section("Doc → struct, same document"), unsafe_allow_html=True)

if struct is None:
    st.info("Set D2S_DIR above to compare the doc-to-struct output for this document "
            "(one file per patient, keyed by docId, as doc_to_struct.run_test writes it).")
elif not struct:
    st.caption("Doc-to-struct returned no sections for this document.")
else:
    points = sum(len(v) for v in struct.values())
    struct_page, struct_cited = document_struct_page(doc_text, events, struct,
                                                     dark=is_dark())
    st.caption(
        f"{points} data point(s) across {len(struct)} section(s) · "
        f"{struct_cited} carry a line citation · the left pane switches between the "
        "document and the date events; the document's highlights are the data points"
    )
    components.html(struct_page, height=PANE_HEIGHT, scrolling=False)

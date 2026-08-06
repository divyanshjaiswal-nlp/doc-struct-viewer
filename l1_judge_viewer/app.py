"""
L1 / judge viewer -- one L1 record at a time, with the judge's verdict beside it.

Pick a patient, an entity and a record. The left column pairs each of the record's date
fields with the judge's verdict on it (ENTITY_FIELDS["dates"] maps judge role -> L1
field, which is the join). The right column holds the documents behind it, tabbed into
the ones L1 cited and the ones the judge matched in, with citations highlighted in place.

Paths (L1_DIR, DATE_EVENTS_DIR, RESULTS_DIR, PATIENT_DATA_DIR) come from .env and are
editable in the "Paths" expander at the top.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

from config import ENTITY_FIELDS, EVIDENCE_KEYS
from highlight_text import document_page
from loader import (
    DIR_VARS,
    claim_rows,
    clear_cache,
    list_entities,
    load_doc,
    load_l1,
    load_results,
)
from styles import CSS, claim_card, crumb, field_table, header, reason_items, section

st.set_page_config(page_title="L1 date-claim review", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

EMPTY = {"", "n/a", "na", "none", "null"}
VERDICT_FULL = {
    "TP": "True Positive",
    "FP": "False Positive",
    "FN": "False Negative",
    "TN": "True Negative",
}


def show(value: Any) -> str:
    """A field value as one readable line. Returns '' when there is nothing to show."""
    if value is None or isinstance(value, bool):
        return "" if value is None else str(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "" if value.strip().lower() in EMPTY else value.strip()
    if isinstance(value, list):
        parts = [show(v) for v in value]
        return ", ".join(p for p in parts if p)
    if isinstance(value, dict):
        parts = [f"{k}: {show(v)}" for k, v in value.items() if show(v)]
        return " | ".join(parts)
    return str(value)


def render_field_table(record: dict[str, Any], configured: dict) -> None:
    """The record's identity and context fields in one table. Empty fields are dropped."""
    rows = [
        (field, show(record.get(field)))
        for field in list(configured["identity"]) + list(configured["extra"])
        if field in record and show(record.get(field))
    ]
    if rows:
        st.html(field_table(rows))
    else:
        st.caption("No identity or detail fields set on this record.")


# `(CHUNK_IDs: 3f2a, 91bc)` markers L1 leaves inside its reasoning. Zero, one or many per
# string, so every occurrence is removed rather than just the first.
CHUNK_IDS = re.compile(r"\(\s*CHUNK_IDs?\s*:[^)]*\)", re.IGNORECASE)


def strip_chunk_ids(text: str) -> str:
    """Drop the chunk-id markers, then close up the whitespace they leave behind."""
    return re.sub(r"[ \t]{2,}", " ", CHUNK_IDS.sub("", text)).strip()


def render_l1_reasoning(record: dict[str, Any]) -> None:
    """L1's own reasoning map, chunk ids stripped."""
    raw = record.get("reasoning")

    # stored as a JSON string (utils_ehealth.py:359), but tolerate a plain dict or text
    reasoning: Any = raw
    if isinstance(raw, str) and raw.strip():
        try:
            reasoning = json.loads(raw)
        except json.JSONDecodeError:
            reasoning = {"reasoning": raw}

    if isinstance(reasoning, dict):
        items = [(key, strip_chunk_ids(show(value))) for key, value in reasoning.items()]
    elif isinstance(reasoning, str) and reasoning.strip():
        items = [("reasoning", strip_chunk_ids(reasoning))]
    else:
        items = []

    items = [(key, text) for key, text in items if text]
    if not items:
        st.caption("No reasoning on this record.")
        return

    st.html(reason_items(items))


def render_claims(record: dict[str, Any], configured: dict | None,
                  judge_rows: list[dict[str, Any]], unjudged: list[str],
                  results_note: str) -> None:
    """
    One card per claim: what L1 said, and what the judge made of it, together.

    ENTITY_FIELDS["dates"] maps the judge's role -> L1's field name, which is what lets
    the two sides be paired instead of read in separate panels.

    Only claims that need review are drawn: every FP, every FN, and a TP confirmed at
    month or year granularity. Exact TPs and TNs are counted and reported, not rendered.
    """
    if not configured:
        return

    by_role = {row.get("role"): row for row in judge_rows}
    unjudged_roles = {cid.split("#")[-1].replace("_", " ") for cid in unjudged}

    shown = hidden = 0

    for role, field in configured["dates"].items():
        if field not in record:
            continue

        row = by_role.get(role)

        # Only the claims worth looking at. An exact TP and a TN are both "nothing to see
        # here" -- the date was confirmed on the day claimed, or nothing was claimed and
        # nothing found. What is left is every FP, every FN, and a TP confirmed only at
        # month or year granularity, where the document never gave the day L1 asserts.
        # Skipped entirely when there are no results at all, since then the filter would
        # hide every claim and the panel would look broken rather than empty.
        if not results_note:
            is_true_negative = row is None and role not in unjudged_roles
            is_exact_tp = bool(row) and row.get("verdict") == "TP" and row.get("match_tier") == "exact"
            if is_true_negative or is_exact_tp:
                hidden += 1
                continue

        shown += 1
        aside = ""
        if not row:
            aside = ("pass 2 did not run for this patient" if role in unjudged_roles
                     else results_note or "no date claimed, and none found")

        fields = [(f"L1 {field}", show(record.get(field)), "date")]
        if row:
            fields.append(("Date event evidence", row.get("matched_date") or "", "date"))
            if row.get("docId"):
                # the docId is how you find this document in the Date event evidence tab,
                # so it stays in full rather than being reduced to type + date
                fields += [
                    ("Doc ID", row["docId"], "doc"),
                    ("Doc", f"{row.get('doctype') or '?'}  ·  {row.get('docDate') or '—'}", "doc"),
                ]

        st.html(claim_card(
            role, fields,
            reasoning=(row or {}).get("reasoning") or "",
            matched_text=(row or {}).get("matched_text") or "",
            aside=aside,
        ))

    # only when there is nothing at all, so a blank column does not read as a failure
    if hidden and not shown:
        st.caption(f"Nothing to review — all {hidden} claim(s) here are exact TP or TN.")


def collect_docs(
    record: dict[str, Any], judge_rows: list[dict[str, Any]]
) -> tuple[dict[str, list[tuple[dict, str]]], dict[str, list[tuple[dict, str]]]]:
    """
    (L1's cited documents, the judge's matched documents), each docId -> [(citation, note)].

    Kept apart rather than pooled so the two can sit side by side: when L1 cites one
    document and the judge matched a different one, that is exactly the comparison you
    want on screen at the same time.
    """
    l1: dict[str, list[tuple[dict, str]]] = {}
    judge: dict[str, list[tuple[dict, str]]] = {}

    evidence = next((record[k] for k in EVIDENCE_KEYS if isinstance(record.get(k), list)), []) or []
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        doc_id = entry.get("docId") or "(no docId)"
        for citation in entry.get("citations") or []:
            if isinstance(citation, dict) and (citation.get("text") or "").strip():
                l1.setdefault(doc_id, []).append((citation, "L1 evidence"))

    for row in judge_rows or []:
        doc_id = row.get("docId")
        text = (row.get("matched_text") or "").strip()
        if doc_id and text:
            note = f"{row.get('role') or '?'} · {VERDICT_FULL.get(row.get('verdict'), '?')}"
            judge.setdefault(doc_id, []).append(({"text": text}, note))

    return l1, judge


def render_doc_panel(title: str, docs: dict[str, list[tuple[dict, str]]],
                     patient_id: str, height: int = 420) -> None:
    """One side of the document comparison: picker, jump pills, highlighted text."""
    if not docs:
        st.caption("Nothing on this side.")
        return

    options = {f"{key}  ·  {len(value)} citation(s)": key for key, value in docs.items()}
    # the title doubles as the widget key, so the two panels never collide
    doc_id = options[st.selectbox(title, list(options), index=0, label_visibility="collapsed")]
    citations = [citation for citation, _ in docs[doc_id]]
    notes = [note for _, note in docs[doc_id]]

    doc = load_doc(patient_id, doc_id) if os.environ.get("PATIENT_DATA_DIR", "").strip() else None
    doc_text = (doc or {}).get("docText") or ""

    if not doc_text:
        st.caption(
            f"No document text for this docId."
            if os.environ.get("PATIENT_DATA_DIR", "").strip()
            else "Set PATIENT_DATA_DIR above to see the document text."
        )
        for number, citation in enumerate(citations, start=1):
            text = show(citation.get("text"))
            if text:
                st.caption(f"citation {number} · {notes[number - 1]}")
                st.text(text)  # literal -- citation text carries markdown
        return

    page, located = document_page(doc_text, citations, notes)
    numbers = [number for number, _ in located]
    missing = [n for n in range(1, len(citations) + 1) if n not in numbers]

    st.caption(
        f"{doc.get('docType') or '?'} · {doc.get('docDate') or '?'} · "
        f"{len(numbers)}/{len(citations)} highlighted"
        + (f" · not located: {', '.join(map(str, missing))}" if missing else "")
    )

    # scrolling=False on purpose: the iframe itself must never scroll. Its body is
    # overflow:hidden and the inner .scroll pane is the only scrollable thing, which is
    # what keeps a citation jump from moving the app page. See PAGE_CSS and PAGE_JS.
    components.html(page, height=height, scrolling=False)

    if missing:
        with st.expander(f"{len(missing)} not found in this text"):
            for number in missing:
                st.caption(f"citation {number} · {notes[number - 1]}")
                st.text(show(citations[number - 1].get("text")) or "(no text)")


# ── controls, all inline at the top ──────────────────────────────────────────
st.markdown(
    header("L1 date-claim review", "L1 output vs the date→events index, per record"),
    unsafe_allow_html=True,
)

with st.expander("Paths", expanded=not os.environ.get("L1_DIR", "").strip()):
    changed = False
    for col, var in zip(st.columns(len(DIR_VARS)), DIR_VARS):
        label = var + (" (optional)" if var == "PATIENT_DATA_DIR" else "")
        value = col.text_input(label, value=os.environ.get(var, ""), key=f"dir_{var}")
        if value != os.environ.get(var, ""):
            os.environ[var] = value
            changed = True
    if changed:
        clear_cache()

    if st.button("Reload from disk"):
        clear_cache()
        st.rerun()

# Patient / entity / record share one row. The entity and record boxes are written into
# their columns further down, once the patient's output has actually been loaded.
top_id, top_entity, top_record = st.columns([2, 2, 3])
patient_id = top_id.text_input("Patient ID", key="patient_id", placeholder="paste a patient id")

if not os.environ.get("L1_DIR", "").strip():
    st.error("Set L1_DIR above (or in .env).")
    st.stop()

patient_id = (patient_id or "").strip()
if not patient_id:
    st.info("Enter a Patient ID to begin.")
    st.stop()

# ── load ─────────────────────────────────────────────────────────────────────
try:
    json_path, smd = load_l1(patient_id)
except Exception as exc:
    st.error(f"Failed to load L1 output: {exc}")
    st.stop()

entities = list_entities(smd)
if not entities:
    st.warning("standardMedicalData has no non-empty entity lists.")
    st.stop()

entity_labels = {f"{key}  ({count})": key for key, count in entities}
entity_key = entity_labels[top_entity.selectbox("Entity", list(entity_labels), index=0)]
records = smd[entity_key]
configured = ENTITY_FIELDS.get(entity_key)


def record_label(idx: int, record: Any) -> str:
    """`#0 — Rituximab`. The index keeps it unique when two records share a name."""
    if not isinstance(record, dict) or not configured:
        return f"#{idx}"
    name = next((show(record.get(f)) for f in configured["identity"] if show(record.get(f))), "")
    return f"#{idx} — {name}" if name else f"#{idx}"


record_labels = {record_label(i, r): i for i, r in enumerate(records)}
picked = top_record.selectbox(f"Record — {len(records)} in list", list(record_labels), index=0)
record = records[record_labels[picked]]

st.markdown(crumb(patient_id, entity_key, picked, json_path), unsafe_allow_html=True)
if configured is None:
    st.info(f"`{entity_key}` has no field config yet — open the raw record below. "
            "Add it to config.py to control which keys appear.")

# ── the selected record ──────────────────────────────────────────────────────
if not isinstance(record, dict):
    st.write(record)
    st.stop()

# loaded before the columns: the judge's matched docIds feed the evidence picker too
judge_rows: list[dict[str, Any]] = []
judge_unjudged: list[str] = []
results, results_note = None, ""

if not os.environ.get("RESULTS_DIR", "").strip():
    results_note = "Set RESULTS_DIR above to see judge verdicts."
else:
    try:
        results = load_results(patient_id)
    except Exception as exc:
        results_note = f"Failed to read results: {exc}"

    if results is None:
        results_note = f"No results file for `{patient_id}` in RESULTS_DIR."
    elif results.get("error"):
        results_note = f"The judge failed for this patient: {results['error']}"
    else:
        judge_rows, judge_unjudged = claim_rows(results, entity_key, record_labels[picked])

l1_docs, judge_docs = collect_docs(record, judge_rows)
record_col, evidence_col = st.columns([5, 6])

with record_col:
    st.markdown(section("Record & verdicts"), unsafe_allow_html=True)

    if configured:
        render_field_table(record, configured)

    if results_note:
        st.caption(results_note)
    render_claims(record, configured, judge_rows, judge_unjudged, results_note)

    with st.expander("Raw record JSON", expanded=configured is None):
        # the place to find keys worth adding to `extra` in config.py
        st.json({k: v for k, v in record.items() if k not in EVIDENCE_KEYS}, expanded=2)

with evidence_col:
    st.markdown(section("Evidence"), unsafe_allow_html=True)

    l1_tab, event_tab, reason_tab = st.tabs(
        [f"L1 cited ({len(l1_docs)})", f"Date event evidence ({len(judge_docs)})", "L1 reasoning"]
    )
    with l1_tab:
        render_doc_panel("L1 cited documents", l1_docs, patient_id, height=520)
    with event_tab:
        render_doc_panel("Date event evidence documents", judge_docs, patient_id, height=520)
    with reason_tab:
        render_l1_reasoning(record)

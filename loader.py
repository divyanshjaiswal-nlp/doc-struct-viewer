"""Data layer: every filesystem / JSON read for the viewer lives here.

Two folders feed the app:

  OUTPUT_DIR/                      <- you pick this
    <subfolder>/                   <- dropdown 1  (a run / strategy)
      <patient_id>.json            <- dropdown 2  ({ "<doc_id>": <response>, ... })
      *_metric*.json / *results*   <- ignored (not patients)

  RAW_DIR/
    <patient_id>.json              <- { "documents": [ {docId, docText, ...}, ... ] }

`<response>` is { "<section_key>": [ datapoint, ... ] }, where each datapoint is
{ text, keywords, citations:[{start,end}], sources, secondary_sections }.

Read pattern:
  output    = load_patient_output(...)        # once per patient  (cached)
  raw_docs  = load_raw_docs(..., doc_ids)      # once per patient  (cached, filtered)
  doc       = raw_docs.get(doc_id)             # selecting a doc is just a dict lookup

All loaders are cached with st.cache_data, keyed by their arguments. The sidebar's
"Reload from disk" button calls st.cache_data.clear() to pick up new files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


import streamlit as st


# --- output side (the structured LLM results) -------------------------------

@st.cache_data(show_spinner=False)
def list_subfolders(output_dir: str) -> list[str]:
    """Immediate subfolders of the output dir — each is one run / strategy."""
    root = Path(output_dir)
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if d.is_dir())


@st.cache_data(show_spinner=False)
def list_patient_ids(output_dir: str, subfolder: str) -> list[str]:
    """Patient ids in a subfolder = the *.json filenames, minus metric/results files."""
    folder = Path(output_dir) / subfolder
    if not folder.is_dir():
        return []
    return sorted(
        f.stem
        for f in folder.glob("*.json")
        if "metric" not in f.name and "results" not in f.name
    )


@st.cache_data(show_spinner=False)
def load_patient_output(output_dir: str, subfolder: str, patient_id: str) -> dict[str, Any]:
    """The whole patient file: { "<doc_id>": <response>, ... }."""
    path = Path(output_dir) / subfolder / f"{patient_id}.json"
    with path.open() as f:
        return json.load(f)


# --- raw side (the original document text the citations point into) ----------

@st.cache_data(show_spinner=False)
def load_raw_docs(
    raw_dir: str, patient_id: str, doc_ids: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    """Read the patient's raw file ONCE and return only the requested docs,
    keyed by docId.

    Called once per patient with the doc ids from the output. Cached on
    (raw_dir, patient_id, doc_ids), so selecting different doc ids in the UI is a
    plain `.get(doc_id)` on the returned dict — no extra disk reads, and we never
    hold documents that weren't processed.
    """
    path = Path(raw_dir) / f"{patient_id}.json"
    if not path.exists():
        return {}
    wanted = set(doc_ids)
    with path.open() as f:
        data = json.load(f)
    return {
        d["docId"]: d
        for d in data.get("documents", [])
        if d.get("docId") in wanted
    }

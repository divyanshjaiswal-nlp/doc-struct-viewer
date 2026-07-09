"""Streamlit viewer: raw docText + every doc-to-struct strategy output, side-by-side on one page."""
from __future__ import annotations

import os
from typing import Any

import streamlit as st

from loader import (
    clear_cache,
    get_raw_doc_text,
    list_doc_ids,
    list_strategy_folders,
    load_strategy_doc,
)

st.set_page_config(page_title="Doc-Struct Viewer", layout="wide")


def render_sections(sections: dict[str, list[dict[str, Any]]]) -> None:
    if not sections:
        st.info("Empty output (no sections)")
        return
    for section_key, chunks in sections.items():
        st.subheader(section_key)
        if not isinstance(chunks, list):
            st.write(chunks)
            continue
        parts = [str(c.get("text", "")) for c in chunks if isinstance(c, dict)]
        body = "\n\n".join(p for p in parts if p)
        if body:
            st.markdown(body)
        else:
            st.caption("(no text)")


with st.sidebar:
    st.markdown("### Paths")
    raw_dir = st.text_input("RAW_DIR", value=os.environ.get("RAW_DIR", ""))
    llm_dir = st.text_input("LLM_DIR", value=os.environ.get("LLM_DIR", ""))
    if raw_dir != os.environ.get("RAW_DIR") or llm_dir != os.environ.get("LLM_DIR"):
        os.environ["RAW_DIR"] = raw_dir
        os.environ["LLM_DIR"] = llm_dir
        clear_cache()

    st.markdown("### Inputs")
    patient_id = st.text_input("Patient ID", value=st.session_state.get("patient_id", ""))
    st.session_state["patient_id"] = patient_id

    if st.button("Reload from disk"):
        clear_cache()
        st.rerun()

if not raw_dir or not llm_dir:
    st.error("Set RAW_DIR and LLM_DIR in the sidebar (or in .env).")
    st.stop()

if not patient_id:
    st.info("Enter a Patient ID in the sidebar to begin.")
    st.stop()

try:
    doc_ids = list_doc_ids(patient_id)
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()
except Exception as e:
    st.error(f"Failed to load patient: {e}")
    st.stop()

if not doc_ids:
    st.warning("No documents found for this patient.")
    st.stop()

with st.sidebar:
    doc_id = st.selectbox("Doc ID", doc_ids, index=0)

st.title(f"Patient {patient_id} — Doc {doc_id}")

folders = list_strategy_folders()
if not folders:
    st.warning("No strategy folders found under LLM_DIR.")
    st.stop()

PANEL_HEIGHT = 800

raw_col, llm_col = st.columns(2)

with raw_col:
    st.header("Raw docText")
    with st.container(height=PANEL_HEIGHT, border=True):
        raw_text = get_raw_doc_text(patient_id, doc_id)
        if raw_text:
            st.text(raw_text)
        else:
            st.info("No raw docText found.")

with llm_col:
    st.header("LLM outputs")
    for folder in folders:
        st.markdown(f"#### {folder}")
        with st.container(height=PANEL_HEIGHT, border=True):
            try:
                sections = load_strategy_doc(folder, patient_id, doc_id)
            except Exception as e:
                st.error(f"Failed to load {folder}: {e}")
                continue

            if sections is None:
                st.info("No output for this patient/doc.")
            else:
                render_sections(sections)

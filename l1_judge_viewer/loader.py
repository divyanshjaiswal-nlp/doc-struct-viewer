"""
Filesystem loaders for the L1 / judge viewer.

Four directories, all set in .env and overridable from the sidebar:

    L1_DIR          one FOLDER per patient (folder name = patient id), holding a single
                    json whose filename is the L0 job id, not the patient id
    DATE_EVENTS_DIR merged date -> events index, <patient_id>.json          (later stage)
    RESULTS_DIR     judge output, <patient_id>_results.json                 (later stage)
    PATIENT_DATA_DIR raw documents, <patient_id>.json                       (optional)
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config import ENTITY_ORDER

load_dotenv(Path(__file__).parent / ".env")

DIR_VARS = ("L1_DIR", "DATE_EVENTS_DIR", "RESULTS_DIR", "PATIENT_DATA_DIR")


def get_dir(var: str, required: bool = True) -> Path | None:
    value = os.environ.get(var, "").strip()
    if not value:
        if required:
            raise RuntimeError(f"{var} is not set")
        return None
    return Path(value)


# ── L1 output ────────────────────────────────────────────────────────────────
def list_patient_ids() -> list[str]:
    """Patient ids = the folder names under L1_DIR."""
    l1 = get_dir("L1_DIR")
    if not l1.exists():
        raise FileNotFoundError(f"L1_DIR does not exist: {l1}")
    return sorted(p.name for p in l1.iterdir() if p.is_dir())


@lru_cache(maxsize=64)
def _load_l1_cached(l1_dir: str, patient_id: str) -> tuple[str, dict[str, Any]]:
    folder = Path(l1_dir) / patient_id
    if not folder.is_dir():
        raise FileNotFoundError(f"No folder for patient {patient_id} under {l1_dir}")

    files = sorted(folder.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No json inside {folder}")

    with files[0].open(encoding="utf-8") as f:
        data = json.load(f)

    return str(files[0]), data


def load_l1(patient_id: str) -> tuple[str, dict[str, Any]]:
    """(path of the json that was read, its standardMedicalData)."""
    path, data = _load_l1_cached(str(get_dir("L1_DIR")), patient_id)
    smd = data.get("jobOutputData", data).get("standardMedicalData", {})
    return path, smd if isinstance(smd, dict) else {}


def list_entities(standard_medical_data: dict[str, Any]) -> list[tuple[str, int]]:
    """[(entity_key, record_count)] for entities that actually have records.

    Configured entities first in ENTITY_ORDER, then anything else in the output, so a
    key we have not configured yet is still reachable rather than silently dropped.
    """
    counts = {
        key: len(value)
        for key, value in standard_medical_data.items()
        if isinstance(value, list) and value
    }
    known = [(k, counts[k]) for k in ENTITY_ORDER if k in counts]
    other = sorted((k, v) for k, v in counts.items() if k not in ENTITY_ORDER)
    return known + other


# ── judge results ────────────────────────────────────────────────────────────
@lru_cache(maxsize=64)
def _load_results_cached(results_dir: str, patient_id: str) -> dict[str, Any] | None:
    base = Path(results_dir)
    for name in (f"{patient_id}_results.json", f"{patient_id}.json"):
        path = base / name
        if path.exists():
            with path.open(encoding="utf-8") as f:
                return json.load(f)
    return None


def load_results(patient_id: str) -> dict[str, Any] | None:
    """The judge output for one patient, or None when RESULTS_DIR is unset / no file."""
    results_dir = get_dir("RESULTS_DIR", required=False)
    if results_dir is None:
        return None
    return _load_results_cached(str(results_dir), patient_id)


def claim_rows(
    results: dict[str, Any] | None, entity_key: str, record_idx: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    (verdict rows, unjudged claim ids) for ONE L1 record.

    claim_id is "<ENTITY_KEY>#<record_idx>#<role>", so a prefix match ties results back
    to the record without needing to know the judge's role names.
    """
    prefix = f"{entity_key}#{record_idx}#"
    results = results or {}

    rows = [
        row for row in results.get("rows", []) or []
        if str(row.get("claim_id", "")).startswith(prefix)
    ]
    unjudged = [
        cid for cid in results.get("unjudged_claim_ids", []) or []
        if str(cid).startswith(prefix)
    ]
    return rows, unjudged


# ── raw documents ────────────────────────────────────────────────────────────
@lru_cache(maxsize=4)
def _load_patient_docs_cached(patient_data_dir: str, patient_id: str) -> dict[str, Any]:
    """{docId: document}. Small maxsize -- these blobs carry every doc's full text."""
    path = Path(patient_data_dir) / f"{patient_id}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {
        str(doc.get("docId")): doc
        for doc in data.get("documents", []) or []
        if isinstance(doc, dict) and doc.get("docId")
    }


def load_doc(patient_id: str, doc_id: str) -> dict[str, Any] | None:
    """One raw document, or None when PATIENT_DATA_DIR is unset / the doc is missing."""
    patient_data_dir = get_dir("PATIENT_DATA_DIR", required=False)
    if patient_data_dir is None:
        return None
    return _load_patient_docs_cached(str(patient_data_dir), patient_id).get(doc_id)


def clear_cache() -> None:
    _load_l1_cached.cache_clear()
    _load_results_cached.cache_clear()
    _load_patient_docs_cached.cache_clear()

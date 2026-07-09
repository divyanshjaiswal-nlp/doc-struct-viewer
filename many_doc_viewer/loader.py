"""Filesystem loaders for the doc-struct viewer."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _raw_dir() -> Path:
    val = os.environ.get("RAW_DIR")
    if not val:
        raise RuntimeError("RAW_DIR is not set")
    return Path(val)


def _llm_dir() -> Path:
    val = os.environ.get("LLM_DIR")
    if not val:
        raise RuntimeError("LLM_DIR is not set")
    return Path(val)


@lru_cache(maxsize=128)
def _load_patient_raw_cached(raw_dir: str, patient_id: str) -> dict[str, Any]:
    path = Path(raw_dir) / f"{patient_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Raw patient file not found: {path}")
    with path.open() as f:
        return json.load(f)


def load_patient_raw(patient_id: str) -> dict[str, Any]:
    return _load_patient_raw_cached(str(_raw_dir()), patient_id)


def list_doc_ids(patient_id: str) -> list[str]:
    data = load_patient_raw(patient_id)
    docs = data.get("documents", [])
    return [d["docId"] for d in docs if "docId" in d]


def get_raw_doc(patient_id: str, doc_id: str) -> dict[str, Any] | None:
    data = load_patient_raw(patient_id)
    for d in data.get("documents", []):
        if d.get("docId") == doc_id:
            return d
    return None


def get_raw_doc_text(patient_id: str, doc_id: str) -> str:
    doc = get_raw_doc(patient_id, doc_id)
    if doc is None:
        return ""
    return doc.get("docText", "") or ""


def list_strategy_folders() -> list[str]:
    llm = _llm_dir()
    if not llm.exists():
        return []
    return sorted(p.name for p in llm.iterdir() if p.is_dir())


@lru_cache(maxsize=256)
def _load_strategy_patient_cached(
    llm_dir: str, folder: str, patient_id: str
) -> dict[str, Any] | None:
    path = Path(llm_dir) / folder / f"{patient_id}.json"
    if not path.exists():
        return None
    with path.open() as f:
        return json.load(f)


def load_strategy_doc(
    folder: str, patient_id: str, doc_id: str
) -> dict[str, list[dict[str, Any]]] | None:
    """Return {section_key: [chunk, ...]} for one doc under one strategy, or None."""
    patient_blob = _load_strategy_patient_cached(str(_llm_dir()), folder, patient_id)
    if patient_blob is None:
        return None
    return patient_blob.get(doc_id)


def clear_cache() -> None:
    _load_patient_raw_cached.cache_clear()
    _load_strategy_patient_cached.cache_clear()

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
from date_text import IS_KEY, as_key

load_dotenv(Path(__file__).parent / ".env")

DIR_VARS = ("L1_DIR", "DATE_EVENTS_DIR", "DATE_EVENTS_RAW_DIR", "RESULTS_DIR",
            "PATIENT_DATA_DIR", "D2S_DIR", "ONCO_L1_DIR", "MERGED_ANCHOR_DIR")

# Split per page, so each page's Paths expander shows only what that page reads.
# PATIENT_DATA_DIR is in both -- one setting, one widget key, shown on both pages.
L1_DIR_VARS = ("L1_DIR", "DATE_EVENTS_DIR", "RESULTS_DIR", "PATIENT_DATA_DIR")
DATE_EVENTS_DIR_VARS = ("DATE_EVENTS_RAW_DIR", "PATIENT_DATA_DIR", "D2S_DIR")
ONCO_DIR_VARS = ("ONCO_L1_DIR", "MERGED_ANCHOR_DIR")


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


# ── merged date -> events index ──────────────────────────────────────────────
@lru_cache(maxsize=8)
def _load_merged_cached(merged_dir: str, patient_id: str) -> dict[str, Any]:
    path = Path(merged_dir) / f"{patient_id}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_merged_index(patient_id: str) -> dict[str, Any]:
    """{date: [{text, citations, docId, docDate, doctype}]} for one patient."""
    merged_dir = get_dir("DATE_EVENTS_DIR", required=False)
    return {} if merged_dir is None else _load_merged_cached(str(merged_dir), patient_id)


def merged_citations(patient_id: str, date: str, text: str, doc_id: str) -> list[dict]:
    """
    The line citations behind one judge match.

    The judge returns `matched_text` and a docId but no citations -- it never sees them.
    They live in the merged index, so the line ranges are recovered by matching the
    verbatim text back to its entry. A paraphrased match finds nothing and simply gets no
    highlight, which is honest: we do not know which lines it came from.
    """
    if not (date and text and doc_id):
        return []

    for entry in load_merged_index(patient_id).get(date) or []:
        if entry.get("docId") == doc_id and (entry.get("text") or "") == text:
            return entry.get("citations") or []
    return []


# ── date -> events, BEFORE the merge ─────────────────────────────────────────
# One file per patient holding every document separately:
#     {doc_id: {"<ISO date>": [{"text":.., "citations":[{"start","end"}]}, ...]}}
# The merged index (DATE_EVENTS_DIR) has already pooled the documents together, so this
# is the only place a citation can still be tied to the document it was read from.
# Not every json in there is a patient: the grounding judge writes its own output
# alongside them. Anything carrying one of these markers is skipped as a patient file and
# read as judge output instead.
_NON_PATIENT = ("grounding", "result", "metric")


def _is_patient_file(stem: str) -> bool:
    return not any(marker in stem.lower() for marker in _NON_PATIENT)


def list_raw_patients() -> list[str]:
    raw_dir = get_dir("DATE_EVENTS_RAW_DIR", required=False)
    if raw_dir is None or not raw_dir.exists():
        return []
    return sorted(p.stem for p in raw_dir.glob("*.json") if _is_patient_file(p.stem))


@lru_cache(maxsize=16)
def _load_raw_cached(raw_dir: str, patient_id: str) -> dict[str, Any]:
    path = Path(raw_dir) / f"{patient_id}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_raw_date_events(patient_id: str) -> dict[str, Any]:
    """{doc_id: {date: [event, ...]}} for one patient, bookkeeping keys removed.

    A document with NO extracted events is kept, mapping to an empty dict. It used to be
    dropped, which hid it from the picker entirely -- and a document the extractor found
    nothing in is one of the more interesting ones to open.
    """
    raw_dir = get_dir("DATE_EVENTS_RAW_DIR", required=False)
    if raw_dir is None:
        return {}

    return {
        str(doc_id): {k: v for k, v in dates.items()
                      if k not in {"response_status", "raw_output"} and isinstance(v, list)}
        for doc_id, dates in _load_raw_cached(str(raw_dir), patient_id).items()
        if isinstance(dates, dict)
    }


# ── doc-to-struct output ─────────────────────────────────────────────────────
# doc_to_struct.run_test writes {source_doc_id: response} per patient, so the layout matches
# DATE_EVENTS_RAW_DIR exactly: <patient_id>.json, keyed by docId, values keyed by section.
@lru_cache(maxsize=16)
def _load_struct_cached(struct_dir: str, patient_id: str) -> dict[str, Any]:
    path = Path(struct_dir) / f"{patient_id}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def load_doc_struct(patient_id: str, doc_id: str) -> dict[str, Any] | None:
    """
    {section: [data_point, ...]} for ONE document.

    None when D2S_DIR is unset or the document is not in the patient's file; an empty dict
    when the document is there but produced no sections. The page needs that difference to
    say "not configured" rather than "nothing extracted".
    """
    struct_dir = get_dir("D2S_DIR", required=False)
    if struct_dir is None:
        return None

    doc = _load_struct_cached(str(struct_dir), patient_id).get(str(doc_id))
    if not isinstance(doc, dict):
        return None

    return {key: value for key, value in doc.items()
            if key not in {"response_status", "raw_output"} and isinstance(value, list)}


# ── grounding judge verdicts ─────────────────────────────────────────────────
# date_to_events_grounding_judge.py writes next to the per-patient files, so there is no
# extra path to configure. Every non-patient json in the directory is read, in name order,
# which means grounding_results_v2 overrides grounding_results wherever they overlap.
def norm_event_text(text: Any) -> str:
    """Whitespace-insensitive key.

    The judge is told to copy `text` back character-for-character and mostly does, but
    models reflow long strings. A lost newline should not lose the verdict.
    """
    return " ".join(str(text or "").split())


@lru_cache(maxsize=4)
def _load_grounding_cached(raw_dir: str) -> dict[tuple[str, str], dict[str, dict]]:
    """(patient_id, doc_id) -> {normalised event text: verdict}.

    A judged document with nothing wrong maps to an empty dict; a document the judge never
    saw is absent. Callers need that difference -- "clean" and "unchecked" look identical
    otherwise.
    """
    verdicts: dict[tuple[str, str], dict[str, dict]] = {}

    for path in sorted(Path(raw_dir).glob("*.json")):
        if _is_patient_file(path.stem):
            continue
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue

        for result in data.get("per_doc_results") or []:
            if not isinstance(result, dict):
                continue
            block = result.get("grounding")
            if not isinstance(block, dict) or "error" in block:
                continue

            flagged = verdicts.setdefault(
                (str(result.get("patient_id")), str(result.get("doc_id"))), {}
            )
            for row in block.get("wrong") or []:
                if isinstance(row, dict) and row.get("text"):
                    flagged[norm_event_text(row["text"])] = {
                        "unsupported": row.get("unsupported"),
                        "reason": row.get("reason"),
                    }

    return verdicts


def load_grounding(patient_id: str, doc_id: str) -> dict[str, dict] | None:
    """Verdicts for one document, or None when the judge never ran on it."""
    raw_dir = get_dir("DATE_EVENTS_RAW_DIR", required=False)
    if raw_dir is None:
        return None
    return _load_grounding_cached(str(raw_dir)).get((str(patient_id), str(doc_id)))


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


# ── oncology-history summary, and the merged date-anchor index ───────────────
# Both of these are one-off runs rather than a standing pipeline output, so either path may
# be a DIRECTORY or a single json file -- the file you want is as often something you paste
# as it is a patient id inside a folder.
#
#   ONCO_L1_DIR        the L1 run holding the summary entity
#   MERGED_ANCHOR_DIR  the merged doc-to-struct date anchors, date -> the texts on it
def _json_for(base: Path, patient_id: str) -> Path | None:
    """The json holding this patient, whichever layout `base` is in."""
    if base.is_file():
        return base

    folder = base / patient_id
    if folder.is_dir():                      # a folder per patient, as L1_DIR is laid out
        files = sorted(folder.glob("*.json"))
        return files[0] if files else None

    exact = base / f"{patient_id}.json"
    if exact.exists():
        return exact

    # `<patient_id>_merged.json` and friends: named after the patient, with a suffix
    near = sorted(p for p in base.glob("*.json") if p.stem.startswith(patient_id))
    return near[0] if near else None


@lru_cache(maxsize=32)
def _load_json_cached(path: str) -> Any:
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def list_onco_patients() -> list[str]:
    """Patient ids under ONCO_L1_DIR -- folder names, file stems, or the one file itself."""
    base = get_dir("ONCO_L1_DIR", required=False)
    if base is None or not base.exists():
        return []
    if base.is_file():
        return [base.stem]

    folders = sorted(p.name for p in base.iterdir() if p.is_dir())
    return folders or sorted(p.stem for p in base.glob("*.json"))


def _standard_medical_data(data: Any) -> dict[str, Any]:
    """
    `standardMedicalData`, wherever this file keeps it.

    Falls back to the object itself, so a file that already IS the entity map -- a single
    entity exported on its own -- still opens instead of reading as empty.
    """
    if not isinstance(data, dict):
        return {}

    inner = data.get("jobOutputData")
    if isinstance(inner, dict):
        data = inner

    smd = data.get("standardMedicalData")
    return smd if isinstance(smd, dict) else data


def load_onco(patient_id: str) -> tuple[str, dict[str, Any]]:
    """(path read, its standardMedicalData). Raises when the patient has no file."""
    base = get_dir("ONCO_L1_DIR")
    path = _json_for(base, patient_id)
    if path is None:
        raise FileNotFoundError(f"No json for {patient_id} under {base}")
    return str(path), _standard_medical_data(_load_json_cached(str(path)))


# The key holding the prose. `summary` is what oncology_history_v3 writes; the others are
# there so a renamed field does not read as "this entity has no summary".
SUMMARY_KEYS = ("summary", "summaryText", "historySummary", "text")


def _summary_of(record: Any) -> str:
    if isinstance(record, str):
        return record.strip()
    if isinstance(record, dict):
        for key in SUMMARY_KEYS:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def summary_blocks(value: Any) -> list[tuple[str, str]]:
    """
    [(label, summary text)] for one entity's value.

    A list of records gives one block each -- an entity may hold more than one summary, and
    concatenating them would hide which prose came from which record. Empty when the entity
    carries no summary at all, which is how `list_summary_entities` filters.
    """
    if isinstance(value, list):
        blocks = [(f"#{index}", _summary_of(record)) for index, record in enumerate(value)]
        return [(label, text) for label, text in blocks if text]

    text = _summary_of(value)
    return [("summary", text)] if text else []


def list_summary_entities(standard_medical_data: dict[str, Any]) -> list[str]:
    """Every entity carrying a text summary, the oncology history first.

    Nothing here comes from config.py: this page is for an entity whose schema is not
    configured, so the entity is found by the shape of its records instead.
    """
    keys = [key for key, value in standard_medical_data.items() if summary_blocks(value)]
    return sorted(keys, key=lambda key: (0 if "oncology_history" in key.lower() else 1, key))


def list_merged_files() -> list[Path]:
    """Every json MERGED_ANCHOR_DIR offers, for the fallback picker."""
    base = get_dir("MERGED_ANCHOR_DIR", required=False)
    if base is None or not base.exists():
        return []
    return [base] if base.is_file() else sorted(base.glob("*.json"))


def merged_anchor_file(patient_id: str) -> Path | None:
    """The merged file for this patient, or None when the name does not line up."""
    base = get_dir("MERGED_ANCHOR_DIR", required=False)
    if base is None or not base.exists():
        return None
    return _json_for(base, patient_id)


def load_merged_anchors(path: str) -> Any:
    return _load_json_cached(str(path))


def _first(item: dict, *keys: str) -> str:
    """The first of these keys the entry actually carries.

    Both spellings turn up: `doc_id` from the merge script, `docId` from the pipeline's own
    output. Reading one and not the other loses the document silently.
    """
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _entries(value: Any, doc_id: str = "") -> list[dict[str, Any]]:
    """One date's entries, whether the merge wrote plain strings or objects."""
    items = value if isinstance(value, list) else [value]
    entries = []

    for item in items:
        if isinstance(item, str) and item.strip():
            entries.append({"text": item.strip(), "docId": doc_id})
        elif isinstance(item, dict):
            text = next((item[key] for key in ("text", "event", "summary")
                         if isinstance(item.get(key), str) and item[key].strip()), "")
            if text:
                entries.append({
                    "text": text.strip(),
                    "docId": _first(item, "docId", "doc_id") or doc_id,
                    "docType": _first(item, "docType", "doc_type"),
                    "docDate": _first(item, "docDate", "doc_date"),
                })

    return entries


def merged_anchor_groups(data: Any, newest_first: bool = False) -> list[dict[str, Any]]:
    """
    The merged anchors as [{key, label, entries}], one group per date, in date order.

    Written to tolerate the shapes the merge can land in, since it is assembled by hand:
    `{date: [text, ...]}`, `{date: [{text, docId}, ...]}`, and `{docId: {date: [...]}}`.
    A date appearing in three documents is ONE group either way -- that pooling is the
    whole point of keying by date.
    """
    buckets: dict[str, list[dict[str, Any]]] = {}
    labels: dict[str, str] = {}

    def add(raw_key: Any, value: Any, doc_id: str = "") -> None:
        key = as_key(raw_key)
        labels.setdefault(key, str(raw_key))
        buckets.setdefault(key, []).extend(_entries(value, doc_id))

    if isinstance(data, dict):
        for raw_key, value in data.items():
            if IS_KEY.match(as_key(raw_key)):
                add(raw_key, value)
            elif isinstance(value, dict):
                # keyed by document first, dates inside; bookkeeping keys are not dates and
                # fall out on their own
                for inner_key, inner in value.items():
                    if IS_KEY.match(as_key(inner_key)):
                        add(inner_key, inner, str(raw_key))

    # ISO keys sort chronologically as plain strings; anything unparseable goes last rather
    # than being dropped, so a malformed key is visible instead of missing
    ordered = sorted(buckets, key=lambda key: (0 if IS_KEY.match(key) else 1, key))

    if newest_first:
        # only the dates flip -- an unparseable key stays at the end, where it is noticed
        dates = [key for key in ordered if IS_KEY.match(key)]
        ordered = dates[::-1] + [key for key in ordered if not IS_KEY.match(key)]

    return [{"key": key, "label": labels[key], "entries": buckets[key]} for key in ordered]


def clear_cache() -> None:
    _load_json_cached.cache_clear()
    _load_l1_cached.cache_clear()
    _load_results_cached.cache_clear()
    _load_patient_docs_cached.cache_clear()
    _load_raw_cached.cache_clear()
    _load_merged_cached.cache_clear()
    _load_grounding_cached.cache_clear()
    _load_struct_cached.cache_clear()

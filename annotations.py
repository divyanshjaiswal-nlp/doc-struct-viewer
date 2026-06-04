"""Annotation store: the reviewer feedback CSV + citation-string helpers.

One CSV, one row per annotated datapoint, keyed by
(run, patient_id, doc_id, section, dp_index). A row exists only when the reviewer
has written a comment and/or a corrected citation; clearing both removes the row.

Columns:
    run, patient_id, doc_id, section, dp_index, text,
    original_cites, comment, corrected_cites

Citations are stored as compact strings ("12-15;20"); use parse_citations() to
turn a reviewer's typed correction back into [{start,end}] objects.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

FIELDS = [
    "run", "patient_id", "doc_id", "section", "dp_index",
    "text", "original_cites", "comment", "corrected_cites",
]

Key = Tuple[str, str, str, str, str]  # (run, patient_id, doc_id, section, dp_index)

# numbers joined by a dash / en-dash / "to" / ".." / ":" form a range
_RANGE = re.compile(r"(\d+)\s*(?:-|–|—|to|\.\.|:)\s*(\d+)")


def parse_citations(text: str) -> List[Dict[str, int]]:
    """Parse a reviewer's typed citation like '12-15, 20, 22 to 24' into
    [{start,end}] objects. Unparseable tokens are skipped (best-effort)."""
    cites: List[Dict[str, int]] = []
    for tok in re.split(r"[,;\n]+", text or ""):
        tok = tok.strip()
        if not tok:
            continue
        m = _RANGE.search(tok)
        if m:
            s, e = int(m.group(1)), int(m.group(2))
        else:
            nums = re.findall(r"\d+", tok)
            if not nums:
                continue
            s = e = int(nums[0]) if len(nums) == 1 else None
            if len(nums) >= 2:
                s, e = int(nums[0]), int(nums[1])
        if e < s:
            s, e = e, s
        cites.append({"start": s, "end": e})
    return cites


def cites_to_str(citations) -> str:
    """[{start,end}] -> compact '12-15;20' for CSV cells and placeholders."""
    parts: List[str] = []
    for c in citations or []:
        if not isinstance(c, dict):
            continue
        try:
            s, e = int(c["start"]), int(c["end"])
        except (KeyError, TypeError, ValueError):
            continue
        parts.append(str(s) if s == e else f"{s}-{e}")
    return ";".join(parts)


def load_annotations(path: str) -> Dict[Key, Dict[str, Any]]:
    """Read the whole CSV into { key: row }. Empty/missing file -> {}."""
    out: Dict[Key, Dict[str, Any]] = {}
    p = Path(path)
    if not p.exists():
        return out
    with p.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key: Key = (
                row.get("run", ""), row.get("patient_id", ""), row.get("doc_id", ""),
                row.get("section", ""), row.get("dp_index", ""),
            )
            out[key] = row
    return out


def save_annotation(
    path: str, key: Key, *, text: str, original_cites: str,
    comment: str, corrected_cites: str,
) -> None:
    """Upsert one datapoint's feedback (load-modify-write the whole CSV).

    If both comment and corrected citation are blank, the row is removed so the
    file only holds datapoints the team actually flagged."""
    data = load_annotations(path)
    comment = (comment or "").strip()
    corrected = (corrected_cites or "").strip()
    if not comment and not corrected:
        data.pop(key, None)
    else:
        data[key] = {
            "run": key[0], "patient_id": key[1], "doc_id": key[2],
            "section": key[3], "dp_index": key[4],
            "text": text, "original_cites": original_cites,
            "comment": comment, "corrected_cites": corrected,
        }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for row in data.values():
            w.writerow({k: row.get(k, "") for k in FIELDS})

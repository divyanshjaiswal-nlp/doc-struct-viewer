"""
Where documents live on disk.

    permanent   OUTPUT_DIR/<key>/<patient_id>/<source_document_id>.<ext>
                plus a _manifest.json beside the files
    view cache  VIEW_CACHE_DIR/<key>/<patient_id>/<source_document_id>.<ext>

Viewing writes to the cache; Save writes to OUTPUT_DIR. A document already in the
permanent store is never re-fetched -- it is read straight from there.

Only the calling thread ever touches _manifest.json. The worker threads download and
nothing else, so there is no write contention on it.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import blob
import config

MANIFEST_NAME = "_manifest.json"
UNKNOWN_PATIENT = "_no_patient_id"

_UNSAFE = re.compile(r"[^A-Za-z0-9._@-]+")


def _segment(value: Any, fallback: str) -> str:
    """One path component. Ids should already be tame; this makes sure of it."""
    text = _UNSAFE.sub("_", str(value or "").strip()).strip("._")
    return text or fallback


def doc_id_of(row: dict[str, Any]) -> str:
    """
    The id a file is named by: the document reference id, since that is the id people
    actually hold. Falls back to the source document's own id, then its db_id.

    Two references can point at one source document, so file names are not unique per
    blob -- _fetch_grouped downloads each distinct blob once and copies it to the rest.
    """
    for field in ("tmx_document_reference_id", "source_document_id", "db_id"):
        value = str(row.get(field) or "").strip()
        if value:
            return value
    return ""


def blob_path_of(row: dict[str, Any]) -> str:
    """The blob holding this document. blob_path is the only column used."""
    return str(row.get("blob_path") or "").strip()


def filename_of(row: dict[str, Any]) -> str:
    return f"{_segment(doc_id_of(row), 'document')}.{config.extension_for(row)}"


def embedded_sibling(path: Path, extension: str) -> Path:
    """
    A document extracted from inside another one -- the base64 PDF an HL7 CDA can
    carry in <nonXMLBody>. Named alongside its container rather than as a plain
    <doc_id>.pdf, so it can never collide with a genuine PDF row.
    """
    return path.with_suffix(f".embedded.{extension}")


# ── the two roots ────────────────────────────────────────────────────────────
def patient_dir(root: Path, key: str, row: dict[str, Any]) -> Path:
    return root / _segment(key, "key") / _segment(row.get("patient_id"), UNKNOWN_PATIENT)


def permanent_path(key: str, row: dict[str, Any]) -> Path | None:
    """None when OUTPUT_DIR is unset -- viewing works, saving does not."""
    root = config.output_dir()
    if root is None:
        return None
    return patient_dir(root, key, row) / filename_of(row)


def cache_path(key: str, row: dict[str, Any]) -> Path:
    return patient_dir(config.view_cache_dir(), key, row) / filename_of(row)


def local_copy(key: str, row: dict[str, Any]) -> tuple[Path | None, str]:
    """(path, origin) where origin is 'saved', 'cache' or '' when not local yet."""
    saved = permanent_path(key, row)
    if saved is not None and blob.present(saved):
        return saved, "saved"
    cached = cache_path(key, row)
    if blob.present(cached):
        return cached, "cache"
    return None, ""


def is_saved(key: str, row: dict[str, Any]) -> bool:
    saved = permanent_path(key, row)
    return saved is not None and blob.present(saved)


# ── fetching ─────────────────────────────────────────────────────────────────
def _fetch_grouped(
    jobs: Sequence[tuple[str, str, Path]],
    on_done: Callable[[str, str | None], None] | None = None,
) -> dict[str, str | None]:
    """
    Fetch each distinct blob once, then copy it to every other destination that wants
    it. Two document references pointing at one source document share a blob but get
    their own file name, so without this the same bytes would be pulled twice.

    jobs     (job_id, blob_path, dest) triples
    returns  {job_id: None on success, else the error}
    """
    by_blob: dict[str, list[tuple[str, Path]]] = {}
    for job_id, blob_path, dest in jobs:
        by_blob.setdefault(blob_path, []).append((job_id, dest))

    leads = [(targets[0][0], blob_path, targets[0][1])
             for blob_path, targets in by_blob.items()]
    fetched = blob.fetch_many(leads)

    results: dict[str, str | None] = {}
    for blob_path, targets in by_blob.items():
        lead_id, lead_dest = targets[0]
        error = fetched.get(lead_id)
        results[lead_id] = error
        if on_done is not None:
            on_done(lead_id, error)

        for job_id, dest in targets[1:]:
            if error is None:
                try:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(lead_dest, dest)
                    results[job_id] = None
                except OSError as exc:
                    results[job_id] = str(exc)
            else:
                results[job_id] = error
            if on_done is not None:
                on_done(job_id, results[job_id])

    return results


def _fetch_into(row: dict[str, Any], dest: Path, conn=None) -> Path:
    """
    One document to one destination. Prefers the blob; falls back to the legacy
    file_content large object for rows that predate blob storage.
    """
    if blob.present(dest):
        return dest

    path = blob_path_of(row)
    if path:
        return blob.fetch(path, dest)

    oid = row.get("file_content")
    if oid and conn is not None:
        import db  # local import: store.py stays importable without a database

        return db.fetch_large_object(conn, int(oid), dest)

    raise blob.BlobError(
        f"document {doc_id_of(row)} has neither a blob path nor a readable file_content"
    )


def ensure_for_view(key: str, row: dict[str, Any], conn=None) -> Path:
    """Local path for a document, fetching it into the view cache if need be."""
    path, _ = local_copy(key, row)
    if path is not None:
        return path
    return _fetch_into(row, cache_path(key, row), conn=conn)


def ensure_all_for_view(
    key: str,
    rows: Sequence[dict[str, Any]],
    conn=None,
    on_done: Callable[[str, str | None], None] | None = None,
) -> dict[str, str | None]:
    """
    Every document of a patient into the view cache in one pass, so clicking through
    the dropdown afterwards is pure local reads.

    Blob-backed rows go through the parallel pool; the handful of legacy large-object
    rows are done on this thread, since they are database reads and not azcopy calls.
    Returns {document id: None on success, else the error}.
    """
    results: dict[str, str | None] = {}
    parallel: list[tuple[str, str, Path]] = []
    serial: list[dict[str, Any]] = []

    for row in rows:
        doc_id = doc_id_of(row)
        path, _ = local_copy(key, row)
        if path is not None:
            results[doc_id] = None
            if on_done is not None:
                on_done(doc_id, None)
            continue
        if blob_path_of(row):
            parallel.append((doc_id, blob_path_of(row), cache_path(key, row)))
        else:
            serial.append(row)

    if parallel:
        results.update(_fetch_grouped(parallel, on_done=on_done))

    for row in serial:
        doc_id = doc_id_of(row)
        try:
            _fetch_into(row, cache_path(key, row), conn=conn)
            error = None
        except Exception as exc:
            error = str(exc)
        results[doc_id] = error
        if on_done is not None:
            on_done(doc_id, error)

    return results


# ── saving permanently ───────────────────────────────────────────────────────
def save(
    key: str,
    rows: Sequence[dict[str, Any]],
    conn=None,
    on_done: Callable[[str, str | None], None] | None = None,
) -> dict[str, str | None]:
    """
    Put documents in the permanent store and record them in _manifest.json. A copy
    already sitting in the view cache is moved across rather than downloaded again.
    """
    root = config.output_dir()
    if root is None:
        raise blob.BlobError("OUTPUT_DIR is not set, so there is nowhere to save to.")

    results: dict[str, str | None] = {}
    to_fetch: list[tuple[str, str, Path]] = []
    by_id: dict[str, dict[str, Any]] = {}
    saved_rows: list[tuple[dict[str, Any], Path]] = []

    for row in rows:
        doc_id = doc_id_of(row)
        by_id[doc_id] = row
        dest = permanent_path(key, row)
        if dest is None:
            continue

        if blob.present(dest):
            results[doc_id] = None
            saved_rows.append((row, dest))
            if on_done is not None:
                on_done(doc_id, None)
            continue

        cached = cache_path(key, row)
        if blob.present(cached):
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cached, dest)
            # an embedded document extracted while viewing travels with its container
            for extra in cached.parent.glob(f"{cached.stem}.embedded.*"):
                shutil.copy2(extra, dest.parent / extra.name)
            results[doc_id] = None
            saved_rows.append((row, dest))
            if on_done is not None:
                on_done(doc_id, None)
            continue

        path = blob_path_of(row)
        if path:
            to_fetch.append((doc_id, path, dest))
        else:
            try:
                _fetch_into(row, dest, conn=conn)
                results[doc_id] = None
                saved_rows.append((row, dest))
                error = None
            except Exception as exc:
                results[doc_id] = str(exc)
                error = str(exc)
            if on_done is not None:
                on_done(doc_id, error)

    if to_fetch:
        fetched = _fetch_grouped(to_fetch, on_done=on_done)
        results.update(fetched)
        for doc_id, error in fetched.items():
            if error is None:
                dest = permanent_path(key, by_id[doc_id])
                if dest is not None:
                    saved_rows.append((by_id[doc_id], dest))

    if saved_rows:
        record(key, saved_rows)
    return results


# ── the manifest ─────────────────────────────────────────────────────────────
def manifest_path(key: str, row: dict[str, Any]) -> Path | None:
    root = config.output_dir()
    if root is None:
        return None
    return patient_dir(root, key, row) / MANIFEST_NAME


def read_manifest(key: str, row: dict[str, Any]) -> dict[str, Any]:
    path = manifest_path(key, row)
    if path is None or not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def record(key: str, saved_rows: Iterable[tuple[dict[str, Any], Path]]) -> None:
    """
    Merge saved documents into the patient's _manifest.json. Read-modify-write on the
    calling thread only, so concurrent downloads cannot corrupt it.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    by_manifest: dict[Path, list[tuple[dict[str, Any], Path]]] = {}

    for row, path in saved_rows:
        manifest = manifest_path(key, row)
        if manifest is not None:
            by_manifest.setdefault(manifest, []).append((row, path))

    for manifest, entries in by_manifest.items():
        data = {}
        if manifest.is_file():
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}

        first_row = entries[0][0]
        data.setdefault("key", key)
        data["tenant_id"] = first_row.get("tenant_id") or data.get("tenant_id")
        data["patient_id"] = first_row.get("patient_id") or data.get("patient_id")
        data["patient_mrn"] = first_row.get("patient_mrn") or data.get("patient_mrn")
        documents = data.setdefault("documents", {})

        for row, path in entries:
            try:
                size = path.stat().st_size
            except OSError:
                size = None
            extras = sorted(p.name for p in path.parent.glob(f"{path.stem}.embedded.*"))
            documents[doc_id_of(row)] = {
                # both ids, so a saved file can be traced back either way
                "source_document_id": row.get("source_document_id"),
                "db_id": row.get("db_id"),
                "reference_db_id": row.get("reference_db_id"),
                "mime_type": row.get("mime_type"),
                "file": path.name,
                "blob_path": blob_path_of(row),
                "bytes": size,
                "downloaded_at": now,
                **({"embedded_files": extras} if extras else {}),
            }

        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(data, indent=2, sort_keys=True, default=str), encoding="utf-8"
        )


def clear_view_cache() -> None:
    cache = config.view_cache_dir()
    if cache.exists():
        shutil.rmtree(cache, ignore_errors=True)

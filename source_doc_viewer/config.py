"""
Configuration for the source-document viewer.

Two halves, both local to this folder and both kept out of git:

    db_config.py   the map of DB keys -> connection details (it holds passwords).
                   Copy db_config.example.py and fill it in.
    dotenv file    blob-storage settings and the two directories on disk.

MEDIA_TYPE_TO_DOC_FORMAT_MAP below is a COPY of the one in
nlp_backend/common/constants.py, not an import. Importing anything under
nlp_backend.common evaluates get_prism_schema() at import time (db_models.py calls it
in a class body) and the pipeline runners start vLLM health checks, so a viewer that
imported it would need the whole backend's environment to boot. The map is eleven
lines and changes about never; l1_judge_viewer/config.py copies the judge's
ENTITY_CONFIG for the same reason.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# ── mime type -> document format ─────────────────────────────────────────────
MEDIA_TYPE_TO_DOC_FORMAT_MAP = {
    "text/plain": "TXT",
    "application/text": "TXT",
    "text/rtf": "RTF",
    "text/html": "HTML",
    "application/xml": "XML",
    "text/xml": "XML",
    "application/pdf": "PDF",
    "image/tiff": "TIFF",
    "application/octet-stream": "BIN",
    "image/jpeg": "JPEG",
    "image/png": "PNG",
}

UNKNOWN_FORMAT = "BIN"

# Reverse direction, for handing a sensible Content-Type to the browser download
# button when all we know is the format.
FORMAT_TO_MEDIA_TYPE = {
    "TXT": "text/plain",
    "RTF": "text/rtf",
    "HTML": "text/html",
    "XML": "application/xml",
    "PDF": "application/pdf",
    "TIFF": "image/tiff",
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "BIN": "application/octet-stream",
}


def doc_format(mime_type: str | None) -> str | None:
    """Format name ('PDF', 'XML', ...) for a mime type, or None when unmapped."""
    if not mime_type:
        return None
    return MEDIA_TYPE_TO_DOC_FORMAT_MAP.get(str(mime_type).strip().lower())


def row_format(row: dict[str, Any]) -> str:
    """
    Format for a document row: its mime_type, else the legacy source_document_type
    column (which already holds 'PDF'/'XML'/... rather than a mime type), else BIN.
    """
    fmt = doc_format(row.get("mime_type"))
    if fmt:
        return fmt
    legacy = str(row.get("source_document_type") or "").strip().upper()
    return legacy or UNKNOWN_FORMAT


def extension_for(row: dict[str, Any]) -> str:
    """
    Filename extension for a document row.

    Lowercasing the format name is exactly what the backend does when it stages a
    source document -- db_utils.get_single_source_document_from_integration_database
    writes f"{source_document_id}.{source_document_type.lower()}" -- so a file saved
    by this viewer is named the same as the pipeline's own copy.
    """
    return row_format(row).lower()


def media_type_for(row: dict[str, Any]) -> str:
    """Content-Type for the browser download button."""
    mime = str(row.get("mime_type") or "").strip()
    if mime:
        return mime
    return FORMAT_TO_MEDIA_TYPE.get(row_format(row), "application/octet-stream")


# ── environment ──────────────────────────────────────────────────────────────
def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def output_dir() -> Path | None:
    """Permanent store. None when unset -- viewing still works, saving does not."""
    value = _env("OUTPUT_DIR")
    return Path(value).expanduser() if value else None


def view_cache_dir() -> Path:
    """
    Throw-away copies made only to render something. Defaults under the system temp
    dir on purpose: these are patient documents, and the permanent store should be
    the only place they persist by intent.
    """
    value = _env("VIEW_CACHE_DIR")
    if value:
        return Path(value).expanduser()
    return Path(tempfile.gettempdir()) / "source_doc_view_cache"


def storage_account() -> str:
    return _env("STORAGE_ACCOUNT")


def container_name() -> str:
    return _env("CONTAINER_NAME")


def sas_token() -> str:
    """Accepted with or without the leading '?'."""
    return os.environ.get("SAS_TOKEN", "").strip().lstrip("?")


def workers() -> int:
    try:
        count = int(_env("WORKERS", "8"))
    except ValueError:
        count = 8
    return max(1, min(count, 32))


def azcopy_bin() -> str:
    return _env("AZCOPY_BIN") or "azcopy"


def azcopy_available() -> bool:
    return shutil.which(azcopy_bin()) is not None


PANEL_HEIGHT = 900

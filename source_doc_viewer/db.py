"""
Read-only Postgres access for the source-document viewer.

The lookup drives from **tmx_document_reference** and joins out to
**patient_source_document**, because the document id people actually hold is
`tmx_document_reference.tmx_document_reference_id`, while the blob lives on the
source-document row:

    tmx_document_reference.fk_patient_source_document_db_id  ->  patient_source_document.db_id

The join is a LEFT JOIN on purpose. `fk_patient_source_document_db_id` is nullable, so
a document reference with no source document behind it still appears in the list and
is reported as unviewable, rather than vanishing from a patient's document count.

Column names collide across the two tables (both have db_id, tenant_id, patient_id,
created_on, metadata), so every column is selected explicitly and aliased. Identity --
patient_id, patient_mrn, tenant_id -- is taken from the reference table, which is the
driving side and always present.

One connection per DB key, cached for the life of the Streamlit process and opened
with default_transaction_read_only so the viewer cannot write even by accident. The
connection wrapper mirrors nlp_backend/common/db_connector.py (psycopg 3, dict rows,
autocommit); the reconnect-if-closed guard is from apps/response_viewer/pkg/vector_db.py.

Values always travel as query parameters. The backend's own SQL interpolates them into
f-strings -- that is not copied here.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import psycopg
import streamlit as st
from psycopg.rows import dict_row

REFERENCE_TABLE = "tmx_document_reference"
SOURCE_TABLE = "patient_source_document"

# (real column, alias) from tmx_document_reference, in display order.
# Note `patientmrn` -- that column genuinely has no underscore, unlike
# patient_source_document.patient_mrn.
REFERENCE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("tmx_document_reference_id", "tmx_document_reference_id"),
    ("patient_id", "patient_id"),
    ("patientmrn", "patient_mrn"),
    ("tenant_id", "tenant_id"),
    ("date", "document_date"),
    ("tmx_document_reference_type", "document_type"),
    ("tmx_document_reference_category", "document_category"),
    ("tmx_document_reference_sub_type", "document_sub_type"),
    ("tmx_document_reference_tag", "document_tag"),
    ("author", "author"),
    ("author_department", "author_department"),
    ("author_role", "author_role"),
    ("relevancy", "relevancy"),
    ("db_id", "reference_db_id"),
    ("fk_patient_source_document_db_id", "fk_patient_source_document_db_id"),
)

# (real column, alias) from patient_source_document. Identity columns are omitted --
# they come from the reference table above. Aliases stay equal to the column names so
# config.py, store.py and render.py keep reading `mime_type`, `blob_path`, `db_id`
# and friends unchanged.
SOURCE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("db_id", "db_id"),
    ("source_document_id", "source_document_id"),
    ("mime_type", "mime_type"),
    ("source_document_type", "source_document_type"),
    ("blob_path", "blob_path"),
    ("is_generated_pdf", "is_generated_pdf"),
    ("style_sheet", "style_sheet"),
    ("facility_name", "facility_name"),
    ("case_id", "case_id"),
    ("processing_status", "processing_status"),
    ("processed_at", "processed_at"),
    ("failure_reason", "failure_reason"),
    ("file_hash", "file_hash"),
    ("file_content", "file_content"),
    ("source_document_attributes", "source_document_attributes"),
    ("metadata", "metadata"),
    ("created_on", "created_on"),
)

# Aliases in the order the details plate should show them.
DISPLAY_COLUMNS: tuple[str, ...] = tuple(
    alias for _, alias in (*REFERENCE_COLUMNS, *SOURCE_COLUMNS)
)

_SAFE_IDENT = re.compile(r"^[A-Za-z0-9_]+$")


class ConfigError(RuntimeError):
    """The viewer's own configuration is wrong, as opposed to the database."""


# ── db_config.py ─────────────────────────────────────────────────────────────
def load_db_configs() -> dict[str, dict[str, str]]:
    try:
        from db_config import DB_CONFIGS
    except ModuleNotFoundError as exc:
        if exc.name != "db_config":
            raise
        raise ConfigError(
            "db_config.py not found. Copy db_config.example.py to db_config.py and "
            "fill in your keys."
        ) from exc
    except ImportError as exc:
        raise ConfigError(f"db_config.py has no DB_CONFIGS map: {exc}") from exc

    if not isinstance(DB_CONFIGS, dict) or not DB_CONFIGS:
        raise ConfigError("DB_CONFIGS in db_config.py is empty.")

    for key, cfg in DB_CONFIGS.items():
        missing = [f for f in ("conninfo", "dbname", "schema") if not str(cfg.get(f, "")).strip()]
        if missing:
            raise ConfigError(f"DB_CONFIGS['{key}'] is missing: {', '.join(missing)}")
    return DB_CONFIGS


def validated_schema(schema: str) -> str:
    schema = str(schema).strip()
    if not _SAFE_IDENT.match(schema):
        raise ConfigError(
            f"schema {schema!r} is not a plain identifier -- letters, digits and "
            "underscores only."
        )
    return schema


# ── connections ──────────────────────────────────────────────────────────────
@st.cache_resource(show_spinner=False)
def _open(key: str, conninfo: str, dbname: str) -> psycopg.Connection:
    return psycopg.connect(
        conninfo=conninfo,
        dbname=dbname,
        row_factory=dict_row,
        autocommit=True,
        # a viewer has no business writing; this makes that structural
        options="-c default_transaction_read_only=on",
    )


def connect(key: str, cfg: dict[str, str]) -> psycopg.Connection:
    conn = _open(key, cfg["conninfo"], cfg["dbname"])
    if conn.closed:
        _open.clear()
        conn = _open(key, cfg["conninfo"], cfg["dbname"])
    return conn


# ── schema introspection ─────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def table_columns(
    _conn: psycopg.Connection, key: str, schema: str, table: str
) -> frozenset[str]:
    """
    Every column a table actually has in this schema. Cached per (key, schema, table);
    _conn is excluded from the cache key by its leading underscore.
    """
    rows = _conn.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    ).fetchall()
    if not rows:
        raise ConfigError(f"{schema}.{table} not found (or not visible to this user).")
    return frozenset(r["column_name"] for r in rows)


def _select_list(
    alias_prefix: str, wanted: tuple[tuple[str, str], ...], present: frozenset[str]
) -> list[str]:
    """`tdr.date AS document_date` for every wanted column the table actually has."""
    return [
        f"{alias_prefix}.{column} AS {alias}"
        for column, alias in wanted
        if column in present
    ]


# ── the lookup ───────────────────────────────────────────────────────────────
def find_documents(
    conn: psycopg.Connection,
    key: str,
    cfg: dict[str, str],
    *,
    patient_id: str = "",
    mrn: str = "",
    doc_id: str = "",
) -> tuple[list[dict[str, Any]], str, bool]:
    """
    Look documents up by patient id, MRN, document id, or a patient/MRN narrowed to
    one document id -- all against tmx_document_reference, joined out to
    patient_source_document for the blob and its metadata.

    A document id is matched against `tmx_document_reference_id` OR the joined
    `source_document_id`, so pasting either kind of id finds the document.

    Returns (rows, sql_with_placeholders, tenant_filter_applied). When a tenant filter
    yields nothing the query is retried without it -- the tenant_id in db_config.py
    may be a label rather than the real column value, and a warning beats an empty
    page.
    """
    schema = validated_schema(cfg["schema"])
    ref_cols = table_columns(conn, key, schema, REFERENCE_TABLE)
    src_cols = table_columns(conn, key, schema, SOURCE_TABLE)

    selected = _select_list("tdr", REFERENCE_COLUMNS, ref_cols) + _select_list(
        "psd", SOURCE_COLUMNS, src_cols
    )
    if not selected:
        raise ConfigError(f"{schema}.{REFERENCE_TABLE} has none of the expected columns.")

    # psd's own deleted check belongs in the ON clause, not the WHERE -- in the WHERE
    # it would discard reference rows whose source document is absent, which is
    # exactly the case the LEFT JOIN exists to surface.
    join_on = ["psd.db_id = tdr.fk_patient_source_document_db_id"]
    if "deleted" in src_cols:
        join_on.append("psd.deleted IS NOT TRUE")

    where, params = [], []
    if patient_id:
        where.append("tdr.patient_id = %s")
        params.append(patient_id)
    if mrn:
        where.append("tdr.patientmrn = %s")
        params.append(mrn)
    if doc_id:
        if "source_document_id" in src_cols:
            where.append("(tdr.tmx_document_reference_id = %s OR psd.source_document_id = %s)")
            params.extend([doc_id, doc_id])
        else:
            where.append("tdr.tmx_document_reference_id = %s")
            params.append(doc_id)
    if not where:
        raise ConfigError("Enter a patient id, an MRN or a document id.")

    if "deleted" in ref_cols:
        where.append("tdr.deleted IS NOT TRUE")

    order_by = "tdr.date" if "date" in ref_cols else "tdr.tmx_document_reference_id"
    tenant_id = str(cfg.get("tenant_id") or "").strip()

    def build(with_tenant: bool) -> tuple[str, list[Any]]:
        clauses = list(where)
        values = list(params)
        if with_tenant and tenant_id and "tenant_id" in ref_cols:
            clauses.append("tdr.tenant_id = %s")
            values.append(tenant_id)
        sql = (
            f"SELECT {', '.join(selected)}\n"
            f"  FROM {schema}.{REFERENCE_TABLE} tdr\n"
            f"  LEFT JOIN {schema}.{SOURCE_TABLE} psd\n"
            f"    ON {' AND '.join(join_on)}\n"
            f" WHERE {' AND '.join(clauses)}\n"
            f" ORDER BY {order_by}"
        )
        return sql, values

    sql, values = build(with_tenant=True)
    rows = conn.execute(sql, values).fetchall()
    tenant_filtered = bool(tenant_id and "tenant_id" in ref_cols)

    if not rows and tenant_filtered:
        sql, values = build(with_tenant=False)
        rows = conn.execute(sql, values).fetchall()
        tenant_filtered = False

    return rows, sql, tenant_filtered


def has_source_document(row: dict[str, Any]) -> bool:
    """
    Whether this document reference actually resolved to a source-document row. False
    means the FK was null, or pointed at a row that is deleted or gone -- nothing to
    fetch and nothing to render.
    """
    return row.get("db_id") is not None


# ── large objects (legacy rows with file_content and no blob_path) ────────────
def fetch_large_object(conn: psycopg.Connection, oid: int, dest: Path) -> Path:
    """
    Materialise a Postgres large object to disk. Some rows predate blob storage and
    carry the document in file_content as an oid instead -- the legacy path in
    db_utils.get_source_documents_from_integration_database. lo_get() is tried first;
    the pg_largeobject scan is the fallback for servers that will not run it.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        row = conn.execute("SELECT lo_get(%s) AS data", (oid,)).fetchone()
        data = bytes(row["data"]) if row and row["data"] is not None else b""
    except psycopg.Error:
        chunks = conn.execute(
            "SELECT data FROM pg_catalog.pg_largeobject WHERE loid = %s ORDER BY pageno",
            (oid,),
        ).fetchall()
        data = b"".join(bytes(c["data"]) for c in chunks if c["data"] is not None)

    if not data:
        raise RuntimeError(f"large object {oid} is empty or unreadable")
    dest.write_bytes(data)
    return dest

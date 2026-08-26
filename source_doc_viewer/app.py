"""
Source-document viewer.

Pick a database key, enter a patient id, an MRN or a document id, and see the raw
source documents behind that patient rendered in their own format.

    patient id / MRN        every document for that patient, all of them fetched into
                            the view cache up front so the dropdown is instant
    patient id / MRN + doc  just that one document
    document id             just that one document, with its patient id and MRN

Fetching for a view is throw-away (VIEW_CACHE_DIR, under the system temp dir by
default). Save is the deliberate act that puts a copy in OUTPUT_DIR as
<key>/<patient_id>/<source_document_id>.<ext> and records it in _manifest.json.

Layout is two plates: the document on the left, its details on the right. The details
plate is the narrow one -- it holds short key/value rows, while a scanned page wants
every pixel. Everything cosmetic lives in styles.py.

    streamlit run app.py
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import streamlit as st

import blob
import config
import db
import render
import store
import styles

st.set_page_config(page_title="Source documents", layout="wide")
st.markdown(styles.CSS, unsafe_allow_html=True)
st.markdown(
    styles.header("Source documents", "raw source files behind a patient"),
    unsafe_allow_html=True,
)

MODES = ("Patient ID", "MRN", "Document ID")
HIDDEN_FIELDS = ("source_document_attributes", "metadata", "file_content")

# ids, paths, hashes and mime strings read better monospaced, and are the values
# allowed to break mid-token so they cannot widen the narrow plate
MONO_FIELDS = {
    "tmx_document_reference_id",
    "patient_id",
    "patient_mrn",
    "tenant_id",
    "reference_db_id",
    "fk_patient_source_document_db_id",
    "db_id",
    "source_document_id",
    "mime_type",
    "blob_path",
    "file_hash",
    "case_id",
}


# ── row helpers ──────────────────────────────────────────────────────────────
def attributes(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("source_document_attributes")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _attribute_date(attrs: dict[str, Any]) -> str:
    """documentDate is epoch seconds (see listener.py); milliseconds happen too."""
    value = attrs.get("documentDate")
    if value in (None, ""):
        return ""
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return str(value)
    if seconds > 1e11:
        seconds /= 1000.0
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return str(value)


def document_date(row: dict[str, Any]) -> str:
    """
    tmx_document_reference.date is a real timestamp, so prefer it. Fall back to the
    source document's own attributes, where the date is epoch seconds instead.
    """
    value = row.get("document_date")
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if value:
        return str(value)[:10]
    return _attribute_date(attributes(row))


def document_label(key: str, row: dict[str, Any]) -> str:
    kind = row.get("document_type") or row.get("document_category") or "—"
    fmt = config.row_format(row) if db.has_source_document(row) else "no source doc"
    parts = [
        "✔" if store.is_saved(key, row) else "○",
        document_date(row) or "no date",
        str(kind),
        fmt,
        store.doc_id_of(row),
    ]
    return "  ·  ".join(p for p in parts if p)


# ── sidebar: connection and lookup ───────────────────────────────────────────
DB_CONFIGS: dict[str, dict[str, str]] = {}
try:
    DB_CONFIGS = db.load_db_configs()
except db.ConfigError as exc:
    st.error(str(exc))
    st.stop()
except Exception as exc:
    # db_config.py is hand-edited, so a SyntaxError in it is a normal Tuesday
    st.error(f"db_config.py could not be loaded — {type(exc).__name__}: {exc}")
    st.stop()

with st.sidebar:
    st.html(styles.section("Connection"))
    key = st.selectbox("DB key", list(DB_CONFIGS), key="db_key", label_visibility="collapsed")
    cfg = DB_CONFIGS[key]
    # never show conninfo -- it holds the password
    st.html(styles.conn_summary(cfg.get("tenant_id", ""), cfg["dbname"], cfg["schema"]))

    st.html(styles.section("Look up"))
    mode = st.segmented_control("By", MODES, default=MODES[0], key="mode",
                                label_visibility="collapsed") or MODES[0]
    identifier = st.text_input(mode, key=f"ident_{mode}").strip()
    narrow = ""
    if mode != "Document ID":
        narrow = st.text_input("Document ID (optional)", key="narrow").strip()
    searched = st.button("Search", type="primary", width="stretch")

    # rendered here, above every early exit, so the diagnostics are on screen
    # precisely when a search has not worked yet
    st.html(styles.section("Environment"))
    st.html(
        '<div class="envline">'
        + styles.chip("azcopy", "ok" if config.azcopy_available() else "bad")
        + styles.chip("SAS token", "ok" if config.sas_token() else "bad")
        + styles.chip(f"{config.workers()} workers", "cool")
        + "</div>"
    )

token = json.dumps([key, mode, identifier, narrow])


# ── search ───────────────────────────────────────────────────────────────────
def run_search() -> dict[str, Any]:
    conn = db.connect(key, cfg)
    lookup = {"patient_id": "", "mrn": "", "doc_id": ""}
    if mode == "Patient ID":
        lookup["patient_id"] = identifier
    elif mode == "MRN":
        lookup["mrn"] = identifier
    else:
        lookup["doc_id"] = identifier
    if mode != "Document ID" and narrow:
        lookup["doc_id"] = narrow

    rows, sql, tenant_filtered = db.find_documents(conn, key, cfg, **lookup)

    errors: dict[str, str | None] = {}
    # references with no source document behind them have nothing to fetch; leaving
    # them out keeps the progress count honest instead of counting guaranteed failures
    fetchable = [r for r in rows if db.has_source_document(r)]
    if fetchable:
        total = len(fetchable)
        bar = st.progress(0.0, text=f"Fetching {total} document(s) for viewing…")
        finished = 0

        def on_done(doc_id: str, error: str | None) -> None:
            nonlocal finished
            finished += 1
            bar.progress(min(finished / total, 1.0), text=f"Fetched {finished}/{total}")

        errors = store.ensure_all_for_view(key, fetchable, conn=conn, on_done=on_done)
        bar.empty()

    return {
        "token": token,
        "rows": rows,
        "sql": sql,
        "tenant_filtered": tenant_filtered,
        "errors": errors,
    }


if searched and not identifier:
    st.warning(f"Enter {'an' if mode == 'MRN' else 'a'} {mode.lower()} to search for.")

if identifier and (searched or st.session_state.get("result", {}).get("token") != token):
    try:
        st.session_state["result"] = run_search()
    except (db.ConfigError, blob.BlobError) as exc:
        st.session_state.pop("result", None)
        st.error(str(exc))
        st.stop()
    except Exception as exc:  # a database that will not answer
        st.session_state.pop("result", None)
        st.error(f"Lookup failed: {exc}")
        st.stop()

result = st.session_state.get("result")
if not result or result["token"] != token:
    st.info("Pick a DB key in the sidebar, then enter a patient id, an MRN or a document id.")
    st.stop()

rows: list[dict[str, Any]] = result["rows"]
if not rows:
    st.warning("No documents matched.")
    st.stop()

if cfg.get("tenant_id") and not result["tenant_filtered"]:
    st.warning(
        f"Nothing matched with `tenant_id = {cfg['tenant_id']}`, so the filter was "
        "dropped — these rows may belong to another tenant in this schema."
    )


# ── identity strip and document picker ───────────────────────────────────────
first = rows[0]
saved_count = sum(1 for r in rows if store.is_saved(key, r))
unlinked = [r for r in rows if not db.has_source_document(r)]
cells = [
    ("patient", str(first.get("patient_id") or ""), "mono"),
    ("mrn", str(first.get("patient_mrn") or ""), "mono"),
    ("documents", str(len(rows)), "plain"),
    ("saved", f"{saved_count} of {len(rows)}", "plain"),
]
if unlinked:
    cells.append(("no source doc", str(len(unlinked)), "plain"))
st.html(styles.strip(cells))

choice = st.selectbox(
    "Document",
    range(len(rows)),
    format_func=lambda i: document_label(key, rows[i]),
    key=f"doc_{token}",
    label_visibility="collapsed",
)
row = rows[choice]
doc_id = store.doc_id_of(row)


# ── the two plates ───────────────────────────────────────────────────────────
doc_pane, meta_pane = st.columns([2, 1], gap="medium")

with doc_pane:
    with st.container(border=True):
        if not db.has_source_document(row):
            st.html(styles.plate_head("no source document",
                                      styles.chip("unlinked", "warn")))
            st.info(
                "This document reference has no source document behind it — "
                "`fk_patient_source_document_db_id` is "
                f"`{row.get('fk_patient_source_document_db_id')}`, which resolved to "
                "nothing. There is no file to show, but the reference's own fields are "
                "in the details plate."
            )
        else:
            path, origin = store.local_copy(key, row)
            if path is None:
                try:
                    with st.spinner("Fetching…"):
                        path = store.ensure_for_view(key, row, conn=db.connect(key, cfg))
                    origin = "cache"
                except Exception as exc:
                    st.error(f"Could not fetch this document: {exc}")
                    path = None

            st.html(
                styles.plate_head(
                    config.row_format(row),
                    styles.chip("saved", "ok") if origin == "saved" else
                    styles.chip("session copy", "cool") if origin == "cache" else
                    styles.chip("not fetched", "bad"),
                )
            )
            if path is not None:
                render.show(path, row)

with meta_pane:
    with st.container(border=True):
        st.html(styles.plate_head("details"))
        fields = []
        for field in db.DISPLAY_COLUMNS:
            if field in HIDDEN_FIELDS or field not in row:
                continue
            value = row.get(field)
            fields.append(
                (field, "" if value is None else str(value),
                 "mono" if field in MONO_FIELDS else "")
            )
        if row.get("file_content"):
            fields.append(("file_content", f"large object {row['file_content']}", "mono"))
        st.html(styles.field_table(fields))

        attrs = attributes(row)
        if attrs:
            with st.expander("attributes"):
                st.json(attrs)
        if row.get("metadata"):
            with st.expander("metadata"):
                st.json(row["metadata"])
        if row.get("style_sheet"):
            st.caption(
                f"`{row['style_sheet']}` selects an HL7 section filter in the pipeline. "
                "It is not an XSLT and is not applied here."
            )


# ── below the plates: what went wrong, and what was asked ────────────────────
failed = [d for d, error in result["errors"].items() if error]
if failed:
    with st.expander(f"{len(failed)} document(s) could not be fetched"):
        for d in failed:
            st.write(f"`{d}` — {result['errors'][d]}")

with st.expander("Query"):
    st.code(result["sql"], language="sql")
    st.caption("Values are bound as parameters, not shown here.")


# ── sidebar: the permanent store ─────────────────────────────────────────────
def save(target_rows: list[dict[str, Any]], what: str) -> None:
    total = len(target_rows)
    bar = st.sidebar.progress(0.0, text=f"Saving {what}…")
    finished = 0

    def on_done(_doc_id: str, _error: str | None) -> None:
        nonlocal finished
        finished += 1
        bar.progress(finished / total, text=f"Saved {finished}/{total}")

    try:
        outcome = store.save(key, target_rows, conn=db.connect(key, cfg), on_done=on_done)
    except blob.BlobError as exc:
        bar.empty()
        st.sidebar.error(str(exc))
        return
    bar.empty()

    broken = {d: e for d, e in outcome.items() if e}
    if broken:
        st.sidebar.error(f"{len(broken)} of {total} failed: {next(iter(broken.values()))}")
    else:
        st.sidebar.success(f"Saved {what}.")
        st.rerun()


with st.sidebar:
    st.html(styles.section("Store"))
    output = config.output_dir()
    if output is None:
        st.caption("OUTPUT_DIR is not set, so nothing can be saved permanently.")
    else:
        st.html(f'<div class="conn">{output}</div>')
        # an unlinked reference has no blob, so saving it can only fail
        savable = [r for r in rows if db.has_source_document(r)]
        if st.button(
            "Save this document",
            width="stretch",
            disabled=store.is_saved(key, row) or not db.has_source_document(row),
        ):
            save([row], f"`{doc_id}`")
        unsaved = [r for r in savable if not store.is_saved(key, r)]
        if st.button(
            f"Save all {len(savable)} document(s)",
            width="stretch",
            disabled=not unsaved,
        ):
            save(savable, f"{len(savable)} document(s)")

    if st.button("Clear view cache", width="stretch"):
        store.clear_view_cache()
        st.rerun()

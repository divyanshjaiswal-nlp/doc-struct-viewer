# Source document viewer

Streamlit app for looking at the **raw source documents** behind a patient — the PDFs,
CDA XML, HTML and text files sitting in blob storage.

The lookup drives from **`tmx_document_reference`**, because that is where the document
id people actually hold lives, and joins out to **`patient_source_document`** for the
blob:

```
tmx_document_reference.fk_patient_source_document_db_id  →  patient_source_document.db_id
```

It is a LEFT JOIN on purpose: that FK is nullable, so a reference with no source
document behind it still shows up in the patient's list, labelled `no source doc`,
instead of silently dropping out of the count.

Enter one id and you get the documents:

| you enter | matched against | you get |
|---|---|---|
| **Patient ID** | `tmx_document_reference.patient_id` | every document for that patient. All of them are fetched up front, so clicking through the dropdown is instant |
| **MRN** | `tmx_document_reference.patientmrn` | the same list (note: that column really has no underscore) |
| **Document ID** | `tmx_document_reference_id` **or** `source_document_id` | just that one document, with its patient id and MRN beside it — paste either kind of id |
| **Patient ID / MRN** + **Document ID** | both | just that one document |

Each document is rendered in its own format — PDF as a PDF, HTML as HTML, XML as
syntax-highlighted source plus a text view, images as pages, RTF through pandoc.

Fetching for a view is **throw-away**: it lands in a cache under the system temp dir.
**Save** is the deliberate act that puts a copy in `OUTPUT_DIR` and records it, so a
document you have saved once opens instantly forever after and never downloads again.

## Setup

Two config files, both gitignored, both local to this folder.

**1. `db_config.py`** — the connections:

```bash
cp db_config.example.py db_config.py   # then edit
```

```python
DB_CONFIGS = {
    "my_key": {
        "tenant_id": "",          # "" to skip the tenant filter
        "conninfo": "user='readonly' password='...' host='localhost' port='5432'",
        "dbname":   "hope_integration",
        "schema":   "tmx_prism_trialfinder_integrations",
    },
}
```

The key is what shows up in the app's Connection dropdown. `conninfo` is a libpq
keyword/value string **without** `dbname` — that is passed separately, mirroring
`nlp_backend/common/db_connector.py`. Connections are opened with
`default_transaction_read_only`, but use a read-only DB user anyway.

**2. a dotenv file** — create `.env` in this folder with these variables (the tooling
would not let me commit a template for it, so this table is the template):

| variable | meaning |
|---|---|
| `OUTPUT_DIR` | where **Save** puts documents. Blank disables saving. |
| `VIEW_CACHE_DIR` | throw-away render copies. Blank → `<system temp>/source_doc_view_cache`. |
| `STORAGE_ACCOUNT` | Azure storage account holding the blobs. |
| `CONTAINER_NAME` | container that `blob_path` is relative to. |
| `SAS_TOKEN` | container-scoped SAS with read + list. Leading `?` optional. |
| `WORKERS` | azcopy processes in flight, default `8`. |
| `AZCOPY_BIN` | only if azcopy is not on `PATH`. |

```
OUTPUT_DIR=/home/you/source_docs
STORAGE_ACCOUNT=
CONTAINER_NAME=
SAS_TOKEN=
WORKERS=8
```

## Run

```bash
cd source_doc_viewer
conda activate backend
pip install -r requirements.txt   # only streamlit-pdf is missing from that env
streamlit run app.py          # .streamlit/config.toml pins port 8571
```

Then forward port **8571** off the bastion. The `backend` env already had everything
except **`streamlit-pdf`**, which `st.pdf` wraps and raises without. It is pinned
`<2` — 2.x needs a newer Streamlit than 1.57 and fails at import. If it is missing or
broken, PDFs still render: `render.py` falls back to PyMuPDF page images with a page
selector and zoom. The two system binaries are already on `PATH`: `azcopy` (required)
and `pandoc` (optional, for RTF).

## What lands on disk

```
OUTPUT_DIR/
└── my_key/                                 the DB key
    └── 4f2c-9a11-patient-uuid/             patient_id
        ├── _manifest.json
        ├── DOC-8831.pdf                    tmx_document_reference_id
        ├── DOC-9042.xml
        └── DOC-9042.embedded.pdf           PDF that was wrapped inside the XML
```

Filenames are `<tmx_document_reference_id>.<ext>` — the id you searched with — and the
extension is the lowercased document format, the same suffix the pipeline gives its own
staged copy (`db_utils.get_single_source_document_from_integration_database`).

Two references can point at one source document, so two files can hold the same bytes
under different names. The blob is still only downloaded **once**: `_fetch_grouped` in
`store.py` groups a batch by `blob_path`, fetches each distinct one, and copies it to
the other destinations.

`_manifest.json` records what was saved and when:

```json
{
  "key": "my_key",
  "tenant_id": "...",
  "patient_id": "...",
  "patient_mrn": "...",
  "documents": {
    "DOC-9042": {
      "source_document_id": "SRC-77",
      "db_id": 100234,
      "reference_db_id": 900412,
      "mime_type": "application/xml",
      "file": "DOC-9042.xml",
      "blob_path": "tenant/2024/09/9042.xml",
      "bytes": 84213,
      "downloaded_at": "2026-08-24T10:12:03+00:00",
      "embedded_files": ["DOC-9042.embedded.pdf"]
    }
  }
}
```

## Files

| file | |
|---|---|
| `app.py` | the whole UI: sidebar, search, document picker, the two panes |
| `config.py` | dotenv loading, and the mime → format map (a copy of the backend's) |
| `db.py` | read-only psycopg 3 connections, column discovery, the lookups |
| `blob.py` | azcopy: one blob, and a bounded parallel pool |
| `store.py` | path layout, cache vs permanent resolution, `_manifest.json` |
| `render.py` | mime type → how to show it |

## Notes on the data

**`mime_type` sometimes lies.** Every file is also sniffed with libmagic and a
disagreement is shown with a "render as sniffed type" switch on by default. The
preprocessor has a whole fallback chain for the same reason (`main_ehealth.py` retries
with the sniffed type when the declared one fails).

**`style_sheet` is not an XSLT.** Despite the `.xsl` names, no XSLT exists anywhere in
`nlp_backend_server` — the value is a dictionary key selecting an HL7 section
whitelist in `workers/xml_to_md/hl7_filters`. The viewer shows it and does not apply it.

**An XML document can be a PDF.** An HL7 CDA can carry a base64 document in
`<component>/<nonXMLBody>`, so a row with `mime_type='application/xml'` may really be a
PDF. The viewer detects that, renders the inner document, and saves it alongside the
container as `<doc_id>.embedded.pdf`. This is the same extraction the pipeline does in
`document_preprocessor/extract_from_xml.py`.

**Columns are discovered, not assumed.** `is_generated_pdf` exists in newer databases
and in no code under `nlp_backend_server`, so the `SELECT` list is intersected with
`information_schema.columns`. The same app works against schemas that have that column
and schemas that do not. `blob_path` is the only blob column read — a row with no
`blob_path` falls through to the `file_content` large object, never to another column.

**Rows with no blob.** Older rows carry the document in `file_content` as a Postgres
large object instead of a blob path. Those are read with `lo_get()` (falling back to a
`pg_largeobject` scan) rather than azcopy, so they are viewable too.

**The tenant filter self-corrects.** If a lookup returns nothing with
`tenant_id = <your config value>`, it is retried without the filter and the page says
so — the value in `db_config.py` may be a label rather than the real column value.

**The SAS token** goes into the azcopy URL, so it is visible to `ps` for the life of
each azcopy process. That is true of the standalone downloader script this replaces and
is not made worse here. The token never reaches a log line, an error message or the
page: azcopy's own output is scrubbed before anything is shown.

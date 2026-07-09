# Doc-Struct Viewer

Streamlit tool to review doc-to-struct LLM outputs with citation highlighting and
reviewer annotations.

Flow: the run/strategy folder is fixed on the server, so a reviewer just **types a
document id** at the top of the page. The app looks that id up in an index CSV
(`doc_id → patient_id`), loads the matching patient file, and picks the section to
view. The raw document is shown line-numbered on the left with the section's
citations highlighted; the structured datapoints are on the right. Click a cite
(`L12–15`) to scroll the document to that line. Each datapoint has a comment box
and a corrected-citation box that save to a CSV on Enter.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit the paths
streamlit run app.py
```

## Configuration (`.env`)

| Variable           | Meaning                                                          |
|--------------------|------------------------------------------------------------------|
| `OUTPUT_DIR`       | Root folder; each subfolder is a run with `<patient_id>.json`.   |
| `RUN_SUBFOLDER`    | The run/strategy subfolder (inside `OUTPUT_DIR`) to serve.       |
| `DOC_PATIENT_CSV`  | Index CSV with `doc_id,patient_id` columns (header required).    |
| `RAW_DIR`          | Folder of `<patient_id>.json` raw documents.                     |
| `ANNOTATIONS_FILE` | CSV path where reviewer feedback is written.                     |

All paths are fixed on the server and are not editable in the UI; reviewers only
enter a document id.


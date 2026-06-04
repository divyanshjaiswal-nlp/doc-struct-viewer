# Doc-Struct Viewer

Streamlit tool to review doc-to-struct LLM outputs with citation highlighting and
reviewer annotations.

Flow: `OUTPUT_DIR → run/strategy → patient → document → section`. The raw document
is shown line-numbered on the left with the section's citations highlighted; the
structured datapoints are on the right. Click a cite (`L12–15`) to scroll the
document to that line. Each datapoint has a comment box and a corrected-citation
box that save to a CSV on Enter.

## Run locally

```bash
pip install -r requirements.txt
cp .env.example .env        # then edit the paths
streamlit run app.py
```

## Configuration (`.env`)

| Variable           | Meaning                                                        |
|--------------------|----------------------------------------------------------------|
| `OUTPUT_DIR`       | Root folder; each subfolder is a run with `<patient_id>.json`. |
| `RAW_DIR`          | Folder of `<patient_id>.json` raw documents.                   |
| `ANNOTATIONS_FILE` | CSV path where reviewer feedback is written.                   |

## Deploying

This app reads documents from **local filesystem paths** and displays clinical
data, so it must run **on a machine/network that can see those folders** (an
internal VM/server) — not on public Streamlit Community Cloud. Keep the paths in
the server's environment (or Streamlit secrets), never in git.

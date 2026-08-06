# L1 / judge viewer

Streamlit viewer for the L1 date-claim work. Stage 1 shows the **L1 output** for one
patient, one entity at a time, with each record's fields and its evidence.

## Setup

Create a `.env` in this folder with these four variables:

```
# L1 output: one FOLDER per patient (folder name = patient id), a single json inside
# whose filename is the L0 job id, not the patient id.
L1_DIR=

# merged date -> events index, <patient_id>.json          (later stage)
DATE_EVENTS_DIR=

# judge output, <patient_id>_results.json                 (later stage)
RESULTS_DIR=

# raw documents, <patient_id>.json                        (optional)
PATIENT_DATA_DIR=
```

All four are also editable from the sidebar at runtime, so `.env` only sets the defaults.

```
pip install -r requirements.txt
streamlit run app.py
```

## Files

| File | |
|---|---|
| `app.py` | UI: sidebar paths, patient id, entity dropdown, record + evidence rendering |
| `loader.py` | Disk access. Resolves `<L1_DIR>/<patient_id>/*.json` and reads `standardMedicalData` |
| `config.py` | **Which fields appear per entity.** Edit `extra` here to promote more keys |

## Stage 1 behaviour

1. Enter a patient id in the sidebar. With the box empty, the app lists every patient
   folder it found so you can copy one.
2. Pick an entity from the dropdown — it shows the record count, e.g. `MEDICATIONS  (3)`.
   Only entities with at least one record appear. Entities missing from `config.py` are
   still listed and fall back to raw JSON, so nothing is hidden.
3. Every record in that entity's list gets an expander, titled with its first non-empty
   identity value. Inside:
   - **Dates** — shown even when null, since a missing date is what the judge scores
   - **Identity** and **Details** — hidden when empty
   - **Evidence** — one expander per `docId`, listing only the `text` of each citation
4. *Show raw record JSON* dumps the full record minus evidence. That's the quickest way
   to spot a key worth adding to `extra` in `config.py`.

`config.py` deliberately duplicates the judge's `ENTITY_CONFIG` rather than importing it:
the judge only needs dates + identity, while the viewer wants context fields too, and
keeping them separate means the app has no dependency on `nlp_backend_server`.

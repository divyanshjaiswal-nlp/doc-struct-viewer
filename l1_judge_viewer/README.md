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

# ── Summary -> anchors page ──
# L1 run holding the summary entity (oncology_history_v3). A folder per patient, a folder
# of <patient_id>.json, or a single json file.
ONCO_L1_DIR=

# merged doc-to-struct date anchors, keyed by date. A directory of <patient_id>.json, or
# the merged file itself.
MERGED_ANCHOR_DIR=
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

## Summary → anchors

The oncology-history summary beside the merged doc-to-struct date anchors.

The entity needs **no entry in `config.py`** — it is found by the shape of its records
(anything carrying a text `summary`), and every other key on the record is ignored. Pick a
patient, pick the entity, and the merged file is matched by patient id (with a picker when
the name does not line up, since that file is assembled by hand).

Every date in the prose is marked at whatever precision it was written — `2024`,
`July 2024`, `7/28/24`, `2024-07-28` — and looked up in the index:

| mark | |
|---|---|
| solid blue | the index has that exact key; click to scroll to it |
| dashed blue | the same date at a different precision, e.g. `July 2024` → `2024-07-28` |
| amber | nothing in the index on that date |

A matched date key scrolls back to the mention that reached it. Two expanders below the
panes list the gaps in both directions: summary dates with no key, and keys the summary
never mentions.

The merged file may be `{date: [text, ...]}`, `{date: [{text, docId}, ...]}` or
`{docId: {date: [...]}}` — dates are pooled across documents either way, so one date is
one group.

`config.py` deliberately duplicates the judge's `ENTITY_CONFIG` rather than importing it:
the judge only needs dates + identity, while the viewer wants context fields too, and
keeping them separate means the app has no dependency on `nlp_backend_server`.

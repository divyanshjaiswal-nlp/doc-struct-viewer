"""
L1 / judge viewer — entry point and navigation.

Three pages:

  L1 review          one L1 record at a time, its date claims paired with the judge's
                     verdicts, and the documents behind both.
  Date -> events     one document at a time, before the merge: its text beside the events
                     extracted from it, with each citation's line range highlighted.
  Summary -> anchors an L1 oncology-history summary beside the merged doc-to-struct date
                     anchors: every date in the prose marked, and looked up in the index.

Page config and the stylesheet are set here, once, so the pages themselves only render.

Paths come from .env and are editable in a "Paths" expander on the page that reads them:
L1_DIR, DATE_EVENTS_DIR, RESULTS_DIR and PATIENT_DATA_DIR on the L1 review page,
DATE_EVENTS_RAW_DIR, PATIENT_DATA_DIR and D2S_DIR on the date-events page, ONCO_L1_DIR and
MERGED_ANCHOR_DIR on the summary page.

    streamlit run app.py
"""
from __future__ import annotations

import streamlit as st

from state import keep
from styles import CSS, header

st.set_page_config(page_title="L1 date-claim review", layout="wide")

# before anything renders: Streamlit drops the session-state of widgets that did not run,
# so without this every switch away from a page clears its controls
keep()
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(
    header("L1 date-claim review", "L1 output vs the date→events index"),
    unsafe_allow_html=True,
)

# st.navigation rather than a pages/ folder: it gives the pages real titles instead of
# filenames, and keeps this file as the only place that configures the app.
st.navigation(
    [
        st.Page("views/l1_review.py", title="L1 review", icon=":material/fact_check:",
                default=True),
        st.Page("views/date_events.py", title="Date → events",
                icon=":material/event_note:"),
        st.Page("views/onco_summary.py", title="Summary → anchors",
                icon=":material/summarize:"),
    ]
).run()

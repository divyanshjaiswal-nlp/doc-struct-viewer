"""The 20 doc-to-struct sections — canonical keys and display labels, in prompt order.

This is the single source of truth for the section list. The keys here MUST match
the keys the LLM emits in each document's response (see the extraction prompt in
nlp_backend/pipelines/doc_to_struct/prompts/line_prompt_with_consolidation.py).

If the prompt ever changes a section key, change it here too — everything else
(the dropdown, the counts, the "X/20 populated" badge) is derived from this list.
"""
from __future__ import annotations

# (canonical_key, human_label) in the order they appear in the extraction prompt.
SECTIONS: list[tuple[str, str]] = [
    ("demographics_and_generic_information", "Patient Demographics & General Info"),
    ("cancer_diagnosis_and_staging",         "Cancer Diagnosis & Staging"),
    ("pathology_event",                      "Pathology Events"),
    ("mutation_and_biomarkers",              "Genetic Mutations & Biomarkers"),
    ("surgical_cancer_treatments",           "Surgical Cancer Treatments"),
    ("radiation_treatments",                 "Radiation Treatments"),
    ("other_cancerous_treatments",           "Other Cancer Treatments"),
    ("non_cancerous_treatments",             "Non-Cancer Treatments"),
    ("imaging_events",                       "Imaging Events"),
    ("labs",                                 "Lab Tests & Results"),
    ("disease_progression",                  "Disease Progression / Response"),
    ("clinical_trials",                      "Clinical Trials"),
    ("comorbidities",                        "Comorbidities & Pre-existing Conditions"),
    ("family_history_cancer",                "Family History of Cancer"),
    ("adverse_events",                       "Toxicity & Adverse Events"),
    ("performance_status",                   "Performance Status"),
    ("social_concern",                       "Social & Financial Concerns"),
    ("miscellaneous",                        "Miscellaneous"),
    ("followup_assessment_and_plan",         "Follow-up, Assessment & Plan"),
    ("any_other_informations",               "Any Other Information"),
]

SECTION_KEYS: list[str] = [k for k, _ in SECTIONS]
SECTION_LABELS: dict[str, str] = dict(SECTIONS)

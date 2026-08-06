"""
Which fields to show per entity, and in what order.

Mirrors ENTITY_CONFIG from the judge (notebook/l1_date_claim_judge.py) but is kept
separate on purpose -- the viewer wants MORE than the judge does. The judge only needs
dates + identity; here you also want the context fields that explain a record.

    dates    : {judge role -> the field holding that date}. The role names MUST match the
               judge's, because that is what pairs an L1 date with its verdict on screen.
               Always shown, even when null -- a missing date is the thing being judged.
    identity : what the record is about; hidden when empty
    extra    : context you want on screen; hidden when empty. ADD KEYS HERE.

Anything not listed is still reachable through the "Show raw record JSON" toggle in the
app, which is the fastest way to find the next key worth promoting into `extra`.
"""

ENTITY_FIELDS = {
    "MEDICATIONS": {
        "dates": {"started": "startDate", "stopped": "endDate"},
        "identity": ["medicationName", "alternativeNames", "regimenName", "medicationClass"],
        "extra": [
            "treatmentStatus",
            "treatmentIntent",
            "treatmentSequence",
            "lineOfTheraphy",
            "terminationReasons",
            "routeOfAdministration",
            "associatedDiagnosis",
        ],
    },
    "ONTADA_RWE_MEDICATIONS": {
        "dates": {"started": "medicationStartDate", "stopped": "medicationEndDate"},
        "identity": ["medicationName", "alternativeNames", "regimenName"],
        "extra": ["medicationStatus", "reasonCode", "reasonForDiscontinuation", "associatedDiagnosis"],
    },
    "RADIATIONS": {
        "dates": {"started": "startDate", "stopped": "endDate"},
        "identity": ["modality", "bodySite", "intent"],
        "extra": [
            "status",
            "totalDosagePlanned",
            "totalDosageDelivered",
            "totalFractionPlanned",
            "totalFractionDelivered",
            "associatedTumor",
        ],
    },
    "ONTADA_RWE_RADIATION": {
        "dates": {"started": "radiationStartDate", "stopped": "radiationEndDate"},
        "identity": ["radiationTypeRaw", "radiationType", "radiationRegion"],
        "extra": [
            "radiationStatus",
            "radiationTotalDose",
            "radiationDoseUnit",
            "radiationFractions",
            "associatedDiagnosis",
        ],
    },
    "SURGERIES": {
        "dates": {"performed": "dateOfSurgery"},
        "identity": ["surgeryName", "site", "surgeryClass"],
        "extra": [
            "status",
            "surgeryReason",
            "resectionMargins",
            "lymphNodeStatus",
            "surgeryOutcome",
            "surgeryComplications",
            "associatedTumor",
        ],
    },
    "ONTADA_RWE_SURGERY": {
        "dates": {"performed": "surgeryDate"},
        "identity": ["rawProcedureName", "surgeryType", "surgerySite"],
        "extra": ["surgeryStatus", "primaryCancerCondition"],
    },
    "DIAGNOSIS_CHARACTERISTICS": {
        "dates": {"diagnosed": "primaryDiagnosisDate", "metastasis identified": "firstMetastasisDate", "recurrence identified": "firstRecurrenceDate", "staged": "dateOfStaging"},
        "identity": ["primaryCancerCondition", "primaryTumorLocation", "histologyOrClassification"],
        "extra": [
            "cancerType",
            "icdCode",
            "diagnosisStatus",
            "diseaseStatus",
            "groupStage",
            "tnmStageT",
            "tnmStageN",
            "tnmStageM",
            "stagingType",
            "tumorGrade",
            "metastasisBodySites",
            "metastasisDatesAndSites",
            "recurrentBodySites",
            "recurrentDateAndSites",
        ],
    },
}

# The record key holding provenance. Schemas use both spellings.
EVIDENCE_KEYS = ("evidences", "evidence")

# Order the entity dropdown by this, then anything else found in the output.
ENTITY_ORDER = list(ENTITY_FIELDS)

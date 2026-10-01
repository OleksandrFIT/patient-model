from pai3.enums import (
    FlagCode,
    FlagStatus,
    ProvenanceOrigin,
    RecordStatus,
    Severity,
    TextOrigin,
)


def test_record_status_has_no_deleted_value():
    # Spec §2.1: clinical data is not deleted; an erroneous record stays.
    assert "deleted" not in {s.value for s in RecordStatus}
    assert RecordStatus.ENTERED_IN_ERROR.value == "entered_in_error"


def test_provenance_origin_separates_extraction_from_inference():
    # Spec §6.19: conflating these is what leaves compounding unnameable.
    assert ProvenanceOrigin.AI_EXTRACTION.value == "ai_extraction"
    assert ProvenanceOrigin.AI_INFERENCE.value == "ai_inference"


def test_provenance_origin_has_no_bare_derived():
    # Spec §6.19: the catch-all narrows to system_derived.
    values = {o.value for o in ProvenanceOrigin}
    assert "derived" not in values
    assert "system_derived" in values


def test_text_origin_covers_the_perimeter_axis():
    assert {o.value for o in TextOrigin} == {
        "practice_authored",
        "patient_submitted",
        "external_document",
        "transcribed_external",
        "unknown",
    }


def test_severity_matches_the_four_d5_classes():
    assert {s.value for s in Severity} == {
        "blocking",
        "human_review_required",
        "warning",
        "acceptable_missing",
    }


def test_flag_codes_present_for_each_spec_section():
    values = {c.value for c in FlagCode}
    for expected in (
        "CONFLICTING_VALUES",
        "MISSING_UNIT",
        "MISSING_REFERENCE_RANGE",
        "UNIT_MISMATCH",
        "INTERPRETATION_DISAGREES_WITH_RANGE",
        "EXTRACTION_FAILED",
        "DISCONTINUED_SHOWN_ACTIVE",
        "DUPLICATE_CANDIDATE",
        "UNCODED_CONCEPT",
        "PARENT_RETRACTED",
        "RECORD_REJECTED_AT_INGEST",
    ):
        assert expected in values


def test_flag_lifecycle_is_four_states():
    assert {s.value for s in FlagStatus} == {"open", "in_review", "resolved", "wont_fix"}

"""The optional normalisation build, against the three real source files.

Every test names the assignment conflict or the spec rule it pins.
"""

from pathlib import Path

import pytest

from pai3.enums import ClinicalStatus, FlagCode, Severity, VerificationStatus
from pai3.normalise.model import ConflictOutcome, SourceClass
from pai3.normalise.pipeline import normalise

SOURCES = Path("mock/sources")


@pytest.fixture(scope="module")
def result():
    return normalise(SOURCES)


def _codes(result) -> set[FlagCode]:
    return {f.code for f in result.flags}


def _flag(result, code: FlagCode):
    found = [f for f in result.flags if f.code is code]
    assert found, f"{code.value} was not raised"
    return found[0]


def _lab(result, analyte: str):
    found = [lab for lab in result.labs if analyte in lab.biomarker.raw_text]
    assert found, f"no lab for {analyte}"
    return found[0]


# --------------------------------------------- the six codes nothing raised before

def test_the_six_previously_unraised_codes_all_fire(result):
    # The point of this build: six codes were declared in §6.5 and raised by nothing.
    for code in (
        FlagCode.CONFLICTING_VALUES,
        FlagCode.DUPLICATE_CANDIDATE,
        FlagCode.UNIT_MISMATCH,
        FlagCode.EXTRACTION_FAILED,
        FlagCode.RECORD_REJECTED_AT_INGEST,
        FlagCode.DISCONTINUED_SHOWN_ACTIVE,
    ):
        assert code in _codes(result), f"{code.value} is still dead code"


def test_only_the_retraction_code_remains_unraised(result):
    # PARENT_RETRACTED belongs to the retraction cascade, not to ingestion.
    assert set(FlagCode) - _codes(result) == {FlagCode.PARENT_RETRACTED}


# ------------------------------------------------- assignment conflict: dose

def test_a_dose_conflict_resolves_to_the_prescriber_not_the_newer_source(result):
    metformin = next(m for m in result.medications if "metformin" in m.drug.raw_text)
    assert metformin.dosage.amount == 500.0  # EMR, not the intake form's 1000
    flag = next(
        f for f in result.flags
        if f.code is FlagCode.CONFLICTING_VALUES and "dose_amount" in f.message
    )
    assert "emr" in flag.message and "1000.0" in flag.message
    assert flag.severity is Severity.HUMAN_REVIEW_REQUIRED


def test_the_rejected_dose_is_still_visible_in_the_flag(result):
    # §9.3: the losing candidate is attached, not discarded.
    flag = next(
        f for f in result.flags
        if f.code is FlagCode.CONFLICTING_VALUES and "dose_amount" in f.message
    )
    assert flag.candidates


# ------------------------------- assignment conflict: discontinued shown active

def test_the_patient_wins_the_status_but_the_model_cannot_store_it(result):
    # The trust rule gives the patient the status; §9.8 requires a stop date for a stopped
    # medication and she cannot name the month. Canonical keeps the EMR's value and the
    # dispute blocks, rather than the status being flipped on an undated self-report.
    metformin = next(m for m in result.medications if "metformin" in m.drug.raw_text)
    assert metformin.status.value == "active"
    assert metformin.is_current

    flag = _flag(result, FlagCode.DISCONTINUED_SHOWN_ACTIVE)
    assert flag.severity is Severity.BLOCKING
    assert flag.blocks_autonomous_use

    conflict = next(
        c for g in result.groups for c in g.conflicts
        if c.field_name == "status" and g.key == "6809"
    )
    assert conflict.outcome is ConflictOutcome.WINNER_UNREPRESENTABLE


# --------------------------------------- assignment conflict: missing lab units

def test_a_lab_with_no_unit_is_kept_and_flagged_not_rejected(result):
    free_t4 = _lab(result, "free T4")
    assert free_t4.quantity is not None
    assert free_t4.quantity.unit is None
    assert FlagCode.MISSING_UNIT in _codes(result)


# ----------------------------- assignment conflict: different condition spelling

def test_two_spellings_of_one_condition_become_one_record(result):
    hypo = [c for c in result.conditions if c.code.code == "E03.9"]
    assert len(hypo) == 1, "the spellings did not merge"
    assert hypo[0].code.raw_text == "Hypothyroidism"  # the coded source supplies the text
    assert hypo[0].verification_status is VerificationStatus.CONFIRMED


def test_an_unmatched_self_reported_diagnosis_is_unconfirmed_and_uncoded(result):
    # The readers' synonym table is deliberately tiny. An unmatched term is not guessed at:
    # it becomes its own record, uncoded, and §6.4 keeps it out of a summary.
    fibro = next(c for c in result.conditions if "fibromyalgia" in c.code.raw_text)
    assert not fibro.code.is_coded
    assert fibro.verification_status is VerificationStatus.UNCONFIRMED
    assert not fibro.is_assertable
    assert FlagCode.UNCODED_CONCEPT in _codes(result)


# ---------------------------------- assignment conflict: supplement list differs

def test_a_supplement_only_the_patient_reports_is_kept(result):
    names = [s.substance.raw_text for s in result.supplements]
    assert any("biotin" in n for n in names), "the patient-only supplement was dropped"
    assert any("vitamin D" in n for n in names)


# ------------------------------------------ assignment conflict: duplicate lab

def test_a_duplicate_that_agrees_across_sources_merges_without_a_flag(result):
    tsh = _lab(result, "TSH")
    assert tsh.quantity.value == 5.6
    assert len(tsh.provenance.source_refs) == 2, "both citations should be attached"
    group = next(g for g in result.groups if g.key == "3016-3|2026-02-26")
    assert group.corroborated


def test_a_duplicate_inside_one_document_that_disagrees_is_flagged(result):
    flag = _flag(result, FlagCode.DUPLICATE_CANDIDATE)
    assert "glucose" in flag.message
    assert flag.candidates


# ------------------------------------------------------- §9.3's empty-slot case

def test_an_unresolvable_conflict_leaves_the_value_empty(result):
    glucose = _lab(result, "glucose")
    assert glucose.quantity is None, "a winner was picked where no rule applies"
    assert not glucose.has_value
    assert glucose.reference_range is not None  # the range agreed; only the value did not


def test_both_conflicting_values_reach_the_flag(result):
    # The first version of Conflict keyed candidates by source class, so two readings from
    # the same class overwrote each other and the report showed one of the two.
    conflict = next(
        c for g in result.groups for c in g.conflicts
        if g.key == "1558-6|2026-02-26" and c.field_name == "value"
    )
    assert conflict.outcome is ConflictOutcome.UNRESOLVED
    assert sorted(c.value for c in conflict.candidates) == [5.5, 7.2]
    assert {c.locator.page for c in conflict.candidates} == {2, 3}


def test_confidence_does_not_break_a_tie(result):
    # The two glucose readings carry 0.93 and 0.88. If confidence decided, 7.2 would win
    # silently -- which is the silent winner §9.3 forbids. Confidence measures how well a
    # line was read, not whether it is true.
    conflict = next(
        c for g in result.groups for c in g.conflicts
        if g.key == "1558-6|2026-02-26" and c.field_name == "value"
    )
    confidences = sorted(c.confidence for c in conflict.candidates)
    assert confidences == [0.88, 0.93], "the fixture no longer exercises this"
    assert conflict.winner is None


# --------------------------------------------------------------- unit systems

def test_the_same_measurement_in_two_unit_systems_is_flagged_not_converted(result):
    hba1c = _lab(result, "HbA1c")
    assert hba1c.quantity.unit == "%"  # the report is primary for a lab value
    flag = _flag(result, FlagCode.UNIT_MISMATCH)
    assert "mmol/mol" in flag.message and "%" in flag.message


def test_a_lab_flag_that_contradicts_its_own_range_is_caught(result):
    ferritin = _lab(result, "ferritin")
    assert ferritin.reported_interpretation.raw_text == "N"
    assert ferritin.computed_interpretation.value == "low"
    # The lab's own reading still wins the display: ours depends on the range we stored,
    # which is exactly what the disagreement puts in doubt (§9.5).
    assert ferritin.display_interpretation == ("N", "reported")
    assert FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE in _codes(result)


# ------------------------------------------------------- layer 1 and failures

def test_a_lab_with_no_collection_date_never_becomes_a_record(result):
    assert not [lab for lab in result.labs if "vitamin D" in lab.biomarker.raw_text]
    assert any("vitamin D" in row.raw.get("analyte", "") for row in result.rejected)
    flag = _flag(result, FlagCode.RECORD_REJECTED_AT_INGEST)
    assert flag.source_locator, "the flag must name the document, not a canonical id"
    assert not flag.targets


def test_an_unreadable_row_is_recorded_rather_than_dropped(result):
    flag = _flag(result, FlagCode.EXTRACTION_FAILED)
    assert flag.source_locator
    assert "obscured" in flag.message or "could not be read" in flag.message


# ------------------------------------------------------------------- identity

def test_the_patient_carries_an_identifier_from_each_system(result):
    systems = {i.system for i in result.patient.identifiers}
    assert systems == {"emr-west", "intake-form"}, "§6.12: one patient, several MRNs"


# --------------------------------------------------------------------- ingest

def test_each_document_gets_a_started_and_a_completed_event(result):
    per_doc: dict[str, set[str]] = {}
    for event in result.audit:
        per_doc.setdefault(event.ingest.source_document_id, set()).add(event.action.value)
    assert len(per_doc) == 3
    for doc_id, actions in per_doc.items():
        assert actions == {"ingest_started", "ingest_completed"}, doc_id


def test_the_pdf_declares_no_row_count_so_completeness_is_unverifiable(result):
    pdf = next(d for d in result.documents if d.source_class is SourceClass.LAB_REPORT)
    assert pdf.declared_row_count is None
    completed = next(
        e for e in result.audit
        if e.ingest.source_document_id == pdf.id and e.action.value == "ingest_completed"
    )
    assert not completed.ingest.completeness_verifiable
    assert completed.ingest.unaccounted is None


def test_the_emr_declares_a_count_so_completeness_is_checkable(result):
    emr = next(d for d in result.documents if d.source_class is SourceClass.EMR)
    assert emr.declared_row_count is not None
    completed = next(
        e for e in result.audit
        if e.ingest.source_document_id == emr.id and e.action.value == "ingest_completed"
    )
    assert completed.ingest.completeness_verifiable


# -------------------------------------------------------- the queue is ordered

def test_the_review_queue_puts_blocking_first(result):
    severities = [f.severity for f in result.review_queue]
    assert severities[0] is Severity.BLOCKING
    assert severities == sorted(
        severities,
        key=lambda s: [
            Severity.BLOCKING, Severity.HUMAN_REVIEW_REQUIRED,
            Severity.WARNING, Severity.ACCEPTABLE_MISSING,
        ].index(s),
    )


def test_nothing_in_canonical_holds_a_value_nobody_vouched_for(result):
    # The invariant, checked over the whole output.
    for lab in result.labs:
        if lab.quantity is None:
            blocking = [
                f for f in result.flags
                if f.severity is Severity.BLOCKING
                and any(t.entity_id == lab.id for t in f.targets)
            ]
            assert blocking, f"{lab.biomarker.raw_text} has an empty slot and no blocking flag"
    for cond in result.conditions:
        assert cond.provenance.asserted_by.ref
    for med in result.medications:
        assert med.provenance.source_refs, "a medication with no citation"


def test_an_active_condition_from_the_emr_is_assertable(result):
    active = [
        c for c in result.conditions
        if c.clinical_status is ClinicalStatus.ACTIVE and c.code.is_coded
    ]
    assert active and all(c.is_assertable for c in active)

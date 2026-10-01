from datetime import UTC, datetime

from pai3.ai.artifact import (
    AIClaim,
    AISummary,
    ClaimValue,
    Engine,
    OmissionReason,
    OmittedRecord,
)
from pai3.ai.guardrails import Verdict, run_guardrails
from pai3.entities.results import LabResult
from pai3.enums import FlagCode, ProvenanceOrigin, Severity
from pai3.ids import CanonicalRef, new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.flags import FlagSummary
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB_ACTOR = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")
PROV = Provenance(
    origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=LAB_ACTOR, asserted_at=NOW
)
PATIENT = new_id("pat")


def _lab(value: float | None, lab_id: str | None = None) -> LabResult:
    return LabResult(
        id=lab_id or new_id("lab"), provenance=PROV, created_at=NOW, updated_at=NOW,
        updated_by=LAB_ACTOR, patient_id=PATIENT,
        biomarker=CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3"),
        collection_date=NOW,
        quantity=None if value is None else Quantity(value=value, unit="mIU/L"),
    )


def _ref(lab: LabResult) -> CanonicalRef:
    return CanonicalRef(entity_type="LabResult", entity_id=lab.id, version=lab.version)


def _summary(claims, inputs, **over) -> AISummary:
    kwargs = {
        "id": new_id("aia"), "patient_id": PATIENT, "trace_id": new_id("trc"),
        "created_at": NOW, "inputs": inputs, "prompt_digest": "sha256:" + "a" * 64,
        "model_id": "llama-3.3-70b-instruct", "engine": Engine.OLLAMA,
        "engine_version": "0.5.1", "consent_ref": new_id("cons"),
        "claims": claims, "unresolved": [],
    }
    return AISummary(**(kwargs | over))


def test_a_grounded_summary_passes():
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.PASS and failures == []


def test_a_citation_the_model_never_read_is_a_hard_failure():
    lab, unread = _lab(2.1), _lab(9.9)
    summary = _summary([AIClaim(text="TSH high.", cites=[_ref(unread)])], [_ref(lab)])
    verdict, failures = run_guardrails(summary, {lab.id: lab, unread.id: unread}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "cites_in_inputs" for f in failures)


def test_a_value_that_does_not_match_the_record_is_a_hard_failure():
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 7.2.", cites=[_ref(lab)],
                 values=[ClaimValue(value=7.2, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "value_matches_source" for f in failures)


def test_asserting_a_value_where_the_slot_is_empty_is_a_hard_failure():
    # §9.6 as code: there is no value, so it can be neither asserted nor inferred.
    lab = _lab(None)
    summary = _summary(
        [AIClaim(text="TSH 2.1.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "no_claim_on_empty_slot" for f in failures)


def test_a_non_droppable_omission_is_a_hard_failure():
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
        omitted=[
            OmittedRecord(
                ref=CanonicalRef(
                    entity_type="AllergyIntolerance", entity_id=new_id("alg"), version=1
                ),
                reason=OmissionReason.CONTEXT_BUDGET,
            )
        ],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "no_non_droppable_omitted" for f in failures)


def test_an_unsurfaced_blocking_flag_is_a_soft_failure():
    lab = _lab(2.1)
    flag = FlagSummary(
        flag_id=new_id("flag"), code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING, message="unresolved conflict",
    )
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [flag])
    assert verdict is Verdict.SOFT_FAIL
    assert any(f.check == "blocking_flags_surfaced" for f in failures)


def test_a_surfaced_blocking_flag_passes():
    lab = _lab(2.1)
    flag = FlagSummary(
        flag_id=new_id("flag"), code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING, message="unresolved conflict",
    )
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)], unresolved=[flag],
    )
    verdict, _ = run_guardrails(summary, {lab.id: lab}, [flag])
    assert verdict is Verdict.PASS


def test_a_hard_failure_outranks_a_soft_one():
    lab, unread = _lab(2.1), _lab(9.9)
    flag = FlagSummary(
        flag_id=new_id("flag"), code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING, message="x",
    )
    summary = _summary([AIClaim(text="x", cites=[_ref(unread)])], [_ref(lab)])
    verdict, failures = run_guardrails(summary, {lab.id: lab, unread.id: unread}, [flag])
    assert verdict is Verdict.HARD_FAIL
    assert len(failures) >= 2


def test_guardrails_cannot_detect_an_omission():
    # §10.5 and §7: a brief that omits a critical allergy passes every check. This test
    # pins the documented limit so nobody later believes the checks cover it.
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, _ = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.PASS


# --- the three fixes to the plan's version. None of the tests above detect them.

def test_a_legitimately_omitted_resolved_condition_is_not_a_failure():
    # The plan matched check 5 on entity TYPE, so a RESOLVED condition -- which §10.6
    # makes droppable and the projection correctly omits -- produced a hard failure.
    # Droppability now comes from the same function the projection uses.
    from pai3.ai.projection import is_non_droppable
    from pai3.entities.clinical import Condition
    from pai3.enums import ClinicalStatus, VerificationStatus

    resolved = Condition(
        id=new_id("cond"), provenance=PROV, created_at=NOW, updated_at=NOW,
        updated_by=LAB_ACTOR, patient_id=PATIENT,
        code=CodeableConcept(raw_text="iron deficiency anaemia"),
        clinical_status=ClinicalStatus.RESOLVED,
        verification_status=VerificationStatus.CONFIRMED,
    )
    assert not is_non_droppable(resolved)

    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
        omitted=[
            OmittedRecord(
                ref=CanonicalRef(
                    entity_type="Condition", entity_id=resolved.id, version=resolved.version
                ),
                reason=OmissionReason.CONTEXT_BUDGET,
            )
        ],
    )
    verdict, failures = run_guardrails(
        summary, {lab.id: lab, resolved.id: resolved}, []
    )
    assert verdict is Verdict.PASS, [f.detail for f in failures]


def test_an_omitted_record_the_checker_cannot_see_fails_closed():
    # Droppability is unknown, so the check refuses rather than passing.
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
        omitted=[
            OmittedRecord(
                ref=CanonicalRef(entity_type="Condition", entity_id=new_id("cond"), version=1),
                reason=OmissionReason.CONTEXT_BUDGET,
            )
        ],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any("droppability is unknown" in f.detail for f in failures)


def test_a_fabricated_vital_value_is_caught_not_only_a_lab():
    # The plan checked isinstance(record, LabResult) and skipped everything else, so a
    # fabricated VitalSign number passed. §10.5 says every ClaimValue.
    from pai3.entities.results import VitalSign
    from pai3.enums import MeasurementContext

    vital = VitalSign(
        id=new_id("vit"), provenance=PROV, created_at=NOW, updated_at=NOW,
        updated_by=LAB_ACTOR, patient_id=PATIENT,
        kind=CodeableConcept(raw_text="body weight"), measured_at=NOW,
        quantity=Quantity(value=71.2, unit="kg"),
        measurement_context=MeasurementContext.CLINICAL,
    )
    ref = CanonicalRef(entity_type="VitalSign", entity_id=vital.id, version=vital.version)
    summary = _summary(
        [AIClaim(text="Weight 85 kg.", cites=[ref],
                 values=[ClaimValue(value=85.0, unit="kg", cites=ref)])],
        [ref],
    )
    verdict, failures = run_guardrails(summary, {vital.id: vital}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "value_matches_source" for f in failures)


def test_a_value_claim_about_a_record_not_supplied_fails_closed():
    # The plan skipped the check silently when records.get returned None.
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "record_available_for_checking" for f in failures)


def test_a_claim_citing_a_record_with_no_quantity_is_not_checked_for_values():
    # A Condition has no quantity; a claim about it carries no ClaimValue, and the
    # value checks must not invent a verdict for it.
    from pai3.entities.clinical import Condition
    from pai3.enums import ClinicalStatus, VerificationStatus

    cond = Condition(
        id=new_id("cond"), provenance=PROV, created_at=NOW, updated_at=NOW,
        updated_by=LAB_ACTOR, patient_id=PATIENT,
        code=CodeableConcept(raw_text="hypothyroidism"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    ref = CanonicalRef(entity_type="Condition", entity_id=cond.id, version=cond.version)
    summary = _summary([AIClaim(text="Active hypothyroidism.", cites=[ref])], [ref])
    verdict, _ = run_guardrails(summary, {cond.id: cond}, [])
    assert verdict is Verdict.PASS


def test_a_claim_stating_a_number_without_declaring_it_is_a_hard_failure():
    # Found by running a real local model, not by reasoning. qwen2.5:7b restated values in
    # prose and left `values` empty, so checks 2 and 3 had nothing to compare and the
    # artifact passed carrying unverified numbers. Check 6 closes that.
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH measured 3.8 mIU/L and 5.6 mIU/L.", cites=[_ref(lab)])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "numbers_in_text_are_declared" for f in failures)


def test_declaring_the_number_satisfies_check_six():
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH measured 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, _ = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.PASS


def test_declaring_one_number_does_not_excuse_a_second_in_prose():
    """The hole check 6 left when it fired only on an empty `values`. A claim declaring the
    value and mentioning the range bound passed, and the bound was compared to nothing —
    defect 15's shape one level in."""
    lab = _lab(5.6)
    summary = _summary(
        [AIClaim(
            text="TSH rose to 5.6 mIU/L, above the 4.0 ceiling.",
            cites=[_ref(lab)],
            values=[ClaimValue(value=5.6, unit="mIU/L", cites=_ref(lab))],
        )],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    stated = [f for f in failures if f.check == "numbers_in_text_are_declared"]
    assert stated and "4.0" in stated[0].detail
    assert "5.6" not in stated[0].detail, "the declared figure is not the complaint"


def test_an_integer_in_prose_is_not_treated_as_a_measurement():
    # The pattern matches decimals only. "type 2 diabetes" and "one measurement" must not
    # trip it, and the cost of that narrowness is named: an integer measurement in prose
    # still slips through.
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="Known type 2 diabetes, stable over 3 visits.", cites=[_ref(lab)])],
        [_ref(lab)],
    )
    verdict, _ = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.PASS


def test_a_claim_describing_a_conflict_without_a_number_passes():
    # What the model should write about a record whose value slot is empty.
    lab = _lab(None)
    summary = _summary(
        [AIClaim(text="There is an unresolved conflict for fasting glucose.",
                 cites=[_ref(lab)])],
        [_ref(lab)],
    )
    verdict, _ = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.PASS

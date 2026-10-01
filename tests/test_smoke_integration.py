"""One patient, one record of every canonical entity, wired together.

Not in the plan. Everything up to here is unit-level: no test constructs two entities
and checks that the ids pointing between them resolve. The first integration is Task 29's
fixture, seven tasks away, and a structural mismatch -- LabResult.report_id against
DiagnosticReport.result_ids being the obvious candidate -- would surface only there.

This is the cheapest possible guard: build the cohort, then assert that every id one
record holds about another actually exists.
"""

from datetime import UTC, date, datetime, timedelta

from pai3.entities.administrative import Consent, Coverage
from pai3.entities.clinical import (
    AllergyIntolerance,
    Condition,
    Criticality,
    Encounter,
    Goal,
    Procedure,
    Reaction,
    SocialFactor,
    Symptom,
    SymptomReporter,
    SymptomStatus,
)
from pai3.entities.infrastructure import (
    AuditAction,
    AuditEvent,
    DataQualityFlag,
    FlagTarget,
    SourceReference,
)
from pai3.entities.narrative import ClinicalNote, NoteType
from pai3.entities.people import CareTeamMembership, Patient, Provider
from pai3.entities.results import DiagnosticReport, LabResult, VitalSign
from pai3.entities.therapy import (
    Medication,
    MedicationStatus,
    Supplement,
    SupplementStatus,
    TreatmentPlan,
)
from pai3.entities.workflow import Task, TaskOrigin, TaskStatus
from pai3.enums import (
    ClinicalStatus,
    ConsentScope,
    FlagCode,
    MeasurementContext,
    ProvenanceOrigin,
    Severity,
    TextOrigin,
    VerificationStatus,
)
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.people import HumanName, PatientIdentifier
from pai3.values.plan import PlanItem
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity, ReferenceRange
from pai3.values.text import ClinicalText

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
LAB_SYS = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")
PIPELINE = Actor(kind=ActorKind.PIPELINE, ref="normaliser", label="normaliser")


def _prov(actor: Actor, origin: ProvenanceOrigin = ProvenanceOrigin.HUMAN, **kw) -> Provenance:
    return Provenance(origin=origin, asserted_by=actor, asserted_at=NOW, **kw)


def _base(prefix: str, actor: Actor = DOC, **prov_kw) -> dict:
    return {
        "id": new_id(prefix),
        "provenance": _prov(actor, **prov_kw),
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": actor,
    }


def build_cohort() -> dict[str, object]:
    """Every built entity, for one patient, with references that point at each other."""
    provider = Provider(**_base("prov"), name=HumanName(given=["Ana"], family="Reyes"))
    patient_id = new_id("pat")
    encounter_id = new_id("enc")
    report_id = new_id("dxr")
    doc_id = new_id("doc")

    patient = Patient(
        id=patient_id,
        provenance=_prov(DOC),
        created_at=NOW,
        updated_at=NOW,
        updated_by=DOC,
        identifiers=[PatientIdentifier(system="emr-west", value="MRN-4471")],
        names=[HumanName(given=["Dana"], family="Okafor")],
        birth_date=date(1979, 4, 2),
        sex_at_birth="female",
        care_team=[
            CareTeamMembership(provider_id=provider.id, role="internist", is_primary=True)
        ],
    )

    source_ref = SourceReference(
        **_base("sref", LAB_SYS, origin=ProvenanceOrigin.SYSTEM_DERIVED),
        patient_id=patient_id,
        document_id=doc_id,
        page=2,
        field_path="results[0].value",
        quote="TSH 5.6 mIU/L",
    )

    encounter = Encounter(
        id=encounter_id,
        provenance=_prov(DOC),
        created_at=NOW,
        updated_at=NOW,
        updated_by=DOC,
        patient_id=patient_id,
        encounter_type="office visit",
        started_at=NOW - timedelta(hours=1),
        ended_at=NOW,
        participant_ids=[provider.id],
    )

    consent = Consent(
        **_base("cons"),
        patient_id=patient_id,
        scope=ConsentScope.AI_PROCESSING,
        effective_from=NOW - timedelta(days=120),
    )

    condition = Condition(
        **_base("cond"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        code=CodeableConcept(raw_text="hypothyroidism", system="ICD-10", code="E03.9"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
        onset=date(2021, 5, 14),
        recorded_by=provider.id,
    )

    symptom = Symptom(
        **_base("sym"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        symptom=CodeableConcept(raw_text="fatigue", system="SNOMED-CT", code="84229001"),
        status=SymptomStatus.ACTIVE,
        reported_by=SymptomReporter.PATIENT,
        patient_concern=ClinicalText(
            value="Worried the tiredness means something is wrong.",
            origin=TextOrigin.PATIENT_SUBMITTED,
        ),
    )

    allergy = AllergyIntolerance(
        **_base("alg"),
        patient_id=patient_id,
        substance=CodeableConcept(raw_text="penicillin", system="RxNorm", code="7980"),
        criticality=Criticality.HIGH,
        verification_status=VerificationStatus.CONFIRMED,
        reactions=[Reaction(manifestation=CodeableConcept(raw_text="hives"), severity="mild")],
        recorded_by=provider.id,
    )

    medication = Medication(
        **_base("med"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        drug=CodeableConcept(raw_text="levothyroxine", system="RxNorm", code="10582"),
        dosage=Dosage(text="75 mcg daily", amount=75.0, unit="mcg", frequency="daily"),
        status=MedicationStatus.ACTIVE,
        started_on=date(2021, 6, 1),
        prescriber_id=provider.id,
    )

    supplement = Supplement(
        **_base("supp"),
        patient_id=patient_id,
        substance=CodeableConcept(raw_text="vitamin D3"),
        dosage=Dosage(text="one dropper daily"),
        status=SupplementStatus.ACTIVE,
    )

    lab = LabResult(
        **_base("lab", LAB_SYS, origin=ProvenanceOrigin.AI_EXTRACTION,
                source_refs=[source_ref.id], extraction_confidence=0.91),
        patient_id=patient_id,
        biomarker=CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3"),
        collection_date=NOW - timedelta(days=14),
        quantity=Quantity(value=5.6, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
        reported_interpretation=CodeableConcept(raw_text="H"),
        performing_lab="Meridian Labs",
        ordering_provider_id=provider.id,
        report_id=report_id,
    )

    report = DiagnosticReport(
        id=report_id,
        provenance=_prov(LAB_SYS, ProvenanceOrigin.SOURCE_SYSTEM),
        created_at=NOW,
        updated_at=NOW,
        updated_by=LAB_SYS,
        patient_id=patient_id,
        report_type=CodeableConcept(raw_text="thyroid panel", system="LOINC", code="24348-5"),
        issued_at=NOW - timedelta(days=13),
        result_ids=[lab.id],
        performing_lab="Meridian Labs",
    )

    vital = VitalSign(
        **_base("vit"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        kind=CodeableConcept(raw_text="body weight", system="LOINC", code="29463-7"),
        measured_at=NOW,
        quantity=Quantity(value=71.2, unit="kg"),
        measurement_context=MeasurementContext.CLINICAL,
    )

    note = ClinicalNote(
        **_base("note"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        note_type=NoteType.PROGRESS,
        authored_at=NOW,
        author_id=provider.id,
        body=ClinicalText(
            value="TSH rising; discussed dose increase.",
            origin=TextOrigin.PRACTICE_AUTHORED,
            captured_by=DOC,
        ),
        signed_at=NOW + timedelta(minutes=20),
    )

    plan = TreatmentPlan(
        **_base("plan"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        title="Thyroid optimisation",
        items=[
            PlanItem(
                description="Increase levothyroxine to 88 mcg",
                targets=[medication.id, condition.id],
            )
        ],
        authored_by=provider.id,
    )

    flag = DataQualityFlag(
        **_base("flag", PIPELINE, origin=ProvenanceOrigin.SYSTEM_DERIVED),
        patient_id=patient_id,
        code=FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE,
        severity=Severity.HUMAN_REVIEW_REQUIRED,
        message="TSH: lab reported 'H' and the stored range agrees; recorded for the trail",
        targets=[
            FlagTarget(
                entity_type="LabResult", entity_id=lab.id, field_path="reported_interpretation"
            )
        ],
        candidates=[source_ref.id],
    )

    audit = AuditEvent(
        **_base("aud", PIPELINE, origin=ProvenanceOrigin.SYSTEM_DERIVED),
        patient_id=patient_id,
        action=AuditAction.CREATE,
        trace_id=new_id("trc"),
        actor=PIPELINE,
        targets=[lab.id],
        field_delta={"quantity": (None, "5.6 mIU/L")},
    )

    coverage = Coverage(
        **_base("cov"),
        patient_id=patient_id,
        payer="Meridian Health",
        member_id="MH-88213",
        effective_from=date(2026, 1, 1),
    )

    procedure = Procedure(
        **_base("proc"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        code=CodeableConcept(raw_text="thyroid ultrasound", system="ICD-10-PCS", code="BB44ZZZ"),
        performed_on=date(2026, 3, 12),
        performer_id=provider.id,
        outcome="no nodules",
    )

    goal = Goal(
        **_base("goal"),
        patient_id=patient_id,
        description="Keep TSH inside range without a dose increase",
        target_date=date(2026, 9, 1),
    )

    social = SocialFactor(
        **_base("soc"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        factor=CodeableConcept(raw_text="smoking status", system="LOINC", code="72166-2"),
        value="never smoked",
        asserted_on=date(2026, 3, 12),
    )

    task = Task(
        **_base("task"),
        patient_id=patient_id,
        encounter_id=encounter_id,
        description="Repeat TSH in six weeks",
        origin=TaskOrigin.HUMAN,
        status=TaskStatus.OPEN,
        assignee_id=provider.id,
        due_on=date(2026, 4, 23),
        source_ref=lab.id,
    )

    return {
        "patient": patient, "provider": provider, "consent": consent,
        "encounter": encounter, "source_ref": source_ref, "condition": condition,
        "allergy": allergy, "symptom": symptom, "medication": medication,
        "supplement": supplement,
        "lab": lab, "report": report, "vital": vital, "note": note, "plan": plan,
        "flag": flag, "audit": audit, "coverage": coverage, "procedure": procedure,
        "goal": goal, "social": social, "task": task,
    }


def test_every_built_entity_constructs_for_one_patient():
    # All twenty-two canonical entities, for one patient.
    cohort = build_cohort()
    assert len(cohort) == 22


def test_every_id_one_record_holds_about_another_resolves():
    # The point of this file. A dangling reference is invisible at unit level.
    c = build_cohort()
    known = {r.id for r in c.values()}
    patient_id = c["patient"].id
    provider_id = c["provider"].id

    references: list[tuple[str, str | None, set[str]]] = [
        ("patient.care_team[0].provider_id", c["patient"].care_team[0].provider_id, {provider_id}),
        ("condition.recorded_by", c["condition"].recorded_by, {provider_id}),
        ("allergy.recorded_by", c["allergy"].recorded_by, {provider_id}),
        ("medication.prescriber_id", c["medication"].prescriber_id, {provider_id}),
        ("lab.ordering_provider_id", c["lab"].ordering_provider_id, {provider_id}),
        ("note.author_id", c["note"].author_id, {provider_id}),
        ("plan.authored_by", c["plan"].authored_by, {provider_id}),
        ("encounter.participant_ids[0]", c["encounter"].participant_ids[0], {provider_id}),
        ("lab.report_id", c["lab"].report_id, {c["report"].id}),
        ("report.result_ids[0]", c["report"].result_ids[0], {c["lab"].id}),
        ("lab.provenance.source_refs[0]", c["lab"].provenance.source_refs[0], {c["source_ref"].id}),
        ("flag.targets[0].entity_id", c["flag"].targets[0].entity_id, known),
        ("flag.candidates[0]", c["flag"].candidates[0], {c["source_ref"].id}),
        ("audit.targets[0]", c["audit"].targets[0], known),
        ("plan.items[0].targets[0]", c["plan"].items[0].targets[0], known),
        ("plan.items[0].targets[1]", c["plan"].items[0].targets[1], known),
        ("procedure.performer_id", c["procedure"].performer_id, {provider_id}),
        ("task.assignee_id", c["task"].assignee_id, {provider_id}),
        ("task.source_ref", c["task"].source_ref, known),
    ]
    for label, value, allowed in references:
        assert value in allowed, f"{label} = {value!r} points at nothing"

    for name, record in c.items():
        encounter_id = getattr(record, "encounter_id", None)
        if encounter_id is not None:
            assert encounter_id == c["encounter"].id, f"{name}.encounter_id dangles"
        scoped = getattr(record, "patient_id", None)
        if scoped is not None and name != "patient":
            assert scoped == patient_id, f"{name}.patient_id is a different patient"


def test_the_report_and_its_lab_agree_in_both_directions():
    # A bidirectional link nothing had checked: either side could drift alone.
    c = build_cohort()
    assert c["lab"].report_id == c["report"].id
    assert c["lab"].id in c["report"].result_ids


def test_every_record_names_who_vouched_for_it():
    c = build_cohort()
    for name, record in c.items():
        prov = record.provenance
        assert prov.asserted_by.ref, f"{name} has no asserting actor"
        if prov.origin is ProvenanceOrigin.AI_EXTRACTION:
            assert prov.source_refs, f"{name} claims extraction with no source"
        if not prov.is_clinical_assertion:
            assert name in {"source_ref", "flag", "audit"}, (
                f"{name} is system_derived but is a clinical record"
            )


def test_the_extracted_lab_carries_its_evidence_and_confidence():
    # §6.19: ai_extraction requires a source ref, and the chain ends in a document.
    c = build_cohort()
    lab = c["lab"]
    assert lab.provenance.origin is ProvenanceOrigin.AI_EXTRACTION
    assert lab.provenance.extraction_confidence == 0.91
    assert lab.provenance.depth == 0
    assert c["source_ref"].document_id

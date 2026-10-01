"""One realistic, entirely fictional patient — D3.

Deliberately includes an active ai_processing consent, because without it the workflow D8
demonstrates cannot run at all (§10.3). `with_conflicting_glucose` produces the
unresolved-conflict case from §9.3: the value slot is empty and a blocking flag names both
candidates.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from pai3.entities.administrative import Consent
from pai3.entities.clinical import AllergyIntolerance, Condition, Criticality, Encounter
from pai3.entities.infrastructure import DataQualityFlag, FlagTarget, SourceReference
from pai3.entities.narrative import ClinicalNote, NoteType
from pai3.entities.people import CareTeamMembership, Patient, Provider
from pai3.entities.results import LabResult, VitalSign
from pai3.entities.therapy import (
    Medication,
    MedicationStatus,
    Supplement,
    SupplementStatus,
    TreatmentPlan,
)
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
from pai3.values.people import HumanName, PatientIdentifier, Preferences
from pai3.values.plan import PlanItem
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity, ReferenceRange
from pai3.values.text import ClinicalText

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
LAB_SYS = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")


def _prov(actor: Actor = DOC, origin: ProvenanceOrigin = ProvenanceOrigin.HUMAN) -> Provenance:
    return Provenance(origin=origin, asserted_by=actor, asserted_at=NOW)


def _base(actor: Actor = DOC) -> dict:
    return {
        "provenance": _prov(actor),
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": actor,
    }


@dataclass
class Fixture:
    now: datetime
    patient: Patient
    provider: Provider
    consents: list[Consent]
    encounters: list[Encounter]
    conditions: list[Condition]
    medications: list[Medication]
    supplements: list[Supplement]
    allergies: list[AllergyIntolerance]
    labs: list[LabResult]
    vitals: list[VitalSign]
    notes: list[ClinicalNote]
    plans: list[TreatmentPlan]
    flags: list[DataQualityFlag] = field(default_factory=list)
    source_refs: list[SourceReference] = field(default_factory=list)


def build_fixture(
    with_ai_consent: bool = True, with_conflicting_glucose: bool = False
) -> Fixture:
    provider = Provider(
        id=new_id("prov"), **_base(),
        name=HumanName(given=["Ana"], family="Reyes", prefix="Dr"),
        specialty="internal medicine",
    )
    patient_id = new_id("pat")
    encounter_id = new_id("enc")
    patient = Patient(
        id=patient_id,
        **_base(),
        identifiers=[
            PatientIdentifier(system="emr-west", value="MRN-4471", assigner="West Clinic"),
            PatientIdentifier(system="lab-portal", value="LP-99812"),
        ],
        names=[HumanName(given=["Dana"], family="Okafor")],
        birth_date=date(1979, 4, 2),
        sex_at_birth="female",
        preferences=Preferences(language="en", contact_preference="portal message"),
        care_team=[
            CareTeamMembership(
                provider_id=provider.id, role="internist",
                since=date(2021, 4, 1), is_primary=True,
            )
        ],
    )

    encounters = [
        Encounter(
            id=encounter_id, **_base(), patient_id=patient_id,
            encounter_type="office visit",
            started_at=NOW - timedelta(days=1, hours=2),
            ended_at=NOW - timedelta(days=1, hours=1),
            participant_ids=[provider.id],
            reason=CodeableConcept(raw_text="thyroid follow-up"),
        )
    ]

    consents: list[Consent] = [
        Consent(
            id=new_id("cons"), **_base(), patient_id=patient_id,
            scope=ConsentScope.TREATMENT, effective_from=NOW - timedelta(days=400),
        )
    ]
    if with_ai_consent:
        consents.append(
            Consent(
                id=new_id("cons"), **_base(), patient_id=patient_id,
                scope=ConsentScope.AI_PROCESSING, effective_from=NOW - timedelta(days=120),
            )
        )

    conditions = [
        Condition(
            id=new_id("cond"), **_base(), patient_id=patient_id,
            code=CodeableConcept(raw_text="hypothyroidism", system="ICD-10", code="E03.9"),
            clinical_status=ClinicalStatus.ACTIVE,
            verification_status=VerificationStatus.CONFIRMED,
            onset=date(2021, 5, 14),
        ),
        Condition(
            id=new_id("cond"), **_base(), patient_id=patient_id,
            code=CodeableConcept(
                raw_text="iron deficiency anaemia", system="ICD-10", code="D50.9"
            ),
            clinical_status=ClinicalStatus.RESOLVED,
            verification_status=VerificationStatus.CONFIRMED,
            onset=date(2019, 2, 3), abatement=date(2019, 11, 20),
        ),
    ]

    medications = [
        Medication(
            id=new_id("med"), **_base(), patient_id=patient_id,
            drug=CodeableConcept(raw_text="levothyroxine", system="RxNorm", code="10582"),
            dosage=Dosage(text="75 mcg daily", amount=75.0, unit="mcg", frequency="daily"),
            status=MedicationStatus.ACTIVE, started_on=date(2021, 6, 1),
            prescriber_id=DOC.ref,
        )
    ]

    allergies = [
        AllergyIntolerance(
            id=new_id("alg"), **_base(), patient_id=patient_id,
            substance=CodeableConcept(raw_text="penicillin", system="RxNorm", code="7980"),
            criticality=Criticality.HIGH,
            verification_status=VerificationStatus.CONFIRMED,
        )
    ]

    tsh = CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3")
    labs = [
        LabResult(
            id=new_id("lab"), **_base(LAB_SYS), patient_id=patient_id, biomarker=tsh,
            collection_date=NOW - timedelta(days=180),
            quantity=Quantity(value=3.8, unit="mIU/L"),
            reference_range=ReferenceRange(low=0.4, high=4.0),
            performing_lab="Meridian Labs",
        ),
        LabResult(
            id=new_id("lab"), **_base(LAB_SYS), patient_id=patient_id, biomarker=tsh,
            collection_date=NOW - timedelta(days=14),
            quantity=Quantity(value=5.6, unit="mIU/L"),
            reference_range=ReferenceRange(low=0.4, high=4.0),
            reported_interpretation=CodeableConcept(raw_text="H"),
            performing_lab="Meridian Labs",
        ),
    ]

    supplements = [
        Supplement(
            id=new_id("supp"), **_base(), patient_id=patient_id,
            substance=CodeableConcept(raw_text="vitamin D3"),
            dosage=Dosage(text="one dropper daily"),
            status=SupplementStatus.ACTIVE, started_on=date(2024, 11, 1),
            reported_reason="low vitamin D on a prior panel",
        ),
        Supplement(
            id=new_id("supp"), **_base(), patient_id=patient_id,
            substance=CodeableConcept(raw_text="biotin"),
            dosage=Dosage(text="5000 mcg daily", amount=5000.0, unit="mcg"),
            status=SupplementStatus.ACTIVE, started_on=date(2025, 9, 1),
            reported_reason="hair and nails",
        ),
    ]

    vitals = [
        VitalSign(
            id=new_id("vit"), **_base(), patient_id=patient_id, encounter_id=encounter_id,
            kind=CodeableConcept(raw_text="body weight", system="LOINC", code="29463-7"),
            measured_at=NOW - timedelta(days=1, hours=2),
            quantity=Quantity(value=71.2, unit="kg"),
            measurement_context=MeasurementContext.CLINICAL,
        ),
        VitalSign(
            id=new_id("vit"), **_base(), patient_id=patient_id,
            kind=CodeableConcept(raw_text="body weight", system="LOINC", code="29463-7"),
            measured_at=NOW - timedelta(days=3),
            quantity=Quantity(value=73.0, unit="kg"),
            measurement_context=MeasurementContext.PATIENT_REPORTED,
        ),
        VitalSign(
            id=new_id("vit"), **_base(), patient_id=patient_id, encounter_id=encounter_id,
            kind=CodeableConcept(
                raw_text="systolic blood pressure", system="LOINC", code="8480-6"
            ),
            measured_at=NOW - timedelta(days=1, hours=2),
            quantity=Quantity(value=128.0, unit="mmHg"),
            measurement_context=MeasurementContext.CLINICAL,
            body_position="seated",
        ),
    ]

    notes = [
        ClinicalNote(
            id=new_id("note"), **_base(), patient_id=patient_id, encounter_id=encounter_id,
            note_type=NoteType.PROGRESS,
            authored_at=NOW - timedelta(days=1, hours=1),
            author_id=provider.id,
            body=ClinicalText(
                value=(
                    "TSH 5.6 on the 26 Feb panel, up from 3.8 in September. Reports "
                    "fatigue and cold intolerance. Discussed raising levothyroxine to "
                    "88 mcg and repeating TSH in six weeks. Notes she started biotin in "
                    "the autumn."
                ),
                origin=TextOrigin.PRACTICE_AUTHORED,
                captured_by=DOC,
            ),
            signed_at=NOW - timedelta(days=1),
        ),
        ClinicalNote(
            id=new_id("note"), **_base(), patient_id=patient_id,
            note_type=NoteType.TELEPHONE,
            authored_at=NOW - timedelta(days=5),
            author_id=provider.id,
            body=ClinicalText(
                value=(
                    "Patient portal message, pasted: \"I have been taking the biotin "
                    "supplement since autumn, could that affect the thyroid blood test?\""
                ),
                origin=TextOrigin.TRANSCRIBED_EXTERNAL,
                captured_by=DOC,
            ),
        ),
    ]

    plans = [
        TreatmentPlan(
            id=new_id("plan"), **_base(), patient_id=patient_id, encounter_id=encounter_id,
            title="Thyroid optimisation, Q2 2026",
            items=[
                PlanItem(
                    description="Increase levothyroxine to 88 mcg daily",
                    targets=[medications[0].id, conditions[0].id],
                    due="2026-03-20",
                ),
                PlanItem(
                    description="Repeat TSH and free T4 in six weeks",
                    targets=[conditions[0].id],
                    due="2026-04-23",
                ),
                PlanItem(
                    description="Pause biotin for three days before the next draw",
                    targets=[supplements[1].id],
                ),
            ],
            authored_by=provider.id,
        )
    ]

    flags: list[DataQualityFlag] = []
    source_refs: list[SourceReference] = []

    if with_conflicting_glucose:
        glucose = CodeableConcept(raw_text="glucose, fasting", system="LOINC", code="1558-6")
        emr_ref = SourceReference(
            id=new_id("sref"), **_base(LAB_SYS), patient_id=patient_id,
            document_id=new_id("doc"), field_path="labs[3].value",
            quote="Glucose 5.5 mmol/L",
        )
        lab_ref = SourceReference(
            id=new_id("sref"), **_base(LAB_SYS), patient_id=patient_id,
            document_id=new_id("doc"), page=2, field_path="results[1].value",
            quote="Glucose 7.2 mmol/L",
        )
        source_refs.extend([emr_ref, lab_ref])
        # The slot stays empty: canonical never holds a value nobody vouched for (§9.3).
        unresolved_lab = LabResult(
            id=new_id("lab"), **_base(LAB_SYS), patient_id=patient_id, biomarker=glucose,
            collection_date=NOW - timedelta(days=14),
            quantity=None,
            reference_range=ReferenceRange(low=3.9, high=5.5),
            performing_lab="Meridian Labs",
        )
        labs.append(unresolved_lab)
        flags.append(
            DataQualityFlag(
                id=new_id("flag"),
                **_base(Actor(kind=ActorKind.PIPELINE, ref="normaliser", label="normaliser")),
                patient_id=patient_id,
                code=FlagCode.CONFLICTING_VALUES,
                severity=Severity.BLOCKING,
                message="fasting glucose: EMR 5.5 mmol/L against lab 7.2 mmol/L, unresolved",
                targets=[
                    FlagTarget(
                        entity_type="LabResult", entity_id=unresolved_lab.id,
                        field_path="quantity",
                    )
                ],
                candidates=[emr_ref.id, lab_ref.id],
            )
        )

    return Fixture(
        now=NOW, patient=patient, provider=provider, consents=consents,
        encounters=encounters, conditions=conditions, medications=medications,
        supplements=supplements, allergies=allergies, labs=labs, vitals=vitals,
        notes=notes, plans=plans, flags=flags, source_refs=source_refs,
    )

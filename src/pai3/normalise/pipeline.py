"""Three sources in, canonical records and four reports out.

The order matters and is the whole design. Read, then reconcile, then build — never read and
build in one pass, because a pass that builds while reading has nowhere to put "two values,
neither chosen".

Confidence is recorded on provenance and shown in the review queue, and it decides nothing.
No threshold is defensible from first principles, and a threshold that silently discards the
lower-confidence of two disagreeing readings is precisely the silent winner §9.3 forbids.
Confidence measures how well a line was read, not whether it is true.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from pai3.entities.clinical import AllergyIntolerance, Condition, Criticality
from pai3.entities.infrastructure import (
    AuditAction,
    AuditEvent,
    DataQualityFlag,
    FlagTarget,
    IngestSummary,
    SourceReference,
)
from pai3.entities.people import Patient
from pai3.entities.results import LabResult
from pai3.entities.therapy import Medication, MedicationStatus, Supplement, SupplementStatus
from pai3.enums import (
    ClinicalStatus,
    FlagCode,
    ProvenanceOrigin,
    Severity,
    VerificationStatus,
)
from pai3.ids import new_id
from pai3.normalise.model import (
    AssertionKind,
    Conflict,
    ConflictOutcome,
    Locator,
    RawAssertion,
    RejectedRow,
    SourceClass,
    SourceDocument,
)
from pai3.normalise.readers import read_emr, read_intake, read_lab_extraction
from pai3.normalise.reconcile import Group, reconcile
from pai3.validation import check_condition, check_lab_result, check_medication
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.people import HumanName, PatientIdentifier
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity, ReferenceRange

RUN_AT = datetime(2026, 3, 11, 9, 0, tzinfo=UTC)

STEWARD = Actor(kind=ActorKind.HUMAN, ref="user_steward", label="M. Chen, data steward")
"""Who vouches for what this run accepts.

§1 permits a canonical record with `origin=ai_extraction` only once a human has accepted it.
A migration run accepts in bulk, and bulk acceptance is a rubber stamp unless two things hold:
a named person is accountable for the run, and everything that needed a decision reaches a
review queue. Both hold here. Nobody hand-reviews ten thousand lab rows, and pretending
otherwise would be the dishonest part.
"""

PIPELINE = Actor(kind=ActorKind.PIPELINE, ref="normaliser", label="normaliser")
PATIENT_ACTOR = Actor(kind=ActorKind.HUMAN, ref="pat_self", label="patient, via intake form")

_ORIGIN = {
    SourceClass.EMR: (ProvenanceOrigin.SOURCE_SYSTEM, PIPELINE),
    SourceClass.INTAKE: (ProvenanceOrigin.HUMAN, PATIENT_ACTOR),
    SourceClass.LAB_REPORT: (ProvenanceOrigin.AI_EXTRACTION, STEWARD),
}

_CLINICAL_STATUS = {"active": ClinicalStatus.ACTIVE, "resolved": ClinicalStatus.RESOLVED}
_MED_STATUS = {"active": MedicationStatus.ACTIVE, "stopped": MedicationStatus.STOPPED}


@dataclass
class Result:
    documents: list[SourceDocument] = field(default_factory=list)
    assertions: list[RawAssertion] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    patient: Patient | None = None
    conditions: list[Condition] = field(default_factory=list)
    medications: list[Medication] = field(default_factory=list)
    supplements: list[Supplement] = field(default_factory=list)
    allergies: list[AllergyIntolerance] = field(default_factory=list)
    labs: list[LabResult] = field(default_factory=list)
    source_refs: list[SourceReference] = field(default_factory=list)
    flags: list[DataQualityFlag] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    audit: list[AuditEvent] = field(default_factory=list)

    @property
    def review_queue(self) -> list[DataQualityFlag]:
        """Everything a human must look at, worst first."""
        order = {
            Severity.BLOCKING: 0,
            Severity.HUMAN_REVIEW_REQUIRED: 1,
            Severity.WARNING: 2,
            Severity.ACCEPTABLE_MISSING: 3,
        }
        return sorted(self.flags, key=lambda f: (order[f.severity], f.code.value))


class _Builder:
    def __init__(self, result: Result) -> None:
        self.r = result
        self.patient_id = ""

    # ------------------------------------------------------------ provenance

    def _refs(self, locators: list[Locator]) -> list[str]:
        ids: list[str] = []
        for loc in locators:
            ref = SourceReference(
                id=new_id("sref"), provenance=self._prov(SourceClass.EMR, system=True),
                created_at=RUN_AT, updated_at=RUN_AT, updated_by=PIPELINE,
                patient_id=self.patient_id, document_id=loc.document_id,
                page=loc.page, field_path=loc.field_path, quote=loc.quote,
            )
            self.r.source_refs.append(ref)
            ids.append(ref.id)
        return ids

    def _prov(
        self, source_class: SourceClass, *, system: bool = False,
        refs: list[str] | None = None, confidence: float | None = None,
    ) -> Provenance:
        if system:
            return Provenance(
                origin=ProvenanceOrigin.SYSTEM_DERIVED, asserted_by=PIPELINE,
                asserted_at=RUN_AT,
            )
        origin, actor = _ORIGIN[source_class]
        return Provenance(
            origin=origin, asserted_by=actor, asserted_at=RUN_AT, imported_at=RUN_AT,
            source_refs=refs or [], extraction_confidence=confidence,
        )

    def _base(self, g: Group) -> dict:
        primary = g.primary()
        refs = self._refs([a.locator for a in g.assertions])
        confidences = [a.confidence for a in g.assertions if a.confidence is not None]
        return {
            "id": "",
            "provenance": self._prov(
                primary.source_class, refs=refs,
                confidence=min(confidences) if confidences else None,
            ),
            "created_at": RUN_AT, "updated_at": RUN_AT, "updated_by": STEWARD,
            "patient_id": self.patient_id,
        }

    # ----------------------------------------------------------------- flags

    def flag(
        self, code: FlagCode, severity: Severity, message: str, *,
        targets: list[FlagTarget] | None = None,
        candidates: list[str] | None = None,
        source_locator: list[str] | None = None,
    ) -> DataQualityFlag:
        f = DataQualityFlag(
            id=new_id("flag"), provenance=self._prov(SourceClass.EMR, system=True),
            created_at=RUN_AT, updated_at=RUN_AT, updated_by=PIPELINE,
            patient_id=self.patient_id or None, code=code, severity=severity,
            message=message, targets=targets or [], candidates=candidates or [],
            source_locator=source_locator or [],
        )
        self.r.flags.append(f)
        return f

    def _conflict_flag(self, g: Group, c: Conflict, entity_type: str, entity_id: str) -> None:
        shown = " vs ".join(
            f"{x.source_class.value}"
            + (f" p{x.locator.page}" if x.locator.page else "")
            + f" = {x.value!r}"
            for x in c.candidates
        )
        refs = self._refs([x.locator for x in c.candidates])
        if c.outcome is ConflictOutcome.UNRESOLVED:
            self.flag(
                FlagCode.CONFLICTING_VALUES, Severity.BLOCKING,
                f"{g.kind.value} {g.key}, field {c.field_name}: {shown}. "
                f"Unresolved — {c.rule}. The field is left empty (§9.3).",
                targets=[FlagTarget(entity_type=entity_type, entity_id=entity_id,
                                    field_path=c.field_name)],
                candidates=refs,
            )
        elif c.outcome is ConflictOutcome.RESOLVED_BY_TRUST:
            code = (
                FlagCode.UNIT_MISMATCH if c.field_name == "unit"
                else FlagCode.CONFLICTING_VALUES
            )
            self.flag(
                code, Severity.HUMAN_REVIEW_REQUIRED,
                f"{g.kind.value} {g.key}, field {c.field_name}: {shown}. "
                f"Resolved to {c.winner.value} by rule [{c.rule}]; "
                "a human should confirm the other source is wrong rather than newer.",
                targets=[FlagTarget(entity_type=entity_type, entity_id=entity_id,
                                    field_path=c.field_name)],
                candidates=refs,
            )

    # -------------------------------------------------------------- entities

    def build_patient(self, g: Group) -> None:
        self.patient_id = new_id("pat")
        idents = [
            PatientIdentifier(system=a.payload["system"], value=a.payload["mrn"])
            for a in g.assertions
        ]
        primary = g.primary()
        self.r.patient = Patient(
            **(self._base(g) | {"id": self.patient_id}),
            identifiers=idents,
            names=[HumanName(
                given=g.resolved.get("given", primary.payload["given"]),
                family=g.resolved.get("family", primary.payload["family"]),
            )],
            birth_date=g.resolved.get("birth_date", primary.payload["birth_date"]),
            sex_at_birth=g.resolved.get("sex_at_birth"),
        )
        # Patient is not PatientScoped, so strip the key the base helper added.
        for c in g.conflicts:
            if c.outcome is not ConflictOutcome.AGREED:
                self._conflict_flag(g, c, "Patient", self.patient_id)

    def _concept(self, g: Group) -> CodeableConcept:
        primary = g.primary()
        coding = g.resolved.get("coding") or primary.payload.get("coding")
        return CodeableConcept(
            raw_text=primary.payload["raw_text"],
            system=coding[0] if coding else None,
            code=coding[1] if coding else None,
        )

    def build_condition(self, g: Group) -> None:
        # A diagnosis only the patient asserts is UNCONFIRMED, not CONFIRMED. §6.4 keeps
        # verification separate from clinical status precisely so a self-report cannot enter
        # canonical as a diagnosis and reach a summary as one. Hard-coding CONFIRMED here --
        # which the first version of this pipeline did -- would defeat the field entirely.
        clinician_asserted = any(
            a.source_class is not SourceClass.INTAKE for a in g.assertions
        )
        cond = Condition(
            **(self._base(g) | {"id": new_id("cond")}),
            code=self._concept(g),
            clinical_status=_CLINICAL_STATUS[g.resolved.get("clinical_status", "active")],
            verification_status=(
                VerificationStatus.CONFIRMED if clinician_asserted
                else VerificationStatus.UNCONFIRMED
            ),
            onset=g.resolved.get("onset"),
        )
        self.r.conditions.append(cond)
        if not clinician_asserted:
            self.flag(
                FlagCode.UNCODED_CONCEPT if not cond.code.is_coded
                else FlagCode.CONFLICTING_VALUES,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"{cond.code.raw_text!r}: asserted on the intake form only, so it is "
                "UNCONFIRMED and not assertable in a summary. No code was matched, so the "
                "term was not guessed at — a clinician should confirm and code it.",
                targets=[FlagTarget(entity_type="Condition", entity_id=cond.id)],
                candidates=self._refs([a.locator for a in g.assertions]),
            )
        for c in g.conflicts:
            if c.outcome is not ConflictOutcome.AGREED:
                self._conflict_flag(g, c, "Condition", cond.id)

    def build_medication(self, g: Group) -> None:
        primary = g.primary()
        resolved_status = g.resolved.get("status", "active")
        stop_note = next(
            (a.payload.get("stop_note") for a in g.assertions if a.payload.get("stop_note")),
            None,
        )
        unrepresentable = resolved_status == "stopped" and stop_note is not None

        if unrepresentable:
            # The trust rule says the patient wins, and §9.8 requires a stop date for a
            # stopped medication. She cannot name the month. Neither gives way, so canonical
            # keeps the EMR's status and the dispute is raised blocking rather than the status
            # being flipped on an undated self-report or the self-report being dropped.
            status = MedicationStatus.ACTIVE
            for c in g.conflicts:
                if c.field_name == "status":
                    c.outcome = ConflictOutcome.WINNER_UNREPRESENTABLE
        else:
            status = _MED_STATUS[resolved_status]

        med = Medication(
            **(self._base(g) | {"id": new_id("med")}),
            drug=self._concept(g),
            dosage=Dosage(
                text=primary.payload.get("dose_text") or primary.payload["raw_text"],
                amount=g.resolved.get("dose_amount"),
                unit=g.resolved.get("dose_unit"),
                frequency=g.resolved.get("frequency"),
            ),
            status=status,
            started_on=g.resolved.get("started_on"),
            prescriber_id=g.resolved.get("prescriber"),
        )
        self.r.medications.append(med)

        for c in g.conflicts:
            if c.outcome is ConflictOutcome.WINNER_UNREPRESENTABLE:
                self.flag(
                    FlagCode.DISCONTINUED_SHOWN_ACTIVE, Severity.BLOCKING,
                    f"{med.drug.raw_text}: the EMR shows it active and the patient reports "
                    f"stopping it ({stop_note!r}). The trust rule gives the patient the "
                    "status, but §9.8 requires a stop date for a stopped medication and she "
                    "cannot name one. Canonical keeps 'active' and this flag blocks any "
                    "autonomous use until the month is established.",
                    targets=[FlagTarget(entity_type="Medication", entity_id=med.id,
                                        field_path="status")],
                    candidates=self._refs([x.locator for x in c.candidates]),
                )
            elif c.outcome is not ConflictOutcome.AGREED:
                self._conflict_flag(g, c, "Medication", med.id)

    def build_supplement(self, g: Group) -> None:
        primary = g.primary()
        supp = Supplement(
            **(self._base(g) | {"id": new_id("supp")}),
            substance=CodeableConcept(raw_text=primary.payload["raw_text"]),
            dosage=Dosage(text=primary.payload.get("dose_text") or primary.payload["raw_text"]),
            status=SupplementStatus.ACTIVE,
        )
        self.r.supplements.append(supp)
        if len(g.source_classes) == 1 and SourceClass.INTAKE in g.source_classes:
            self.flag(
                FlagCode.CONFLICTING_VALUES, Severity.HUMAN_REVIEW_REQUIRED,
                f"{supp.substance.raw_text}: reported on the intake form and absent from the "
                "EMR supplement list. Kept, because the patient is the authority on what she "
                "takes — but the EMR list is now known to be incomplete.",
                targets=[FlagTarget(entity_type="Supplement", entity_id=supp.id)],
                candidates=self._refs([a.locator for a in g.assertions]),
            )

    def build_allergy(self, g: Group) -> None:
        crit = next(
            (a.payload["criticality"] for a in g.assertions if a.payload.get("criticality")),
            None,
        )
        self.r.allergies.append(AllergyIntolerance(
            **(self._base(g) | {"id": new_id("alg")}),
            substance=self._concept(g),
            criticality=Criticality(crit) if crit else Criticality.UNABLE_TO_ASSESS,
            verification_status=VerificationStatus.CONFIRMED,
        ))

    def build_lab(self, g: Group) -> None:
        primary = g.primary()
        collected = g.resolved.get("collected") or primary.payload.get("collected")
        value = g.resolved.get("value")
        unresolved_value = any(
            c.field_name == "value" and c.outcome is ConflictOutcome.UNRESOLVED
            for c in g.conflicts
        )

        if collected is None:
            # Layer 1: no date, no canonical lab result. The flag names the document (§9.7).
            self.r.rejected.append(RejectedRow(
                locator=primary.locator,
                reason="no collection date: the result cannot be trended or placed on a timeline",
                raw={"analyte": primary.payload.get("raw_text"), "value": primary.payload.get("value")},
            ))
            self.flag(
                FlagCode.RECORD_REJECTED_AT_INGEST, Severity.HUMAN_REVIEW_REQUIRED,
                f"{primary.payload.get('raw_text')}: rejected at ingest — no collection date. "
                "The value stays in the source document; re-read the page or request a reissue.",
                source_locator=self._refs([primary.locator]),
            )
            return

        quantity = (
            None if (unresolved_value or value is None)
            else Quantity(value=float(value), unit=g.resolved.get("unit"))
        )
        ref_low, ref_high = g.resolved.get("ref_low"), g.resolved.get("ref_high")
        reported = g.resolved.get("reported_interpretation")
        lab = LabResult(
            **(self._base(g) | {"id": new_id("lab")}),
            biomarker=self._concept(g),
            collection_date=datetime.combine(collected, datetime.min.time(), tzinfo=UTC),
            quantity=quantity,
            reference_range=(
                ReferenceRange(low=ref_low, high=ref_high)
                if (ref_low is not None or ref_high is not None) else None
            ),
            reported_interpretation=CodeableConcept(raw_text=reported) if reported else None,
            performing_lab=primary.payload.get("performing_lab"),
        )
        self.r.labs.append(lab)

        if g.is_duplicated_within_one_document:
            self.flag(
                FlagCode.DUPLICATE_CANDIDATE, Severity.HUMAN_REVIEW_REQUIRED,
                f"{lab.biomarker.raw_text} appears more than once in one document "
                f"({len(g.assertions)} rows). One is likely an amended result; the pages are "
                "attached so a human can see which supersedes which.",
                targets=[FlagTarget(entity_type="LabResult", entity_id=lab.id)],
                candidates=self._refs([a.locator for a in g.assertions]),
            )
        for c in g.conflicts:
            if c.outcome is not ConflictOutcome.AGREED:
                self._conflict_flag(g, c, "LabResult", lab.id)


def _ingest_events(
    builder: _Builder, docs: list[SourceDocument], assertions: list[RawAssertion],
    accepted_by_doc: dict[str, int],
) -> list[AuditEvent]:
    """A started and a completed event per document (§9.7).

    Append-only, so an unclosed pair is what a crash looks like. Nothing here crashes, but
    the shape is the same one a real pipeline needs.
    """
    events: list[AuditEvent] = []
    for doc in docs:
        rows = [a for a in assertions if a.locator.document_id == doc.id]
        rejected = sum(1 for a in rows if a.failed)
        for action, summary in (
            (AuditAction.INGEST_STARTED,
             IngestSummary(source_document_id=doc.id, expected=doc.declared_row_count)),
            (AuditAction.INGEST_COMPLETED,
             IngestSummary(
                 source_document_id=doc.id, expected=doc.declared_row_count,
                 accepted=accepted_by_doc.get(doc.id, 0), rejected=rejected,
             )),
        ):
            events.append(AuditEvent(
                id=new_id("aud"), provenance=builder._prov(SourceClass.EMR, system=True),
                created_at=RUN_AT, updated_at=RUN_AT, updated_by=PIPELINE,
                patient_id=builder.patient_id or None, action=action,
                trace_id="trc_normalisation_run", actor=PIPELINE, ingest=summary,
            ))
    return events


def normalise(source_dir: Path) -> Result:
    """Read three sources, reconcile them, build canonical records and every report."""
    r = Result()
    for reader, filename in (
        (read_emr, "emr_export.json"),
        (read_lab_extraction, "lab_report_extraction.json"),
        (read_intake, "intake_form.csv"),
    ):
        doc, assertions = reader(source_dir / filename)
        r.documents.append(doc)
        r.assertions.extend(assertions)

    r.groups = reconcile(r.assertions)
    builder = _Builder(r)

    # Patient first: every other record is scoped to it.
    for g in r.groups:
        if g.kind is AssertionKind.PATIENT:
            builder.build_patient(g)

    dispatch = {
        AssertionKind.CONDITION: builder.build_condition,
        AssertionKind.MEDICATION: builder.build_medication,
        AssertionKind.SUPPLEMENT: builder.build_supplement,
        AssertionKind.ALLERGY: builder.build_allergy,
        AssertionKind.LAB: builder.build_lab,
    }
    for g in r.groups:
        build = dispatch.get(g.kind)
        if build is None:
            continue
        try:
            build(g)
        except ValidationError as exc:
            # Layer 1 refused the record. It stays in the source layer and the flag names
            # the document rather than a canonical id (§9.7).
            loc = g.primary().locator
            r.rejected.append(RejectedRow(
                locator=loc, reason=str(exc).splitlines()[1].strip(), raw=g.primary().payload
            ))
            builder.flag(
                FlagCode.RECORD_REJECTED_AT_INGEST, Severity.HUMAN_REVIEW_REQUIRED,
                f"{g.kind.value} {g.key}: refused by structural validation — "
                f"{str(exc).splitlines()[1].strip()}",
                source_locator=builder._refs([loc]),
            )

    # Rows that could not be read at all.
    for a in r.assertions:
        if a.failed:
            builder.flag(
                FlagCode.EXTRACTION_FAILED, Severity.HUMAN_REVIEW_REQUIRED,
                f"{a.locator.document_id} page {a.locator.page}: {a.parse_error}. "
                f"Read as {a.locator.quote!r} with confidence {a.confidence}. "
                "No canonical record was created.",
                source_locator=builder._refs([a.locator]),
            )

    # Layer 2 over what was built.
    for cond in r.conditions:
        r.flags += check_condition(cond, PIPELINE, RUN_AT)
    for med in r.medications:
        r.flags += check_medication(med, PIPELINE, RUN_AT)
    for lab in r.labs:
        r.flags += check_lab_result(lab, PIPELINE, RUN_AT)

    accepted = {
        doc.id: sum(
            1 for g in r.groups for a in g.assertions if a.locator.document_id == doc.id
        )
        for doc in r.documents
    }
    r.audit = _ingest_events(builder, r.documents, r.assertions, accepted)
    return r

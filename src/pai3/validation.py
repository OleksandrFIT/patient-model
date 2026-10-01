"""Layer-2 checks: the record exists, and these mark what is wrong with it (§9.1).

Layer 1 is the Pydantic validators on each entity — a structurally invalid record is
never created and the flag attaches to the source document instead (§9.7). Layer 2 runs
here, so that a lab with no unit stays visible in canonical rather than vanishing from
every brief and trend.

These functions are pure: they take a record and return flags. Persisting the flags and
closing them is the caller's job.
"""

from datetime import datetime

from pai3.entities.clinical import Condition
from pai3.entities.infrastructure import DataQualityFlag, FlagTarget
from pai3.entities.results import LabResult
from pai3.entities.therapy import Medication
from pai3.enums import FlagCode, ProvenanceOrigin, Severity
from pai3.ids import new_id
from pai3.interpretation import interpretation_disagrees
from pai3.values.actor import Actor
from pai3.values.provenance import Provenance


def _flag(
    code: FlagCode,
    severity: Severity,
    message: str,
    entity_type: str,
    entity_id: str,
    patient_id: str,
    actor: Actor,
    now: datetime,
    field_path: str | None = None,
) -> DataQualityFlag:
    return DataQualityFlag(
        id=new_id("flag"),
        provenance=Provenance(
            origin=ProvenanceOrigin.SYSTEM_DERIVED, asserted_by=actor, asserted_at=now
        ),
        created_at=now,
        updated_at=now,
        updated_by=actor,
        patient_id=patient_id,
        code=code,
        severity=severity,
        message=message,
        targets=[
            FlagTarget(entity_type=entity_type, entity_id=entity_id, field_path=field_path)
        ],
    )


def check_lab_result(lab: LabResult, actor: Actor, now: datetime) -> list[DataQualityFlag]:
    """D5's lab rules, as layer-2 checks.

    An empty value slot is not flagged here. Three different situations present as an
    empty slot, and only the normaliser that produced the record knows which — so the
    flag with its candidates is raised there (§9.3). Absence alone proves nothing.
    """
    out: list[DataQualityFlag] = []
    args = ("LabResult", lab.id, lab.patient_id, actor, now)

    if lab.quantity is not None and lab.quantity.unit is None:
        out.append(
            _flag(
                FlagCode.MISSING_UNIT,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"{lab.biomarker.raw_text}: value {lab.quantity.value} has no unit",
                *args,
                field_path="quantity",
            )
        )
    if lab.quantity is not None and lab.reference_range is None:
        out.append(
            _flag(
                FlagCode.MISSING_REFERENCE_RANGE,
                Severity.WARNING,
                f"{lab.biomarker.raw_text}: no reference range from the performing lab",
                *args,
                field_path="reference_range",
            )
        )
    if not lab.biomarker.is_coded:
        out.append(
            _flag(
                FlagCode.UNCODED_CONCEPT,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"analyte {lab.biomarker.raw_text!r} is not coded",
                *args,
                field_path="biomarker",
            )
        )
    if interpretation_disagrees(lab.reported_interpretation, lab.computed_interpretation):
        out.append(
            _flag(
                FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE,
                Severity.HUMAN_REVIEW_REQUIRED,
                (
                    f"{lab.biomarker.raw_text}: lab reported "
                    f"{lab.reported_interpretation.raw_text!r} but the stored range gives "
                    f"{lab.computed_interpretation.value!r} — the stored range is suspect"
                ),
                *args,
                field_path="reported_interpretation",
            )
        )
    return out


def check_condition(
    condition: Condition, actor: Actor, now: datetime
) -> list[DataQualityFlag]:
    if condition.code.is_coded:
        return []
    return [
        _flag(
            FlagCode.UNCODED_CONCEPT,
            Severity.HUMAN_REVIEW_REQUIRED,
            f"condition {condition.code.raw_text!r} is not coded",
            "Condition",
            condition.id,
            condition.patient_id,
            actor,
            now,
            field_path="code",
        )
    ]


def check_medication(med: Medication, actor: Actor, now: datetime) -> list[DataQualityFlag]:
    """A current medication with no parsed dose cannot be reconciled safely."""
    out: list[DataQualityFlag] = []
    args = ("Medication", med.id, med.patient_id, actor, now)

    if med.is_current and (med.dosage.amount is None or med.dosage.unit is None):
        out.append(
            _flag(
                FlagCode.MISSING_UNIT,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"{med.drug.raw_text}: dose {med.dosage.text!r} has no parsed amount and unit",
                *args,
                field_path="dose",
            )
        )
    if not med.drug.is_coded:
        out.append(
            _flag(
                FlagCode.UNCODED_CONCEPT,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"drug {med.drug.raw_text!r} is not coded",
                *args,
                field_path="drug",
            )
        )
    return out

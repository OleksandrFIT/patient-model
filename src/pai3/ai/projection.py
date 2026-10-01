"""The only place canonical data becomes model context (§10.4, §10.6).

Four duties: refuse any caller without an `AIReadScope`, emit `AIPatientView` instead of
`Patient`, preserve each text span's origin, and report everything the budget left out.

Budget units here are records rather than tokens. A token count depends on the engine's
tokeniser, which belongs to the adapter; the shape of the decision — what is droppable,
what is reported — is the same either way, and keeping it countable keeps it testable.
"""

from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel

from pai3.ai.artifact import OmissionReason, OmittedRecord
from pai3.ai.scope import AIReadScope
from pai3.entities.clinical import AllergyIntolerance, Condition
from pai3.entities.people import Patient
from pai3.entities.therapy import Medication
from pai3.enums import ClinicalStatus
from pai3.ids import CanonicalRef


class AIPatientView(BaseModel):
    """The only patient shape a projection emits (§10.4).

    No names, identifiers, contacts, addresses or date of birth. Age replaces the
    birthday because dosing and reference ranges need an age. Since the type has no
    identity fields, "the model saw the patient's name" is unexpressible.

    The deeper reason is that `fields_read` (§6.3) exists to measure exposure, and a
    default projection carrying identifiers makes that measurement meaningless.
    """

    patient_id: str
    age_years: int | None
    sex: str | None


class BudgetUsage(BaseModel):
    limit: int
    consumed: int


class ProjectionResult(BaseModel):
    included: list[CanonicalRef]
    omitted: list[OmittedRecord]
    budget: BudgetUsage


class BudgetExceeded(RuntimeError):
    """A non-droppable category did not fit, so the budget is wrong, not the allergies.

    §10.6: the generation is refused rather than truncated. The caller still writes an
    artifact with no output so that the refusal is visible.
    """


class PatientScopedRecord(Protocol):
    """What a projection needs of a record: its identity and whose it is."""

    id: str
    version: int
    patient_id: str


def _is_non_droppable(record: object) -> bool:
    """§10.6's list: allergies, current medications, active conditions.

    Open blocking flags are the fourth member and are carried separately, on the
    read-model's required `unresolved` field (§9.4), so they never pass through here.
    """
    if isinstance(record, AllergyIntolerance):
        return True
    if isinstance(record, Medication):
        return record.is_current
    if isinstance(record, Condition):
        return record.clinical_status in (ClinicalStatus.ACTIVE, ClinicalStatus.RECURRENCE)
    return False


def _ref(record: PatientScopedRecord) -> CanonicalRef:
    return CanonicalRef(
        entity_type=type(record).__name__, entity_id=record.id, version=record.version
    )


def _check(scope: AIReadScope, patient_id: str, now: datetime | None) -> None:
    if scope.patient_id != patient_id:
        raise PermissionError(f"scope authorises {scope.patient_id}, not {patient_id}")
    if now is not None and not scope.is_valid_at(now):
        raise PermissionError(f"scope expired at {scope.valid_until.isoformat()}")


def project_patient(
    patient: Patient, scope: AIReadScope, on: date, now: datetime | None = None
) -> AIPatientView:
    _check(scope, patient.id, now)
    return AIPatientView(
        patient_id=patient.id,
        age_years=patient.age_years(on),
        sex=patient.sex_at_birth,
    )


def project_records(
    records: list[PatientScopedRecord],
    scope: AIReadScope,
    budget: int,
    now: datetime | None = None,
) -> ProjectionResult:
    """Select within the budget, non-droppable records first.

    Raises BudgetExceeded when the non-droppable set alone does not fit. Everything else
    that does not fit is reported in `omitted` with a reason — nothing is dropped without
    being named.
    """
    if budget < 1:
        raise BudgetExceeded(
            f"budget is {budget}; a generation with no inputs produces nothing to review"
        )
    for record in records:
        _check(scope, record.patient_id, now)

    required = [r for r in records if _is_non_droppable(r)]
    optional = [r for r in records if not _is_non_droppable(r)]

    if len(required) > budget:
        kinds = sorted({type(r).__name__ for r in required})
        raise BudgetExceeded(
            f"non-droppable records ({', '.join(kinds)}) need {len(required)} slots "
            f"but the budget is {budget}; the budget is wrong, not the records"
        )

    included = list(required)
    omitted: list[OmittedRecord] = []
    for record in optional:
        if len(included) < budget:
            included.append(record)
        else:
            omitted.append(
                OmittedRecord(ref=_ref(record), reason=OmissionReason.CONTEXT_BUDGET)
            )

    return ProjectionResult(
        included=[_ref(r) for r in included],
        omitted=omitted,
        budget=BudgetUsage(limit=budget, consumed=len(included)),
    )

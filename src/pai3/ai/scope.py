"""The consent gate (§10.3).

`AIReadScope` is a capability: every projection takes one, no overload takes a bare
`patient_id`, and the only way to obtain one is `authorize_ai_read`. That makes reading a
patient's data for a model without a consent check unexpressible rather than merely
discouraged.

It is deliberately not persisted — a stored capability is a forgeable and replayable one.

This gates the AI path only. A physician reading a chart needs `treatment` consent under
different rules including break-glass, and this model does not build general access
control (§10.3).
"""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel

from pai3.entities.administrative import Consent
from pai3.enums import ConsentScope, RecordStatus
from pai3.ids import new_id

MAX_SCOPE_LIFETIME = timedelta(hours=1)
"""A token good forever is a token nobody re-checks. §10.3's mid-flight limit."""


class ConsentDenied(PermissionError):
    """No active ai_processing consent. Refusal is the default path, not a return value."""


class AIReadScope(BaseModel):
    patient_id: str
    consent_id: str
    scope: Literal["ai_processing"] = "ai_processing"
    valid_until: AwareDatetime
    trace_id: str

    model_config = {"frozen": True}

    def is_valid_at(self, moment: datetime) -> bool:
        return moment <= self.valid_until


def authorize_ai_read(
    patient_id: str, consents: list[Consent], now: datetime
) -> AIReadScope:
    """Produce a scope, or refuse.

    `consents` is passed in rather than queried so this stays a pure function. The caller
    supplies the patient's consent records; filtering them is this function's job.
    """
    for consent in consents:
        if consent.patient_id != patient_id:
            continue
        if consent.scope is not ConsentScope.AI_PROCESSING:
            continue
        if consent.record_status is not RecordStatus.ACTIVE:
            continue
        if not consent.is_active_at(now):
            continue
        ceiling = now + MAX_SCOPE_LIFETIME
        valid_until = (
            min(ceiling, consent.effective_until)
            if consent.effective_until is not None
            else ceiling
        )
        return AIReadScope(
            patient_id=patient_id,
            consent_id=consent.id,
            valid_until=valid_until,
            trace_id=new_id("trc"),
        )
    raise ConsentDenied(
        f"no active ai_processing consent for patient {patient_id} at {now.isoformat()}"
    )

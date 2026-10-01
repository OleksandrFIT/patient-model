"""Consent and Coverage.

Consent is a separate entity rather than a field on Patient because it is an enforcement
point: an agent asks for it before doing anything, and §10.3 turns that question into a
capability token. Embedded, a revocation would bump the patient version and "whose
AI-processing consent expires this month" would be unanswerable. Coverage arrives in
Phase 3.
"""

from datetime import date, datetime

from pydantic import AwareDatetime, model_validator

from pai3.base import PatientScoped
from pai3.enums import ConsentScope
from pai3.values.actor import Actor


class Consent(PatientScoped):
    scope: ConsentScope
    effective_from: AwareDatetime
    effective_until: AwareDatetime | None = None
    revoked_at: AwareDatetime | None = None
    revoked_by: Actor | None = None
    document_ref: str | None = None

    @model_validator(mode="after")
    def _revocation_is_attributable(self) -> "Consent":
        if self.revoked_at is not None and self.revoked_by is None:
            raise ValueError("revoked_at requires revoked_by")
        if self.revoked_at is not None and self.revoked_at < self.effective_from:
            raise ValueError("revoked_at precedes effective_from")
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise ValueError("effective_until precedes effective_from")
        return self

    def is_active_at(self, moment: datetime) -> bool:
        """Revocation beats the window: a withdrawn consent is inactive at once."""
        if self.revoked_at is not None and moment >= self.revoked_at:
            return False
        if moment < self.effective_from:
            return False
        return self.effective_until is None or moment <= self.effective_until


class Coverage(PatientScoped):
    """Payment context. Thin by design (§4).

    Kept because a concierge practice commonly bills labs and procedures through
    insurance even when membership is self-pay, so "if relevant" in the brief is a scope
    call rather than permission to assume it away. Outside AI read scope (§10.4): payment
    context is not clinical.
    """

    payer: str
    member_id: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None

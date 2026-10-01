"""Patient and Provider.

Patient inherits CanonicalRecord rather than PatientScoped because its own id is the
scope. Provider does too, for a reason that is governance and not tidiness: a provider
record is not covered by any patient's consent scope and is not part of a patient data
export (§2.4).
"""

from datetime import date

from pydantic import BaseModel, Field, model_validator

from pai3.base import CanonicalRecord
from pai3.values.people import (
    Address,
    ContactPoint,
    HumanName,
    PatientIdentifier,
    Preferences,
)


class CareTeamMembership(BaseModel):
    """Embedded on Patient: a membership is read with the patient, never alone (§5)."""

    provider_id: str
    role: str
    since: date | None = None
    is_primary: bool = False


class Patient(CanonicalRecord):
    identifiers: list[PatientIdentifier] = Field(min_length=1)
    names: list[HumanName] = Field(min_length=1)
    birth_date: date | None = None
    sex_at_birth: str | None = None
    gender_identity: str | None = None
    contacts: list[ContactPoint] = Field(default_factory=list)
    addresses: list[Address] = Field(default_factory=list)
    preferences: Preferences | None = None
    care_team: list[CareTeamMembership] = Field(default_factory=list)

    @model_validator(mode="after")
    def _identifier_values_are_present(self) -> "Patient":
        if any(not i.value.strip() for i in self.identifiers):
            raise ValueError("every patient identifier needs a value")
        return self

    def age_years(self, on: date) -> int | None:
        """Derived, never stored. §10.4's projection carries this and not birth_date."""
        if self.birth_date is None:
            return None
        had_birthday = (on.month, on.day) >= (self.birth_date.month, self.birth_date.day)
        return on.year - self.birth_date.year - (0 if had_birthday else 1)


class Provider(CanonicalRecord):
    """Practice reference data: prescriber, note author, lab orderer.

    Normalised rather than a free-text name on each record, so that "every medication
    prescribed by Dr X" is answerable and names do not drift into
    "J. Smith" / "John Smith MD" (§5).
    """

    name: HumanName
    identifiers: list[PatientIdentifier] = Field(default_factory=list)
    specialty: str | None = None
    is_external: bool = False

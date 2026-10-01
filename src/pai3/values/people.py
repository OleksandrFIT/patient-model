"""Identity parts, embedded on Patient.

These are embedded rather than normalised because they are read with the patient
every time and never queried on their own (§5).
"""

from pydantic import BaseModel, Field


class PatientIdentifier(BaseModel):
    """One identifier from one system.

    Patient carries a list of these rather than a single `mrn` field: a concierge
    practice pulls from several EMRs and one patient has several MRNs, which §6.12
    names as the primary cause of duplicate patient records.
    """

    system: str = Field(min_length=1)
    value: str = Field(min_length=1)
    assigner: str | None = None


class HumanName(BaseModel):
    given: list[str] = Field(default_factory=list)
    family: str = Field(min_length=1)
    prefix: str | None = None


class ContactPoint(BaseModel):
    system: str
    value: str
    use: str | None = None


class Address(BaseModel):
    lines: list[str] = Field(default_factory=list)
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None


class Preferences(BaseModel):
    """Attributes of the person, as distinct from a Goal (§6 entity table)."""

    language: str | None = None
    contact_preference: str | None = None
    notes: str | None = None

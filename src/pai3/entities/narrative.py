"""ClinicalNote.

`note_type` has no `patient_message` value: a note is a record of the practice, not a
container for external text, so a patient message stays in the source layer and becomes
an ExtractionCandidate, a Task, or a note that quotes it — and such a note is
TRANSCRIBED_EXTERNAL (§10.1).

A fact mentioned in the prose does not live here either. It becomes a Condition whose
provenance records ai_extraction with source_refs pointing at the span, and it enters
canonical only when a human accepts it (§6.14).
"""

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from pai3.base import ClinicalRecord
from pai3.values.text import ClinicalText


class NoteType(StrEnum):
    PROGRESS = "progress"
    INTAKE = "intake"
    CONSULT = "consult"
    TELEPHONE = "telephone"


class ClinicalNote(ClinicalRecord):
    note_type: NoteType
    authored_at: AwareDatetime
    author_id: str = Field(min_length=1, description="Provider id")
    body: ClinicalText
    addenda: list[ClinicalText] = Field(default_factory=list)
    signed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _signature_follows_authoring(self) -> "ClinicalNote":
        if self.signed_at is not None and self.signed_at < self.authored_at:
            raise ValueError("signed_at precedes authored_at")
        return self

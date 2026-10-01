"""How something is taken.

`text` is required and the structured parts optional, for the same reason
CodeableConcept keeps `raw_text` (§6.10): a supplement arrives as "one dropper", and
refusing it loses the fact that the patient is taking something.
"""

from pydantic import BaseModel, Field


class Dosage(BaseModel):
    text: str = Field(min_length=1)
    amount: float | None = None
    unit: str | None = None
    frequency: str | None = None
    route: str | None = None

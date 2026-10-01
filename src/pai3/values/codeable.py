"""A clinical concept as received, optionally coded.

Requiring ICD-10 / RxNorm / LOINC at ingestion is unrealistic, so `raw_text` is
always required and the code is optional (§6.10). An uncoded concept raises a
HUMAN_REVIEW_REQUIRED flag rather than being rejected — see validation.py.
"""

from pydantic import BaseModel, Field, model_validator


class CodeableConcept(BaseModel):
    raw_text: str = Field(min_length=1)
    system: str | None = None
    code: str | None = None
    display: str | None = None

    @model_validator(mode="after")
    def _raw_text_is_not_whitespace(self) -> "CodeableConcept":
        if not self.raw_text.strip():
            raise ValueError("raw_text must not be blank")
        return self

    @model_validator(mode="after")
    def _code_requires_a_system(self) -> "CodeableConcept":
        if self.code is not None and self.system is None:
            raise ValueError("code requires the system that issued it")
        return self

    @property
    def is_coded(self) -> bool:
        return self.code is not None and self.system is not None

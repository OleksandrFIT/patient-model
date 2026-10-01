"""A flag as a read-model shows it.

Read-models carry a required list of these so that a brief which dropped a flagged
record cannot be constructed (§9.4). It is a projection of DataQualityFlag, not the
flag itself — the flag is an entity with its own lifecycle (§6.5).
"""

from pydantic import BaseModel, Field

from pai3.enums import FlagCode, Severity


class FlagSummary(BaseModel):
    flag_id: str
    code: FlagCode
    severity: Severity
    message: str = Field(min_length=1)

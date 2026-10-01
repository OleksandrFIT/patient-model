"""Who or what acted.

A string would not do: §2.1 requires `updated_by` to distinguish a person from a
pipeline from an agent, and §10.4's rights matrix is unenforceable if the four are
indistinguishable at the point of a write.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class ActorKind(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"
    PIPELINE = "pipeline"
    AGENT = "agent"


class Actor(BaseModel):
    kind: ActorKind
    ref: str = Field(min_length=1)
    label: str = Field(min_length=1)

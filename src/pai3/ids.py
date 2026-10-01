"""Prefixed ULIDs.

The prefix exists so that an identifier appearing in a log line, a prompt or an AI
citation can be attributed to an entity without a database lookup, and so that
`med_` against `supp_` catches a type substitution before validation runs. It is a
readability affordance and never a type check: resolution against the real target is
the registry's job (spec §8.3).
"""

from pydantic import BaseModel, Field
from ulid import ULID


def new_id(prefix: str) -> str:
    if not prefix:
        raise ValueError("prefix must not be empty")
    if "_" in prefix:
        raise ValueError(f"prefix must not contain '_': {prefix!r}")
    return f"{prefix}_{ULID()}"


class CanonicalRef(BaseModel):
    """A pointer to a canonical record at a known version.

    The version is required rather than optional because every consumer of a ref
    needs reproducibility: §6.19's depth computation and §10.2's prompt
    reconstruction both break if a ref can silently follow a record forward.
    """

    entity_type: str
    entity_id: str
    version: int = Field(ge=1)

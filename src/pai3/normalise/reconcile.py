"""Grouping assertions and resolving what they disagree about.

The trust order is **explicit and per field class**, never "the newest wins". §9.3 forbids
recency as a tiebreak: it is a heuristic, not a vouching. Where no rule applies, the field
stays empty and the conflict is the record of why.

Nothing here writes a canonical record. It decides what the value is, or that there is not
one, and `pipeline.py` builds from that.
"""

from typing import Any

from pai3.normalise.model import (
    AssertionKind,
    Conflict,
    ConflictCandidate,
    ConflictOutcome,
    RawAssertion,
    SourceClass,
)

EMR = SourceClass.EMR
LAB = SourceClass.LAB_REPORT
INTAKE = SourceClass.INTAKE

TRUST_ORDER: dict[str, tuple[SourceClass, ...]] = {
    "prescribed": (EMR, INTAKE),
    "self_reported": (INTAKE, EMR),
    "lab_value": (LAB, EMR, INTAKE),
    "coding": (EMR, LAB, INTAKE),
    "demographics": (EMR, INTAKE),
}
"""Which source class wins, by what kind of claim it is.

- **prescribed** — a dose, a prescriber, a start date. The prescriber's record is the
  authority on what was prescribed; a patient's recollection of milligrams is not.
- **self_reported** — whether she is still taking it, and what supplements she buys. Here the
  patient is the *only* reliable source, and the EMR is a record of what was intended.
- **lab_value** — the report is primary and the EMR holds a transcription of it.
- **coding** — whoever already supplied a code; free text cannot outrank it.

Two assertions of the same class that disagree are never resolved automatically, whatever
their confidence scores say. Confidence measures how well a line was read, not whether it
is true.
"""

FIELD_RULE: dict[tuple[AssertionKind, str], str] = {
    # `dose_text` and other free text are deliberately absent. "75 mcg daily" against
    # "levothyroxine 75mcg daily" is a difference in phrasing, not in fact, and reporting it
    # as a conflict buries the one that matters two lines below it. Free text is taken from
    # the primary source; the structured amount and unit are what get reconciled.
    (AssertionKind.MEDICATION, "dose_amount"): "prescribed",
    (AssertionKind.MEDICATION, "dose_unit"): "prescribed",
    (AssertionKind.MEDICATION, "frequency"): "prescribed",
    (AssertionKind.MEDICATION, "prescriber"): "prescribed",
    (AssertionKind.MEDICATION, "started_on"): "prescribed",
    (AssertionKind.MEDICATION, "status"): "self_reported",
    (AssertionKind.SUPPLEMENT, "status"): "self_reported",
    (AssertionKind.CONDITION, "clinical_status"): "prescribed",
    (AssertionKind.CONDITION, "onset"): "prescribed",
    (AssertionKind.CONDITION, "coding"): "coding",
    (AssertionKind.LAB, "value"): "lab_value",
    (AssertionKind.LAB, "unit"): "lab_value",
    (AssertionKind.LAB, "ref_low"): "lab_value",
    (AssertionKind.LAB, "ref_high"): "lab_value",
    (AssertionKind.LAB, "reported_interpretation"): "lab_value",
    (AssertionKind.PATIENT, "birth_date"): "demographics",
    (AssertionKind.PATIENT, "sex_at_birth"): "demographics",
    (AssertionKind.PATIENT, "family"): "demographics",
    (AssertionKind.PATIENT, "given"): "demographics",
}

RESOLVABLE_FIELDS = frozenset(name for _, name in FIELD_RULE)


class Group:
    """Every assertion about one fact, across every source."""

    def __init__(self, kind: AssertionKind, key: str) -> None:
        self.kind = kind
        self.key = key
        self.assertions: list[RawAssertion] = []
        self.resolved: dict[str, Any] = {}
        self.conflicts: list[Conflict] = []

    @property
    def source_classes(self) -> set[SourceClass]:
        return {a.source_class for a in self.assertions}

    @property
    def documents(self) -> set[str]:
        return {a.locator.document_id for a in self.assertions}

    @property
    def is_duplicated_within_one_document(self) -> bool:
        """Two rows of the same document about one fact — a genuine double entry."""
        seen: set[str] = set()
        for a in self.assertions:
            if a.locator.document_id in seen:
                return True
            seen.add(a.locator.document_id)
        return False

    @property
    def corroborated(self) -> bool:
        """Asserted by more than one source, with nothing unresolved between them."""
        return len(self.source_classes) > 1 and not any(
            c.outcome is not ConflictOutcome.AGREED for c in self.conflicts
        )

    def primary(self) -> RawAssertion:
        """The assertion whose non-contested fields the record is built from."""
        order = TRUST_ORDER["coding"]
        return min(
            self.assertions,
            key=lambda a: order.index(a.source_class) if a.source_class in order else 99,
        )


def group(assertions: list[RawAssertion]) -> list[Group]:
    """Collect assertions by (kind, key). Failed rows are not grouped — they assert nothing."""
    buckets: dict[tuple[AssertionKind, str], Group] = {}
    for a in assertions:
        if a.failed:
            continue
        g = buckets.setdefault((a.kind, a.key), Group(a.kind, a.key))
        g.assertions.append(a)
    return list(buckets.values())


def _candidates(g: Group, field: str) -> list[tuple[RawAssertion, Any]]:
    return [(a, a.payload[field]) for a in g.assertions if a.payload.get(field) is not None]


def resolve(g: Group) -> None:
    """Fill `g.resolved` and record a `Conflict` for every field that needed a decision."""
    fields = {f for a in g.assertions for f in a.payload} & RESOLVABLE_FIELDS
    for field in sorted(fields):
        cands = _candidates(g, field)
        if not cands:
            continue
        candidates = [
            ConflictCandidate(
                source_class=a.source_class, value=v, locator=a.locator,
                confidence=a.confidence,
            )
            for a, v in cands
        ]
        distinct = {repr(v) for _, v in cands}

        if len(distinct) == 1:
            g.resolved[field] = cands[0][1]
            if len(g.source_classes) > 1:
                g.conflicts.append(Conflict(
                    kind=g.kind, key=g.key, field_name=field,
                    outcome=ConflictOutcome.AGREED, candidates=candidates,
                ))
            continue

        rule_name = FIELD_RULE.get((g.kind, field))
        order = TRUST_ORDER.get(rule_name) if rule_name else None
        if order is None:
            g.conflicts.append(Conflict(
                kind=g.kind, key=g.key, field_name=field,
                outcome=ConflictOutcome.UNRESOLVED, candidates=candidates,
                rule="no trust rule covers this field",
            ))
            continue

        ranked = sorted(
            cands,
            key=lambda c: order.index(c[0].source_class)
            if c[0].source_class in order
            else 99,
        )
        top_class = ranked[0][0].source_class
        tied = [c for c in ranked if c[0].source_class is top_class]

        if len(tied) > 1 and len({repr(v) for _, v in tied}) > 1:
            # Same source class, different values. No rule can break this, and §9.3 forbids
            # inventing one: the field stays empty.
            g.conflicts.append(Conflict(
                kind=g.kind, key=g.key, field_name=field,
                outcome=ConflictOutcome.UNRESOLVED, candidates=candidates,
                rule=f"{rule_name}: both candidates are {top_class.value}, so no rule applies",
            ))
            continue

        g.resolved[field] = ranked[0][1]
        g.conflicts.append(Conflict(
            kind=g.kind, key=g.key, field_name=field,
            outcome=ConflictOutcome.RESOLVED_BY_TRUST, candidates=candidates,
            winner=top_class,
            rule=f"{rule_name}: {' > '.join(s.value for s in order)}",
        ))


def reconcile(assertions: list[RawAssertion]) -> list[Group]:
    groups = group(assertions)
    for g in groups:
        resolve(g)
    return groups

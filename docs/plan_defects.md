# Plan defects found during implementation

Running log, kept while implementing `docs/implementation_plan.md`. Feeds D10, which asks
what the AI output got wrong, what was accepted, what was rejected and why.

The plan was itself AI-written, from a spec that was also AI-assisted. This file is the
honest record of where it was wrong, what each error would have cost, and how it surfaced.
Entries are added as they are found rather than reconstructed afterwards — a defect log
assembled from memory at the end shows.

Phases 1–4 complete at the time of writing; Phase 5 pending.

---

## Summary

| # | Task | Defect | Would have caused | Found by |
|---|---|---|---|---|
| 1 | 10 | A validator that can never run | Silent erosion of a constraint | Checking the assumption first |
| 2 | 11 | Comparison before the `None` guard, twice | `TypeError` on the commonest range shape | **The plan's own tests** |
| 3 | 15 | Bare class attribute on a Pydantic model | Module fails to import at all, ×5 entities | Checking the assumption first |
| 4 | 24 | Naive `datetime` where the model uses `AwareDatetime` | An unorderable review timestamp, silently | Consistency check against `base.py` |

Two of the four would have been caught by running the code. One was caught by the tests the
plan itself specified. One — defect 1 — would never have failed anything, which is why it
is in this list at all.

---

## 1. Task 10 — a validator that can never run

**The plan wrote** `created_at: AwareDatetime` *and* a `field_validator` raising when
`tzinfo is None`.

**Why that is wrong.** Pydantic rejects a naive datetime while coercing the input, before
any `field_validator` runs. The validator is unreachable.

**What it would have cost.** Nothing at runtime, which is the problem. A reader meets the
validator and concludes that is where the constraint lives. From there it is one step to
"`AwareDatetime` is redundant, the validator covers it" — and the real guard is removed
while the dead one stays, looking reassuring.

**Fixed.** Removed; the reason is in `CanonicalRecord`'s docstring so the next reader does
not re-add it. Verified afterwards that a naive timestamp is still refused.

---

## 2. Task 11 — the comparison ran before the guard

**The plan wrote:**

```python
strictly_below_low = (x <= low) if quantity.comparator == "<" else (x < low)
if low is not None and strictly_below_low:
```

and the same shape again for the upper bound.

**Why that is wrong.** `x <= low` is evaluated before `low is not None` is tested, so a
range with no lower bound raises `TypeError: '<=' not supported between instances of
'float' and 'NoneType'`.

**What it would have cost.** `interpret()` crashes on any half-open reference range. That
is not an edge case: hs-CRP is reported as 0–3.0 with no meaningful lower bound, and many
analytes have no upper bound at all. It would have failed on the first realistic lab in the
mock patient.

**How it surfaced.** The plan's own tests. Rather than fixing the code on sight, the plan's
version was written verbatim and run: **2 failed, 17 passed**, with `TypeError` at both
sites, and both failing tests described real labs. This is the one place in the build where
writing the tests first paid for itself outright.

**Fixed.** Each bound comparison moved inside its own `is not None` guard. Because both
defects were `TypeError`, the guard against a third is "never raises" rather than "returns
the right answer": all 280 combinations of range shape, comparator and value were swept, and
none raises.

---

## 3. Task 15 — a bare class attribute on a Pydantic model

**The plan wrote** `FIELD_PROVENANCE_WHITELIST = frozenset({"clinical_status"})` inside a
`BaseModel` subclass.

**Why that is wrong.** Pydantic v2 raises `PydanticUserError` at class-definition time: *"A
non-annotated attribute was detected ... All model fields require a type annotation."*

**What it would have cost.** The module does not import. Not a subtle failure — but it
recurred in **five** entities (`Condition`, `Medication`, `Supplement`, `LabResult`,
`VitalSign`), so discovering it at Task 15 and leaving the plan untouched would have meant
hitting the same wall four more times.

**Fixed.** `ClassVar[frozenset[str]]` here, and the plan's other four occurrences patched in
the same commit so Tasks 16, 17, 20 and 21 did not repeat it. Verified the attribute is not
a model field, so the whitelist does not serialise into every record.

---

## 4. Task 24 — a naive datetime in a model that refuses them

**The plan wrote** `reviewed_at: datetime | None = None` on `AIArtifact`, where every other
timestamp in the model is `AwareDatetime`.

**Why that is wrong.** Nothing fails. The field simply accepts a timestamp with no zone.

**What it would have cost.** A human review time that cannot be ordered against the audit
events around it. §6.3 builds incident reconstruction on timestamps, so this is the kind of
inconsistency that never crashes and quietly makes the audit weaker than the document claims
it is.

**Fixed.** `AwareDatetime | None`. Verified a naive value is now refused.

---

## Where the plan was silent rather than wrong

Not defects. Behaviour the plan implemented without stating, which was documented in place
so it is not rediscovered as a surprise.

| Task | Unstated behaviour | Now recorded |
|---|---|---|
| 13 | The retraction cascade is single-level: retracting A flags B but not C | In the function's docstring, with why it is tolerable (§6.19 caps AI chains at depth 1) |
| 20 | `Supplement` does not require a stop date where `Medication` does | In the class docstring: a patient who stopped a vitamin rarely knows when, and demanding the date discards the fact |
| 7 | `crossed_perimeter` fails *open* for any `TextOrigin` not listed in `_EXTERNAL` | A test that walks the whole enum, so a sixth origin cannot default to trusted |
| — | No test built two entities together before Task 29 | A cross-entity smoke test added at the Phase 2/3 boundary, seven tasks early |

---

## Inaccuracies not worth a section

- **Task 11** — the plan's step 4 expects "20 passed"; the tests it specifies number 19. An
  arithmetic slip, not a missing test.
- **Task 19** — `is_active_at` tripped ruff `SIM103`. A style nit, rewritten positively
  rather than as a double negation.

---

## The pattern, which is the point

Defect density tracked **novelty, not care**:

| Phase | Tasks | Real defects |
|---|---|---|
| 1 — foundations, invariants, the comparator table | 18 | **3** |
| 2 — remaining full-depth entities | 4 | 0 |
| 3 — the thin five | 1 | 0 |
| 4 — AI layer schema | 1 | 1 |

Phase 1 is where the plan designed something for the first time. Phases 2 and 3 applied
patterns Phase 1 had already settled, and produced nothing worse than an import-order nit.

The practical consequence was a prediction made before Phase 5 rather than after it: Phase 5
contains more original logic than the other four together — a capability token, a projection
layer with a budget, five guardrail checks over set arithmetic, an adapter — so two to three
defects were expected there, most likely in `project_records` and in the guardrails. Whether
that prediction held is recorded below once Phase 5 is complete.

Phase 5 is also the only place where a missing piece does not degrade honestly: an
unimplemented consent gate is an open door, not a `None`.

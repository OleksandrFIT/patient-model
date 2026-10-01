# Plan defects found during implementation

Running log, kept while implementing `docs/implementation_plan.md`. Feeds D10, which asks
what the AI output got wrong, what was accepted, what was rejected and why.

The plan was itself AI-written, from a spec that was also AI-assisted. This file is the
honest record of where it was wrong, what each error would have cost, and how it surfaced.
Entries are added as they are found rather than reconstructed afterwards — a defect log
assembled from memory at the end shows.

All five phases complete, plus step 7 (the deliverable documents) and the optional
normalisation build.

---

## Summary

| # | Task | Defect | Would have caused | Found by |
|---|---|---|---|---|
| 1 | 10 | A validator that can never run | Silent erosion of a constraint | Checking the assumption first |
| 2 | 11 | Comparison before the `None` guard, twice | `TypeError` on the commonest range shape | **The plan's own tests** |
| 3 | 15 | Bare class attribute on a Pydantic model | Module fails to import at all, ×5 entities | Checking the assumption first |
| 4 | 24 | Naive `datetime` where the model uses `AwareDatetime` | An unorderable review timestamp, silently | Consistency check against `base.py` |
| 5 | 26 | `budget=0` returns an empty projection instead of refusing | A generation with no inputs; guardrail 1 passes vacuously | Edge sweep |
| 6 | 27 | Check 5 matched entity **type**, contradicting the projection's droppability | Hard rejection of a brief that correctly omitted a resolved condition | Feeding it a real `ProjectionResult` |
| 7 | 27 | Checks 2–3 ran only on `LabResult` | A fabricated `VitalSign` value passed | Reading the check against §10.5's wording |
| 8 | 27 | Checks 2–3 skipped silently when the record was not supplied | A checker that cannot see the record reports a pass | Same |
| 9 | 28 | Series unit conflated "not yet established" with "established as `None`" | A unit-less value averaged in with mmol/L, unnamed | Probe with a unit-less lab |
| 10 | 29 | Narrative trends built from every lab, not the projection | Claims citing omitted labs; guardrail 1 rejects the whole narrative | Simulating intermediate budgets |

Of the ten, **three** would have been caught by running the plan's own tests. The other
seven passed its suite: four were found by checking an assumption before writing, and three
by feeding a component real output from the component upstream of it rather than hand-built
input. That second instrument found the three worst — defects 6, 9 and 10, each of which
makes two parts of the system disagree while both pass their own tests.

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

## The optional normalisation build

Written after the plan, so the defects below are mine rather than the plan's. Recorded in the
same file because D10 asks what was wrong with AI output, and this was AI output too.

| # | Defect | Would have caused | Found by |
|---|---|---|---|
| 11 | `Conflict` candidates keyed by source class | Two values asserted by the *same* class overwrote each other — exactly the glucose case, so the conflict report would have shown one of the two readings | Inspecting the output on real data |
| 12 | Free-text `dose_text` treated as a conflicting field | "75 mcg daily" against "levothyroxine 75mcg daily" reported as a conflict, burying the real dose disagreement two lines below | Same |
| 13 | `verification_status` hard-coded to `CONFIRMED` | A self-reported diagnosis entering canonical as a confirmed one, defeating the field §6.4 exists for | Reviewing the builder against §6.4 |
| 14 | A dict literal evaluating `c.winner.value` | `AttributeError` on every outcome where no source won — which is every unresolved conflict | Running it |

Defect 11 is the one worth keeping. The data model for conflicts could not represent the
central case the build exists to demonstrate, and its own tests passed because they were
written against the same wrong shape. Only looking at the rendered output caught it — the same
instrument that found the three worst defects in Phase 5, applied one layer further out.

Defect 13 is the one that would have mattered clinically. §6.4 separates verification from
clinical status so a suspicion cannot be rendered as a diagnosis; a normaliser that stamps
`CONFIRMED` on everything it reads undoes that for every record it touches.

## The pattern, which is the point

Defect density tracked **novelty, not care**:

| Phase | Tasks | Real defects |
|---|---|---|
| 1 — foundations, invariants, the comparator table | 18 | **3** |
| 2 — remaining full-depth entities | 4 | 0 |
| 3 — the thin five | 1 | 0 |
| 4 — AI layer schema | 1 | 1 |
| 5 — gate, projection, guardrails, adapter, D8 | 5 | **6** |
| optional — normalisation (written after the plan) | — | **4** |

Phase 1 is where the plan designed something for the first time. Phases 2 and 3 applied
patterns Phase 1 had already settled, and produced nothing worse than an import-order nit.

**The prediction, and how it did.** Before starting Phase 5 the forecast on record was two to
three defects, "most likely in `project_records` and in the guardrails". The direction was
right — Phase 5 produced more defects than the other four phases combined, and three of the
six were indeed in the guardrails with one in `project_records`. The count was wrong by a
factor of two.

Where the forecast was wrong is more useful than where it was right. It assumed defects would
sit *inside* components, and the three worst sat *between* them: the guardrails and the
projection held separate definitions of droppability (6); the adapter built the narrative's
trends from a different lab set than the one it projected (10); the trend's unit logic
disagreed with what §9.2 lets into canonical (9). Each of those passed every unit test on both
sides of the seam, because a unit test constructs its own input and so never sees what the
neighbouring component actually emits.

The instrument that found them was the same one each time: run the component on real output
from the component upstream of it. That is also what the cross-entity smoke test did at the
Phase 2/3 boundary, seven tasks before the plan's first integration — and the lesson is that it
should have come earlier still, and been repeated at each seam rather than once.

Phase 5 was also the only place where a missing piece does not degrade honestly: an
unimplemented consent gate is an open door, not a `None`. Nothing in it was deferred.

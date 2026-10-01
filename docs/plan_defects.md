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

## 15. The design's output checks had a hole, found by a real model

Not a defect in code against design. A defect **in the design**, and the only one in this file
that no amount of reading could have found.

§10.5 argues that AI output must be structured claims because over prose nothing is checkable,
and then specifies five checks on that shape. Check 2 compares every `ClaimValue` against the
record it cites. **`values` was optional.**

A model can therefore satisfy the schema, put its figures in the prose of `text`, declare
nothing, and leave check 2 iterating an empty list. `qwen2.5:7b` did it on the first real run:
*"TSH 3.8 mIU/L and 5.6 mIU/L"*, `values: []`, verdict pass. Four unverified numbers reached a
physician through a layer built to stop exactly that.

**What it survived.** The structured-output decision was proposed with its cost, argued over
several exchanges, and approved. The plan specified the checks. Fourteen tests were written
against them — including one whose only job is to pin a known limit. None caught it, for a reason
that generalises: **every test of check 2 supplied the values it then verified.** They proved a
declared number is compared correctly. They could not show that declaring was assumed, because
the test author and the design author held the same assumption. A real model held none of it and
read an optional field as optional.

Fixed by check 6: a claim stating a decimal must declare it. Narrow on purpose — "type 2
diabetes" must not trip it — and the residue is named: an integer measurement in prose still
passes.

The lesson, now in §10.5: **a structured field the model may omit is free text with extra
steps.** The original argument against prose was right and was applied one level too shallow.

## 16. An artifact that was itself a false claim

The stub standing in for a model reported `engine=ollama`, `model_id=llama-3.3-70b-instruct`,
`engine_version=0.5.1`, `execution=local` and a genuine SHA-256 prompt digest — of a prompt never
sent, for a model not installed on the machine. Five cited claims sat beneath it.

Every field was individually defensible. The record as a whole asserted that a 70-billion
parameter model had run locally, which it had not, inside a submission whose subject is
provenance. A different failure mode from the others in this log: not a wrong sentence in prose,
but a well-formed data record whose every part was plausible and whose sum was untrue.

Fixed by adding `Engine.STUB`, so a run with no inference says so in the artifact rather than in
a footnote a reviewer may not reach.

## 17 and 18. Found by re-running the dimension audit properly

The brief's 25 required dimensions were audited once and the audit was worthless: it compared a
mapping written by hand against the same mapping, and guessed the example record's JSON keys from
class names with a string heuristic that got four of them wrong. Both mistakes are the same
mistake — checking a claim against another copy of the claim.

Re-run against the code and against the example record, it found two things.

**17. Five entities existed in the code and were absent from the example record.** Coverage, Goal,
Procedure, SocialFactor and Task — the thin five. D2 claims dimensions 5, 17, 18, 19 and 22 live
in them, and a reviewer opening `d3_example_patient.json` to verify any of those claims would not
have found an instance. Covered in code, tested, and undemonstrated. The fixture now carries all
five, written into the thyroid story rather than beside it: a task to ask which month she stopped
the metformin, a goal of staying under 88 mcg, the ultrasound, her smoking and sleep.

**18. The design document named a field the code does not have.** `TreatmentPlan.plan_items`
appears in §4 and §5 and in two D2 rows; the field is `items`. It has read that way since the
design phase and survived the whole build, because nothing resolved a documented identifier
against the model. A reviewer grepping for `plan_items` finds four mentions and no code. Docs
corrected to follow the code, which has the better name — `plan.plan_items` is redundant.

Both now gate the submission: `scripts_audit_dimensions.py` exits non-zero on a dimension with no
row, an identifier that does not resolve, or an entity D2 names and the example record does not
contain.

## 19. A trend advertised another analyte's blocking flag

Found by rendering the brief the way a physician reads it, rather than by asserting on its
fields. `_trends_for` handed every trend the patient's whole list of open blocking flags, so
the glucose conflict appeared under TSH and under free T4 as well:

```
• TSH              rising          [3.8 mIU/L, 5.6 mIU/L]
  ↳ флаг [blocking] CONFLICTING_VALUES     <- about glucose
```

TSH is clean, rising, and the most actionable line in the brief. `blocking` means no
read-model and no agent may draw a conclusion from the record (§9.1), so the brief was
telling a physician that its best signal was unusable, on the strength of a problem with a
different analyte.

The cause is structural rather than a slip in that line. `FlagSummary` carries `flag_id`,
`code`, `severity` and `message` and **no reference to the record it is about**, so a trend
handed the flags cannot tell which concern its own series. The full `DataQualityFlag` has the
target; the projection into read models dropped it.

Two fixes were priced. Adding a target to `FlagSummary` would let trends filter, but widens a
value object that was kept narrow on purpose in order to repair a rendering decision. Not
passing flags to trends at all removes the false attribution and the duplication in one move,
because the brief already carries the same flags at its own level, where they are true of the
patient rather than of one series. The second was taken: a trend showing another analyte's
blocking flag is worse than a trend showing none.

Nothing had pinned either behaviour, so the suite passed before and after. It is pinned now,
and the test fails if the flags are passed back in.

## 20. A test that could no longer fail

Introduced and caught inside the prompt-index change. `GenerationContext.render()` went from
returning `str` to returning a `RenderedPrompt` named tuple, and this test kept passing:

```python
prompt = _ctx([_lab(5.6)]).render()
for forbidden in ("Okafor", "Dana", "MRN"):
    assert forbidden not in prompt
```

`"Okafor" not in RenderedPrompt(...)` compares the string against the tuple's *elements* — a
string and a dict — finds it equal to neither, and passes whatever the prompt actually says.
The one test standing behind §10.4, that no identity reaches the model, had become unable to
fail.

It surfaced because two sibling tests broke on the same change and this one did not, which is
the signal worth generalising: a type change that breaks some assertions and silently satisfies
others has probably turned the quiet ones into tautologies. The same shape as defect 1, a
validator that can never run, in a test rather than in a validator — and the same shape as the
guardrail hole in defect 15, where every test of check 2 supplied the values it then verified.
Fixed by asserting against `.text`, with the reason in a comment so it is not re-broken.

## 21. The prompt printed numbers the model was forbidden to use

Found by running the same prompt eight times instead of once. After the switch to indices every
run was rejected, deterministically, on check 6 — and the cause was not the switch.

The context included each open blocking flag's message verbatim:

```
CONFLICTING_VALUES: fasting glucose: EMR 5.5 mmol/L against lab 7.2 mmol/L, unresolved
```

Those two figures are the competing readings of an unresolved conflict, so canonical holds
**neither**: §9.3 leaves the value empty. A claim that declares one fails check 2, which finds
no value to match, or check 3, which forbids asserting a value for an empty slot. A claim that
states one without declaring it fails check 6. There is no legal way to put either figure in a
claim, and the prompt offered both.

The guardrails were right every time. The defect is that the context handed the model a number
and then forbade every use of it, which is a trap rather than an instruction — and it had been
there since check 6 landed, making the narrative unreachable for any patient carrying a numeric
conflict flag. One earlier run passed only because the model happened to phrase that claim
without numbers; a single run looked like evidence that the prompt was fine.

Flag messages now reach the model with their figures removed, and the header says why. The
redaction pattern is deliberately **broader** than check 6's: check 6 ignores integers so that
"type 2 diabetes" is not read as a measurement, but an integer left in a flag message would be
restated and would pass every check. The two patterns are allowed to differ and the reason is
written where both live, because unifying them would reopen the hole.

The lesson is about method rather than about prompts. A generation was checked once, saw a pass,
and the pass was the unlucky outcome: it hid a failure that eight runs made unmissable. Running
a non-deterministic component once tests the run, not the component.

## Not numbered: the deliverables that went stale, found by the reviewer

This one is deliberately outside the numbering, and the reason is a taxonomy rather than an
excuse. The eighteen above are defects in the **code and the model** — something the system does
wrong. This is a defect in AI-written **documentation**, which is where D9's unverified word count
already sits, in D10's "claims that outran the code" rather than in this list. Numbering it here
would make the two kinds of failure share a counter and make neither figure mean anything.

It is still the worst of them.

D11 stated that *"the optional normalisation build was not started."* The build was finished,
committed, and sitting in `deliverables/normalisation/` with four outputs and 25 tests. In the
same file, the table of what the repository can attest to claimed 271 tests, 10 defects, 2,684
lines of `src/`, and 21 of 21 entities. D10 carried the same stale figures and, worse, contradicted
itself: its instrument table accounted for sixteen defects while its own heading and bottom line
had been updated past that. README's quickstart told a reviewer to expect 271 tests.

**Nothing here was invented.** Every figure was correct at `1428ce4`, the commit that wrote D10 and
D11, and verified at the time. Four feature commits then moved all of them — the normalisation
build, real inference, the `Symptom` entity, and the dimension audit — and nothing re-read the
documents that described the repository. The sentence about the normalisation build is the sharpest
case: it was true when written, because the build genuinely had not been started yet, and it became
a false claim by being left alone.

That is what makes it worse than a wrong number. A reviewer cannot distinguish a figure that went
stale from one that was never true, and should not have to. The claim sat in the one file whose
subject is the honesty of the work, in a submission arguing that canonical data must never hold a
value nobody vouched for.

**How it surfaced.** The reviewer read the two documents against the repository. Not a test, not a
sweep, not a seam — the same instrument that found defect 16, which is the one instrument a
submission cannot supply for itself. It has now fired twice, and both times the answer was that
the artifact claimed something the repository did not support.

### The same shape again, in a script written to display the work

While rendering the real-inference verdict for review, the display script re-ran
`run_guardrails` on the artifact the adapter returned and printed `PASS, failures=0` — for an
artifact the adapter had already **rejected** and whose claims it had therefore cleared. An
empty claim list passes every check vacuously.

[scripts_run_ollama.py](../scripts_run_ollama.py) carries a comment warning about exactly
this, placed there because the first version of that script did the same thing. The warning was
read, the script was used as the model to copy from, and the trap was walked into anyway. Like
D9's word count it is unnumbered, because it is a defect in a throwaway display script rather
than in the model or the deliverables, and it belongs here for the reason that one does: the
verdict is read off the artifact now, and a comment in the code is weaker protection than a
shape that cannot be got wrong.

**What changed.** `scripts_audit_figures.py` recomputes every figure D10, D11 and README assert,
renders each into the exact string the document must contain, and exits non-zero on any drift. It
also checks that D10's instrument table accounts for every defect in this log, and that D11 no
longer says the normalisation build was not started. The three failure modes were each verified by
breaking them deliberately. The instruction that produced the script was blunter and is the lesson:
check the figures against the repository *before* the commit, not after.

There is no reason the dimension audit existed and this one did not. Both are the same shape — a
claim in a document, resolved against the thing it describes — and only one of them had been built,
because the dimension gap had been pointed out and this one had not yet.

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
| real inference, and auditing what the stub looked like | — | **2** |
| re-running the dimension audit against code and example | — | **2** |
| rendering the brief for its actual reader | — | **1** |
| switching the prompt from ids to indices | — | **1** |
| running the same prompt eight times instead of once | — | **1** |

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

**A fourth instrument appeared last and found the worst defect of all: run the real thing.**
Defects 15 and 16 were invisible to every other method — one because the tests and the design
shared an assumption, the other because each field of the artifact was defensible in isolation.
Reading found the most defects; crossing a seam found the worst implementation ones; running a
real model found the one that was wrong in the **design**, which is the only category where
neither the author nor the tests could know what they had assumed.

Phase 5 was also the only place where a missing piece does not degrade honestly: an
unimplemented consent gate is an open door, not a `None`. Nothing in it was deferred.

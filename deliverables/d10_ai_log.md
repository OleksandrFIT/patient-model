# D10 — AI prompt log and critique

> **To complete before submission.** The *Prompt* column below is deliberately empty. The
> assignment asks for the exact prompts used, and those are the candidate's own record — they
> should be pasted in verbatim rather than paraphrased by the tool that answered them.
> Everything else in this file is factual and already filled in.

---

## How AI was used

One assistant, Claude Opus (via Claude Code), across one working session. No other tool.

AI produced three things, in order, each reviewed before the next began:

| Artifact | In the repo | Size |
|---|---|---|
| The design specification | `docs/model_design.md` | 1,595 lines |
| The implementation plan | `docs/implementation_plan.md` | 29 tasks, 153 TDD steps |
| The implementation | `src/`, `tests/`, `mock/` | 4,627 + 4,433 lines, 322 tests |

AI was **not** used to decide the stack, the workflow for D8, or whether to do the optional
normalisation build. Those were set before any prompting, and are recorded in `CLAUDE.md`.

The working method mattered more than the prompting. Every design decision was proposed with
its cost and its rejected alternatives, approved or rejected explicitly, and only then
written. Nothing was implemented from a plan that had not been read.

---

## Prompt log

| # | Tool | Prompt | What it produced | What was useful | What was wrong, generic or incomplete | Decision |
|---|---|---|---|---|---|---|
| 1 | Claude Opus | *(paste)* | Entity list for the canonical layer: 21 entities, shared fields, normalised vs embedded | The three-tier base split, and the argument for merging medical history into `Condition` | Proposed `review_status` on every entity, which contradicts the project's own rule that AI never writes to canonical | Accepted the entity list and tiering. **Rejected** `review_status` entirely |
| 2 | Claude Opus | *(paste)* | Fork answers: versioning, Medication/Supplement split, labs/vitals split, provenance granularity, timeline | Each fork priced with its cost, including the option not recommended | — | Accepted all five, with `field_provenance` narrowed from "wherever it differs" to an explicit whitelist |
| 3 | Claude Opus | *(paste)* | `comparator` on `Quantity`, and its consequences for range comparison and trends | Interval reasoning: a comparator makes a value an interval, so a range check is decidable only when the interval lies on one side | First draft would have raised a flag for an indeterminate comparison | **Changed**: `indeterminate` is a value, not a flag. Flagging correct assay output would fill the review queue with items nobody can fix |
| 4 | Claude Opus | *(paste)* | Six security gaps found by audit: audit correlation, text perimeter, `AIArtifact`, consent gate, rights matrix, output guardrails | The audit distinguished "already covered and where" from "genuinely absent", including one case where the document contradicted itself | §6.3 claimed an agent's context could be reconstructed while the field list could not deliver it | Accepted all six. The self-contradiction was the most valuable finding of the session |
| 5 | Claude Opus | *(paste)* | Error handling, context limits, and recursion through extracted data | §6.19's depth cap closed a question that arose later in §10.6 — a decision made for one reason resolved another | — | Accepted. `ai_inference` capped at `depth <= 1` |
| 6 | Claude Opus | *(paste)* | The implementation plan | Full TDD granularity where the invariants live; honest about where it grouped mechanical work | Four defects in the code it specified, listed below | Accepted as a plan, executed task by task, corrected in flight |
| 7 | Claude Opus | *(paste)* | Implementation, 29 tasks | 264 passing tests at the close of task 29, ruff clean, every spec section traceable to a task | Ten defects, six of them in Phase 5 | Each corrected before the task was committed; all recorded |
| 8 | Claude Opus | *(paste)* | The optional normalisation build: three conflicting sources into canonical | Produced a state nobody designed — see `WINNER_UNREPRESENTABLE` in D8 | Four defects of its own, including a conflict model that could not represent the central case it existed for | Accepted, corrected, logged |
| 9 | Claude Opus | *(paste)* | Wiring a real local model, and auditing what the stub looked like | Found that the stub reported `engine=ollama` with a real model name and a genuine prompt digest, for a prompt never sent | **The design's five output checks had a hole a real model walked straight through** | Accepted; `Engine.STUB` added, check 6 added |
| 10 | Claude Opus | *(paste)* | Re-running the 25-dimension audit against the code and the example record | Two gaps that four earlier passes over the same table had not shown | The first audit had been circular — it compared a hand-written mapping to itself | Accepted; audit rewritten as `scripts_audit_dimensions.py`, which now gates the submission |
| 11 | Claude Opus | *(paste)* | Prompt indices in place of ULIDs, and the trend-flag fix | Removed the cause of a fabricated citation instead of relying on the catch; replies also became deterministic | A test that could no longer fail was introduced in the same change, and the switch exposed a prompt that hands the model unciteable numbers | Accepted; map kept local to one call, guardrails untouched |
| 12 | Claude Opus | *(paste)* | Withholding a flag's competing figures from the prompt | Turned 8 rejections out of 8 into 8 narratives out of 8, by removing a number rather than loosening a check | The placeholder leaks into the model's prose, and the claim about the conflict is now dropped for citing nothing | Accepted; redaction pattern deliberately broader than check 6's, with the reason recorded |

---

## Critique of the AI output

The full record is `docs/plan_defects.md`. The summary, with the numbers rather than an
impression.

### Twenty-one defects in AI-written code, and how each surfaced

| How found | Count | Example |
|---|---|---|
| Reading the code against the spec, before or while writing it | 6 | A Pydantic attribute without `ClassVar`, which stops the module importing at all, repeated across five entities |
| Running a component on real output from the one upstream of it | 5 | The guardrails and the projection held **separate definitions** of droppability, so a brief that correctly omitted a resolved condition was rejected |
| The plan's own tests | 2 | `TypeError` on any half-open reference range — the commonest shape, since hs-CRP has no lower bound |
| Resolving a documented identifier against the code, and a documented entity against the example record | 2 | `TreatmentPlan.plan_items` appears in the design document and in D2; the field is `items`, and had read that way since the design phase |
| An exhaustive sweep of one function's inputs | 1 | A budget of zero returned an empty projection instead of refusing |
| **Rendering the output for the reader it is for** | **1** | Every lab trend advertised the glucose conflict, so a clean rising TSH was marked unusable |
| A type change that broke two sibling tests and silently satisfied a third | 1 | The one test behind "no identity reaches the model" had become unable to fail |
| **Running the same prompt eight times instead of once** | **1** | The prompt printed the figures of an unresolved conflict, which no claim may legally use |
| **Running a real local model** | **1** | **The design's output checks had a hole. See below** |
| **Being asked whether the artifact was real** | **1** | **The stub reported a real engine and model for a run that never happened** |

The second row matters because each of those defects made two parts of the system disagree while
**both passed their own unit tests** — a unit test constructs its own input and so never sees
what its neighbour emits. They were invisible to the test suite the AI wrote for its own code.

The last two rows matter more. Neither was reachable by any amount of reading, and the final one
is the least comfortable line in this file: that defect was not found by a method at all. It was
found because the reviewer asked whether the inference was real, and the honest answer was no.

### The one defect reasoning could not have found

Every other defect in this log is a gap between the design and the code, or a silence in the
design. This one was a **hole in the design itself**, and nothing short of a real model would
have exposed it.

§10.5 specifies that AI output is a list of claims, each carrying its citations and its numbers
structurally, because *"over free prose none of the checks works: a number extractor that misses
one produces a false pass, which is worse than no check at all."* Five checks were specified on
top of that shape. Check 2 compares every `ClaimValue` against the record it cites.

`values` was optional.

So a model can satisfy the schema, write its figures in the prose of `text`, declare nothing,
and leave check 2 with an empty list to iterate. On the first run against `qwen2.5:7b` that is
exactly what happened:

> *"The TSH levels are rising, with values of 3.8 mIU/L and 5.6 mIU/L, both outside the
> reference range of 0.4-4.0 mIU/L."* — `values: []`, verdict **pass**

An artifact carrying four unverified numbers reached the physician, through a guardrail layer
built specifically to stop that.

**What makes it the strongest finding is what it survived.** The structured-output argument was
proposed, costed, and approved across several exchanges. The plan specified the checks. Fourteen tests
existed against them at that point — eighteen now, after check 6 — including one asserting the guardrails cannot detect omission —
a test whose whole purpose is to pin a known limit. None of it caught this, and the reason is
uncomfortable and general: **every test of check 2 supplied the values it then verified.** The
tests proved that a declared number is compared correctly. They could not show that declaring
was assumed, because the test author and the design author shared the assumption.

A real model shared none of it. It was given a schema with an optional field and treated it as
optional.

Check 6 closes the hole — a claim stating a decimal must declare it — and the behaviour since
is itself worth recording. Same model, same prompt, same temperature zero:

| Run | What the model did | Outcome |
|---|---|---|
| before check 6 | numbers in prose, `values` empty | passed, unverified |
| after | numbers in prose, `values` empty | **rejected**, narrative withheld |
| after | values declared | accepted, `review=pending` |

The model is not reliably obedient even when the instruction is explicit. That is not a defect
to be fixed in the prompt; it is the condition the guardrails exist for, and the three outcomes
above are the difference between a system that survives it and one that does not notice.

The generalised lesson, now in §10.5: **a structured field the model is allowed to omit is free
text with extra steps.** The original argument against prose was right and was applied one level
too shallow.

A second finding came out of the same audit, and is a different kind of failure. The stub that
stood in for a model reported `engine=ollama`, `model_id=llama-3.3-70b-instruct`,
`engine_version=0.5.1` and a genuine SHA-256 prompt digest — of a prompt never sent, for a model
not installed. Every field was individually defensible and the artifact as a whole was a false
claim, in the one submission where that matters most. `Engine.STUB` now exists so the artifact
says what it is.

### The fabrication a reviewer could not have seen

The guardrail hole above was found because a number appeared in prose. A reader can see a
number. This one is the opposite case, and it is the stronger example.

Four runs of the same prompt, same model, temperature zero, nothing changed between them:

| Run | `review` | claims | narrative | guardrail |
|---|---|---|---|---|
| 1 | `pending` | 2 | delivered | — |
| 2 | **`rejected_by_guardrail`** | 0, cleared | **withheld** | `cites_in_inputs`, `record_available_for_checking` |
| 3 | `pending` | 3 | delivered | — |
| 4 | `pending` | 2 | delivered | — |

Three runs produced a brief. One fabricated a citation. That spread, on one unchanged prompt,
is the argument for having guardrails at all: there is no prompt to write and no temperature to
set that makes the check unnecessary, because the same input does not produce the same output.

In run 2 the model cited `lab_01M3VPPWQX677QFJMES2FGFSBQ1` and attached the value 11.2 to it —
free T4's figure, bound to a record that does not exist. The real ids in that run shared the
timestamp prefix `lab_01M3VPPWQX6…` and diverged only in the tail. Nothing about it looks wrong.
It is 26 characters of base32 in a field full of 26-character base32 strings, and a reviewer
checking it by eye would have to compare the tail of one ULID against four others.

That is what makes it worse than a number in prose. The prose case is caught by a careful
reader and the check is a second line of defence. Here the check is the **only** line of
defence: `cites_in_inputs` rejected the citation, `record_available_for_checking` rejected the
value bound to it, the claims were cleared and the narrative never reached the physician.

**What changed.** The prompt no longer shows ids. Each result is labelled `[1]`, `[2]`, `[3]`,
the adapter keeps the index-to-id map for the length of one call, expands the indices when the
reply comes back, and discards the map. The artifact still carries real ids, `inputs` is
unchanged, and the guardrails are untouched. An index the prompt never offered — `[9]` where
three results were listed — resolves to nothing and fails as the same hard rejection, which is
pinned by a test. A digit is short enough to copy correctly and short enough for a reviewer to
check against the prompt, so the cause is removed rather than merely caught.

The table above stays as a historical record, of the system as it was when it was found. It is
not evidence about the current prompt and should not be read as any. And the guardrail stays,
for a reason that the fix itself does not address: it removes **this** class of fabrication, not
fabrication. The next class has not been seen yet, which is exactly what was true of this one
before run 2.

### What the indices changed, measured

Eight runs after the switch, then eight more after the prompt defect it exposed was fixed.
Same prompt within each set, same model, nothing else changed:

| Runs | `review` | narrative | guardrail |
|---|---|---|---|
| before indices, 4 runs | 3 `pending`, 1 `rejected` | 3 delivered | `cites_in_inputs` on the fabricated id |
| after indices, 8 of 8 | `rejected_by_guardrail` | **none delivered** | `numbers_in_text_are_declared` |
| after redaction, 8 of 8 | `pending` | 8 delivered | — |

No fabricated citation in any of the sixteen runs after the switch, and the replies became
identical to each other rather than merely similar — a model no longer spending its output on a
26-character string stopped varying. Both are what the change was for. The middle row is the
point of the exercise: eight runs turned a prompt defect from invisible into unmissable, where
the single run that preceded them had looked like a pass.

The rejections are a separate problem the change exposed rather than caused, and it is worth
naming because it is in the **prompt**, not in the model. Inspected before the adapter clears
them, the first two claims are correct, cite resolved real ids and declare their values. The
third restates the two glucose figures from this line of the prompt:

```
Unresolved data problems you must not reason past:
  CONFLICTING_VALUES: fasting glucose: EMR 5.5 mmol/L against lab 7.2 mmol/L, unresolved
```

Those two numbers belong to no citable record, by design: the conflict is unresolved, so
canonical holds no glucose value at all (§9.3). So a claim mentioning them numerically cannot
declare them against anything — check 2 would find no value to match and check 3 forbids
claiming a value for an empty slot — and stating them without declaring them fails check 6.
There is no legal way to put those figures in a claim, and the prompt prints them anyway.

The guardrails were behaving correctly every time: nobody vouched for either figure, and the one
record involved is deliberately empty. The defect was that the context handed the model a number
and then forbade every use of it, which is a trap rather than an instruction, and it had been
there since check 6 landed. Flag messages now reach the model with their figures removed and a
header saying why, which is defect 21 in the log.

One thing the fix did not recover, recorded because it is the kind of detail a summary hides.
The model still writes a third claim about the conflict, now without numbers, and emits it with
an empty `cites` array:

```json
{ "text": "There is a conflicting value for fasting glucose, with the EMR showing a withheld
           value that conflicts with a lab result that is also withheld.", "cites": [], "values": [] }
```

§10.5 requires a claim to cite, so the parser drops it and records the reason in
`generation_notes` rather than swallowing it. The conflict therefore reaches the physician only
through the deterministic part of the brief — which is where it is already surfaced, with the
real figures, because a physician may see them. Nothing clinical is lost. What the phrasing does
show is that the placeholder leaks into the model's prose: had that claim cited `[4]`, a brief
would have told a physician about "a withheld value" sitting directly above the two numbers in
plain sight. The word is addressed to the model and reads as though it were addressed to the
reader.

### Where the AI output was systematically weakest

**Seams, not components.** Defect density tracked novelty: 3 in the foundations phase, 0 and 0
in the two phases that applied settled patterns, 1 in the schema phase, **6** in the phase
with the most original logic. A forecast of two to three for that phase was made in writing
before it started; the direction held and the count was wrong by half.

**Claims that outran the code.** Five distinct instances: a design section promising an audit
capability the field list could not deliver; a validator placed after a constraint that made it
unreachable; a docstring asserting that wiring a real model would change "one method and no
invariant", when the prompt had to move from after generation to before it; this file's own
sibling, D9, committed twice with a word count that had not been re-checked after the edit; and
the worst of the five, **D11 stating that the optional normalisation build "was not started"**
while that build sat finished in the repository with four outputs and 25 tests — in the one
file whose subject is the honesty of the work. The same commit left this file asserting 271
tests and 10 defects. The pattern is the same each time: an assertion written in the same
breath as the thing it describes, with no step that verifies it.

The fifth instance is the only one that was never false when written. D11's figures were
correct at the commit that produced it and were simply not re-checked while four feature
commits moved the repository underneath them — the normalisation build, real inference, the
`Symptom` entity and the dimension audit. A reader cannot distinguish that from a lie, and
should not have to. It is also the instance least reachable by reading, because every sentence
is locally plausible and only the repository contradicts it. `scripts_audit_figures.py` now
recomputes every number in D10 and D11 from the repository and exits non-zero on any drift, so
the claim fails the gate instead of reaching a reviewer. The instruction that produced it was
blunter than the script: check the figures against the repository *before* the commit, not
after.

**Artifacts that looked like evidence.** The stub case above is the sharpest, and it is a
distinct failure mode from the others: not a wrong claim in prose, but a well-formed data record
whose every field was plausible and whose sum was untrue.

**Plausible-looking completeness.** The plan's self-review declared `TimelineEvent` a safe
gap. D3 requires timeline events outright, so it was not safe; the gap had been assessed
against the plan rather than against the assignment.

### What AI was reliably good at

Decomposition and the defence of a decision. The three-tier base split, the separation of
provenance from audit, the invariant that canonical never holds a value nobody vouched for,
and the argument that making a bad state unrepresentable beats detecting it — these held up
under pressure and are the parts of the design worth keeping.

It was also good at pricing an option it was arguing against, which is what made the
accept/reject decisions possible.

### What was rejected outright

- `review_status` on every canonical entity — contradicts the founding rule.
- A flag for an indeterminate lab interpretation — correct data is not a defect.
- `provenance.artifact_ref` — a back-pointer from canonical to the AI layer would break the
  one-way rule the whole design rests on.
- Free prose as AI output — a number extractor that misses one produces a false pass.
- Automatic conflict resolution by recency — recency is a heuristic, not a vouching.
- `docs/superpowers/specs/` as a path — a plugin convention leaking into the repository.

### The honest bottom line

The design is defensible and the implementation works. Neither would be trustworthy as submitted
if it had been accepted as produced: twenty-one defects, five of which only a cross-component check
could find, one that only a real model could find, two that only resolving a document against the
code could find, one that only reading the rendered output could find, five overstated claims, and
one artifact that was itself a false claim.

The value came from the review discipline, not from the generation, and the table above ranks
that discipline. Reading the code found the most defects. Crossing a seam found the worst of the
implementation ones. Running the real thing found the one that was wrong in the design — the only
category where neither the author nor the tests could have known what they had assumed.

And one was found by none of those. A reviewer asked a question the work had not asked itself.
Of the ten instruments, that is the only one a submission cannot supply on its own — and it
has now fired twice, the second time on this document's own sibling, where the claim had gone
stale rather than been invented. Both times the correction was mechanised afterwards, into
`Engine.STUB` and into `scripts_audit_figures.py`, which is the right response and still leaves
the finding where it was made. That is a poor note to end on and the accurate one.

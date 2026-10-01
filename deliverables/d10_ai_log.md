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
| The design specification | `docs/model_design.md` | 1,529 lines |
| The implementation plan | `docs/implementation_plan.md` | 29 tasks, 153 TDD steps |
| The implementation | `src/`, `tests/`, `mock/` | 2,684 + 3,564 lines, 271 tests |

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
| 7 | Claude Opus | *(paste)* | Implementation, 29 tasks | 271 passing tests, ruff clean, every spec section traceable to a task | Ten defects total, six of them in Phase 5 | Each corrected before the task was committed; all recorded |

---

## Critique of the AI output

The full record is `docs/plan_defects.md`. The summary, with the numbers rather than an
impression.

### Ten defects in AI-written code, and how each surfaced

| How found | Count | Examples |
|---|---|---|
| The plan's own tests | 3 | `TypeError` on any half-open reference range — the commonest shape, since hs-CRP has no lower bound |
| Checking an assumption before writing | 4 | A Pydantic model attribute without `ClassVar`, which prevents the module from importing at all, repeated across five entities |
| Running a component on real output from the one upstream of it | 3 | The guardrails and the projection held **separate definitions** of droppability and disagreed, so a brief that correctly omitted a resolved condition was rejected |

The third row is the important one. Those three defects each made two parts of the system
disagree while **both passed their own unit tests**, because a unit test constructs its own
input and so never sees what its neighbour actually emits. They were invisible to the test
suite the AI wrote for its own code.

### Where the AI output was systematically weakest

**Seams, not components.** Defect density tracked novelty: 3 in the foundations phase, 0 and 0
in the two phases that applied settled patterns, 1 in the schema phase, **6** in the phase
with the most original logic. A forecast of two to three for that phase was made in writing
before it started; the direction held and the count was wrong by half.

**Claims that outran the code.** Three distinct instances: a design section promising an audit
capability the field list could not deliver; a validator placed after a constraint that made
it unreachable; and this file's own sibling, D9, committed twice with a word count that had not
been checked after the edit. The pattern is the same each time — an assertion written in the
same breath as the thing it describes, without a step that verifies it.

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

The design is defensible and the implementation works. Neither would be trustworthy as
submitted if it had been accepted as produced: ten defects, three of which only a
cross-component check could find, and three overstated claims. The value came from the review
discipline, not from the generation.

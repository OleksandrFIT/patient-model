# D11 — Time log

> **To complete before submission.** The hours below are the candidate's to fill in; this
> file records the *work breakdown* so the categories match what actually happened, but only
> the candidate knows the clock time. Numbers are not estimated here, because a time log with
> invented hours is worse than none.

| Activity | Time spent |
|---|---|
| Reading the assignment | |
| Planning: stack, D8 workflow choice, scope decisions (recorded in `CLAUDE.md`) | |
| Design: entity list, forks, comparator semantics | |
| Design: the six security topics (audit correlation, text perimeter, `AIArtifact`, consent gate, rights matrix, output guardrails) | |
| Design: error handling, context limits, recursion through extracted data | |
| Writing the implementation plan | |
| Implementation, Phase 1 — foundations, value objects, base tiers, 8 highest-risk entities | |
| Implementation, Phase 2 — remaining full-depth entities | |
| Implementation, Phase 3 — the thin five | |
| Implementation, Phase 4 — AI layer schema | |
| Implementation, Phase 5 — consent gate, projection, guardrails, adapter, D8 end to end | |
| Deliverable documents (D2, D3, D8, D9, D10, D11, README) | |
| Optional build — three conflicting sources reconciled into canonical, with conflict report and review queue | |
| Wiring a real local model (ollama, `qwen2.5:7b`) and auditing what the stub had been claiming | |
| The 25-dimension audit, rebuilt as a repeatable gate after the first pass proved circular | |
| Rendering every artifact for review, and the two defects that only the rendered output showed | |
| Switching the prompt from ids to indices, after a run fabricated a near-miss ULID | |
| Withholding a conflict's figures from the prompt, found by running it eight times | |
| Flags to the model as structure rather than prose, and closing check 6's partial declaration | |
| Review and correction of AI output | |
| **Total** | |

## What the repository can attest to, independent of the clock

| | |
|---|---|
| Commits | One per task or per decision — see `git log --oneline` |
| Design document | `docs/model_design.md`, 1,595 lines, 11 sections |
| Implementation plan | `docs/implementation_plan.md`, 29 tasks, 153 steps |
| Code | 4,638 lines in `src/`, 4,466 in `tests/` and `mock/` |
| Tests | 324, all passing; ruff clean |
| Canonical entities | 22 of 22, tier placements verified against the spec programmatically |
| Optional normalisation build | Four outputs in `deliverables/normalisation/`, 25 tests; 16 data-quality flags across 10 distinct codes — every code in the enum except `PARENT_RETRACTED` |
| Real inference | `deliverables/d8_real_inference/` — prompt, artifact and run metadata from an actual `qwen2.5:7b` call, deliberately not reproducible |
| Dimension audit | `scripts_audit_dimensions.py` exits non-zero on an unmapped dimension, an identifier that does not resolve, or an entity D2 names and the example record lacks |
| Defects found in AI-written code | 23, each recorded in `docs/plan_defects.md` with how it surfaced |

Figures are current as of this commit and are checked by `scripts_audit_figures.py`, which
fails if any number in this table or in D10 has drifted from the repository. That script
exists because this table was wrong once: it was written at the commit that produced D10 and
D11 and then left to stand through four feature commits, still claiming 271 tests and 10
defects. The line counts will drift again if the repository changes; the gate is what makes
the drift visible, and the git history is what does not move.

The git history is the honest record of sequence: each design decision was committed before
the code that depended on it, and each task's correction was committed with the reason.

## Against the recommended time

The assignment recommends 4–5 hours for this role, plus 2 for the optional normalisation
build. The scope here exceeded that, and the decision to let it was explicit rather than
accidental: the brief was deepened in three places — the six security topics, the three
reliability topics, and running D8 end to end rather than specifying it.

Two cuts were taken rather than letting it grow without limit, both pre-authorised by the
design document because both degrade honestly: the `EntityKind` registry (§8.4) and
field-level `fields_read` recording (§6.3).

The optional normalisation build **was done**, and it earned its time twice over. It is where
the flag codes that no other artifact raises actually fire, which is what distinguishes a
validation enum that works from one that is merely declared. It also produced
`ConflictOutcome.WINNER_UNREPRESENTABLE` — a state nobody designed, reached because two
invariants both held on real data — and four defects of its own, including a conflict model
that could not represent the central case the build exists to show.

The scope decision is defensible either way, and the time log should show the real number so
the reviewer can judge it. A small number that is not true would be the worse outcome.

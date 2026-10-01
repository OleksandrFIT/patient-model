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
| Deliverable documents (D2, D3, D8, D9, D10, README) | |
| Review and correction of AI output | |
| **Total** | |

## What the repository can attest to, independent of the clock

| | |
|---|---|
| Commits | One per task or per decision — see `git log --oneline` |
| Design document | `docs/model_design.md`, 1,529 lines, 11 sections |
| Implementation plan | `docs/implementation_plan.md`, 29 tasks, 153 steps |
| Code | 2,684 lines in `src/`, 3,564 in `tests/` and `mock/` |
| Tests | 271, all passing; ruff clean |
| Canonical entities | 21 of 21, tier placements verified against the spec programmatically |
| Defects found in AI-written code | 10, each recorded in `docs/plan_defects.md` with how it surfaced |

Figures are as of the final commit. The line counts will drift if the repository changes; the
git history will not.

The git history is the honest record of sequence: each design decision was committed before
the code that depended on it, and each task's correction was committed with the reason.

## Against the recommended time

The assignment recommends 4–5 hours for this role, plus 2 for the optional normalisation
build. The scope here exceeded that, and the decision to let it was explicit rather than
accidental: the brief was deepened in three places — the six security topics, the three
reliability topics, and running D8 end to end rather than specifying it.

Two cuts were taken rather than letting it grow without limit, both pre-authorised by the
design document because both degrade honestly: the `EntityKind` registry (§8.4) and
field-level `fields_read` recording (§6.3). The optional normalisation build was not started.

The scope decision is defensible either way, and the time log should show the real number so
the reviewer can judge it. A small number that is not true would be the worse outcome.

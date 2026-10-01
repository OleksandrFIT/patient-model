# D11 — Time log

> The clock time is the candidate's own record, to the nearest five minutes. The breakdown is
> split by the categories the work actually fell into rather than by deliverable, so each row
> can be checked against the git history for that stretch. The rows sum to the total, and
> `scripts_audit_figures.py` fails if they ever stop summing to it.

| Activity | Time spent |
|---|---|
| Reading the assignment | 0:10 |
| Planning: stack, D8 workflow choice, scope decisions (recorded in `CLAUDE.md`) | 0:10 |
| Design: entity list, forks, comparator semantics | 0:25 |
| Design: the six security topics (audit correlation, text perimeter, `AIArtifact`, consent gate, rights matrix, output guardrails) | 0:25 |
| Design: error handling, context limits, recursion through extracted data | 0:15 |
| Writing the implementation plan | 0:20 |
| Implementation, Phase 1 — foundations, value objects, base tiers, 8 highest-risk entities | 0:35 |
| Implementation, Phase 2 — remaining full-depth entities | 0:10 |
| Implementation, Phase 3 — the thin five | 0:05 |
| Implementation, Phase 4 — AI layer schema | 0:10 |
| Implementation, Phase 5 — consent gate, projection, guardrails, adapter, D8 end to end | 0:35 |
| Deliverable documents (D2, D3, D8, D9, D10, D11, README) | 0:20 |
| Optional build — three conflicting sources reconciled into canonical, with conflict report and review queue | 0:30 |
| Wiring a real local model (ollama, `qwen2.5:7b`) and auditing what the stub had been claiming | 0:15 |
| The 25-dimension audit, rebuilt as a repeatable gate after the first pass proved circular | 0:10 |
| Correcting the stale figures in D10 and D11, and the gate that now fails on any drift | 0:10 |
| Rendering every artifact for review, and the two defects that only the rendered output showed | 0:10 |
| Switching the prompt from ids to indices, after a run fabricated a near-miss ULID | 0:05 |
| Withholding a conflict's figures from the prompt, found by running it eight times | 0:05 |
| Flags to the model as structure rather than prose, and closing check 6's partial declaration | 0:05 |
| Review and correction of AI output | 0:20 |
| **Total** | **5:30** |

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
build. The total is **5:30**: half an hour over the top of the role's own band, and an hour
and a half inside the 6–7 the assignment allows for the role and the optional build together.
Both were done.

Where the time went is more useful than the total. The brief was deepened in three places —
the six security topics, the three reliability topics, and running D8 against a real local
model rather than specifying the workflow on paper. None of those three was in the
recommendation, and together they account for fifty-five minutes.

What paid for them is visible in the row breakdown. Phases 2 and 3 took fifteen minutes
between them, against thirty-five for Phase 1, because Phase 1 settled the patterns the later
phases only applied — the same split the defect log shows, with three defects in Phase 1 and
none in the two that followed. Design that is argued before code is written is not time taken
away from implementation.

Two cuts were taken rather than letting the scope grow without limit, both pre-authorised by
the design document because both degrade honestly: the `EntityKind` registry (§8.4) and
field-level `fields_read` recording (§6.3).

The optional normalisation build cost half an hour and earned it twice over. It is where the
flag codes that no other artifact raises actually fire, which is what distinguishes a
validation enum that works from one that is merely declared. It also produced
`ConflictOutcome.WINNER_UNREPRESENTABLE` — a state nobody designed, reached because two
invariants both held on real data — and four defects of its own, including a conflict model
that could not represent the central case the build exists to show.

The last seven rows, an hour and five minutes between them, are all review and correction
after the build was nominally finished — and they produced defects 17 to 23, every one of the
last seven in the log, plus the stale figures in these two documents. In that hour a reviewer's
reading found a fabricated citation that no test could see, a prompt handing the model numbers
it was forbidden to use, a trend advertising another analyte's blocking flag, and a test that
had quietly stopped being able to fail. It is the cheapest hour here.

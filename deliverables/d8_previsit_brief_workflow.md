# D8 — Workflow: the Physician Pre-Visit Brief

Chosen because it exercises almost the whole model — conditions, medications, supplements,
labs, vitals, allergies, notes, flags, consent — so it demonstrates the model in operation
rather than one entity in isolation. D8 asks which parts of the patient model are used; this
workflow has a real answer.

It runs. `tests/test_d8_previsit_brief.py` builds the brief end to end from the example
patient, including the case where it is refused.

---

## Current state

Ten minutes before a visit, the physician opens the chart and reconstructs the picture by
hand.

1. Scroll the problem list. Decide which entries are current and which are history, because
   the list does not say.
2. Open the medication list. Cross-check against the intake form the patient filled in at
   reception, which usually disagrees with it.
3. Open the lab tab. Find the most recent panel, then hunt backwards for the previous one to
   see which way a value moved. Reference ranges differ between the two labs; nobody notices.
4. Skim the last two or three notes for what was planned and whether it happened.
5. Check allergies, if there is time.
6. Remember that the patient mentioned a supplement on the phone three weeks ago.

Elapsed: eight to fifteen minutes per patient, done twice if the first attempt is
interrupted. Nothing produced by it is written down, so the next person repeats it.

## Pain points

| | What goes wrong | Why the model addresses it |
|---|---|---|
| 1 | **Current and historical conditions look the same.** The physician infers status from dates and context | `Condition.clinical_status`, with `verification_status` separate so a suspicion is not read as a diagnosis |
| 2 | **The medication list and the intake form disagree**, and reconciling them is manual every time | Conflicts become a `DataQualityFlag` with both candidates attached, raised once, visible until resolved |
| 3 | **Trends are read by eye** across two results, in whatever units each lab used | `LabTrend`, with mismatched units excluded and named rather than silently averaged |
| 4 | **Supplements live in the physician's memory** or in a phone note | `Supplement` is a first-class entity. Biotin distorts thyroid assays; this patient started it in the autumn and her TSH is the reason for the visit |
| 5 | **Nothing produced is retained.** The reconstruction is thrown away after the visit | The brief is a read-model: reproducible, and the generation that produced its narrative is auditable |
| 6 | **Known data problems are invisible at the point of care.** The person who could resolve a conflict never sees it | Open blocking flags are a **required** field on the brief, so one cannot be constructed without them |

## Future state

```
  canonical records
        │
        ├─ authorize_ai_read(patient, consents, now) ──► AIReadScope   ◄── refuses if absent
        │                                                    │
        │   deterministic assembly (no budget)                │  projection (budgeted)
        ▼                                                    ▼
  PreVisitBrief                                        AIPatientView + selected records
   header: name, MRN, DOB                              age and sex only — no identity
   active conditions, medications, supplements               │
   allergies, recent vitals                                  ▼
   lab trends, timeline                              local model, structured output
   unresolved: [blocking flags]  ◄── required                 │
   narrative: AISummary | None   ◄───────────────────  five guardrail checks
                                                              │
                                                       pass → review=pending
                                                       hard fail → rejected_by_guardrail,
                                                                   no narrative, reason shown
```

The physician opens one page. The left side is deterministic and complete: every active
condition, every current medication and supplement, allergies, the vitals from the last
visit and the patient's own last reading, a trend per analyte, the timeline, and — at the
top, not buried — anything unresolved. The right side is a short narrative, each sentence
carrying the record it came from, or an explicit statement of why there is none.

Nothing on the left depends on the model working. That is the point of the split.

## Which parts of the patient model are used

| Used | How |
|---|---|
| `Patient` | Identity on the header; **age and sex only** in the projection |
| `Consent` | The gate. No active `ai_processing` consent, no read at all |
| `Condition` | Active ones listed and non-droppable; `verification_status` keeps a suspicion out of the narrative |
| `Medication`, `Supplement` | Current ones listed and non-droppable |
| `AllergyIntolerance` | Listed, never droppable at any budget |
| `LabResult`, `DiagnosticReport` | Trends, with the lab's own interpretation preferred over ours |
| `VitalSign` | Listed with `measurement_context`, so clinic and home readings are distinguishable |
| `ClinicalNote` | Projected with its `TextOrigin`; the transcribed portal message arrives marked external |
| `TreatmentPlan` | What was planned, for the follow-up question |
| `DataQualityFlag` | Required `unresolved` on the brief; required in the narrative's output |
| `SourceReference` | What a claim cites through, transitively |
| `AuditEvent` | One batched read event per entity type, sharing the generation's `trace_id` |
| `AIArtifact` / `AISummary` | The narrative, its inputs, its omissions, and its review status |
| `TimelineEvent`, `LabTrend`, `PreVisitBrief` | The three read-models, derived at request time |

Not used: `Coverage` (not clinical), `Goal`, `Procedure`, `SocialFactor`, `Task`,
`Encounter` beyond ordering. They exist in the model and this workflow does not need them,
which is a better outcome than inventing a use.

## Where AI can assist

- **Synthesis.** Turning twelve records into four sentences a physician can read in twenty
  seconds. This is the actual value, and it is the only thing in the list that a
  deterministic projection cannot do.
- **Direction, stated with its basis.** "TSH rising across two measurements" is useful when
  the two are named and the excluded points are named too.
- **Candidate follow-ups.** Proposed as `Task` with `status=proposed`, never opened and
  assigned.
- **Extraction from prose into structure.** A supplement mentioned in a note becomes an
  `ExtractionCandidate`, not a canonical record.

## Where human review is required

- **Everything AI proposes for canonical.** An `ExtractionCandidate` is not a fact. Accepting
  it is what creates the canonical record, and that record names the accepting human as the
  one who vouched.
- **Every narrative.** `review` starts `pending`. A brief is read with that status visible.
- **Every unresolved conflict.** The model will not pick a winner; the field stays empty with
  both candidates named until someone decides. Taking the newer source automatically is
  explicitly forbidden — recency is a heuristic, not a vouching.
- **Clinical judgement, always.** The guardrails verify grounding, not judgement. A claim can
  cite the right record, carry the right number, and still be a poor inference.

## Where two invariants met and produced a state nobody designed

The strongest evidence in this submission is not a feature. It is a state the model entered on
real data that no one had anticipated, and the fact that it entered it rather than resolving
the question quietly.

The optional normalisation build reconciles three sources for one patient. The EMR says
metformin is active. The intake form says the patient stopped taking it. The trust order
settles that without ambiguity: for whether a drug is still being taken, the patient is the
authority and the EMR records only what was intended. So the patient wins and the status
becomes `stopped`.

Except §9.8 requires a stop date for a stopped medication — that invariant is what makes
"discontinued shown as active" a record that cannot be constructed rather than a defect to be
flagged. And the patient cannot name the month: *"around January, not sure of the date"*.

Neither invariant gives way. The trust rule's answer is unrepresentable, and the model will not
hold a value nobody vouched for. So canonical keeps the EMR's `active`, and a **blocking** flag
records that the patient reports otherwise and that no autonomous use may rest on the status
until the month is established.

Three outcomes were possible and two of them were wrong. Flipping the status would have
recorded a stop with no date, which §9.8 exists to forbid. Dropping the patient's statement
would have lost the most clinically important thing either source said. What happened instead
is the third: the dispute became visible and stayed that way.

`ConflictOutcome.WINNER_UNREPRESENTABLE` exists in the code because the data produced it. It
was not in the design, not in the implementation plan, and not anticipated when §9.8 was
written — the invariant was argued for on the grounds that it removes a defect class, and this
is a second consequence of it that only appeared under real conflicting input.

That is the case for designing with invariants rather than with checks. A check would have
asked "is this medication shown as active when it was stopped?" and answered no, because the
status had been flipped. The invariant could not be satisfied, and so it surfaced a question
instead of producing an answer.

## What could go wrong

| Risk | What the model does | What it does not do |
|---|---|---|
| The model invents a number | Guardrail 2 compares every asserted value against the record it cites; a mismatch is a hard failure and the narrative is withheld | Nothing, if the number appears only in prose — which is why the output is structured claims |
| It asserts a value where there is none | Guardrail 3: an empty value slot cannot be asserted about. This is §9.6 as code | — |
| It cites a record it never read | Guardrail 1 is a set difference against `inputs` | — |
| A known conflict never reaches the physician | Guardrail 4, plus `unresolved` being required on the brief | — |
| The context window silently truncates | Non-droppable categories refuse rather than truncate; everything else omitted is named with a reason | Convert mismatched units — they are excluded instead |
| **The brief omits something critical** | **Nothing.** A brief that failed to mention an allergy passes all five checks | There is nothing to diff a summary against that was never written. This is the sharpest limit in the submission and is named in §7 |
| A pasted patient message contains an instruction | The span arrives marked `transcribed_external`, so the AI layer can refuse to act on it | Make the text safe. There is deliberately no `sanitized` flag — marking is the schema's job, refusing is policy |
| An agent reads without consent | Unexpressible: the projection takes a capability the consent check alone can mint | Cover clinical access by staff — that is `treatment` consent and out of scope |
| Consent revoked mid-generation | `valid_until` bounds the token and the adapter re-checks before constructing the artifact | Catch a revocation arriving mid-inference |
| An extraction error grows derivatives | `ai_inference` capped at `depth <= 1`; retraction cascades `PARENT_RETRACTED` to every record that named the retracted one | Walk the chain transitively in one pass — the caller re-runs per newly flagged record |

## Out of scope for Phase 1

- **Writing anything back to the EMR.** The brief is read-only. Phase 1 earns the right to
  write by demonstrating it can read correctly.
- **Real-time generation during the visit.** Generated before, read during.
- **Patient message triage**, medication reconciliation as its own workflow, and risk
  scoring. Each is a separate workflow over the same model.
- **Unit conversion**, so a mismatched unit excludes a point rather than converting it.
- **Field-level `fields_read` recording.** `None` is a legal value meaning "assume the whole
  record", so the audit is honest about its own precision.
- **Replacing the physician's own review of the chart.** The brief shortens preparation; it
  does not become the chart. A brief read instead of the record would make the omission
  limit above a clinical risk rather than a documented one.

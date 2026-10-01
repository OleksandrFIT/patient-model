# D10 — AI prompt log and critique

> The prompts below are taken from the session transcript rather than reconstructed from
> memory; they are complete, which is why some cells are long. Row 1 is from a Claude chat
> session that preceded this repository, so it is the candidate's own account rather than a
> transcript extract. The short per-task approvals during implementation are gathered into
> row 8 rather than listed as rows of their own.

---

## How AI was used

Claude Opus, in two sittings. A Claude chat session first, used only to understand the problem
and settle four decisions (row 1). Then Claude Code for everything in this repository, from the
entity list to the last fix.

The division matters for reading the log. The chat session produced no artifact on purpose: it
offered a complete architecture document and that was refused, because the assignment asks for
every major design choice to be defended and a decision taken by the tool cannot be defended by
the candidate. What came out of it was a 35-line `CLAUDE.md` holding four decisions in the
candidate's own words, which then constrained every prompt after it.

AI produced three things in the repository, in order, each reviewed before the next began:

| Artifact | In the repo | Size |
|---|---|---|
| The design specification | `docs/model_design.md` | 1,669 lines |
| The implementation plan | `docs/implementation_plan.md` | 29 tasks, 153 TDD steps |
| The implementation | `src/`, `tests/`, `mock/` | 4,638 + 4,466 lines, 324 tests |

AI was **not** used to decide the stack, the rule that AI never writes to canonical, the
workflow for D8, or whether to do the optional normalisation build. Those four were settled
before any prompt in this repository and are recorded in `CLAUDE.md`.

The working method mattered more than the prompting. Every design decision was proposed with
its cost and its rejected alternatives, approved or rejected explicitly, and only then
written. Nothing was implemented from a plan that had not been read.

---

## Prompt log

| # | Tool | Prompt | What it produced | What was useful | What was wrong, generic, unsafe, or incomplete | Accepted | Rejected | Changed | Why |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Claude (chat) | Background questions before starting: what a canonical patient data model is, how normalisation and validation differ, why one implementation stack over another, which of the seven D8 workflow options best fits the assignment. The assistant offered to produce a full architecture document covering the entity list, field definitions, validators and implementation sequence. I rejected it: the assignment requires defending every major design choice, and I cannot defend decisions I did not make. I kept a short CLAUDE.md in my own words with only the four decisions I had actually reached. | Answers on what a canonical patient data model is, how normalisation differs from validation, stack trade-offs, and seven candidate workflows for D8 — plus an unsolicited offer of a complete architecture document | The vocabulary and the shape of the problem, and seven workflow options to choose between rather than one recommendation | It offered to make every design decision for me, which would have left nothing in the submission I could defend | The vocabulary and the shape of the problem, and seven workflow options to choose between | The offer of a complete architecture document | Wrote a short `CLAUDE.md` in my own words holding only the four decisions I had actually reached | The assignment requires defending every major design choice, and a choice made by the tool cannot be defended by the candidate |
| 2 | Claude Opus | Read ASSIGNMENT.md and CLAUDE.md.<br><br>Propose the entity list for the canonical layer: which entities, what belongs in each, what is normalized vs embedded, and which fields every entity shares.<br><br>Do not write code. Give me the proposal and your reasoning for the non-obvious choices. I will push back before we implement anything. | Entity list for the canonical layer: 21 entities, shared fields, normalised vs embedded | The three-tier base split, and the argument for merging medical history into `Condition` | Proposed `review_status` on every entity, which contradicts the project's own rule that AI never writes to canonical | The entity list and the three-tier base split | `review_status` on every entity | — | It contradicts the project's own rule that AI never writes to canonical — if canonical cannot hold unreviewed AI content, there is nothing for the field to describe |
| 3 | Claude Opus | Scope. Nothing gets cut. Checking the assignment against your list, all 21 entities have a requirement behind them, and D7 says "at least 12" — that is a floor, not a ceiling. What I am managing is depth, not count.<br><br>Full depth (16): Patient, Encounter, Condition, Medication, Supplement, LabResult, ClinicalNote, TreatmentPlan, SourceReference, AuditEvent, DataQualityFlag, AllergyIntolerance, VitalSign, Consent, Provider, DiagnosticReport<br><br>Thin, 4-6 fields each (5): Coverage, Procedure, Goal, SocialFactor, Task<br><br>The split is by risk, not convenience. Full depth where a modelling mistake reaches a patient — allergies, doses, lab units, consent. Thin where the dimension is administrative and Phase 1 only needs to prove it is modelled and can be deepened later.<br><br>Two corrections to things I considered and rejected: Goal stays separate, not folded into TreatmentPlan. A patient goal can exist before any plan does. Coverage stays. Concierge practices commonly bill labs and procedures through insurance even when membership is self-pay. "If relevant" in the assignment is a scope call, not permission to assume it away.<br><br>Build order — dangerous entities first: 1. All base models, then Patient, Condition, Medication, LabResult, AllergyIntolerance, SourceReference, AuditEvent, DataQualityFlag 2. Encounter, Supplement, VitalSign, ClinicalNote, TreatmentPlan, DiagnosticReport, Consent, Provider 3. The thin five 4. Documentation<br><br>Fork answers: 1. Versioning: current state + AuditEvent carrying the field delta. Full row versioning is a temporal database and that is not what Phase 1 asks for. If someone needs state as of a date, we replay the audit deltas — slow, but out of scope here. 2. Medication / Supplement: split. Different trust presumption is the right axis — a drug was asserted by a prescriber, a supplement is self-reported. Interaction checking reads two entities instead of one. That is an extra query, not an architectural problem. 3. Labs / vitals: split. The validation severities genuinely differ — a lab without a unit is blocking, a BP without cuff size is acceptable missing. D5 requires classifying those. Merging them would make the validator branch on category. 4. Provenance: hybrid, but field_provenance is an explicit whitelist — dose, status, value, unit. Not "wherever it differs". A vague rule means that map grows to twenty fields within a week. 5. Timeline: derived. Agreed, and for the reason you gave — a stored timeline becomes a second source of truth that goes stale silently.<br><br>Three things I am pushing back on: review_status on every entity. What does Patient.review_status mean? A patient pending review? Should this live only on entities where provenance.origin can be ai_extraction? encounter_id in the base mixin. Consent has no encounter. Patient has no encounter. That is a clinical-entity field, not a universal one — right now half the entities carry a nullable field that is never set. Prefixed ULIDs. I like the idea, but who owns the prefix registry, and what happens when an entity is renamed? If Medication becomes MedicationStatement, do existing med_ IDs stay or migrate?<br><br>Answer those three, then we lock the model and move to implementation planning.<br><br>Make git init. | Fork answers: versioning, Medication/Supplement split, labs/vitals split, provenance granularity, timeline | Each fork priced with its cost, including the option not recommended | — | All five fork answers — versioning, the Medication/Supplement split, the labs/vitals split, hybrid provenance, a derived timeline | — | `field_provenance` narrowed from "wherever it differs" to an explicit whitelist | A vague rule grows that map to twenty fields within a week |
| 4 | Claude Opus | I accept all three, and two of them are better than what I asked for.<br><br>`indeterminate` instead of a flag is right. >100 against a threshold of 150 is not a defect — the value was vouched for, there is simply no conclusion to draw. If we flagged it, the review queue would fill up with things nobody can fix.<br><br>A series with all its points is better than mine. I said "name the ones thrown out"; you say three consecutive <0.01 results are themselves a signal. Agreed. The physician sees three points and the arrow stays silent — that is how it should be.<br><br>Good that you added UNIT_MISMATCH. A trend that quietly adds 5.5 mmol/L to 99 mg/dL is exactly what the whole model is against.<br><br>`reported_interpretation` — we keep it. The laboratory vouched for its own "H", that is a source fact. Overwriting it with a computed one is no better than letting AI rewrite canonical. Add INTERPRETATION_DISAGREES_WITH_RANGE, the argument about the wrong range holds.<br><br>Titer in §7 — yes.<br><br>Leave the "< 2" rule and the ban on tuned thresholds as they are. Without that line someone will put 0.5 in.<br><br>I am still reading the spec. Corrections in one pass after the review. | `comparator` on `Quantity`, and its consequences for range comparison and trends | Interval reasoning: a comparator makes a value an interval, so a range check is decidable only when the interval lies on one side | First draft would have raised a flag for an indeterminate comparison | `comparator` on `Quantity`, the full series with its excluded points, `UNIT_MISMATCH`, and `reported_interpretation` kept as a source fact | — | `indeterminate` became a value rather than a flag | A comparison with no conclusion is not a defect, and flagging correct assay output would fill the review queue with items nobody can fix |
| 5 | Claude Opus | We have not talked about security once, and D6 requires it. Four things that have to be in the model, not in the docs:<br><br>1. Locality of inference. PAI3 requires local-only. Right now that is nowhere enforced. AIArtifact must carry the model, the engine and the fact that execution was local — and that has to be a Literal, not a str. A string can be set to "cloud" and nothing will stop it.<br><br>2. Consent as a gate, not as a record. We have Consent with scope ai_processing, but nowhere can I see where it is checked. An agent reading a patient without active consent is the simplest and the worst error in the system. It must be structurally impossible, the way you did it with unresolved.<br><br>3. What exactly the model saw. AuditEvent logs the read — good. But can it answer the question "which fields were in the context when this brief was generated"? Without that an incident cannot be investigated.<br><br>4. Prompt injection through clinical data. ClinicalNote.content is free text. A patient's message ends up in a note, the note goes into the prompt to a local model. The text can contain an instruction. For the data model the question is this: does the schema distinguish text produced by the practice from text that arrived from the patient or from an external document? As far as I can see, right now it does not.<br><br>Do not propose solutions straight away — first tell me which of these is already covered in the spec and where, and what is genuinely missing. Possibly I have missed something. | Six security gaps found by audit: audit correlation, text perimeter, `AIArtifact`, consent gate, rights matrix, output guardrails | The audit distinguished "already covered and where" from "genuinely absent", including one case where the document contradicted itself | §6.3 claimed an agent's context could be reconstructed while the field list could not deliver it | All six gaps — audit correlation, the text perimeter, `AIArtifact`, the consent gate, the rights matrix, output guardrails | — | — | The audit separated "already covered, and where" from "genuinely absent", and found §6.3 contradicting itself — the most valuable finding of the session |
| 6 | Claude Opus | And let us quickly discuss this. Three more topics; the role requirements name them directly — error handling and reliability under messy data.<br><br>Error handling. Extraction failed halfway, the document is corrupt, normalisation fell over on one record out of a batch. Is the batch accepted partially or rejected entirely? If partially — how is it visible that something is missing. A missing record looks the same as one that never existed, and a failure must not be silent.<br><br>Limits. 400 labs over ten years, a 50-page note, a panel of 80 analytes. Where are the limits and what happens when we hit them. For local inference especially: the context is small, and silent truncation before the prompt is the same invisibility we are building everything against.<br><br>Recursion through data. The AI extracted a fact, the fact went into canonical, the next run reads it and extracts a derived one. Is a fact from a source document distinguishable from a fact derived from another extracted fact, and is the chain visible. If not, an extraction error grows derivatives and the source is lost.<br><br>First what is already covered and where, then proposals. Do not touch the file. | Error handling, context limits, and recursion through extracted data | §6.19's depth cap closed a question that arose later in §10.6 — a decision made for one reason resolved another | — | All three topics — partial ingestion, context limits, recursion through extracted data | — | — | §6.19's depth cap closed a question that arose later in §10.6: `ai_inference` at `depth <= 1` means AI never reasons from its own inferences |
| 7 | Claude Opus | Write the plan.<br><br>[skill arguments] Implementation plan for steps 1-5 of docs/model_design.md — canonical patient data model (Python + Pydantic v2). Spec is complete and locked at docs/model_design.md (1474 lines). | The implementation plan | Full TDD granularity where the invariants live; honest about where it grouped mechanical work | Four defects in the code it specified, listed below | The plan, as a plan | — | Four defects in the code it specified, corrected in flight | Full TDD granularity where the invariants live, and honest about where it grouped mechanical work; the defects were in specified code, not in the plan's shape |
| 8 | Claude Opus | Yes, with a stop after each task. Start with Task 1.<br><br>[then, per task] yes / next / go on<br><br>[and three process corrections during execution] Are the fixes live? Have those bugs gone? If so, carry on. — Go on. Give me feedback after each phase is finished. — Insert the smoke test now. Also, you do not need to ask me after every step, do it after every phase. | Implementation, 29 tasks | 264 passing tests at the close of task 29, ruff clean, every spec section traceable to a task | Ten defects, six of them in Phase 5 | The implementation, task by task | — | Ten defects, six of them in Phase 5, each corrected before the task was committed | A defect fixed after its own commit is indistinguishable from one that was never there; all ten are in `docs/plan_defects.md` |
| 9 | Claude Opus | There is enough time — we are doing the optional normalisation build.<br><br>Three conflicting sources for one patient: an EMR export, an extraction from a laboratory PDF, a row from an intake table. The conflicts from the assignment — a different dose, missing units, a different spelling of a diagnosis, a divergent supplement list, a discontinued drug shown as active, a duplicated lab.<br><br>On the output: canonical JSON, a validation report, a conflict report, a human review queue, and briefly what was automated and what was not.<br><br>Here, at last, the six flag codes that nothing raises so far will fire. That is the proof that they are not dead code.<br><br>We skip step 6.<br><br>Write the phase in full, then show me. | The optional normalisation build: three conflicting sources into canonical | Produced a state nobody designed — see `WINNER_UNREPRESENTABLE` in D8 | Four defects of its own, including a conflict model that could not represent the central case it existed for | The optional normalisation build | — | Four defects of its own, including a conflict model that could not represent the central case it existed for | It produced a state nobody designed — `WINNER_UNREPRESENTABLE`, two invariants meeting on real data — which is the strongest evidence in the submission |
| 10 | Claude Opus | Two questions I have not had an answer to yet.<br><br>What is currently substituted for the model in the adapter — a stub or a real call? If a stub: how much work is it to connect ollama so that D8 runs on real generation, and the guardrails catch real misses rather than planted ones.<br><br>And does the stub look anywhere like real inference. If so — that has to be named directly in the README, not left for the reviewer to guess.<br><br>Move WINNER_UNREPRESENTABLE into D8 or D10 as a separate paragraph. That two invariants met on real data and produced a state nobody designed is the strongest piece of evidence in the whole submission, and right now it is sitting in a report rather than in a deliverable. | Wiring a real local model, and auditing what the stub looked like | Found that the stub reported `engine=ollama` with a real model name and a genuine prompt digest, for a prompt never sent | **The design's five output checks had a hole a real model walked straight through** | Wiring a real local model, and the audit of what the stub had been claiming | — | `Engine.STUB` added, and a sixth output check | The stub reported `engine=ollama` with a real model name and a genuine prompt digest, for a prompt never sent — unverifiable provenance inside a submission about provenance |
| 11 | Claude Opus | Two things before submission.<br><br>Where in the model do "symptoms and patient concerns" live? That is a separate item in the list of required dimensions, and there is no Symptom entity. If they are deliberately folded into Condition with verification_status, or into ClinicalNote — that has to be written directly in D2, because the reviewer will walk the list of dimensions and put a tick against each one.<br><br>And fix Evidence: 0 source reference(s) in the review queue, as you proposed yourself. It is the first file after canonical, and four rows with zero evidence read as a hole, even if by construction that is exactly what they are. | The `Symptom` entity, and the review queue's evidence lines rewritten to distinguish three kinds of evidence | Confirmed the gap was real rather than a wording omission: dimension 8 had no entity behind it at all | Four queue rows reading `0 source reference(s)` — correct by construction and indistinguishable from a hole | Both findings | — | `Symptom` added as a clinical record, and the queue's evidence lines rewritten to distinguish three kinds of evidence | Dimension 8 had no entity behind it at all, and four rows reading `0 source reference(s)` were correct by construction yet indistinguishable from a hole |
| 12 | Claude Opus | Run the full 25-dimension audit again, so that nothing is left over. | Re-running the 25-dimension audit against the code and the example record | Two gaps that four earlier passes over the same table had not shown | The first audit had been circular — it compared a hand-written mapping to itself | Both gaps the re-run found | — | The audit rewritten as `scripts_audit_dimensions.py`, which now gates the submission | The first pass had been circular — it compared a hand-written mapping to itself, so it could not fail |
| 13 | Claude Opus | Three errors in D10 and D11.<br><br>D11 says "The optional normalisation build was not started" — it is done, four outputs and 25 tests. That is exactly the defect you describe yourself in D10 as claims that outran the code, and it is sitting in the file about honesty.<br><br>The figures are stale everywhere: 271 tests instead of 319, 10 defects instead of 18, lines of code. D10 contradicts itself — the table says one thing, the attest section another.<br><br>D11 has no rows for the normalisation build, wiring the real model and the dimension audit. Add them.<br><br>Check the figures against the repository before the commit, not after. | Corrected figures in D10, D11 and README, and `scripts_audit_figures.py` | Named the failure as the one D10 already describes — claims that outran the code — in the file whose subject is honesty | Every figure had been correct when written and was left to stand through four feature commits; D10 also contradicted itself, its instrument table against its own heading | All three errors | — | Figures corrected in D10, D11 and the README, and `scripts_audit_figures.py` added as a gate | Every figure had been correct when written and was left to stand through four feature commits — claims that outran the code, in the file whose subject is honesty |
| 14 | Claude Opus | [first asked after the optional build] Show me the result of the normalisation build directly in the chat, not as a description. For each of the three sources — a fragment of the raw data, and what came out of it in canonical. Then the three reports in full: validation, conflicts, the review queue. Separately show the input and the output of a real ollama run: the prompt, what the model returned, what the guardrails said. And tell me where these files are, so that I open them myself.<br><br>[repeated after each later change] Run everything again and show me the input and the output, not a description. Three runs: 1. Normalisation — three sources into canonical. Show a fragment of each source and what came out of it, plus the four reports. 2. D8 on the real model — the prompt in full, what the model answered, the guardrails verdict. 3. The assembled PreVisitBrief for this patient, as the physician sees it — both parts, the deterministic one and the narrative. Plus run both audits and the tests, show the outputs. Show everything as actual output in the chat. | Every artifact rendered as actual output: each source fragment against what it became in canonical, the four reports, the real prompt and reply, both parts of the brief | Reading the rendered output found what asserting on fields had not — defects 19, 20 and 22 | The first display script re-ran the guardrails on an artifact the adapter had already rejected, and reported a pass on its cleared claims — the trap that script's own source file warns about | Rendering every artifact as actual output, as standing practice | — | The verdict is read off the artifact, never recomputed | Reading rendered output found defects 19, 20 and 22, which asserting on fields had not — and the first display script re-ran the guardrails on an artifact already rejected and reported a pass |
| 15 | Claude Opus | Take (b). FlagSummary was kept narrow deliberately, and widening it to fix rendering is wrong. The flag at brief level already blocks the conclusion and it is true there. A trend with someone else's flag is worse than a trend with no flag: right now TSH, clean and rising, is marked unusable.<br><br>Commit the new run, it is stronger, because there is a real id fabrication in it rather than a theoretical one. Add a table of all four runs: three pending and one rejected on the same prompt is precisely the proof of what the guardrails are for.<br><br>Move the id fabrication into D10 separately. An invented ULID with the right prefix and a divergence in the tail is not something you catch by eye; that is a stronger example than numbers in prose.<br><br>And record your own script, the one that walked into the documented trap, in plan_defects outside the numbering, like the word count.<br><br>Separately, make indices instead of ULIDs in the prompt: [1], [2], [3], the adapter maps them back. The map is local to one call: we assembled the prompt, the model answered, we expanded the indices into ULIDs, we threw the map away. The real ULID goes into the artifact; inputs and the guardrails do not change. If the model writes [9], which does not exist, that is the same hard fail.<br><br>Leave the table with the fabrication as a historical record and write plainly: the indices remove the cause, the guardrail stays, because it has not yet seen the next class of fabrication.<br><br>Show the runs after the indices too, I am curious whether it disappears. | Prompt indices in place of ULIDs, and the trend-flag fix | Removed the cause of a fabricated citation instead of relying on the catch; replies also became deterministic | A test that could no longer fail was introduced in the same change, and the switch exposed a prompt that hands the model unciteable numbers | Prompt indices in place of ULIDs, and the trend-flag fix | Widening `FlagSummary` to fix rendering | The index map kept local to one call and thrown away; the guardrails untouched | Removing the cause beats relying on the catch, but the guardrail stays because it has not yet seen the next class of fabrication; a trend carrying another analyte's flag is worse than one carrying none |
| 16 | Claude Opus | Take (a), and run it again after that. | Withholding a flag's competing figures from the prompt | Turned 8 rejections out of 8 into 8 narratives out of 8, by removing a number rather than loosening a check | The placeholder leaks into the model's prose, and the claim about the conflict is now dropped for citing nothing | Withholding a flag's competing figures from the prompt | — | The redaction pattern made deliberately broader than check 6's, with the reason recorded where both live | 8 rejections out of 8 became 8 narratives out of 8 by removing a number rather than loosening a check; an integer left in a flag message would be restated and would pass every check |
| 17 | Claude Opus | Two loose ends.<br><br>Remove (withheld) from the prompt entirely. The word is addressed to the model, and the model repeats it back, and the physician reads "a withheld value" above two numbers that are visible in the deterministic part. The flag line simply must not contain a place for a number: name the code, the field, and that two sources disagree. Do not hide anything textually, just do not print it.<br><br>Close the partial declaration. Check 6 currently lets through a claim that declares one number and mentions a second in prose. That is the same hole as defect 15, only narrower, and you have already named it yourself. Every decimal in the text must be declared, not "at least one".<br><br>After both, run it again, the same set of eight. | Flags as structure rather than prose, and check 6 closed | Removed the slot a figure could sit in, instead of removing the figure from it; the conflict claim became legal and survived | Both were defects in the previous two commits, one of them in that commit's own fix | Both — flags as structure, and check 6 closed | — | The target reaches the prompt via `GenerationContext` rather than via `FlagSummary` | Removing the slot a figure could sit in, instead of removing the figure from it; both were defects in the previous two commits, one of them in that commit's own fix |
---

## Critique of the AI output

The full record is `docs/plan_defects.md`. The summary, with the numbers rather than an
impression.

### Twenty-three defects in AI-written code, and how each surfaced

| How found | Count | Example |
|---|---|---|
| Reading the code against the spec, before or while writing it | 7 | A Pydantic attribute without `ClassVar`, which stops the module importing at all, repeated across five entities |
| Running a component on real output from the one upstream of it | 5 | The guardrails and the projection held **separate definitions** of droppability, so a brief that correctly omitted a resolved condition was rejected |
| The plan's own tests | 2 | `TypeError` on any half-open reference range — the commonest shape, since hs-CRP has no lower bound |
| Resolving a documented identifier against the code, and a documented entity against the example record | 2 | `TreatmentPlan.plan_items` appears in the design document and in D2; the field is `items`, and had read that way since the design phase |
| An exhaustive sweep of one function's inputs | 1 | A budget of zero returned an empty projection instead of refusing |
| **Rendering the output for the reader it is for** | **2** | Every lab trend advertised the glucose conflict, so a clean rising TSH was marked unusable |
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

Four sets, 28 runs. Same prompt and same model within each set; between sets, one change each:

| Runs | `review` | narrative | guardrail |
|---|---|---|---|
| before indices, 4 runs | 3 `pending`, 1 `rejected` | 3 delivered | `cites_in_inputs` on the fabricated id |
| after indices, 8 of 8 | `rejected_by_guardrail` | **none delivered** | `numbers_in_text_are_declared` |
| after redaction, 8 of 8 | `pending` | 8 delivered, 2 claims | — |
| after structured flag lines, 8 of 8 | `pending` | 8 delivered, **3 claims** | — |

No fabricated citation in any of the 24 runs after the switch, and the replies became
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

The first form of that fix substituted a placeholder for each figure, and the model read the
placeholder as content and wrote it back: *"the EMR showing a withheld value that conflicts with
a lab result that is also withheld"*. It emitted that claim with an empty `cites` array, so the
parser dropped it and recorded the reason — but had it cited `[4]`, a brief would have told a
physician about "a withheld value" sitting directly above the two numbers in the deterministic
section, which a physician is entitled to see. That is defect 22, and the mistake behind it was
treating the message as something to launder. It is written for a physician and has no business
in a prompt at any level of redaction.

The flag now reaches the model as structure rather than prose — its code, its severity, the
record by prompt index, and the field:

```
Unresolved data problems you must not reason past. Name one by its code if it
is worth a physician's attention, and state no figure for it:
  CONFLICTING_VALUES (blocking) at [4], field quantity
```

There is no slot where a figure could appear, so nothing has to be taken out of one. Naming the
field needed the flag's target, which `FlagSummary` does not carry and was deliberately not grown
to carry — settled in defect 19. It reaches the prompt through a field on `GenerationContext`
instead, the type whose whole job is deciding what the model may see.

What the model writes about the conflict now is a legal claim, and the third row of the table is
that claim surviving:

```json
{ "text": "There is a conflict in the fasting glucose value, and it is unresolved.",
  "cites": ["[4]"] }
```

No figure, a citation that resolves, nothing dropped and nothing rejected. The deterministic part
of the brief still carries the flag with the real readings, because that reader may see them.

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
if it had been accepted as produced: twenty-three defects, five of which only a cross-component
check could find, one that only a real model could find, two that only resolving a document against
the code could find, two that only reading the rendered output could find, five overstated claims,
and one artifact that was itself a false claim.

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

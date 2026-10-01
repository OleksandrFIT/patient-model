# D2 — Explanation of each model element

One row per entity, in the columns the assignment suggests. Grouped rather than given as a
single twenty-five row table, which nobody reads.

The reasoning behind the non-obvious choices is in `docs/model_design.md` §6; this file is
the per-element reference. Section numbers point there.

---

## The assignment's required dimensions, and where each one lives

A reviewer walking the list in the brief should be able to tick every line. One of them —
symptoms and patient concerns — was **missed on the first pass** and is recorded as an omission
in §6.20 rather than presented as a refinement.

| # | Required dimension | Where it lives |
|---|---|---|
| 1 | Patient identity and demographics | `Patient` |
| 2 | Contact information | `Patient.contacts`, `Patient.addresses` (embedded — §5) |
| 3 | Consent and authorization | `Consent`, enforced as a capability (§10.3) |
| 4 | Care team and provider relationships | `Provider` + `Patient.care_team` |
| 5 | Insurance or payment context, if relevant | `Coverage` (thin; outside AI read scope) |
| 6 | Medical history | `Condition` with `clinical_status` resolved — **one entity with 7** (§6.4) |
| 7 | Current conditions and diagnoses | `Condition` with `clinical_status` active |
| 8 | **Symptoms and patient concerns** | **`Symptom`, with `patient_concern` in the patient's own words (§6.20)** |
| 9 | Medications | `Medication` |
| 10 | Supplements | `Supplement` — split from 9 on trust, not fields (§6.7) |
| 11 | Allergies and contraindications | `AllergyIntolerance` |
| 12 | Lab results and biomarkers | `LabResult`, grouped by `DiagnosticReport` (§6.8) |
| 13 | Vitals and measurements | `VitalSign` with `measurement_context` (§6.6) |
| 14 | Imaging and diagnostic reports | `DiagnosticReport` — narrative, no discrete values |
| 15 | Clinical notes | `ClinicalNote`, body marked with its perimeter origin (§10.1) |
| 16 | Treatment plans | `TreatmentPlan` with embedded `items` |
| 17 | Procedures and interventions | `Procedure` |
| 18 | Patient goals and preferences | `Goal` (patient-owned) + `Patient.preferences` |
| 19 | Lifestyle and social factors | `SocialFactor`, dated so staleness is visible (§6.16) |
| 20 | Timeline of clinical events | `TimelineEvent` — **derived, never stored** (§6.13) |
| 21 | Documents and source references | `SourceDocument` (source layer) + `SourceReference` |
| 22 | Tasks, follow-ups, and workflow state | `Task`, AI may only propose |
| 23 | Data provenance and audit trail | `Provenance` (a value) + `AuditEvent` (a record) — §6.3 |
| 24 | Data quality flags | `DataQualityFlag`, an entity not a list (§6.5) |
| 25 | AI-generated summaries and human review status | `AISummary` + `review`; status is **derived** in canonical (§6.1) |

Two of these are answered by a decision rather than by an entity, and both are defended rather
than assumed: 6 and 7 are one `Condition` because they differ by a single field, and 25's review
status is derived from open flags because a stored one goes stale.

---

## D4's ten items, and where each one lives

Same purpose as the table above. D4 lists ten things the model must track, and a reviewer going
through them one by one should find each rather than have to derive it. Nine are fields. The
tenth — human review status — is **absent as a field by design**, and that is said here plainly
instead of being left to §6.1 to argue.

| D4 asks the model to track | Where it is |
|---|---|
| Source system | `SourceDocument.source_class` in the source layer, reached by `Provenance.source_refs` → `SourceReference.document_id` |
| Source document | `SourceReference.document_id`, with `SourceDocument.filename` and `content_sha256` — the hash is what makes the document the one that was read |
| Source field | `SourceReference.field_path`, plus `page`, `span_start`/`span_end` and `quote` (§6.17) |
| Date imported | `Provenance.imported_at` — distinct from `asserted_at`, which is when a human or system vouched for the value |
| Date last updated | `updated_at` on every canonical record (§2.1) |
| Who or what changed the record | `updated_by` for the current state, and `AuditEvent.actor` per event — append-only, reads logged as well as writes (§6.3) |
| Whether a field came from a human, a source system or AI extraction | `Provenance.origin`, five values, with `ai_extraction` and `ai_inference` kept apart because the second compounds (§6.19) |
| Confidence level, if AI extraction was used | `Provenance.extraction_confidence` |
| **Human review status** | **No field, deliberately (§6.1).** AI never writes to canonical, so canonical cannot by construction hold unreviewed AI content for a status to describe |
| Version history | `version` and `superseded_by` on every record, with the field-level delta on `AuditEvent.field_delta` (§6.15) |

The review-status capability is not missing; it is three fields that already exist, and the
reason for preferring them is that a stored status diverges from reality the moment a flag is
resolved and the field is not updated with it:

| The question D4 is really asking | What answers it |
|---|---|
| Is anything about this record still outstanding? | Open `DataQualityFlag` records targeting it — `status`, and `severity` for how badly |
| Who vouched for this value? | `Provenance.asserted_by` — for an accepted extraction, the human who accepted it, not the model |
| When was it reviewed, and from which candidate? | `AuditEvent`, correlated by `trace_id`, plus `ExtractionCandidate.produced` in the AI layer |

---

## Identity and context

| Element | What it contains | Why it matters | Source systems | AI / workflow use | Risks if missing, stale, duplicated or wrong |
|---|---|---|---|---|---|
| **Patient** | `identifiers[]`, names, birth date, sex at birth, gender identity, contacts, addresses, preferences, care-team memberships | The anchor every clinical record scopes to. Identifiers are a **list** because a concierge practice pulls from several EMRs and one person has several MRNs | EMR exports, intake forms, lab portals | Age and sex only, via `AIPatientView`; identity never reaches a model | A single `mrn` field is the primary cause of duplicate patients. Two records for one person splits their history, and a brief built from one half is confidently incomplete. Stale contacts delay results that change management |
| **Provider** | Name, identifiers, specialty, `is_external` | Referenced as prescriber, note author and lab orderer. Normalised so "every medication prescribed by Dr X" is answerable | EMR provider directory, referral letters | Read; attribution in a brief | Free-text names drift into "J. Smith" / "John Smith MD", and the question becomes unanswerable. Not patient-scoped, so it is **outside** a patient's consent and data export (§2.4) |
| **Consent** | `scope`, effective window, `revoked_at`, `revoked_by` | The enforcement point for the whole AI layer, not documentation. §10.3 turns it into a capability token | Signed forms, portal consent, scanned PDFs | Consumed by the gate; never read by the agent | Missing or expired consent and an agent still reading is the simplest and worst failure in the system. Revocation that cannot be told from expiry makes the audit trail unable to answer whether the patient withdrew |
| **Coverage** | Payer, member id, effective dates | Concierge practices bill labs and procedures through insurance even when membership is self-pay | Insurance cards, clearing-house files | **Outside AI read scope** — payment context is not clinical | Thin by design. Stale coverage causes a denied claim, not a clinical error, which is why it is thin |
| **Encounter** | Type, period, participants, reason | The grouping anchor for "what happened at the March visit" and for the pre-visit brief | EMR scheduling and visit records | Read; orders the timeline | Clinical records with no encounter cannot be grouped into a visit, so a brief lists facts without the context that produced them |

---

## Clinical core

| Element | What it contains | Why it matters | Source systems | AI / workflow use | Risks if missing, stale, duplicated or wrong |
|---|---|---|---|---|---|
| **Condition** | Coded concept, `clinical_status`, `verification_status`, onset, abatement | Medical history and current diagnoses in **one** entity: they differ by `clinical_status` alone (§6.4) | EMR problem list, notes, intake forms | Read; active ones are non-droppable from any projection | Two entities would let the same diabetes exist as a history row and a current row that diverge at the first update. Without `verification_status`, "suspected lupus" enters a summary as "has lupus" — the cheapest safeguard against the most expensive error |
| **Symptom** | Coded symptom, `status`, `reported_by`, `severity`, onset, `patient_concern` | What the patient reports experiencing. **Not** a `Condition` with `verification_status=unconfirmed`: that field means "we do not know whether this diagnosis holds", and a symptom's existence is not in doubt (§6.20) | Intake forms, visit notes, portal messages, triage calls | Read; the complaint a brief is usually about | Folded into `Condition`, every symptom reads as a weak diagnosis and a brief cannot tell "reports fatigue" from "has hypothyroidism". Left in note prose, "which patients report fatigue" is unanswerable. `severity` defaults to `unspecified` because an unrecorded severity is not a mild one |
| **AllergyIntolerance** | Substance, reactions, `criticality`, `verification_status` | The most safety-critical list in the model, with its own audit trail. `criticality` — is it life-threatening — is separate from the `severity` of a past reaction | EMR allergy list, intake forms, patient report | Read; **never droppable**, whatever its verification status | A missed allergy is the canonical harm case. Never embedded on `Patient`, so a change is attributable. A brief that omits one passes every output guardrail, which is why §7 names omission as undetectable |
| **Medication** | Drug, `Dosage`, status, start and stop dates, prescriber | `status` and `stopped_on` must agree in both directions, so a discontinued medication presenting as active is a record that **cannot be constructed** (§9.8) | EMR, e-prescribing, notes, intake | Read; current ones non-droppable | D5 asks for a flag on "discontinued shown as active"; layer 1 removes the state instead. Conflicting doses between EMR and intake leave the field empty with a blocking flag, never a silently chosen winner |
| **Supplement** | Substance, dose as reported, status, reported reason | Split from `Medication` on **trust**, not field overlap: a drug was asserted by a prescriber, a supplement is self-reported (§6.7) | Intake forms, patient messages, visit notes | Read; current ones non-droppable | Interaction checking uses a different knowledge base. Biotin distorts thyroid immunoassays: a brief that hides supplements hides the likeliest explanation for an abnormal TSH. Unlike medications, no stop date is demanded — a patient rarely knows when they stopped, and demanding it discards the fact that they did |
| **DiagnosticReport** | Report type, issue date, result ids, findings, impression | Groups a panel or an imaging study, so a fourteen-analyte panel is not fourteen orphan rows and "the CBC from 12 March" has something to cite (§6.8) | Lab portals, imaging PDFs, outside reports | Read and cited | Without it there is nothing to cite at report granularity, and the lab's own interpretation has nowhere to live. Imaging is the same entity with narrative and no discrete values |
| **LabResult** | Analyte, collection date, `quantity` **or** `coded_value`, reference range, reported interpretation, specimen, performing lab | Two parallel value slots, at most one filled. The empty state is legal and meaningful: it is how an unresolved conflict is held (§9.3) | Lab PDFs, portal feeds, EMR, outside labs | Trends, brief, reconciliation | Unit mismatch silently averaging 5.5 mmol/L with 99 mg/dL. A missing unit is a flag, not a rejection — rejecting makes the lab invisible. The lab's own "H" is a **source fact** and is never overwritten by our computation, because a disagreement means the stored reference range is suspect |
| **VitalSign** | Kind, measured at, quantity, `measurement_context`, body position, cuff size | `measurement_context` is required so trend analysis can exclude patient-reported points | In-clinic devices, wearables, patient portal | Trends, brief | Home weight and clinic weight averaged together is a trend that means nothing. A missing cuff size is an **acceptable** missing value, not a defect — the severity difference from labs is why the two stay separate entities (§6.6) |
| **Procedure** | Code, performed date, performer, outcome | Dated interventions on the timeline | EMR procedure log, operative notes, outside records | Read; timeline | Thin. A missing date means it cannot be placed, and it contributes nothing rather than appearing at an invented moment |
| **ClinicalNote** | `note_type`, author, `body` as `ClinicalText`, addenda, signature | Narrative, with the perimeter origin travelling **with** the text rather than beside it (§10.1) | EMR notes, dictation, scanned letters | Read, labelled; extraction source | A fact mentioned in prose does **not** live here — it becomes a `Condition` with `ai_extraction` provenance pointing at the span, entering canonical only when a human accepts it. `note_type` has no `patient_message` value: a note is a record of the practice, not a container for external text |
| **TreatmentPlan** | Title, embedded `items[]` of `PlanItem`, author | Items have no lifecycle of their own and are revised as part of the plan | Visit notes, care-plan modules | Read; follow-up extraction | A plan whose items point at no record cannot be reconciled against what was actually prescribed |
| **Goal** | Description, target date, status | Patient-owned and outlives any single plan, which is why it did not fold into `TreatmentPlan` | Intake, portal, visit conversation | Read | `PatientScoped`, not clinical: a goal can exist before any plan and before any visit |
| **SocialFactor** | Factor, value, `asserted_on` | A record with an assertion date, not a mutable block on `Patient` (§6.16) | Intake forms, visit notes, questionnaires | Read; risk context | **Staleness is the whole risk**: "smoker" recorded in 2019 and never revisited. A mutable block has no history and cannot show when the claim was last true |
| **Task** | Description, `origin`, status, assignee, due date, source | Follow-up and workflow state | Staff workflow, extracted follow-ups | **May propose**, with `status=proposed` | An AI-extracted task opened and assigned by the pipeline is an instruction nobody authorised. Assignment is the human approval step |

---

## Provenance, audit and quality

| Element | What it contains | Why it matters | Source systems | AI / workflow use | Risks if missing, stale, duplicated or wrong |
|---|---|---|---|---|---|
| **Provenance** (embedded on every record) | `origin`, `asserted_by`, `asserted_at`, `imported_at`, `source_refs`, `derived_from`, `depth`, `extraction_confidence` | A property of a **value**: where this number came from and who vouched for it | All | Citation, confidence, review routing | Without it an AI value is indistinguishable from a physician's within a week. `ai_extraction` and `ai_inference` are separate because the second **compounds** — a fact inferred from facts grows derivatives, which is why inference is capped at `depth <= 1` |
| **SourceReference** | Document id, page, field path, span, quote | The single citation primitive. Normalised, because one lab PDF supports forty results | All ingested documents | **Must** be cited; dispute resolution | Embedded, "show me everything from this report" becomes unanswerable and storage multiplies. Without the quote and span, a citation points at a document rather than at the claim inside it |
| **AuditEvent** | Actor, action, `trace_id`, targets, `fields_read`, `ingest`, field delta | A stream of events over a **record**, and it logs **reads** as well as writes | System-generated | Incident reconstruction | Conflating this with provenance is the commonest failure in such models. Uncorrelated read events answer nothing, so `trace_id` ties every read to the generation it served. Reads get their own retention, since only writes carry the deltas versioning needs |
| **DataQualityFlag** | `code`, `severity`, `targets[]`, `candidates[]`, `source_locator[]`, lifecycle | An entity, not a list on each record: the review queue is a cross-patient query, a conflict needs two targets, and a flag's lifecycle is independent of the record's version | Validators, normaliser, ingest pipeline | **Must** be surfaced by any read-model | `blocking` does not block persistence — it blocks autonomous conclusion. Embedded, every review action would bump the version of a clinical fact and bury its change history under review noise |
| **ClinicalText** (embedded) | `value`, `origin`, `captured_by` | The trust boundary is whether the text **crossed the practice perimeter**, not who signed the record (§10.1) | Notes, outside reports, pasted messages | Every span reaches a model labelled | A physician pasting a patient message carries external text inside, and the signature does not change what the text is. `unknown` counts as external: the default fails closed. There is deliberately **no `sanitized` flag** |

---

## Derived — never stored

| Element | What it contains | Why it matters | AI / workflow use | Risks |
|---|---|---|---|---|
| **TimelineEvent** | Dated projection over encounters, condition onset and abatement, medication start and stop, labs, procedures, notes | Stored, it becomes a second source of truth that goes stale the moment any entity changes, with nothing to detect the divergence (§6.13) | Timeline view, brief | A record with no usable date contributes nothing rather than appearing at an invented moment. Every row names the record it projects |
| **LabTrend** | Full series, `numeric_basis`, **required** `excluded[]`, direction | A comparator point leaves the **arithmetic**, not the series: three consecutive `TSH <0.01` are a signal, and dropping them loses it | Trend analysis, brief | Excluding points silently is the failure this prevents. `direction` is indeterminate below two numeric points — the minimum at which a direction exists, not a tuned threshold |
| **PreVisitBrief** | Header with identity, clinical lists, trends, timeline, **required** `unresolved[]`, optional narrative | Identity sits on the deterministic wrapper; the narrative is generated from `AIPatientView` and cannot contain a name it never received (§10.4) | D8's workflow | `unresolved` is required with no default, so a brief that dropped a flagged lab cannot be constructed. The brief has **no context budget** — only the narrative is bounded |

Five of the assignment's six columns here, and the divergence is deliberate: *Source systems* is
dropped because nothing in this table has one. Each of these is computed from canonical records on
demand and never stored (§6.13), so its sources are the records it projects — named in its own row
rather than given as a column that would read "canonical" three times.

---

## AI layer

| Element | What it contains | Why it matters | AI / workflow use | Risks |
|---|---|---|---|---|
| **AIArtifact** | `trace_id`, versioned `inputs`, `omitted`, `produced`, `prompt_digest`, model id and digest, engine, `execution`, `consent_ref`, review, guardrail failures | What is recorded about one generation. `execution` is `Literal["local"]`, so a cloud run is unrepresentable | Audit, review queue | The prompt is **not** stored: it contains PHI, and storing it duplicates canonical data outside canonical governance. Digest plus versioned inputs supports *reconstruction*, which holds only while those versions are unchanged — and the digest proves when it no longer does |
| **AISummary** | Claims, each with citations and structured values; required `unresolved[]` | Structured, not prose, because over prose none of the five output checks works | The narrative a physician reads | A number extractor over prose that misses one produces a **false pass**, worse than no check |
| **ExtractionCandidate** | Proposed entity type and payload, `produced[]` | The suggestion channel. Nothing here is canonical | Human review | `produced` runs this direction because canonical never references the AI layer. Its durability is the lineage's durability: prune the AI layer and facts already accepted can no longer be explained |

Five columns again, for the same reason: the AI layer's input is canonical, not a source system.
What a given generation actually read is recorded per artifact in `AIArtifact.inputs` with the
record versions it saw, which is a stronger answer than a column here could give.

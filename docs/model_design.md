# Canonical Patient Data Model — Design

Status: locked for implementation.
Scope: the canonical layer. Covers D1 (model), the reasoning behind D2, D4
(provenance and auditability) and D5 (validation) at design level, and the
constraints D6 (AI governance) builds on.

This document does not specify the source layer beyond the interface canonical
depends on. It specifies what the AI layer must record about a generation (§10),
but not its prompting or orchestration.

Field-level detail is given where a decision was made. Where no decision was
required, fields are settled during implementation rather than invented here.

---

## 1. Three layers

**Founding rule: AI never writes to the canonical layer.**

| Layer | Contents | Mutability |
|---|---|---|
| Source | `SourceDocument` — the PDF, spreadsheet, EMR export, message, as received, with a content hash and storage pointer | Immutable |
| Canonical | Accepted clinical fact. 21 entities (§4). Every value is vouched for by an identifiable actor | Versioned, never hard-deleted |
| AI | `AIArtifact`, `AISummary`, `ExtractionCandidate`, `ReviewDecision` | Own lifecycle |

The AI layer references canonical by `id` + `version`. Canonical never
references the AI layer.

The reason is not output quality. Once written, an AI-produced value is
indistinguishable from a physician-entered one: there is nothing to roll back
to and nothing to show in an audit.

**Consequence that shapes everything below.** If AI never writes to canonical,
then canonical cannot contain unreviewed AI content. A pending extraction is an
`ExtractionCandidate` in the AI layer. When a human accepts it, a canonical
record comes into existence with `provenance.origin = ai_extraction` — crediting
the extraction — and `provenance.asserted_by` set to the accepting human. There
is no "pending" state inside canonical. §6.1 follows from this.

---

## 2. Shared fields — three tiers

Not every entity is patient-scoped, and not every patient-scoped entity belongs
to an encounter. A single universal base would give nine of twenty-one entities
a nullable field that is never set.

Three tiers. The class an entity inherits from states what kind of data it is.

### 2.1 `CanonicalRecord`

| Field | Type | Req | Notes |
|---|---|---|---|
| `id` | prefixed ULID | ✅ | `cond_01J8…` — see §8 |
| `provenance` | `Provenance` | ✅ | Embedded, 1:1 |
| `field_provenance` | `dict[str, Provenance]` | ⬜ | Per-entity whitelist only — §6.2 |
| `record_status` | `active \| superseded \| entered_in_error` | ✅ | No `deleted` value |
| `version` | `int` | ✅ | Monotonic per record |
| `superseded_by` | `ULID \| None` | ⬜ | Deduplication chain |
| `created_at` | `datetime` (tz-aware) | ✅ | |
| `updated_at` | `datetime` (tz-aware) | ✅ | |
| `updated_by` | `Actor` | ✅ | Discriminated union, not a string |

`Actor` = `human | system | pipeline | agent`.

`record_status` has no `deleted` value by design. Clinical data is not deleted —
an erroneous record stays as `entered_in_error`. Otherwise the reason a
physician prescribed something disappears from the record while the
prescription remains.

Applies to: **Patient, Provider, AuditEvent, DataQualityFlag.**

### 2.2 `PatientScoped(CanonicalRecord)`

Adds `patient_id: ULID` — required.

Applies to: **Encounter, Consent, Coverage, Goal, SourceReference.**

### 2.3 `ClinicalRecord(PatientScoped)`

Adds `encounter_id: ULID | None`.

Applies to: **Condition, Medication, Supplement, LabResult, VitalSign,
ClinicalNote, TreatmentPlan, Procedure, DiagnosticReport, AllergyIntolerance,
Task, SocialFactor.**

### 2.4 Tier placements that are not obvious

- **`Patient` is not `PatientScoped`.** Its own `id` is the scope.
- **`Provider` is not `PatientScoped`.** It is practice reference data. This has
  a governance consequence, not just a tidiness one: a provider record is not
  covered by any patient's consent scope and is not included in a patient data
  export.
- **`Encounter` is `PatientScoped`, not `ClinicalRecord`.** It *is* the
  encounter; it does not reference itself.
- **`Goal` is `PatientScoped`.** A patient goal can exist before any treatment
  plan and before any visit.
- **`AuditEvent` and `DataQualityFlag` carry `patient_id: ULID | None`** as a
  denormalized query key — per-patient review queue, patient audit export — and
  not as ownership. They must be able to target a `Provider` record, which has
  no patient.

There is no `review_status` on any tier. See §6.1.

---

## 3. Value objects and derived models

**Embedded value objects** (no independent identity, always read with their
owner): `Provenance`, `Actor`, `Quantity`, `CodeableConcept`, `ReferenceRange`,
`Dosage`, `HumanName`, `PatientIdentifier`, `ContactPoint`, `Address`,
`Preferences`, `PlanItem`, `FlagSummary`, `ClinicalText`.

**Derived read-models, not stored**: `TimelineEvent`, `PreVisitBrief`,
`MedicationReconciliationView`, lab trend series. See §6.13, §9.4 and §9.5.

§10 defines further types that are never persisted either: `AIReadScope`
(§10.3) and the projection shapes `AIPatientView` and `PatientHeader` (§10.4).

---

## 4. Entities

Twenty-one entities. Every one has a requirement behind it; D7's list of twelve
is a floor, not a ceiling. What is managed is depth, not count, and the split is
by risk.

**Full depth (16)** — a modelling mistake here reaches a patient:
Patient, Encounter, Condition, Medication, Supplement, LabResult, ClinicalNote,
TreatmentPlan, SourceReference, AuditEvent, DataQualityFlag, AllergyIntolerance,
VitalSign, Consent, Provider, DiagnosticReport.

**Thin, 4–6 fields (5)** — administrative; Phase 1 proves the dimension is
modelled and can be deepened later: Coverage, Procedure, Goal, SocialFactor,
Task.

| Entity | Tier | Embedded within it | Note |
|---|---|---|---|
| `Patient` | Canonical | `identifiers[]`, `names[]`, `contacts[]`, `addresses[]`, `preferences`, care-team memberships | Identifiers are a list — §6.12. Contacts embedded: read with the patient 100% of the time, never queried alone. The AI projection carries no identity — §10.4 |
| `Provider` | Canonical | `name`, `identifiers[]` | Referenced as prescriber, note author, lab orderer. A free-text name produces spelling drift and makes "all meds from Dr X" unanswerable |
| `Consent` | PatientScoped | `scope`, validity window, `revoked_at`, `revoked_by` | An enforcement point, not documentation — §6.11. Enforced as a capability — §10.3 |
| `Coverage` | PatientScoped | payer, member id, effective dates | Thin. Concierge practices commonly bill labs and procedures through insurance even when membership is self-pay |
| `Encounter` | PatientScoped | type, period, participants | Grouping anchor for the pre-visit brief |
| `Condition` | Clinical | `code: CodeableConcept`, `clinical_status`, `verification_status`, onset, abatement | Merges history and current diagnoses — §6.4 |
| `AllergyIntolerance` | Clinical | substance, reactions[], `criticality`, `severity`, `verification_status` | Never embedded on Patient. The most safety-critical list in the model needs its own audit trail. `criticality` (is it life-threatening) is separate from the `severity` of a past reaction |
| `Medication` | Clinical | `dosage: Dosage`, status, prescriber, start/stop | Split from Supplement — §6.7 |
| `Supplement` | Clinical | dose as reported, status, start/stop | Almost always patient-reported |
| `DiagnosticReport` | Clinical | `findings: ClinicalText`, `impression: ClinicalText`, results[] refs | Groups a panel or an imaging study — §6.8. Text origin — §10.1 |
| `LabResult` | Clinical | `quantity`, `coded_value`, `reference_range`, specimen, performing lab | Two parallel value slots — §6.9 |
| `VitalSign` | Clinical | `quantity`, `measurement_context` | `clinical \| patient_reported \| device` — §6.6 |
| `Procedure` | Clinical | code, performed date, performer | Thin |
| `ClinicalNote` | Clinical | `note_type`, author, `body: ClinicalText`, signed_at, `addenda[]` | Facts mentioned in prose do not live here — §6.14. Text origin — §10.1 |
| `TreatmentPlan` | Clinical | `plan_items[]` | Items embedded: no independent lifecycle, revised as part of the plan. Each item may reference a Condition or Medication by id |
| `Goal` | PatientScoped | description, target date, status | Patient-owned, outlives any single plan |
| `SocialFactor` | Clinical | factor code, value, asserted_at | Normalized records, not a block on Patient — §6.16 |
| `Task` | Clinical | status, assignee, due, origin | AI-extracted tasks land `proposed`, never `open` and assigned |
| `SourceReference` | PatientScoped | document ref, page, `field_path`, span, `quote` | The single citation primitive — §6.17 |
| `DataQualityFlag` | Canonical | `code`, `severity`, `targets[]`, `candidates[]`, lifecycle | An entity, not an embedded list — §6.5 |
| `AuditEvent` | Canonical | actor, action, `trace_id`, `targets`, `fields_read`, field delta | Append-only. Logs reads as well as writes, correlated by `trace_id` — §6.3 |

---

## 5. What is normalized and what is embedded

The test applied throughout: **does this thing have an independent lifecycle, or
is it ever queried without its owner?** If yes to either, normalize.

| Embedded | Why |
|---|---|
| `Provenance` | 1:1 with its record, meaningless without it |
| Contacts, addresses, names | Read with the patient every time, never queried alone |
| `plan_items` in `TreatmentPlan` | Revised as part of the plan, no independent lifecycle |
| `reactions` in `AllergyIntolerance` | Describe one allergy, not reusable |
| `ClinicalText` | Travels with the text so the origin marker cannot be left behind — §10.1 |

| Normalized | Why |
|---|---|
| `SourceReference` | One lab PDF supports forty lab results. Embedding kills "show me everything from this report" and multiplies storage |
| `DataQualityFlag` | §6.5 — three separate reasons |
| `Consent` | §6.11 — queried independently as a gate |
| `Provider` | Referenced from three entities; free text drifts |
| `SocialFactor` | §6.16 — needs history |
| `LabResult` under `DiagnosticReport` | §6.8 |

---

## 6. Decisions and reasoning

### 6.1 No `review_status` in canonical — and the direct answer to D4

D4 lists "Human review status" among what the model must track. There is no
such field on any canonical entity. This is deliberate, and because someone
walking the D4 list will otherwise read it as a dropped requirement, the
reasoning and the replacement are stated here in full.

**Why a per-entity field was rejected.** The first instinct is to narrow it to
entities whose `provenance.origin` can be `ai_extraction`. That narrows nothing:
`Patient` can be extracted from an intake spreadsheet, `Provider` from an
outside specialist named in a note, `Consent` from a scanned PDF, `Coverage`
from a photographed insurance card. Eighteen of twenty-one qualify, and all
twenty-one can have a non-human origin.

**Why the axis was wrong.** Review is not an AI concept. A lab result arriving
from an EMR export with no unit needs review and no AI touched it.

**Why the field contradicts the founding rule.** Per §1, AI never writes to
canonical, so canonical cannot by construction hold unreviewed AI content.
`review_status = pending` inside a canonical record contradicts the rule the
whole model is built on.

**Where the D4 capabilities live.**

| D4 requirement | Location |
|---|---|
| Human review status | **Derived**: open `DataQualityFlag` records targeting this record. No open `blocking` flags ⇒ fit for autonomous consumption |
| Who or what changed the record | `AuditEvent.actor` — `human \| system \| pipeline \| agent` |
| Whether a field came from a human, source system, or AI extraction | `provenance.origin` |
| Who vouched for the value | `provenance.asserted_by` — for an accepted extraction this is the human who accepted it, not the pipeline |
| When it was accepted, and from which candidate | `AuditEvent` acceptance events, referencing the `ExtractionCandidate` |
| Confidence level if AI extraction was used | `provenance.extraction_confidence` |
| Source system / document / field / import date | `provenance.source_refs` → `SourceReference` → `SourceDocument`; `provenance.imported_at` |
| Date last updated | `updated_at` |
| Version history | `version` plus the `AuditEvent` chain carrying field deltas |

**Why derived is more reliable than stored.** A stored review flag diverges from
reality the moment a flag is resolved and the field is not updated with it.
Trustworthiness is a function of outstanding problems, so it is computed from
them rather than cached beside them.

### 6.2 Provenance: record-level, plus a per-entity whitelist

A medication assembled from an EMR export (drug, dose) and an intake form (the
patient says they stopped it) has two origins. Record-level provenance alone
loses that; a full per-field map triples record size for fields nobody disputes.

`provenance` describes the record. `field_provenance` overrides it for a
**closed, per-entity whitelist** of fields — not "wherever it differs", because
a vague rule grows the map to twenty fields within a week.

| Entity | Whitelist |
|---|---|
| `Medication`, `Supplement` | `dose`, `status` |
| `LabResult`, `VitalSign` | `quantity` |
| `Condition` | `clinical_status` |

Keys are top-level field names, not paths: the whitelisted key for a lab is
`quantity`, not `quantity.value`, because the value and its unit arrive from one
source together and are disputed together (§6.9).

Declared per entity class, not globally: a global list of four names would leave
`Condition` with none, and `clinical_status` is exactly where conditions
conflict — "resolved" in the EMR against "active" in the intake form.

The whitelist does not grow by default. `reported_interpretation` (§6.9) was
considered and rejected as its first candidate: two lab reports disagreeing on
`H` against `N` for the same draw is a `DUPLICATE_CANDIDATE` flag, not a
field-level provenance conflict.

Consumers read `field_provenance.get(f) or provenance`. One helper.

**Rejected: an assertion-based model** where every clinical fact is an assertion
with its own provenance and canonical is the currently-accepted assertion. More
correct, but it is a different database, and reading any field becomes a join.

### 6.3 Provenance is not audit

Conflating these is the most common failure in models of this kind.

- **Provenance is a property of a value.** "This dose came from the EMR export
  of 12 March, field `rx_dose`."
- **`AuditEvent` is a stream of events over a record.** "Coordinator X changed
  the status at 14:05." "Agent Y read this patient."

`AuditEvent` logs **reads**, not only writes. Without read events there is no
way to reconstruct what an agent saw when it produced a summary, which for local
inference is the only way to reproduce a result after the fact.

An uncorrelated read log does not deliver that. One brief reads forty records,
and forty unlinked events say that something touched them without saying which
operation did. Such a log carries the full cost of read auditing and answers
nothing. The real choice is therefore between correlating reads and not logging
them at all — the second being the honest form of dropping this capability. It is
rejected.

**Shape for read events:**

| Field | Purpose |
|---|---|
| `trace_id: ULID` | The unit of work, not a record: one brief generation, one extraction run, one agent turn. `AIArtifact` carries the same `trace_id`, which is what makes the join possible. An operation that produced nothing still has a trace, and those are the ones worth investigating |
| `targets: list[ULID]` | Read events batch by `(trace_id, entity_type)`. Write events keep a single target |
| `fields_read: list[str] \| None` | Which fields of those records entered the context |

**`fields_read` is trustworthy only for reads that pass through a projection
layer that records it.** If a caller runs `model_dump()` and puts the result in a
prompt, this field lies — and a lying audit field is exactly the defect this
section exists to remove. So `None` is legal and means *unknown; assume the whole
record was read*. It is never an empty list standing in for "nothing". Assembling
context for a model is required to go through the recording path. The same
discipline as `field_provenance.get(f) or provenance` in §6.2.

**Why reads batch and writes do not.** One brief is forty-odd read events;
batching by entity type collapses that to roughly eight. The asymmetry inside a
single entity is not elegant, and it loses nothing — the question an incident
asks is "what was in context", which a batch answers as well as forty rows with
millisecond timestamps. For a local deployment with no log store, a fivefold
reduction outweighs symmetry.

**Retention is separate for reads.** §6.15 reconstructs state as of a date by
replaying audit deltas, and only **write** events carry deltas. Read events can
therefore be truncated on their own schedule without touching the versioning
story. Write events cannot.

**What this promises, precisely.** With `trace_id` alone: which records were in
context for a given generation. With `fields_read` populated: which fields. The
second is best-effort by construction, and `None` says so rather than implying a
precision that is not there. Sequencing is in §11, step 4.

### 6.4 `Condition` merges medical history and current diagnoses

The assignment lists them separately. They differ by exactly one field,
`clinical_status` (`active | recurrence | remission | resolved`). Two entities
means the same diabetes exists as a history row and a current row, and they
diverge at the first update.

`verification_status` (`confirmed | provisional | differential | refuted |
unconfirmed`) is separate from and independent of `clinical_status`. Without it,
"suspected lupus" enters an AI summary as "has lupus". It is the cheapest
safeguard in the model against its most expensive error.

### 6.5 `DataQualityFlag` is an entity, and its `code` is a closed enum

Three reasons not to embed `quality_flags: list[...]` in the base:

1. **The review queue is a cross-patient query.** Embedded flags mean scanning
   every patient object to build a work queue.
2. **A conflict exists between two records, not inside one.** "EMR says 500 mg,
   intake says 1000 mg" is one flag with two targets. An embedded flag cannot
   express that without being duplicated into both records and kept in sync on
   close.
3. **It has its own lifecycle.** `open → in_review → resolved → wont_fix`,
   independent of the record's `version`. Embedded, every review action bumps
   the version of a clinical fact and buries the change history in review noise.

Shape: `targets: list[(entity_type, entity_id, field_path)]`,
`candidates: list[SourceReference]`, `severity`, `code`, lifecycle status.

`code` is a **closed enum, never free text**, because under §6.9 and §9.1 it is
the only carrier of *why* a value is absent, and consumers branch on it:
`CONFLICTING_VALUES`, `MISSING_UNIT`, `MISSING_REFERENCE_RANGE`,
`UNIT_MISMATCH`, `INTERPRETATION_DISAGREES_WITH_RANGE`, `EXTRACTION_FAILED`,
`DISCONTINUED_SHOWN_ACTIVE`, `DUPLICATE_CANDIDATE`, `UNCODED_CONCEPT`.

`candidates` is what makes a conflict actionable: it lets the UI say "glucose —
conflict between EMR 5.5 and lab 7.2, unresolved" rather than merely reporting
that something is wrong.

### 6.6 Labs and vitals stay separate

FHIR would merge both into `Observation`. Not done here:

- **Validation severities genuinely differ.** A lab without a unit is a layer-2
  flag; a blood pressure without a cuff size is an acceptable missing value. D5
  requires classifying violations by severity, and merging forces the validator
  to branch on category to do it.
- **The fields differ sharply.** A lab carries specimen, performing lab,
  lab-specific reference range, ordering provider, report reference. A vital
  carries body position and measurement context. Merged, half the fields are
  nullable.

Shared instead: the `Quantity` value object and a trend read-model.

**Wearable and patient-reported measurements go into `VitalSign`**, not a
separate entity, with a required `measurement_context:
clinical | patient_reported | device`. Hard rule: trend analysis must be able to
filter on it. Home weight and in-clinic weight are never silently averaged.

### 6.7 `Medication` and `Supplement` stay separate

The axis is **trust presumption**, not field overlap. A drug was asserted by a
prescriber; a supplement is self-reported. Beyond that, a supplement has no
prescriber, no reliable numeric dose (drops, scoops, "one dropper"), usually no
RxNorm code, and interaction checking against it uses a different knowledge
base.

Merged into one entity with a `kind` discriminator, every consumer and the
validator branch on `kind` anyway.

Accepted cost: interaction checking reads two entities instead of one. An extra
query, not an architectural problem.

### 6.8 `DiagnosticReport` sits above `LabResult`

Not in D7's required list; added. Without it a fourteen-analyte panel is
fourteen orphan rows and there is nothing to cite when a physician says "the CBC
from 12 March". The report also carries the lab's own interpretation and one
`SourceReference` to the document.

Imaging is the same entity with `findings` and `impression` and no discrete
values. No separate imaging entity is needed.

### 6.9 `LabResult` value: two parallel slots

```
quantity:     Quantity | None
coded_value:  CodeableConcept | None    # positive, negative, trace
```

At most one populated; a `model_validator` enforces it. Three legal states —
`quantity` only, `coded_value` only, neither (the value is absent and a flag
carries the reason). One illegal state: both.

**Why not a union.** A non-discriminated union of two models validates by order
and breaks on ambiguity; making it discriminated requires a literal tag field on
*both* value objects. `CodeableConcept` is used by Condition,
AllergyIntolerance, Procedure and Medication; `Quantity` by VitalSign. Tagging
two shared objects to serve one union in `LabResult` is the tail wagging the
dog.

Accepted cost: the illegal both-populated state exists in the type and is
excluded by a validator rather than by structure. One validator, one test, and
it fails loudly.

**`Quantity` shape:**

```
value:       float                              # required inside Quantity
unit:        str | None                         # None = D5 "missing unit"
ucum_code:   str | None
comparator:  Literal["<", ">", "<=", ">="] | None
```

`value` is required *inside* `Quantity`, so the nonsense state "unit present,
value absent" is unrepresentable, and consumers make one `None` check rather
than two. `quantity is not None` implies a value exists.

`comparator` carries limit-of-detection results — `TSH <0.01`, `hs-CRP <0.3` —
which are neither coded values nor plain numbers. It makes a value an interval
rather than a point, which changes both range comparison (§9.5) and trend
arithmetic (§9.4): `<0.01` cannot be averaged as `0.01`, and it cannot be
compared to a reference range as though it were a measured `0.01`.

**`reported_interpretation`.** The lab's own abnormal flag — `H`, `L`, `HH`, `A`
— stored as a `CodeableConcept` rather than as a new enum, so `raw_text` is
required, the code is optional, and §6.10 applies unchanged: the token the lab
sent is never overwritten by a normalised code. It is independent of the
exclusivity above — a result can carry both a quantity and the lab's reading of
it.

Why store it when interpretation is derived (§9.5): the lab vouched for its `H`.
That is a source fact, and replacing it with our own computation is no better
than letting AI rewrite canonical (§1).

Known gap: a result that is both coded and numeric ("Positive, titer 1:160") is
not representable under either design. If it appears, exclusivity relaxes from
"at most one" to "at least one" without restructuring.

### 6.10 `CodeableConcept.raw_text` is required, the code is optional

Requiring ICD-10 / RxNorm / LOINC / UCUM at ingestion is unrealistic: an intake
spreadsheet arrives with "high bp" as a string. So `raw_text` is always
required, `system` + `code` are optional, and a missing code raises a flag of
severity *human review required* rather than rejecting the record.

The original string is **never** overwritten by the code. Otherwise there is no
way to check whether the coding was correct.

### 6.11 `Consent` is an enforcement point, not documentation

A separate entity rather than a field on `Patient`.
`scope: treatment | ai_processing | data_sharing | research | family_access`
plus a validity window.

It is the gate for the entire AI layer. How that gate is *enforced*, rather than
merely intended, is §10.3. Embedded on `Patient`, revocation would bump the patient
version, and "whose AI-processing consent expires this month" becomes unanswerable.

Revocation is distinct from expiry, and distinct again from `record_status =
superseded`, which means replaced by a newer version. A patient who withdrew
consent and a consent that simply lapsed must be told apart in the audit trail, so
`Consent` carries `revoked_at` and `revoked_by`.

### 6.12 `Patient.identifiers` is a list, not `mrn: str`

A concierge practice pulls from several EMRs and one patient has several MRNs. A
single `mrn` field is the primary cause of duplicate patient records. Each
`PatientIdentifier` carries `system`, `value`, `assigner`.

### 6.13 The timeline is derived, never stored

`TimelineEvent` is a projection over `Encounter`, `Condition.onset/abatement`,
`Medication.start/stop`, `LabResult`, `Procedure` and `ClinicalNote`. Stored, it
becomes a second source of truth that goes stale the moment any entity changes,
and nothing will detect the divergence.

Implemented as a Pydantic model with no persistence plus a builder. The
assignment's "Timeline of clinical events" requirement is met as a read-model,
deliberately.

### 6.14 Canonical entities carry no AI fields

No `ai_summary: str` on `Patient`, no `ai_confidence` anywhere. The reference is
one-way: `AIArtifact` points at canonical by `id` + `version`. The naive design
puts the summary on the patient, and a week later nobody can tell a physician
did not write it.

The one AI-adjacent marker is `provenance.origin == ai_extraction` on facts that
originated from extraction — recording *where the structure came from*, after a
human accepted it.

**Consequence for `ClinicalNote`.** A fact mentioned in a note's prose does not
live in the note. It becomes a `Condition` whose provenance records
`ai_extraction` with `source_refs` pointing at the span in the note, and it
enters canonical only when a human accepts it. This boundary is what the
assignment is testing.

### 6.15 Versioning: current state plus audit delta

Canonical holds current state and a monotonic `version`. Every change writes an
`AuditEvent` carrying the before/after of changed fields.

Full row versioning is a temporal database, which is not what Phase 1 asks for.
State as of a date is reconstructed by replaying audit deltas — slow, and out of
scope here.

### 6.16 `SocialFactor` is a record, not a block on `Patient`

Smoking, alcohol, exercise, diet, occupation, stress, sleep, living situation.
These change, and staleness is the whole risk — "smoker" recorded in 2019 and
never revisited. Records with `asserted_at` and a status give a timeline; an
embedded block gives one mutable blob with no history.

### 6.17 `SourceDocument` is source-layer, `SourceReference` is canonical

The document — blob, hash, storage pointer — stays in the source layer.
`SourceReference` is the canonical-layer pointer into it: document id, page,
`field_path`, extraction span, `quote`. This keeps canonical free of blob
concerns and makes `SourceReference` the single citation primitive AI must emit.

### 6.18 FHIR is borrowed from, not adopted

FHIR's decomposition is taken where it is battle-tested —
`AllergyIntolerance` as its own entity, `verification_status` separate from
clinical status, `DiagnosticReport` above results. Its wire format is not: FHIR
does not carry provenance the way this model needs, and its
`Reference`/`extension` machinery makes local validation heavy.

---

## 7. Deliberately out of scope

- **A high-frequency wearable stream entity.** Time series belong in the source
  layer with aggregates promoted to `VitalSign`. Not Phase 1.
- **`PatientLink` / merge candidates.** Belongs to the optional normalization
  build, not the base model.
- **A result that is both coded and numeric** — "Positive, titer 1:160". Not
  representable under the two-slot design (§6.9). Named here rather than left to
  be discovered: the way out, if it appears, is to relax exclusivity from "at
  most one populated" to "at least one", which is a validator change and not a
  restructuring.
- **Detecting transcribed external text.** `transcribed_external` (§10.1) cannot
  be established from the data: a physician who pasted text is indistinguishable
  from one who typed it. It can only be declared by the author, and a declaration
  in a UI will be skipped. Phase 1 makes the bulk case explicit and names this
  residue rather than claiming to cover it.
- **A canonical carrier for `patient_submitted`** — §10.1 wraps four narrative
  fields, and patient-authored free text such as `Goal.description` is not among
  them.
- **General access control.** §10.3 gates the AI read path only. Staff access,
  role permissions and break-glass are Phase 1 boundaries, resting on
  authentication and the audit trail of §6.3.
- **Revocation arriving mid-inference** — §10.3. Bounded by `valid_until` and a
  re-check at artifact construction, not guaranteed.
- **Unit conversion inside trends** — §9.4. Mismatched units are excluded with a
  visible reason rather than converted.
- **FHIR as a wire format** — §6.18.
- **Temporal queries** — §6.15.

---

## 8. Identifiers

Prefixed ULIDs: `cond_01J8…`, `med_01J8…`, `lab_01J8…`.

The prefix is not cosmetic. In logs, prompts and AI citations a bare UUID cannot
be attributed to an entity, and `med_` against `supp_` catches a type
substitution before validation runs. ULID sorts by time and generates locally
without a database round trip, which matters for offline inference.

(UUIDv7 gives the same time ordering with a native database type. ULID is kept
because ids here are strings in JSON and Pydantic anyway, and Crockford base32
is shorter and has no ambiguous characters. Swapping is one generator.)

### 8.1 Registry ownership

One module declares `EntityKind`: a mapping of `prefix → model class`, the
single source of truth. Not a table in the docs and not a convention. Two
assertions, run at import and in tests: every canonical model is registered, and
prefixes are unique. Discipline becomes a failing test.

### 8.2 Prefixes are allocated once, never reused, never migrated

If `Medication` is renamed to `MedicationStatement`, existing `med_` ids stay and
the registry rebinds the old prefix to the new class. `med_` outlives
`Medication`.

The prefix is part of an immutable identifier that has already left the system:
into `AuditEvent` records, `SourceReference` records, AI summary citations, and
potentially a signed document a physician read and acted on. Migrating `med_` to
`medstmt_` invalidates every citation the system has ever emitted — precisely
the failure provenance exists to prevent.

### 8.3 The prefix is a readability affordance, not a type check

A hand-forged `cond_` prefix on a medication id passes any string check.
Validation resolves the id through the registry and against the actual target;
the prefix remains a hint for humans, logs and citations. Two lines of code,
without which the prefix gives a false sense of safety.

### 8.4 Sequencing

The registry comes **after** the sixteen full-depth entities. Shipping without
the registry is preferable to shipping without half the model.

So: a thin `new_id(prefix: str) -> str` exists from the start, with the prefix
passed as a literal at call sites. The registry later replaces those literals
with `EntityKind` lookups and adds the assertions and id resolution. The registry
is then a pure refactor rather than a missing dependency — step 1 can create a
`Patient` without it.

---

## 9. Validation (D5)

### 9.1 Two layers

D5's list mixes two mechanisms. Separating them explicitly:

| Layer | Mechanism | Outcome | Example from D5 |
|---|---|---|---|
| 1. Structural invariants | Pydantic validation | The record is never created. It stays in the source layer and the flag attaches to the **document** | "Patient must have a durable patient identifier" |
| 2. Data quality | `DataQualityFlag` | The record exists in canonical, marked and visible | "Missing units must trigger review" |

**Severity semantics.** `blocking` is the top severity *within layer 2*, and it
must be defined precisely, because the natural reading — "the record fails
validation and does not enter the system" — would contradict §9.3:

> **`blocking` does not block persistence. It blocks autonomous conclusion.**
> The record exists in canonical, is readable and citable; but no read-model and
> no agent may use it to make an assertion without surfacing the flag.

Full taxonomy, mapped to D5's four classes:

| Class | Meaning | Example |
|---|---|---|
| Blocking error | Record exists, unusable for autonomous conclusion, flag must be surfaced | Unresolved value conflict |
| Human review required | Usable with the caveat attached; a human should look | Missing code on a `CodeableConcept`; missing unit |
| Warning | Usable; recorded for data-hygiene reporting | Missing reference range on a common analyte |
| Acceptable missing value | Not a defect | Blood pressure without cuff size |

### 9.2 The D5 lab rule sits across both layers

D5 states: *"Lab value must include biomarker name, value, unit, and collection
date."* Under the invariant in §9.3 this does not survive as a single blocking
check, and it is set out here rather than as a table row because someone walking
the D5 list item by item should not read it as a dropped requirement.

The rule splits. `biomarker.raw_text` and `collection_date` are **layer 1**: a
measurement with no analyte name is not a lab result, and one with no date
cannot be placed on a timeline or trended, so it has no canonical meaning. Both
are rejected at the boundary and the flag attaches to the source document.
`quantity.value` and `quantity.unit` are **layer 2**: the record is created, the
field is empty or partial, and a flag carries the reason.

The argument for the split is D5's own. It asks for violations to be *classified*
by severity, and it classifies this one itself — "Missing units must trigger
review" says review, not reject. A rule that rejected the record instead would
make the lab invisible in canonical: present in the source layer, absent from
every brief and every trend, and unseen by the person who has to resolve it.
That is the outcome D5's "conflicting records must be flagged, not silently
overwritten" exists to prevent, reached by a different mechanism.

### 9.3 The invariant

> **Canonical never holds a value nobody vouched for.**

This is the invariant, not "canonical is always complete". An empty field with an
open blocking flag satisfies it. A silently picked winner does not.

Applied to an unresolved conflict: canonical takes the value from the
higher-trust source if an explicit source-trust rule decides it; otherwise the
field **stays empty** and a `blocking` flag with
`code = CONFLICTING_VALUES` points at both candidates. The physician sees
"glucose — conflict between EMR 5.5 and lab 7.2, unresolved" rather than nothing
at all.

The accepted cost is that `quantity` is `Quantity | None` and every consumer
handles `None`. That is preferable to a lab result disappearing from a pre-visit
brief.

The invariant also forbids **automatic selection by recency**. "Take the newer
source" is a heuristic, not a vouching. If a tie is not resolved by a human or
by an explicit source-trust rule, the value stays empty. This is stated because
"take the newer one" is the first thing anyone proposes, including an AI.

### 9.4 Read-models must surface blocking flags — as a type, not a convention

Any read-model consuming canonical — pre-visit brief, timeline, trend analysis —
must surface open blocking flags rather than skipping incomplete records. A
brief that quietly drops a flagged lab reintroduces exactly the invisibility
§9.3 avoids.

As a sentence in a document this survives until the first refactor, so it is
structural instead. Every read-model carries a **required** field:

```
PreVisitBrief:
    ...
    unresolved: list[FlagSummary]      # required, no default
```

A brief that dropped a flagged lab cannot be constructed — the field must be
filled deliberately. Plus one test: for any patient with an open blocking flag,
the brief mentions it. The convention becomes a failing test.

The same requirement applied to a lab trend, where the temptation is to drop
points rather than whole records:

```
LabTrend:
    analyte:       CodeableConcept
    series:        list[TrendPoint]      # every point, in order, comparator kept
    numeric_basis: list[ULID]            # which of them fed the arithmetic
    excluded:      list[ExcludedPoint]   # required, no default
    direction:     rising | falling | flat | indeterminate
    unresolved:    list[FlagSummary]     # required
```

A point with a comparator is excluded from the **arithmetic**, not from the
**series**. `TSH <0.01` on three consecutive draws is clinically meaningful —
consistently suppressed — and dropping it loses real signal. The physician sees
`<0.01, <0.01, <0.01` on the chart while the trend arrow abstains.

`ExcludedPoint` carries the result id, the date, the value as it arrived, and a
reason from a closed enum: `LIMIT_OF_DETECTION`, `NO_VALUE` (§9.3),
`CODED_RESULT`, `UNIT_MISMATCH`, `PATIENT_REPORTED`.

`UNIT_MISMATCH` is deliberate. A trend that quietly adds 5.5 mmol/L to 99 mg/dL
is the exact failure this model exists to prevent. Converting requires UCUM plus
a conversion table, which is real scope; for Phase 1, excluding with a visible
reason is the honest option.

**No tuned thresholds.** `direction` is `indeterminate` when and only when
`len(numeric_basis) < 2` — not a chosen number, but the minimum at which a
direction exists at all. Whether an arrow can be trusted when half the points
were excluded is a clinical judgement, not a schema rule. This is stated
explicitly so that nobody later inserts `0.5`.

### 9.5 Derived interpretation: a comparator is an interval, not a defect

Whether a result is low, normal or high is **derived**, not stored. A
`comparator` (§6.9) turns the value into a half-open interval, and the comparison
against a reference range is decidable only when that interval lies entirely on
one side of the boundary.

| `comparator` | Condition | Result |
|---|---|---|
| none | ordinary comparison | `low \| normal \| high` |
| `<x` | `x <= range.low` | `low` |
| `<x` | `range.low` is 0 or absent, and `x <= range.high` | `normal` |
| `>x` | `x >= range.high` | `high` |
| any | the interval crosses a boundary | `indeterminate` |

Worked through:

- `TSH <0.01`, range 0.4–4.0 → `0.01 <= 0.4` → **`low`**. Strictly sound:
  anything below 0.01 is below 0.4.
- `hs-CRP <0.3`, range 0–3.0 → the lower bound is 0 and `0.3 <= 3.0` →
  **`normal`**. Without that row this returns `indeterminate` and floods the
  output with results a physician reads as plainly normal.
- `>100` against an upper bound of 150 → the true value lies in `(100, ∞)`, which
  crosses 150 → **`indeterminate`**.

**Why `indeterminate` is a value and not a flag.** `>100` against an upper bound
of 150 is not a data defect. The value is correct, it is vouched for, and only
the derived interpretation is unavailable. Raising a `DataQualityFlag` would fill
the review queue with items nobody can resolve, because there is nothing to fix.
Correct data is never flagged. `indeterminate` surfaces through the same
read-model rule as `unresolved` (§9.4).

**Reported against computed.** `LabResult.reported_interpretation` holds what the
lab itself asserted. When it is present, it is what read-models display; the
computed value is then used for exactly two things — filling in when the lab sent
nothing, labelled as computed, and detecting disagreement.

Disagreement between the two *is* a defect:
`INTERPRETATION_DISAGREES_WITH_RANGE`. It almost always means the reference range
stored here is not the one the lab used, which makes every other interpretation
against that range suspect. A computed `indeterminate` alongside a reported value
is not a disagreement.

The lab's assertion is never overwritten by the computed one, for the same reason
AI output never overwrites canonical (§1): the lab vouched for its `H`, and that
is a source fact.

Implementation: one pure function, one test per row of the table above. That is
what keeps the rule out of the intuition of whoever reads the code next.

### 9.6 The rule this gives the AI layer (feeds D6)

An agent **may read** a blocking-flagged record, **must cite the flag**, and may
**neither** assert the value — there is none — **nor** infer it from
surrounding fields.

---

## 10. AI layer and governance

§1 fixes the rule that AI never writes to canonical. This section covers what
follows from it: how text that crossed the practice perimeter is marked, and what
is recorded about a generation.

The second is not only a D6 requirement. D7's required list of twelve objects
includes an "AI-generated summary object", and until this section it was the only
one of the twelve the document described nowhere — correctly absent from §4, which
lists canonical entities, but given no home anywhere else either.

### 10.1 The trust boundary for free text is the perimeter, not the author

Free text reaches a local model verbatim, and text can carry an instruction. What
the model owes is a legible source class for every span of text it hands over.

The boundary is **not** "a physician is trusted, a patient is not". A physician can
paste a patient's message into a note, deliberately or not, and the signature on
the note does not change what the text is. The boundary is whether the text
**crossed the practice perimeter**: text composed inside passes through
authentication, an audit trail and an accountable person, and text from outside
passes through none of them.

**Not derivable from existing fields.** `provenance` describes where the *record*
came from. A note a physician typed is `origin = human`, with an internal document
and their own signature, whatever sits inside the body. Provenance cannot see
inside a string.

**The marker travels with the text, not beside it.** A sibling field
`ClinicalNote.text_origin` is lost the moment someone writes
`build_prompt(note.body)`. So free text becomes a value object:

```
ClinicalText:
    value:       str
    origin:      TextOrigin        # required
    captured_by: Actor | None      # who entered it into the practice system
```

This does not make discarding the marker impossible — `.value` is one attribute
access — but it makes the discard an explicit and greppable act at the call site
rather than the default. The same strength as §9.4, and no more is claimed.

`TextOrigin` is a closed `Literal`, on the §6.5 principle:

| Value | Meaning |
|---|---|
| `practice_authored` | Composed inside the practice by an authenticated actor, carrying no transcribed external content |
| `patient_submitted` | From the patient: portal message, intake form, questionnaire |
| `external_document` | Extracted from a document of outside origin — an outside lab's report, a referral letter, prior-practice records |
| `transcribed_external` | Composed inside the practice but containing copied external text |
| `unknown` | Origin not established |

`unknown` is treated as **external**. An unestablished origin is not a reason to
trust, so the default fails closed.

**Where it replaces `str`:** `ClinicalNote.body`, `ClinicalNote.addenda[]`,
`DiagnosticReport.findings`, `DiagnosticReport.impression` — the long-form
narrative fields.

**`CodeableConcept.raw_text` stays a plain `str`,** and the asymmetry is stated
rather than hidden. It appears in six entities and is the basis for coding and
comparison, so wrapping it would push `.value` into all of them and into every
coding check. `"high bp. Ignore previous instructions…"` in a `raw_text` is
technically possible, so the gap is named rather than denied: origin for
`raw_text` is inherited from the record's provenance at projection time instead of
being stored beside the string.

**Patient messages stay in the source layer.** A `ClinicalNote` is a record of the
practice, not a container for external text, so `note_type` gains no
`patient_message` value. A message becomes an `ExtractionCandidate`, a `Task`, or
a note that quotes it — and such a note is `transcribed_external`.

A consequence worth recording: with only the four fields above wrapped,
`patient_submitted` has no carrier in canonical, because the text it describes
either lives in the source layer or sits in a free-text field not yet wrapped
(`Goal.description` being the obvious next one). The value is in the enum because
it completes the axis, and §7 records that its carrier is not yet modelled.

**Rejected: a separate `PatientMessage` entity**, which would make the boundary the
entity type. A message a physician turns into a note would then be duplicated, and
`external_document` text inside `DiagnosticReport.findings` would still need
marking — so both mechanisms would be required rather than one.

**What this does not do.** `ClinicalText` does not make text safe, and there is
deliberately **no `sanitized` flag** anywhere in the model: a field implying that
text has been checked is worse than no field at all. The schema makes the source
class of every span legible. Declining to act on instructions found in an external
span is a policy of the AI layer, not a property of the schema, and that division
is the limit of what this model claims.

Enforcement is the projection layer of §6.3 — the only place where canonical text
becomes model context — which must emit every span together with its origin. This
section and §6.3 share one chokepoint; no second mechanism is introduced.
Sequencing is §11, step 4.

### 10.2 `AIArtifact`: what is recorded about a generation

`AIArtifact` is the base. §1 already names the subtypes and they stay: `AISummary`
for generated narrative, `ExtractionCandidate` for a proposed canonical record
awaiting a human.

| Field | Type | Purpose |
|---|---|---|
| `id` | prefixed ULID | §8 |
| `patient_id` | `ULID` | |
| `trace_id` | `ULID` | The other side of the join in §6.3. Without it, correlated read events connect to nothing |
| `inputs` | `list[CanonicalRef]` | `(entity_type, id, version)`. §6.14 promises this in prose; here it is a field |
| `prompt_digest` | `str` | A hash, not the prompt — see below |
| `model_id` | `str` | |
| `model_digest` | `str \| None` | `llama-3.3-70b` is not a reproducible identifier: one name covers several quantisations, and incident analysis needs the exact artefact. `None` means the engine reported none, on the §6.3 semantics |
| `engine` | `Literal["ollama", "llama_cpp", "vllm", "transformers"]` | Closed, per §6.5 |
| `engine_version` | `str` | |
| `execution` | `Literal["local"]` | One legal value — see below |
| `consent_ref` | `ULID` | The `Consent` record that authorised this generation (§6.11) |
| `review` | `pending \| accepted \| rejected \| superseded`, with `reviewed_by`, `reviewed_at` | |

**`execution` has one legal value, not two.** `Literal["local", "cloud"]` would let
someone write `"cloud"` and nothing would fail. With a single value a cloud
execution is unrepresentable: the record does not construct.

What makes that hold is not the type. The field can lie — a caller could invoke a
hosted API and record `execution="local"`. It holds because **`AIArtifact` is
constructed by the local-inference adapter itself, and no public path takes
`execution` as an argument.** This is the third invariant in the model resting on a
wrapper rather than on trusting the caller, alongside `fields_read` (§6.3) and
`TextOrigin` (§10.1). One architecture, not three.

**`prompt_digest` stores a hash and not the prompt.** A prompt contains PHI, and
storing it duplicates canonical data outside canonical governance — which is what
§1 exists to prevent. The digest, together with `trace_id` and `inputs`, supports
**reconstruction** of the prompt from canonical instead.

Reconstruction is not a copy, and the difference is worth stating plainly: it holds
only while the records named in `inputs` are unchanged, which is why `inputs`
carries versions and not bare ids. If a record has moved on, the digest proves the
prompt is no longer reproducible rather than quietly reproducing a different one.

**Two loose ends this closes.** §6.1 removed `review_status` from canonical on the
grounds that a pending state belongs to the AI layer; until now the document gave
it nowhere to live, and `review` is that place. §6.3's `trace_id` gets its
counterpart.

### 10.3 The consent gate is a capability, not a convention

§6.11 says three times over that `Consent` is the gate for the AI layer. Saying it
is not enforcing it, and §9.4 already set the standard: a rule that lives in a
sentence survives until the first refactor.

**Why `consent_ref` (§10.2) does not close this.** A required `consent_ref`
guarantees that an artifact *names* a consent, and nothing further — not that the
consent was active, that its scope was right, or that it belonged to this patient.
And it fires too late: an agent that read forty records and then failed the check
has already assembled PHI into a prompt. The leak has happened. Validating at
artifact construction catches the consequence, not the event.

So the gate stands **before the read**, in the one place where canonical data
becomes model context: the projection layer of §6.3.

```
AIReadScope:              # produced only by the consent check
    patient_id:  ULID
    consent_id:  ULID
    scope:       Literal["ai_processing"]
    valid_until: datetime
    trace_id:    ULID
```

Every projection function takes an `AIReadScope`, not a `patient_id`, and no
overload taking a bare `patient_id` exists. "Read a patient's data for a model
without checking consent" is then **unexpressible**: the function cannot be called
without the token, and the token cannot be made except through the check. This is
stronger than §9.4 — there a required field stopped a flag being dropped on the way
out; here the gate stands at the entrance.

`authorize_ai_read(patient_id, now) -> AIReadScope` **raises rather than returning
`None`.** `None` invites `if scope:` and the one caller who omits it; an exception
makes refusal the default path. Fail-closed, the same discipline as treating
`TextOrigin.unknown` as external (§10.1).

`AIReadScope` is **not persisted** — not an entity, not a value object, nothing in
§3's taxonomy. It is a runtime capability. Storing it would make it forgeable and
replayable, which is the opposite of its purpose.

**`consent_ref` is derived, not supplied.** The adapter copies it from the
`AIReadScope` it was handed, so it cannot be set independently of the check. The
same principle as `execution` in §10.2.

**`trace_id` rides on the token.** §6.3 priced threading `trace_id` through the
read paths as a separate cost. Carried on `AIReadScope` it is threaded by the
parameter being added anyway, and the two costs collapse into one.

**This gate does not degrade.** Every other item in §11 step 4 fails honestly when
time runs short: `fields_read` stays `None`, which is a legal value meaning "the
whole record", and ids keep their prefixes without the registry. **An unimplemented
consent gate is not a `None`. It is an open door.** It cannot be dropped the way
the others can.

That is not a deferral risk, and the reason is worth stating: before step 4 there is
no projection layer, so there is no AI read path to guard. The door and its lock are
installed in the same step.

**This is a gate for the AI path only.** A physician reading a chart needs
`treatment` consent, under different rules including break-glass access in an
emergency. **This model does not build general access control** and does not pretend
to: clinical access rests on authentication and on the audit trail of §6.3. That is
a deliberate Phase 1 boundary, not an omission.

**Revocation during a generation.** `valid_until` bounds the window, and the adapter
re-checks before constructing the artifact, which catches the realistic case — a
revocation arriving between the read and the write. A revocation arriving
mid-inference is not caught. That is a limit rather than a guarantee, and §7 records
it.

**Rejected: a check inside each read function** (`if not has_consent(...): raise`).
Rejected for the reason §9.4 rejected a rule in prose — it is a convention that
every new read function must remember, and the one that forgets becomes the leak.
The token moves this from "remember to check" to "cannot be called without having
checked".

### 10.4 What AI may read, write, suggest, and must have approved (D6)

This assembles rules already taken in §1, §6.14, §9.4, §9.6 and §10.1–10.3, plus
two decisions taken here: the audit log is outside AI read scope, and the
projection carries no identity.

| Object | Read | Write | Suggest | Human approval |
|---|---|---|---|---|
| Canonical clinical records — `Condition`, `Medication`, `Supplement`, `LabResult`, `VitalSign`, `AllergyIntolerance`, `DiagnosticReport`, `Procedure`, `TreatmentPlan`, `Goal`, `SocialFactor`, `Encounter`, `ClinicalNote` | Yes, via `AIReadScope`; text spans labelled per §10.1 | **Never** | Via `ExtractionCandidate` | Acceptance into canonical |
| `Patient` — age, sex | Yes, as `AIPatientView` | Never | — | — |
| `Patient` — names, `identifiers`, contacts, addresses, exact date of birth | **No** | Never | — | — |
| `DataQualityFlag` | Yes, and **must be surfaced** per §9.4 | Never | — | — |
| `SourceReference` | Yes, and must be cited | Never | — | — |
| `Provider` | Yes — prescriber, note author, lab orderer | Never | — | — |
| `Consent` | Not read by the agent; consumed by the gate in §10.3 | Never | — | — |
| `Coverage` | **No** — payment context is not clinical | Never | — | — |
| `AuditEvent` | **No** | Never; written by the system | — | — |
| `AIArtifact`, `AISummary` | Yes, including its own prior output | **Yes — the only writable objects** | — | `review` transitions |
| `ExtractionCandidate` | Yes | Yes | This is the suggestion channel | Acceptance into canonical |
| `Task` | Yes | No | `origin = ai_suggested`, `status = proposed` | Assignment |

**The write column has exactly one non-empty row.** That is the shortest statement
of §1.

**The audit log is outside AI read scope.** There is no clinical need for an agent
to reason about who did what, and the trail of every actor who touched a chart is a
wider surface than the chart itself.

**Identity is absent from the projection, and that is a type rather than a policy.**

```
AIPatientView:          # the only patient shape a projection emits
    patient_id: ULID
    age_years:  int
    sex:        ...
```

No names, identifiers, contacts, addresses or exact date of birth. Age replaces
date of birth because dosing and reference ranges need an age, not a birthday.
Since the type has no identity fields, "the model saw the patient's name" is
unexpressible rather than merely discouraged — the same move as `AIReadScope` in
§10.3 and `Literal["local"]` in §10.2.

Why this matters beyond minimisation: `fields_read` (§6.3) exists to measure
exposure. A default projection carrying identifiers makes the measurement
meaningless, because exposure is then maximal on every call.

**The split is shown in the deliverables, not described in them.**

```
PreVisitBrief:                       # deterministic, assembled by the practice
    header:     PatientHeader        # name, MRN, date of birth — for the physician
    ...
    unresolved: list[FlagSummary]    # required, §9.4
    narrative:  AISummary | None     # generated from AIPatientView
```

Identity sits on the deterministic wrapper. The generated narrative is produced
from `AIPatientView` and therefore cannot contain a name it never received. D3's
example record and D8's workflow are to present these as two objects with two
shapes; a sentence saying that the narrative omits identity is a weaker claim than
a type that cannot carry one.

---

## 11. Build order

Dangerous entities first.

1. Base models (`CanonicalRecord`, `PatientScoped`, `ClinicalRecord`), value
   objects, `new_id`, then **Patient, Condition, Medication, LabResult,
   AllergyIntolerance, SourceReference, AuditEvent, DataQualityFlag**
2. **Encounter, Supplement, VitalSign, ClinicalNote, TreatmentPlan,
   DiagnosticReport, Consent, Provider**
3. The thin five: **Coverage, Procedure, Goal, SocialFactor, Task**
4. `EntityKind` registry, uniqueness assertions, id resolution (§8.4);
   `trace_id` plumbing through the read-model builders and the projection layer
   that populates `fields_read` (§6.3), labels every emitted text span with its
   `TextOrigin` (§10.1), emits `AIPatientView` rather than `Patient` (§10.4), and
   admits no caller without an `AIReadScope` (§10.3). The registry and the
   `fields_read` plumbing are refactors over a working model and degrade honestly
   if time runs short: ids keep their prefixes without the registry, and
   `fields_read` stays `None`, a legal value meaning "the whole record". The
   consent gate does not degrade — see §10.3. The `AuditEvent` schema itself is
   built in step 1
5. Documentation

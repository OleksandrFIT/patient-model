# Canonical Patient Data Model — Design

Status: locked for implementation.
Scope: the canonical layer. Covers D1 (model), the reasoning behind D2, D4
(provenance and auditability) and D5 (validation) at design level, and the
constraints D6 (AI governance) builds on.

This document does not specify the source layer beyond the interface canonical
depends on, and does not specify the internals of the AI layer.

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
`Preferences`, `PlanItem`, `FlagSummary`.

**Derived read-models, not stored**: `TimelineEvent`, `PreVisitBrief`,
`MedicationReconciliationView`, lab trend series. See §6.13 and §9.2.

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
| `Patient` | Canonical | `identifiers[]`, `names[]`, `contacts[]`, `addresses[]`, `preferences`, care-team memberships | Identifiers are a list — §6.12. Contacts embedded: read with the patient 100% of the time, never queried alone |
| `Provider` | Canonical | `name`, `identifiers[]` | Referenced as prescriber, note author, lab orderer. A free-text name produces spelling drift and makes "all meds from Dr X" unanswerable |
| `Consent` | PatientScoped | `scope`, validity window | An enforcement point, not documentation — §6.11 |
| `Coverage` | PatientScoped | payer, member id, effective dates | Thin. Concierge practices commonly bill labs and procedures through insurance even when membership is self-pay |
| `Encounter` | PatientScoped | type, period, participants | Grouping anchor for the pre-visit brief |
| `Condition` | Clinical | `code: CodeableConcept`, `clinical_status`, `verification_status`, onset, abatement | Merges history and current diagnoses — §6.4 |
| `AllergyIntolerance` | Clinical | substance, reactions[], `criticality`, `severity`, `verification_status` | Never embedded on Patient. The most safety-critical list in the model needs its own audit trail. `criticality` (is it life-threatening) is separate from the `severity` of a past reaction |
| `Medication` | Clinical | `dosage: Dosage`, status, prescriber, start/stop | Split from Supplement — §6.7 |
| `Supplement` | Clinical | dose as reported, status, start/stop | Almost always patient-reported |
| `DiagnosticReport` | Clinical | `findings`, `impression`, results[] refs | Groups a panel or an imaging study — §6.8 |
| `LabResult` | Clinical | `quantity`, `coded_value`, `reference_range`, specimen, performing lab | Two parallel value slots — §6.9 |
| `VitalSign` | Clinical | `quantity`, `measurement_context` | `clinical \| patient_reported \| device` — §6.6 |
| `Procedure` | Clinical | code, performed date, performer | Thin |
| `ClinicalNote` | Clinical | `note_type`, author, `body`, signed_at, addenda[] | Facts mentioned in prose do not live here — §6.14 |
| `TreatmentPlan` | Clinical | `plan_items[]` | Items embedded: no independent lifecycle, revised as part of the plan. Each item may reference a Condition or Medication by id |
| `Goal` | PatientScoped | description, target date, status | Patient-owned, outlives any single plan |
| `SocialFactor` | Clinical | factor code, value, asserted_at | Normalized records, not a block on Patient — §6.16 |
| `Task` | Clinical | status, assignee, due, origin | AI-extracted tasks land `proposed`, never `open` and assigned |
| `SourceReference` | PatientScoped | document ref, page, `field_path`, span, `quote` | The single citation primitive — §6.17 |
| `DataQualityFlag` | Canonical | `code`, `severity`, `targets[]`, `candidates[]`, lifecycle | An entity, not an embedded list — §6.5 |
| `AuditEvent` | Canonical | actor, action, target, field delta | Append-only. Logs reads as well as writes — §6.3 |

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
way to reconstruct what an agent saw when it produced a summary — which for
local inference is the only way to reproduce a result after the fact.

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
`EXTRACTION_FAILED`, `DISCONTINUED_SHOWN_ACTIVE`,
`DUPLICATE_CANDIDATE`, `UNCODED_CONCEPT`.

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
which are neither coded values nor plain numbers. Trend analysis must be able to
exclude them: `<0.01` cannot be averaged as `0.01`.

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

It is the gate for the entire AI layer: an agent asks "is there active
`ai_processing` consent for this patient" before doing anything. Embedded,
revocation bumps the `Patient` version, and "whose AI-processing consent expires
this month" becomes unanswerable.

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

### 9.5 The rule this gives the AI layer (feeds D6)

An agent **may read** a blocking-flagged record, **must cite the flag**, and may
**neither** assert the value — there is none — **nor** infer it from
surrounding fields.

---

## 10. Build order

Dangerous entities first.

1. Base models (`CanonicalRecord`, `PatientScoped`, `ClinicalRecord`), value
   objects, `new_id`, then **Patient, Condition, Medication, LabResult,
   AllergyIntolerance, SourceReference, AuditEvent, DataQualityFlag**
2. **Encounter, Supplement, VitalSign, ClinicalNote, TreatmentPlan,
   DiagnosticReport, Consent, Provider**
3. The thin five: **Coverage, Procedure, Goal, SocialFactor, Task**
4. `EntityKind` registry, uniqueness assertions, id resolution (§8.4)
5. Documentation

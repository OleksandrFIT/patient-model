# Canonical Patient Data Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the canonical patient data model specified in `docs/model_design.md`, through to a working Physician Pre-Visit Brief (D8) that demonstrates the governance layer enforcing itself.

**Architecture:** Three layers, with a one-way dependency. Source artifacts are immutable; canonical records hold accepted clinical fact and are reached only through typed base tiers; the AI layer reads canonical through a projection that cannot be called without a consent capability, and writes only its own artifacts. Three invariants rest on wrappers rather than on callers remembering: `AIReadScope` gates reads, `AIPatientView` strips identity, and the local-inference adapter is the only constructor of an `AIArtifact`.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, `python-ulid`, ruff.

**Spec:** `docs/model_design.md` (1474 lines). Every task below cites the section it implements. Where this plan and the spec disagree, the spec wins — stop and raise it.

---

## Granularity note

Phases 1 and 5 hold every non-obvious invariant, and are written at full TDD
granularity: one action per step. Phases 2–4 are largely mechanical application of
patterns established in Phase 1, so structurally identical entities are grouped into
one task each — with all their code written out, never "as in Task N".

## Phase map

| Phase | Spec §11 step | Produces |
|---|---|---|
| 1 | 1 | ids, enums, value objects, base tiers, 8 highest-risk entities, provenance invariants, retraction cascade |
| 2 | 2 | 8 remaining full-depth entities |
| 3 | 3 | the thin five |
| 4 | 4 | AI layer schema |
| 5 | 5 | consent gate, projection layer, guardrails, pre-visit brief, D8 demonstration |

Steps 6 (registry, `fields_read` recording) and 7 (deliverable documents) are out of
this plan's scope — §11 marks step 6 deferred, and step 7 is prose assembled from the
spec.

---

## File structure

```
pyproject.toml
src/pai3/
  __init__.py
  ids.py              # new_id, CanonicalRef — §8
  enums.py            # every closed enum in one place — §6.5, §6.19, §10.1
  values/
    __init__.py
    actor.py          # Actor — §2.1
    provenance.py     # Provenance + resolve_provenance — §6.2, §6.19
    quantity.py       # Quantity, ReferenceRange — §6.9
    codeable.py       # CodeableConcept — §6.10
    text.py           # ClinicalText — §10.1
    people.py         # HumanName, PatientIdentifier, ContactPoint, Address, Preferences
    dosage.py         # Dosage
    plan.py           # PlanItem
    flags.py          # FlagSummary
  base.py             # CanonicalRecord, PatientScoped, ClinicalRecord — §2
  entities/
    __init__.py
    people.py         # Patient, Provider
    administrative.py # Consent, Coverage
    clinical.py       # Encounter, Condition, AllergyIntolerance, Procedure, Goal, SocialFactor
    therapy.py        # Medication, Supplement, TreatmentPlan
    results.py        # DiagnosticReport, LabResult, VitalSign
    narrative.py      # ClinicalNote
    workflow.py       # Task
    infrastructure.py # SourceReference, DataQualityFlag, AuditEvent
  lineage.py          # depth, the ai_inference cap, retraction cascade — §6.19
  interpretation.py   # comparator -> interpretation — §9.5
  validation.py       # layer-2 checks that raise flags — §9.1
  ai/
    __init__.py
    artifact.py       # AIArtifact, AISummary, ExtractionCandidate, AIClaim, ClaimValue, GuardrailFailure — §10.2, §10.5
    scope.py          # AIReadScope, authorize_ai_read — §10.3
    projection.py     # AIPatientView, ProjectionResult, OmittedRecord, BudgetUsage — §10.4, §10.6
    guardrails.py     # the five checks — §10.5
    adapter.py        # the only constructor of an AIArtifact — §10.2
  readmodels/
    __init__.py
    trend.py          # LabTrend, TrendPoint, ExcludedPoint — §9.4
    brief.py          # PreVisitBrief, PatientHeader — §10.4
tests/
  (mirrors src/pai3/)
mock/
  patient_fixture.py  # D3 — built in Phase 5
```

Entities are grouped by change-affinity rather than one file each: `Condition` and
`AllergyIntolerance` are both coded clinical statements and change together;
`LabResult`, `VitalSign` and `DiagnosticReport` share `Quantity`; `Medication` and
`Supplement` share a dosing shape. Eight files instead of twenty-one, each holdable in
context at once.

---

## Phase 1 — foundations and the eight highest-risk entities

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/pai3/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "pai3-patient-model"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.9", "python-ulid>=3.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2: Create the two empty package files**

```bash
mkdir -p src/pai3 tests
touch src/pai3/__init__.py tests/__init__.py
```

- [ ] **Step 3: Create the venv and install**

```bash
python3.12 -m venv .venv && .venv/bin/pip install -q -e ".[dev]"
```

- [ ] **Step 4: Verify the toolchain runs**

Run: `.venv/bin/pytest -q`
Expected: `no tests ran` — exit code 5, not an import error.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src tests
git commit -m "chore: python project scaffolding"
```

---

### Task 2: Identifiers (§8)

Prefixed ULIDs. §8.4 puts the `EntityKind` registry in the deferred step, so the
prefix is passed as a literal here and `new_id` stays thin.

**Files:**
- Create: `src/pai3/ids.py`
- Test: `tests/test_ids.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ids.py
import pytest

from pai3.ids import CanonicalRef, new_id


def test_new_id_carries_the_prefix():
    assert new_id("cond").startswith("cond_")


def test_new_id_is_unique():
    assert new_id("cond") != new_id("cond")


def test_ids_sort_by_creation_order():
    first, second = new_id("lab"), new_id("lab")
    assert first < second


def test_empty_prefix_is_refused():
    with pytest.raises(ValueError):
        new_id("")


def test_prefix_with_underscore_is_refused():
    # An underscore in the prefix would make the id unsplittable.
    with pytest.raises(ValueError):
        new_id("lab_result")


def test_canonical_ref_carries_type_id_and_version():
    ref = CanonicalRef(entity_type="LabResult", entity_id=new_id("lab"), version=3)
    assert ref.version == 3


def test_canonical_ref_rejects_version_below_one():
    with pytest.raises(ValueError):
        CanonicalRef(entity_type="LabResult", entity_id=new_id("lab"), version=0)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_ids.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'pai3.ids'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/ids.py
"""Prefixed ULIDs.

The prefix exists so that an identifier appearing in a log line, a prompt or an AI
citation can be attributed to an entity without a database lookup, and so that
`med_` against `supp_` catches a type substitution before validation runs. It is a
readability affordance and never a type check: resolution against the real target is
the registry's job (spec §8.3).
"""

from pydantic import BaseModel, Field
from ulid import ULID


def new_id(prefix: str) -> str:
    if not prefix:
        raise ValueError("prefix must not be empty")
    if "_" in prefix:
        raise ValueError(f"prefix must not contain '_': {prefix!r}")
    return f"{prefix}_{ULID()}"


class CanonicalRef(BaseModel):
    """A pointer to a canonical record at a known version.

    The version is required rather than optional because every consumer of a ref
    needs reproducibility: §6.19's depth computation and §10.2's prompt
    reconstruction both break if a ref can silently follow a record forward.
    """

    entity_type: str
    entity_id: str
    version: int = Field(ge=1)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/test_ids.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/ids.py tests/test_ids.py
git commit -m "feat: prefixed ULIDs and CanonicalRef"
```

---

### Task 3: Enums (§6.5, §6.19, §10.1)

Every closed enum in one module. The spec's reason for closing them (§6.5) is that
consumers branch on the value, so a free-text field would make the branch unsound.

**Files:**
- Create: `src/pai3/enums.py`
- Test: `tests/test_enums.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_enums.py
from pai3.enums import (
    FlagCode,
    FlagStatus,
    ProvenanceOrigin,
    RecordStatus,
    Severity,
    TextOrigin,
)


def test_record_status_has_no_deleted_value():
    # Spec §2.1: clinical data is not deleted; an erroneous record stays.
    assert "deleted" not in {s.value for s in RecordStatus}
    assert RecordStatus.ENTERED_IN_ERROR.value == "entered_in_error"


def test_provenance_origin_separates_extraction_from_inference():
    # Spec §6.19: conflating these is what leaves compounding unnameable.
    assert ProvenanceOrigin.AI_EXTRACTION.value == "ai_extraction"
    assert ProvenanceOrigin.AI_INFERENCE.value == "ai_inference"


def test_provenance_origin_has_no_bare_derived():
    # Spec §6.19: the catch-all narrows to system_derived.
    values = {o.value for o in ProvenanceOrigin}
    assert "derived" not in values
    assert "system_derived" in values


def test_text_origin_covers_the_perimeter_axis():
    assert {o.value for o in TextOrigin} == {
        "practice_authored",
        "patient_submitted",
        "external_document",
        "transcribed_external",
        "unknown",
    }


def test_severity_matches_the_four_d5_classes():
    assert {s.value for s in Severity} == {
        "blocking",
        "human_review_required",
        "warning",
        "acceptable_missing",
    }


def test_flag_codes_present_for_each_spec_section():
    values = {c.value for c in FlagCode}
    for expected in (
        "CONFLICTING_VALUES",
        "MISSING_UNIT",
        "MISSING_REFERENCE_RANGE",
        "UNIT_MISMATCH",
        "INTERPRETATION_DISAGREES_WITH_RANGE",
        "EXTRACTION_FAILED",
        "DISCONTINUED_SHOWN_ACTIVE",
        "DUPLICATE_CANDIDATE",
        "UNCODED_CONCEPT",
        "PARENT_RETRACTED",
        "RECORD_REJECTED_AT_INGEST",
    ):
        assert expected in values


def test_flag_lifecycle_is_four_states():
    assert {s.value for s in FlagStatus} == {"open", "in_review", "resolved", "wont_fix"}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_enums.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.enums'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/enums.py
"""Closed enumerations.

Each of these is closed rather than a free string because consumers branch on the
value (spec §6.5). A value that can be anything makes every branch unsound, and in
the case of `execution` in §10.2 it makes an invariant unenforceable.
"""

from enum import StrEnum


class RecordStatus(StrEnum):
    """There is deliberately no `deleted`.

    An erroneous record stays as ENTERED_IN_ERROR, because deleting it removes the
    reason a physician prescribed something while the prescription remains (§2.1).
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ENTERED_IN_ERROR = "entered_in_error"


class ProvenanceOrigin(StrEnum):
    """Where a value came from, one meaning per member (§6.19).

    AI_EXTRACTION and AI_INFERENCE are separate because the second compounds: a fact
    inferred from other facts can grow derivatives, and a single catch-all `derived`
    could not distinguish that from pipeline bookkeeping.
    """

    HUMAN = "human"
    SOURCE_SYSTEM = "source_system"
    AI_EXTRACTION = "ai_extraction"
    AI_INFERENCE = "ai_inference"
    SYSTEM_DERIVED = "system_derived"


class TextOrigin(StrEnum):
    """Whether a span of text crossed the practice perimeter (§10.1).

    The axis is not authorship. A physician who pastes a patient's message carries
    external text inside, and their signature does not change what the text is.
    UNKNOWN is treated as external everywhere: an unestablished origin is not a
    reason to trust.
    """

    PRACTICE_AUTHORED = "practice_authored"
    PATIENT_SUBMITTED = "patient_submitted"
    EXTERNAL_DOCUMENT = "external_document"
    TRANSCRIBED_EXTERNAL = "transcribed_external"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """D5's four classes (§9.1).

    BLOCKING does not block persistence. It blocks autonomous conclusion: the record
    exists and is citable, but no read-model or agent may assert from it without
    surfacing the flag.
    """

    BLOCKING = "blocking"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    WARNING = "warning"
    ACCEPTABLE_MISSING = "acceptable_missing"


class FlagCode(StrEnum):
    """Why a flag was raised (§6.5).

    Closed because under §6.9 and §9.3 this is the only carrier of *why* a value is
    absent — three different situations all present as an empty slot.
    """

    CONFLICTING_VALUES = "CONFLICTING_VALUES"
    MISSING_UNIT = "MISSING_UNIT"
    MISSING_REFERENCE_RANGE = "MISSING_REFERENCE_RANGE"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    INTERPRETATION_DISAGREES_WITH_RANGE = "INTERPRETATION_DISAGREES_WITH_RANGE"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    DISCONTINUED_SHOWN_ACTIVE = "DISCONTINUED_SHOWN_ACTIVE"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    UNCODED_CONCEPT = "UNCODED_CONCEPT"
    PARENT_RETRACTED = "PARENT_RETRACTED"
    RECORD_REJECTED_AT_INGEST = "RECORD_REJECTED_AT_INGEST"


class FlagStatus(StrEnum):
    """A flag's own lifecycle, independent of the record's version (§6.5)."""

    OPEN = "open"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    WONT_FIX = "wont_fix"


class ClinicalStatus(StrEnum):
    """§6.4 — the only field distinguishing history from a current diagnosis."""

    ACTIVE = "active"
    RECURRENCE = "recurrence"
    REMISSION = "remission"
    RESOLVED = "resolved"


class VerificationStatus(StrEnum):
    """§6.4 — independent of ClinicalStatus.

    Without this, "suspected lupus" enters a summary as "has lupus". It is the
    cheapest safeguard in the model against its most expensive error.
    """

    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    DIFFERENTIAL = "differential"
    REFUTED = "refuted"
    UNCONFIRMED = "unconfirmed"


class Interpretation(StrEnum):
    """§9.5 — four states, because a comparator makes a value an interval."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    INDETERMINATE = "indeterminate"


class MeasurementContext(StrEnum):
    """§6.6 — trend analysis must be able to filter on this.

    Home weight and in-clinic weight are never silently averaged.
    """

    CLINICAL = "clinical"
    PATIENT_REPORTED = "patient_reported"
    DEVICE = "device"


class ConsentScope(StrEnum):
    """§6.11 — AI_PROCESSING is the gate for the whole AI layer."""

    TREATMENT = "treatment"
    AI_PROCESSING = "ai_processing"
    DATA_SHARING = "data_sharing"
    RESEARCH = "research"
    FAMILY_ACCESS = "family_access"
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/test_enums.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/enums.py tests/test_enums.py
git commit -m "feat: closed enumerations"
```

---

### Task 4: `Actor` and the plain value objects

**Files:**
- Create: `src/pai3/values/__init__.py`
- Create: `src/pai3/values/actor.py`
- Create: `src/pai3/values/people.py`
- Test: `tests/values/test_actor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/values/test_actor.py
import pytest
from pydantic import ValidationError

from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.people import Address, ContactPoint, HumanName, PatientIdentifier


def test_actor_distinguishes_kinds():
    human = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
    agent = Actor(kind=ActorKind.AGENT, ref="brief-agent", label="brief-agent")
    assert human.kind is not agent.kind


def test_actor_requires_a_ref():
    # An actor without a ref cannot be held accountable, which defeats the point.
    with pytest.raises(ValidationError):
        Actor(kind=ActorKind.HUMAN, ref="", label="x")


def test_patient_identifier_keeps_its_assigning_system():
    # Spec §6.12: one patient has several MRNs across source systems.
    ident = PatientIdentifier(system="emr-west", value="MRN-4471", assigner="West Clinic")
    assert ident.system == "emr-west"


def test_human_name_keeps_the_parts_separately():
    name = HumanName(given=["Dana"], family="Okafor")
    assert name.family == "Okafor"


def test_contact_point_and_address_construct():
    assert ContactPoint(system="phone", value="+1-555-0100", use="mobile").use == "mobile"
    assert Address(lines=["12 Rue Haute"], city="Lyon", country="FR").city == "Lyon"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/values/test_actor.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.values'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/values/__init__.py
```

```python
# src/pai3/values/actor.py
"""Who or what acted.

A string would not do: §2.1 requires `updated_by` to distinguish a person from a
pipeline from an agent, and §10.4's rights matrix is unenforceable if the four are
indistinguishable at the point of a write.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class ActorKind(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"
    PIPELINE = "pipeline"
    AGENT = "agent"


class Actor(BaseModel):
    kind: ActorKind
    ref: str = Field(min_length=1)
    label: str = Field(min_length=1)
```

```python
# src/pai3/values/people.py
"""Identity parts, embedded on Patient.

These are embedded rather than normalised because they are read with the patient
every time and never queried on their own (§5).
"""

from pydantic import BaseModel, Field


class PatientIdentifier(BaseModel):
    """One identifier from one system.

    Patient carries a list of these rather than a single `mrn` field: a concierge
    practice pulls from several EMRs and one patient has several MRNs, which §6.12
    names as the primary cause of duplicate patient records.
    """

    system: str = Field(min_length=1)
    value: str = Field(min_length=1)
    assigner: str | None = None


class HumanName(BaseModel):
    given: list[str] = Field(default_factory=list)
    family: str = Field(min_length=1)
    prefix: str | None = None


class ContactPoint(BaseModel):
    system: str
    value: str
    use: str | None = None


class Address(BaseModel):
    lines: list[str] = Field(default_factory=list)
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None


class Preferences(BaseModel):
    """Attributes of the person, as distinct from a Goal (§6 entity table)."""

    language: str | None = None
    contact_preference: str | None = None
    notes: str | None = None
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/values/test_actor.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/values tests/values
git commit -m "feat: Actor and identity value objects"
```

---

### Task 5: `CodeableConcept` (§6.10)

`raw_text` is required and the code optional, because an intake spreadsheet arrives
with "high bp" as a string. The original string is never overwritten by a code —
otherwise there is no way to check whether the coding was correct.

**Files:**
- Create: `src/pai3/values/codeable.py`
- Test: `tests/values/test_codeable.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/values/test_codeable.py
import pytest
from pydantic import ValidationError

from pai3.values.codeable import CodeableConcept


def test_raw_text_alone_is_valid():
    # An intake spreadsheet gives "high bp" and nothing else. It must still land.
    concept = CodeableConcept(raw_text="high bp")
    assert concept.code is None


def test_raw_text_is_required():
    with pytest.raises(ValidationError):
        CodeableConcept(system="ICD-10", code="I10")


def test_blank_raw_text_is_refused():
    with pytest.raises(ValidationError):
        CodeableConcept(raw_text="   ")


def test_a_code_requires_its_system():
    # A bare code is unresolvable, so it is refused rather than stored half-named.
    with pytest.raises(ValidationError):
        CodeableConcept(raw_text="hypertension", code="I10")


def test_coding_does_not_replace_the_original_string():
    concept = CodeableConcept(raw_text="high bp", system="ICD-10", code="I10")
    assert concept.raw_text == "high bp"


def test_is_coded_reports_whether_review_is_needed():
    assert not CodeableConcept(raw_text="high bp").is_coded
    assert CodeableConcept(raw_text="high bp", system="ICD-10", code="I10").is_coded
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/values/test_codeable.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.values.codeable'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/values/codeable.py
"""A clinical concept as received, optionally coded.

Requiring ICD-10 / RxNorm / LOINC at ingestion is unrealistic, so `raw_text` is
always required and the code is optional (§6.10). An uncoded concept raises a
HUMAN_REVIEW_REQUIRED flag rather than being rejected — see validation.py.
"""

from pydantic import BaseModel, Field, model_validator


class CodeableConcept(BaseModel):
    raw_text: str = Field(min_length=1)
    system: str | None = None
    code: str | None = None
    display: str | None = None

    @model_validator(mode="after")
    def _raw_text_is_not_whitespace(self) -> "CodeableConcept":
        if not self.raw_text.strip():
            raise ValueError("raw_text must not be blank")
        return self

    @model_validator(mode="after")
    def _code_requires_a_system(self) -> "CodeableConcept":
        if self.code is not None and self.system is None:
            raise ValueError("code requires the system that issued it")
        return self

    @property
    def is_coded(self) -> bool:
        return self.code is not None and self.system is not None
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/values/test_codeable.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/values/codeable.py tests/values/test_codeable.py
git commit -m "feat: CodeableConcept with required raw_text"
```

---

### Task 6: `Quantity` and `ReferenceRange` (§6.9)

`value` is required *inside* `Quantity` so that "unit present, value absent" is
unrepresentable and consumers make one `None` check rather than two. `comparator`
carries limit-of-detection results, which turns a value into an interval and changes
both range comparison (§9.5) and trend arithmetic (§9.4).

**Files:**
- Create: `src/pai3/values/quantity.py`
- Test: `tests/values/test_quantity.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/values/test_quantity.py
import pytest
from pydantic import ValidationError

from pai3.values.quantity import Quantity, ReferenceRange


def test_value_is_required_inside_quantity():
    # The nonsense state "unit present, value absent" must be unrepresentable.
    with pytest.raises(ValidationError):
        Quantity(unit="mmol/L")


def test_unit_may_be_absent():
    # D5's "missing units must trigger review" — review, not reject.
    assert Quantity(value=7.2).unit is None


def test_comparator_is_restricted_to_four_operators():
    assert Quantity(value=0.01, unit="mIU/L", comparator="<").comparator == "<"
    with pytest.raises(ValidationError):
        Quantity(value=0.01, comparator="~")


def test_is_bounded_reports_a_comparator_result():
    assert Quantity(value=0.01, comparator="<").is_bounded
    assert not Quantity(value=0.01).is_bounded


def test_reference_range_allows_an_open_lower_bound():
    # hs-CRP is reported as 0–3.0; TSH as 0.4–4.0. Both shapes are needed by §9.5.
    assert ReferenceRange(low=0.0, high=3.0).low == 0.0
    assert ReferenceRange(high=3.0).low is None


def test_reference_range_refuses_an_inverted_interval():
    with pytest.raises(ValidationError):
        ReferenceRange(low=4.0, high=0.4)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/values/test_quantity.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.values.quantity'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/values/quantity.py
"""A measured value.

`value` is required here so that `quantity is not None` implies a value exists, which
is what lets LabResult carry an empty slot for an unresolved conflict (§9.3) without
admitting a half-filled one.
"""

from typing import Literal

from pydantic import BaseModel, model_validator

Comparator = Literal["<", ">", "<=", ">="]


class Quantity(BaseModel):
    value: float
    unit: str | None = None
    ucum_code: str | None = None
    comparator: Comparator | None = None

    @property
    def is_bounded(self) -> bool:
        """True when this is a limit-of-detection result rather than a point.

        A bounded value cannot be averaged (§9.4) and cannot be compared to a
        reference range as though it were measured (§9.5).
        """
        return self.comparator is not None


class ReferenceRange(BaseModel):
    """The range as the performing lab reported it.

    `low` is optional because many analytes have no meaningful lower bound, and §9.5
    depends on being able to tell "low is zero or absent" from "low is 0.4".
    """

    low: float | None = None
    high: float | None = None
    source_label: str | None = None

    @model_validator(mode="after")
    def _interval_is_not_inverted(self) -> "ReferenceRange":
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(f"inverted reference range: {self.low} > {self.high}")
        return self
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/values/test_quantity.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/values/quantity.py tests/values/test_quantity.py
git commit -m "feat: Quantity with comparator, and ReferenceRange"
```

---

### Task 7: `ClinicalText` (§10.1)

The marker travels with the text rather than beside it. A sibling field is lost the
moment someone writes `build_prompt(note.body)`; a value object makes discarding it an
explicit act at the call site.

**Files:**
- Create: `src/pai3/values/text.py`
- Test: `tests/values/test_text.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/values/test_text.py
import pytest
from pydantic import ValidationError

from pai3.enums import TextOrigin
from pai3.values.text import ClinicalText


def test_origin_is_required():
    # An unlabelled span is exactly what §10.1 exists to prevent.
    with pytest.raises(ValidationError):
        ClinicalText(value="Patient reports fatigue.")


def test_unknown_origin_counts_as_external():
    # Fail closed: an unestablished origin is not a reason to trust.
    assert ClinicalText(value="x", origin=TextOrigin.UNKNOWN).crossed_perimeter


def test_practice_authored_is_internal():
    text = ClinicalText(value="x", origin=TextOrigin.PRACTICE_AUTHORED)
    assert not text.crossed_perimeter


def test_transcribed_external_counts_as_external_despite_the_author():
    # A physician who pasted a patient's message carries external text inside.
    text = ClinicalText(value="x", origin=TextOrigin.TRANSCRIBED_EXTERNAL)
    assert text.crossed_perimeter


def test_patient_submitted_and_external_document_are_external():
    for origin in (TextOrigin.PATIENT_SUBMITTED, TextOrigin.EXTERNAL_DOCUMENT):
        assert ClinicalText(value="x", origin=origin).crossed_perimeter


def test_there_is_no_sanitized_flag():
    # Spec §10.1: a field implying text has been checked is worse than no field.
    assert "sanitized" not in ClinicalText.model_fields
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/values/test_text.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.values.text'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/values/text.py
"""Free text with its origin attached.

The trust boundary is whether the text crossed the practice perimeter, not who signed
the record holding it (§10.1). This does not make text safe, and there is
deliberately no `sanitized` field: declining to act on instructions found in an
external span is a policy of the AI layer, not a property of the schema.
"""

from pydantic import BaseModel, Field

from pai3.enums import TextOrigin
from pai3.values.actor import Actor

_EXTERNAL = {
    TextOrigin.PATIENT_SUBMITTED,
    TextOrigin.EXTERNAL_DOCUMENT,
    TextOrigin.TRANSCRIBED_EXTERNAL,
    TextOrigin.UNKNOWN,
}


class ClinicalText(BaseModel):
    value: str
    origin: TextOrigin
    captured_by: Actor | None = Field(
        default=None, description="Who entered this into the practice system"
    )

    @property
    def crossed_perimeter(self) -> bool:
        """True for anything that did not originate inside the practice.

        UNKNOWN is included: the default fails closed.
        """
        return self.origin in _EXTERNAL
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/values/test_text.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/values/text.py tests/values/test_text.py
git commit -m "feat: ClinicalText carrying perimeter origin"
```

---

### Task 8: `Provenance` and its invariants (§6.2, §6.19)

The full shape is in §6.19. Three invariants are enforced here; the fourth —
`depth == 1 + max(parent depth)` — needs to read the parents and therefore lives in
`lineage.py` (Task 12). This validator enforces only what a single record can know
about itself: that `depth` is zero exactly when `derived_from` is empty.

**Files:**
- Create: `src/pai3/values/provenance.py`
- Test: `tests/values/test_provenance.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/values/test_provenance.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.enums import ProvenanceOrigin
from pai3.ids import CanonicalRef, new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance, resolve_provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
CLINICIAN = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PIPELINE = Actor(kind=ActorKind.PIPELINE, ref="emr-import", label="emr-import")


def _ref(version: int = 1) -> CanonicalRef:
    return CanonicalRef(entity_type="Condition", entity_id=new_id("cond"), version=version)


def test_human_origin_needs_neither_refs_nor_parents():
    prov = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=CLINICIAN, asserted_at=NOW)
    assert prov.depth == 0


def test_ai_extraction_requires_a_source_ref():
    # Extraction came from a document; without the pointer there is no evidence.
    with pytest.raises(ValidationError, match="source_refs"):
        Provenance(
            origin=ProvenanceOrigin.AI_EXTRACTION, asserted_by=CLINICIAN, asserted_at=NOW
        )


def test_ai_extraction_with_a_source_ref_is_valid():
    prov = Provenance(
        origin=ProvenanceOrigin.AI_EXTRACTION,
        asserted_by=CLINICIAN,
        asserted_at=NOW,
        source_refs=[new_id("sref")],
        extraction_confidence=0.82,
    )
    assert prov.depth == 0


def test_ai_inference_requires_a_parent():
    with pytest.raises(ValidationError, match="derived_from"):
        Provenance(
            origin=ProvenanceOrigin.AI_INFERENCE, asserted_by=CLINICIAN, asserted_at=NOW
        )


def test_ai_inference_is_capped_at_depth_one():
    # Spec §6.19: AI may reason from documents and from first-generation facts,
    # never from its own inferences. Without the cap the chain compounds.
    with pytest.raises(ValidationError, match="depth"):
        Provenance(
            origin=ProvenanceOrigin.AI_INFERENCE,
            asserted_by=CLINICIAN,
            asserted_at=NOW,
            derived_from=[_ref()],
            depth=2,
        )


def test_ai_inference_at_depth_one_is_valid():
    prov = Provenance(
        origin=ProvenanceOrigin.AI_INFERENCE,
        asserted_by=CLINICIAN,
        asserted_at=NOW,
        derived_from=[_ref()],
        depth=1,
    )
    assert prov.depth == 1


def test_depth_zero_requires_no_parents():
    with pytest.raises(ValidationError, match="depth"):
        Provenance(
            origin=ProvenanceOrigin.AI_INFERENCE,
            asserted_by=CLINICIAN,
            asserted_at=NOW,
            derived_from=[_ref()],
            depth=0,
        )


def test_parents_require_a_nonzero_depth():
    with pytest.raises(ValidationError, match="depth"):
        Provenance(
            origin=ProvenanceOrigin.HUMAN,
            asserted_by=CLINICIAN,
            asserted_at=NOW,
            derived_from=[_ref()],
            depth=0,
        )


def test_system_derived_asserts_nothing_clinical():
    prov = Provenance(
        origin=ProvenanceOrigin.SYSTEM_DERIVED, asserted_by=PIPELINE, asserted_at=NOW
    )
    assert not prov.is_clinical_assertion


def test_human_and_extraction_are_clinical_assertions():
    for origin, extra in (
        (ProvenanceOrigin.HUMAN, {}),
        (ProvenanceOrigin.AI_EXTRACTION, {"source_refs": [new_id("sref")]}),
    ):
        prov = Provenance(
            origin=origin, asserted_by=CLINICIAN, asserted_at=NOW, **extra
        )
        assert prov.is_clinical_assertion


def test_confidence_outside_zero_to_one_is_refused():
    with pytest.raises(ValidationError):
        Provenance(
            origin=ProvenanceOrigin.AI_EXTRACTION,
            asserted_by=CLINICIAN,
            asserted_at=NOW,
            source_refs=[new_id("sref")],
            extraction_confidence=1.4,
        )


def test_resolve_provenance_prefers_the_field_override():
    record = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=CLINICIAN, asserted_at=NOW)
    field = Provenance(
        origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=PIPELINE, asserted_at=NOW
    )
    assert resolve_provenance("dose", record, {"dose": field}).origin is (
        ProvenanceOrigin.SOURCE_SYSTEM
    )


def test_resolve_provenance_falls_back_to_the_record():
    record = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=CLINICIAN, asserted_at=NOW)
    assert resolve_provenance("dose", record, {}).origin is ProvenanceOrigin.HUMAN
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/values/test_provenance.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.values.provenance'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/values/provenance.py
"""Where a value came from.

Provenance is a property of a value; AuditEvent is a stream of events over a record
(§6.3). Conflating the two is the most common failure in models of this kind.

`source_refs` terminates in a document, so `derived_from` exists to say "this fact
came from that canonical record" — without which a second-generation fact is
indistinguishable from a first-generation one and an extraction error grows
derivatives invisibly (§6.19).
"""

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from pai3.enums import ProvenanceOrigin
from pai3.ids import CanonicalRef
from pai3.values.actor import Actor

AI_INFERENCE_MAX_DEPTH = 1
"""§6.19: AI reasons from documents and first-generation facts, not from inferences."""

_CLINICAL_ASSERTIONS = {
    ProvenanceOrigin.HUMAN,
    ProvenanceOrigin.SOURCE_SYSTEM,
    ProvenanceOrigin.AI_EXTRACTION,
    ProvenanceOrigin.AI_INFERENCE,
}


class Provenance(BaseModel):
    origin: ProvenanceOrigin
    asserted_by: Actor
    asserted_at: datetime
    imported_at: datetime | None = None
    source_refs: list[str] = Field(
        default_factory=list, description="SourceReference ids — document, page, span"
    )
    derived_from: list[CanonicalRef] = Field(
        default_factory=list, description="Canonical records this was reasoned from"
    )
    depth: int = Field(default=0, ge=0, description="0 = straight from a document")
    extraction_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _extraction_cites_a_document(self) -> "Provenance":
        if self.origin is ProvenanceOrigin.AI_EXTRACTION and not self.source_refs:
            raise ValueError("ai_extraction requires a non-empty source_refs")
        return self

    @model_validator(mode="after")
    def _inference_names_its_parents(self) -> "Provenance":
        if self.origin is ProvenanceOrigin.AI_INFERENCE and not self.derived_from:
            raise ValueError("ai_inference requires a non-empty derived_from")
        return self

    @model_validator(mode="after")
    def _depth_agrees_with_parents(self) -> "Provenance":
        if bool(self.derived_from) != (self.depth > 0):
            raise ValueError(
                "depth must be 0 exactly when derived_from is empty; "
                f"got depth={self.depth} with {len(self.derived_from)} parents"
            )
        return self

    @model_validator(mode="after")
    def _inference_respects_the_cap(self) -> "Provenance":
        if (
            self.origin is ProvenanceOrigin.AI_INFERENCE
            and self.depth > AI_INFERENCE_MAX_DEPTH
        ):
            raise ValueError(
                f"ai_inference is capped at depth {AI_INFERENCE_MAX_DEPTH}; got {self.depth}"
            )
        return self

    @property
    def is_clinical_assertion(self) -> bool:
        """False for SYSTEM_DERIVED, which is pipeline bookkeeping (§6.19)."""
        return self.origin in _CLINICAL_ASSERTIONS


def resolve_provenance(
    field_name: str, record: Provenance, overrides: dict[str, Provenance]
) -> Provenance:
    """Provenance for one field: the override if the whitelist carries one (§6.2).

    The whitelist is per entity class and deliberately short — `dose` and `status` on
    Medication, `quantity` on LabResult, `clinical_status` on Condition. A vague rule
    grows the map to twenty fields within a week.
    """
    return overrides.get(field_name, record)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/values/test_provenance.py -q`
Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/values/provenance.py tests/values/test_provenance.py
git commit -m "feat: Provenance with lineage invariants and the ai_inference cap"
```

---

### Task 9: `Dosage`, `PlanItem`, `FlagSummary`

Three small embedded objects with no decisions behind them beyond §5's test: each is
read with its owner and never queried alone.

**Files:**
- Create: `src/pai3/values/dosage.py`
- Create: `src/pai3/values/plan.py`
- Create: `src/pai3/values/flags.py`
- Test: `tests/values/test_small_values.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/values/test_small_values.py
import pytest
from pydantic import ValidationError

from pai3.enums import FlagCode, Severity
from pai3.ids import new_id
from pai3.values.dosage import Dosage
from pai3.values.flags import FlagSummary
from pai3.values.plan import PlanItem


def test_dosage_keeps_the_text_as_given():
    # A supplement arrives as "one dropper", which no structured field accepts.
    assert Dosage(text="one dropper twice daily").text == "one dropper twice daily"


def test_dosage_structured_parts_are_optional():
    dose = Dosage(text="500 mg BID", amount=500.0, unit="mg", frequency="BID", route="oral")
    assert dose.amount == 500.0


def test_dosage_requires_some_text():
    with pytest.raises(ValidationError):
        Dosage(text="")


def test_plan_item_may_reference_a_canonical_record():
    item = PlanItem(description="Titrate metformin", targets=[new_id("med")])
    assert item.targets


def test_flag_summary_carries_code_and_severity():
    summary = FlagSummary(
        flag_id=new_id("flag"),
        code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING,
        message="glucose: EMR 5.5 against lab 7.2, unresolved",
    )
    assert summary.severity is Severity.BLOCKING


def test_flag_summary_message_is_required():
    # A summary with no message cannot be rendered to a physician, which is its job.
    with pytest.raises(ValidationError):
        FlagSummary(
            flag_id=new_id("flag"),
            code=FlagCode.MISSING_UNIT,
            severity=Severity.HUMAN_REVIEW_REQUIRED,
            message="",
        )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/values/test_small_values.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.values.dosage'`

- [ ] **Step 3: Write the implementations**

```python
# src/pai3/values/dosage.py
"""How something is taken.

`text` is required and the structured parts optional, for the same reason
CodeableConcept keeps `raw_text` (§6.10): a supplement arrives as "one dropper", and
refusing it loses the fact that the patient is taking something.
"""

from pydantic import BaseModel, Field


class Dosage(BaseModel):
    text: str = Field(min_length=1)
    amount: float | None = None
    unit: str | None = None
    frequency: str | None = None
    route: str | None = None
```

```python
# src/pai3/values/plan.py
"""One line of a treatment plan.

Embedded rather than normalised: a plan item has no lifecycle of its own and is
revised as part of the plan (§5). It may still point at a Condition or Medication.
"""

from pydantic import BaseModel, Field


class PlanItem(BaseModel):
    description: str = Field(min_length=1)
    targets: list[str] = Field(
        default_factory=list, description="Canonical ids this item acts on"
    )
    due: str | None = None
```

```python
# src/pai3/values/flags.py
"""A flag as a read-model shows it.

Read-models carry a required list of these so that a brief which dropped a flagged
record cannot be constructed (§9.4). It is a projection of DataQualityFlag, not the
flag itself — the flag is an entity with its own lifecycle (§6.5).
"""

from pydantic import BaseModel, Field

from pai3.enums import FlagCode, Severity


class FlagSummary(BaseModel):
    flag_id: str
    code: FlagCode
    severity: Severity
    message: str = Field(min_length=1)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/values/test_small_values.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/values tests/values/test_small_values.py
git commit -m "feat: Dosage, PlanItem and FlagSummary"
```

---

### Task 10: The three base tiers (§2)

A single universal base would give nine of twenty-one entities a nullable
`encounter_id` they never set. The class an entity inherits from states what kind of
data it is — and `Provider` sitting outside `PatientScoped` is a governance fact, not
tidiness: a provider record is not covered by any patient's consent scope.

**Files:**
- Create: `src/pai3/base.py`
- Test: `tests/test_base.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_base.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.base import CanonicalRecord, ClinicalRecord, PatientScoped
from pai3.enums import ProvenanceOrigin, RecordStatus
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
CLINICIAN = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=CLINICIAN, asserted_at=NOW)


def _base_kwargs(prefix: str) -> dict:
    return {
        "id": new_id(prefix),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": CLINICIAN,
    }


def test_canonical_record_defaults_to_active_version_one():
    record = CanonicalRecord(**_base_kwargs("prov"))
    assert record.record_status is RecordStatus.ACTIVE
    assert record.version == 1


def test_canonical_record_has_no_patient_id():
    # Patient's own id is the scope; Provider is practice reference data (§2.4).
    assert "patient_id" not in CanonicalRecord.model_fields


def test_patient_scoped_requires_a_patient_id():
    with pytest.raises(ValidationError):
        PatientScoped(**_base_kwargs("cons"))


def test_patient_scoped_has_no_encounter_id():
    # Consent and Goal have no encounter; the field belongs one tier down (§2.4).
    assert "encounter_id" not in PatientScoped.model_fields


def test_clinical_record_encounter_is_optional():
    # An outside lab result has no encounter.
    record = ClinicalRecord(**_base_kwargs("cond"), patient_id=new_id("pat"))
    assert record.encounter_id is None


def test_clinical_record_accepts_an_encounter():
    record = ClinicalRecord(
        **_base_kwargs("cond"), patient_id=new_id("pat"), encounter_id=new_id("enc")
    )
    assert record.encounter_id is not None


def test_version_below_one_is_refused():
    with pytest.raises(ValidationError):
        CanonicalRecord(**_base_kwargs("prov") | {"version": 0})


def test_naive_timestamps_are_refused():
    # A clinical timestamp without a zone cannot be ordered across sites.
    with pytest.raises(ValidationError):
        CanonicalRecord(**_base_kwargs("prov") | {"created_at": datetime(2026, 3, 12, 9, 0)})


def test_is_retracted_reports_entered_in_error():
    record = CanonicalRecord(
        **_base_kwargs("prov") | {"record_status": RecordStatus.ENTERED_IN_ERROR}
    )
    assert record.is_retracted
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_base.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.base'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/base.py
"""The three tiers every canonical entity inherits from (§2).

Which class an entity extends is a statement about the data: CanonicalRecord for
practice-level and infrastructure records, PatientScoped for anything belonging to one
patient, ClinicalRecord for anything that may belong to an encounter.
"""

from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from pai3.enums import RecordStatus
from pai3.values.actor import Actor
from pai3.values.provenance import Provenance


class CanonicalRecord(BaseModel):
    """Applies to Patient, Provider, AuditEvent, DataQualityFlag."""

    id: str
    provenance: Provenance
    field_provenance: dict[str, Provenance] = Field(
        default_factory=dict,
        description="Per-entity whitelist only; see each entity's FIELD_PROVENANCE_WHITELIST",
    )
    record_status: RecordStatus = RecordStatus.ACTIVE
    version: int = Field(default=1, ge=1)
    superseded_by: str | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    updated_by: Actor

    @field_validator("created_at", "updated_at")
    @classmethod
    def _require_a_zone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @property
    def is_retracted(self) -> bool:
        """Retraction cascades to derivatives — see lineage.retraction_cascade (§6.19)."""
        return self.record_status is RecordStatus.ENTERED_IN_ERROR


class PatientScoped(CanonicalRecord):
    """Applies to Encounter, Consent, Coverage, Goal, SourceReference."""

    patient_id: str


class ClinicalRecord(PatientScoped):
    """Applies to the twelve entities that may belong to an encounter (§2.3)."""

    encounter_id: str | None = None
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/test_base.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/base.py tests/test_base.py
git commit -m "feat: three canonical base tiers"
```

---

### Task 11: Interpretation from a comparator (§9.5)

A comparator turns a value into a half-open interval, so a range comparison is
decidable only when the interval lies entirely on one side of the boundary. The spec
gives a five-row decision table and asks for one test per row. `indeterminate` is a
value and not a flag: a `>100` against an upper bound of 150 is correct assay output,
and flagging it would fill the review queue with items nobody can resolve.

**Files:**
- Create: `src/pai3/interpretation.py`
- Test: `tests/test_interpretation.py`

- [ ] **Step 1: Write the failing tests — one per table row, plus the worked cases**

```python
# tests/test_interpretation.py
from pai3.enums import Interpretation
from pai3.interpretation import interpret, interpretation_disagrees
from pai3.values.codeable import CodeableConcept
from pai3.values.quantity import Quantity, ReferenceRange

TSH = ReferenceRange(low=0.4, high=4.0)
HS_CRP = ReferenceRange(low=0.0, high=3.0)
NO_UPPER = ReferenceRange(low=0.4)


# --- row 1: no comparator, ordinary comparison
def test_row1_plain_value_below_range_is_low():
    assert interpret(Quantity(value=0.2), TSH) is Interpretation.LOW


def test_row1_plain_value_inside_range_is_normal():
    assert interpret(Quantity(value=2.0), TSH) is Interpretation.NORMAL


def test_row1_plain_value_above_range_is_high():
    assert interpret(Quantity(value=9.0), TSH) is Interpretation.HIGH


# --- row 2: "<x" where x <= low
def test_row2_below_detection_under_the_lower_bound_is_low():
    # TSH <0.01 against 0.4-4.0. Strictly sound: anything below 0.01 is below 0.4.
    assert interpret(Quantity(value=0.01, comparator="<"), TSH) is Interpretation.LOW


# --- row 3: "<x" where low is zero or absent and x <= high
def test_row3_below_detection_with_a_zero_lower_bound_is_normal():
    # hs-CRP <0.3 against 0-3.0. Without this row it returns indeterminate and
    # floods the output with results a physician reads as plainly normal.
    assert interpret(Quantity(value=0.3, comparator="<"), HS_CRP) is Interpretation.NORMAL


def test_row3_applies_when_the_lower_bound_is_absent():
    assert (
        interpret(Quantity(value=0.3, comparator="<"), ReferenceRange(high=3.0))
        is Interpretation.NORMAL
    )


# --- row 4: ">x" where x >= high
def test_row4_above_detection_over_the_upper_bound_is_high():
    assert (
        interpret(Quantity(value=4.0, comparator=">"), TSH) is Interpretation.HIGH
    )


# --- row 5: the interval crosses a boundary
def test_row5_greater_than_inside_the_range_is_indeterminate():
    # >100 against an upper bound of 150: the true value lies in (100, inf).
    rng = ReferenceRange(low=0.0, high=150.0)
    assert (
        interpret(Quantity(value=100.0, comparator=">"), rng) is Interpretation.INDETERMINATE
    )


def test_row5_less_than_crossing_a_real_lower_bound_is_indeterminate():
    # <1.0 against 0.4-4.0 straddles 0.4.
    assert (
        interpret(Quantity(value=1.0, comparator="<"), TSH) is Interpretation.INDETERMINATE
    )


def test_row5_greater_than_with_no_upper_bound_is_indeterminate():
    assert (
        interpret(Quantity(value=9.0, comparator=">"), NO_UPPER)
        is Interpretation.INDETERMINATE
    )


# --- inclusive comparators follow from the same interval reasoning
def test_inclusive_less_than_at_the_bound_is_indeterminate():
    # "<=0.4" includes 0.4, which is itself in range, so "low" is not sound.
    assert (
        interpret(Quantity(value=0.4, comparator="<="), TSH) is Interpretation.INDETERMINATE
    )


def test_inclusive_less_than_below_the_bound_is_low():
    assert interpret(Quantity(value=0.3, comparator="<="), TSH) is Interpretation.LOW


# --- no range at all
def test_without_a_range_nothing_can_be_concluded():
    assert interpret(Quantity(value=2.0), None) is Interpretation.INDETERMINATE


def test_an_empty_range_concludes_nothing():
    assert interpret(Quantity(value=2.0), ReferenceRange()) is Interpretation.INDETERMINATE


# --- reported against computed
def test_disagreement_is_detected():
    reported = CodeableConcept(raw_text="H")
    assert interpretation_disagrees(reported, Interpretation.NORMAL)


def test_agreement_is_not_a_disagreement():
    assert not interpretation_disagrees(CodeableConcept(raw_text="H"), Interpretation.HIGH)


def test_computed_indeterminate_is_not_a_disagreement():
    # Spec §9.5: indeterminate alongside a reported value is not a conflict.
    assert not interpretation_disagrees(
        CodeableConcept(raw_text="H"), Interpretation.INDETERMINATE
    )


def test_absent_reported_value_is_not_a_disagreement():
    assert not interpretation_disagrees(None, Interpretation.HIGH)


def test_an_unrecognised_reported_token_is_not_a_disagreement():
    # We cannot claim a conflict with a token we failed to understand.
    assert not interpretation_disagrees(CodeableConcept(raw_text="??"), Interpretation.HIGH)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_interpretation.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.interpretation'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/interpretation.py
"""Whether a result is low, normal or high — derived, never stored (§9.5).

A comparator makes a value an interval, so the comparison is decidable only when the
interval lies entirely on one side of a boundary. Where it is not, the answer is
INDETERMINATE: a value, not a defect. The assay output is correct and only the derived
interpretation is unavailable, so raising a flag would fill the review queue with
items nobody can resolve.

The lab's own reading is stored separately as `LabResult.reported_interpretation` and
is never overwritten by this computation — the lab vouched for its "H", which makes it
a source fact, and replacing it with ours is no better than letting AI rewrite
canonical (§1).
"""

from pai3.enums import Interpretation
from pai3.values.codeable import CodeableConcept
from pai3.values.quantity import Quantity, ReferenceRange

_REPORTED_TOKENS: dict[str, Interpretation] = {
    "l": Interpretation.LOW,
    "ll": Interpretation.LOW,
    "low": Interpretation.LOW,
    "n": Interpretation.NORMAL,
    "normal": Interpretation.NORMAL,
    "h": Interpretation.HIGH,
    "hh": Interpretation.HIGH,
    "high": Interpretation.HIGH,
}


def interpret(quantity: Quantity, reference: ReferenceRange | None) -> Interpretation:
    """Apply §9.5's decision table.

    Returns INDETERMINATE whenever the comparison is not sound, including when there
    is no usable range at all.
    """
    if reference is None or (reference.low is None and reference.high is None):
        return Interpretation.INDETERMINATE

    low, high = reference.low, reference.high
    x = quantity.value

    # Row 1 — a point value compares ordinarily.
    if quantity.comparator is None:
        if low is not None and x < low:
            return Interpretation.LOW
        if high is not None and x > high:
            return Interpretation.HIGH
        return Interpretation.NORMAL

    # Rows 2-3 — the interval lies below x.
    if quantity.comparator in ("<", "<="):
        strictly_below_low = (x <= low) if quantity.comparator == "<" else (x < low)
        if low is not None and strictly_below_low:
            return Interpretation.LOW
        # Row 3: with no meaningful lower bound the interval is contained in range.
        if (low is None or low == 0.0) and high is not None and x <= high:
            return Interpretation.NORMAL
        return Interpretation.INDETERMINATE

    # Row 4 — the interval lies above x.
    strictly_above_high = (x >= high) if quantity.comparator == ">" else (x > high)
    if high is not None and strictly_above_high:
        return Interpretation.HIGH

    # Row 5 — the interval crosses a boundary, or extends past an absent one.
    return Interpretation.INDETERMINATE


def interpretation_disagrees(
    reported: CodeableConcept | None, computed: Interpretation
) -> bool:
    """True when the lab's own reading and ours conflict (§9.5).

    A disagreement almost always means the reference range stored here is not the one
    the lab used, which makes every other interpretation against that range suspect —
    hence FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE.

    An unrecognised token returns False: we cannot claim a conflict with something we
    failed to understand.
    """
    if reported is None or computed is Interpretation.INDETERMINATE:
        return False
    mapped = _REPORTED_TOKENS.get(reported.raw_text.strip().lower())
    if mapped is None:
        return False
    return mapped is not computed
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/test_interpretation.py -q`
Expected: `20 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/interpretation.py tests/test_interpretation.py
git commit -m "feat: comparator-aware interpretation with four states"
```

---

### Task 12: Infrastructure entities — `SourceReference`, `DataQualityFlag`, `AuditEvent`

These three come early because everything else raises flags against them and writes
audit events. All three inherit `CanonicalRecord`: `SourceReference` is `PatientScoped`,
while the flag and the event are practice-level and carry `patient_id` only as a
denormalised query key, since they must be able to target a `Provider` (§2.4).

**Files:**
- Create: `src/pai3/entities/__init__.py`
- Create: `src/pai3/entities/infrastructure.py`
- Test: `tests/entities/test_infrastructure.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_infrastructure.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.enums import FlagCode, FlagStatus, ProvenanceOrigin, Severity
from pai3.entities.infrastructure import (
    AuditAction,
    AuditEvent,
    DataQualityFlag,
    FlagTarget,
    IngestSummary,
    SourceReference,
)
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
PIPELINE = Actor(kind=ActorKind.PIPELINE, ref="emr-import", label="emr-import")
PROV = Provenance(
    origin=ProvenanceOrigin.SYSTEM_DERIVED, asserted_by=PIPELINE, asserted_at=NOW
)


def _base(prefix: str) -> dict:
    return {
        "id": new_id(prefix),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": PIPELINE,
    }


def test_source_reference_points_into_a_document():
    ref = SourceReference(
        **_base("sref"),
        patient_id=new_id("pat"),
        document_id=new_id("doc"),
        page=4,
        field_path="results[2].value",
        quote="Glucose 7.2 mmol/L",
    )
    assert ref.page == 4


def test_source_reference_requires_a_document():
    with pytest.raises(ValidationError):
        SourceReference(**_base("sref"), patient_id=new_id("pat"))


def test_flag_can_target_two_records_for_one_conflict():
    # Spec §6.5: "EMR says 500 mg, intake says 1000 mg" is one flag, two targets.
    flag = DataQualityFlag(
        **_base("flag"),
        code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING,
        message="dose conflict",
        targets=[
            FlagTarget(entity_type="Medication", entity_id=new_id("med"), field_path="dose"),
            FlagTarget(entity_type="Medication", entity_id=new_id("med"), field_path="dose"),
        ],
    )
    assert len(flag.targets) == 2


def test_flag_may_name_a_place_in_a_document_instead_of_a_record():
    # Spec §9.7: a rejected record has no id, so the flag names the source.
    flag = DataQualityFlag(
        **_base("flag"),
        code=FlagCode.RECORD_REJECTED_AT_INGEST,
        severity=Severity.HUMAN_REVIEW_REQUIRED,
        message="row 17: no collection_date",
        source_locator=[new_id("sref")],
    )
    assert not flag.targets
    assert flag.source_locator


def test_flag_with_neither_target_nor_locator_is_refused():
    # A flag pointing at nothing cannot be actioned, which is its only purpose.
    with pytest.raises(ValidationError, match="targets"):
        DataQualityFlag(
            **_base("flag"),
            code=FlagCode.MISSING_UNIT,
            severity=Severity.HUMAN_REVIEW_REQUIRED,
            message="x",
        )


def test_flag_opens_in_the_open_state():
    flag = DataQualityFlag(
        **_base("flag"),
        code=FlagCode.MISSING_UNIT,
        severity=Severity.HUMAN_REVIEW_REQUIRED,
        message="x",
        targets=[FlagTarget(entity_type="LabResult", entity_id=new_id("lab"))],
    )
    assert flag.status is FlagStatus.OPEN
    assert flag.blocks_autonomous_use is False


def test_an_open_blocking_flag_blocks_autonomous_use():
    flag = DataQualityFlag(
        **_base("flag"),
        code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING,
        message="x",
        targets=[FlagTarget(entity_type="LabResult", entity_id=new_id("lab"))],
    )
    assert flag.blocks_autonomous_use


def test_a_resolved_blocking_flag_no_longer_blocks():
    flag = DataQualityFlag(
        **_base("flag"),
        code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING,
        message="x",
        status=FlagStatus.RESOLVED,
        targets=[FlagTarget(entity_type="LabResult", entity_id=new_id("lab"))],
    )
    assert not flag.blocks_autonomous_use


def test_read_event_batches_targets_and_may_omit_fields_read():
    # Spec §6.3: None means "unknown, assume the whole record".
    event = AuditEvent(
        **_base("aud"),
        action=AuditAction.READ,
        trace_id=new_id("trc"),
        targets=[new_id("cond"), new_id("cond")],
    )
    assert event.fields_read is None


def test_ingest_events_carry_counts_and_a_nullable_expected():
    started = AuditEvent(
        **_base("aud"),
        action=AuditAction.INGEST_STARTED,
        trace_id=new_id("trc"),
        ingest=IngestSummary(source_document_id=new_id("doc"), expected=40),
    )
    assert started.ingest.expected == 40


def test_expected_none_records_unverifiable_completeness():
    # Spec §9.7: not flagged, but not invisible either — the None stays queryable.
    summary = IngestSummary(source_document_id=new_id("doc"), expected=None, accepted=12)
    assert summary.completeness_verifiable is False


def test_expected_present_makes_completeness_verifiable():
    summary = IngestSummary(
        source_document_id=new_id("doc"), expected=40, accepted=38, rejected=2
    )
    assert summary.completeness_verifiable
    assert summary.unaccounted == 0


def test_unaccounted_detects_a_gap():
    summary = IngestSummary(
        source_document_id=new_id("doc"), expected=40, accepted=37, rejected=2
    )
    assert summary.unaccounted == 1


def test_ingest_summary_only_on_ingest_actions():
    with pytest.raises(ValidationError, match="ingest"):
        AuditEvent(
            **_base("aud"),
            action=AuditAction.READ,
            trace_id=new_id("trc"),
            targets=[new_id("cond")],
            ingest=IngestSummary(source_document_id=new_id("doc")),
        )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_infrastructure.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.entities'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/entities/__init__.py
```

```python
# src/pai3/entities/infrastructure.py
"""SourceReference, DataQualityFlag, AuditEvent.

The flag and the event are practice-level: they must be able to target a Provider,
which has no patient, so they inherit CanonicalRecord and carry `patient_id` only as a
denormalised key for the per-patient review queue and audit export (§2.4).
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from pai3.base import CanonicalRecord, PatientScoped
from pai3.enums import FlagCode, FlagStatus, Severity
from pai3.ids import CanonicalRef
from pai3.values.actor import Actor


class SourceReference(PatientScoped):
    """A pointer into a source document — the single citation primitive (§6.17).

    Normalised rather than embedded because one lab PDF supports forty lab results;
    embedding would kill "show me everything from this report" and multiply storage.
    """

    document_id: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    field_path: str | None = None
    span_start: int | None = Field(default=None, ge=0)
    span_end: int | None = Field(default=None, ge=0)
    quote: str | None = None


class FlagTarget(BaseModel):
    entity_type: str
    entity_id: str
    field_path: str | None = None


class DataQualityFlag(CanonicalRecord):
    """A defect, with its own lifecycle (§6.5).

    An entity rather than an embedded list, for three reasons: the review queue is a
    cross-patient query; a conflict exists between two records and needs two targets;
    and its lifecycle is independent of the clinical record's version, so embedding
    would bury change history under review noise.
    """

    patient_id: str | None = Field(
        default=None, description="Denormalised query key, not ownership"
    )
    code: FlagCode
    severity: Severity
    message: str = Field(min_length=1)
    status: FlagStatus = FlagStatus.OPEN
    targets: list[FlagTarget] = Field(default_factory=list)
    candidates: list[str] = Field(
        default_factory=list,
        description="SourceReference ids for the competing values in a conflict",
    )
    source_locator: list[str] = Field(
        default_factory=list,
        description="SourceReference ids, when no canonical record exists to target (§9.7)",
    )

    @model_validator(mode="after")
    def _points_at_something(self) -> "DataQualityFlag":
        if not self.targets and not self.source_locator:
            raise ValueError("a flag needs targets or a source_locator to be actionable")
        return self

    @property
    def blocks_autonomous_use(self) -> bool:
        """§9.1: blocking blocks autonomous conclusion, never persistence."""
        return self.severity is Severity.BLOCKING and self.status in (
            FlagStatus.OPEN,
            FlagStatus.IN_REVIEW,
        )


class AuditAction(StrEnum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    RETRACT = "retract"
    INGEST_STARTED = "ingest_started"
    INGEST_COMPLETED = "ingest_completed"
    INGEST_FAILED = "ingest_failed"


class IngestSummary(BaseModel):
    """Counts for one ingestion attempt (§9.7).

    `expected` is None when the document declares no count — a free-form PDF. That is
    not flagged, because one flag per PDF is noise, but it stays here so that "which
    documents have unverifiable completeness" remains an ordinary query. Not flagging
    something and not knowing it are different claims, and None is the second.
    """

    source_document_id: str
    expected: int | None = Field(default=None, ge=0)
    accepted: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    failure_reason: str | None = None

    @property
    def completeness_verifiable(self) -> bool:
        return self.expected is not None

    @property
    def unaccounted(self) -> int | None:
        """Rows the document claimed that neither landed nor were rejected."""
        if self.expected is None:
            return None
        return self.expected - self.accepted - self.rejected


class AuditEvent(CanonicalRecord):
    """Append-only. Logs reads as well as writes (§6.3).

    Payloads are populated by action: `fields_read` on reads, `ingest` on ingestion,
    `field_delta` on writes. That is the ordinary shape of an event log — each field is
    documented by the action that fills it and absent otherwise.
    """

    patient_id: str | None = Field(default=None, description="Denormalised query key")
    action: AuditAction
    trace_id: str = Field(
        min_length=1,
        description="The unit of work: one brief generation, one extraction run, one agent turn",
    )
    actor: Actor | None = None
    targets: list[str] = Field(
        default_factory=list,
        description="Reads batch by (trace_id, entity_type); writes keep a single target",
    )
    fields_read: list[str] | None = Field(
        default=None,
        description="None means unknown — assume the whole record was read (§6.3)",
    )
    field_delta: dict[str, tuple[str | None, str | None]] = Field(default_factory=dict)
    ingest: IngestSummary | None = None
    occurred_at: AwareDatetime | None = None
    inputs: list[CanonicalRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _ingest_payload_matches_the_action(self) -> "AuditEvent":
        is_ingest = self.action in (
            AuditAction.INGEST_STARTED,
            AuditAction.INGEST_COMPLETED,
            AuditAction.INGEST_FAILED,
        )
        if self.ingest is not None and not is_ingest:
            raise ValueError(f"ingest payload is only valid on ingest actions, not {self.action}")
        if self.ingest is None and is_ingest:
            raise ValueError(f"{self.action} requires an ingest payload")
        return self
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_infrastructure.py -q`
Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities tests/entities
git commit -m "feat: SourceReference, DataQualityFlag and AuditEvent"
```

---

### Task 13: Lineage — depth and the retraction cascade (§6.19)

`Provenance` enforces what one record knows about itself (Task 8). The part needing the
parents lives here: computing `depth`, and raising `PARENT_RETRACTED` on every record
that named a now-retracted parent. Without the cascade, `derived_from` is documentation.

**Files:**
- Create: `src/pai3/lineage.py`
- Test: `tests/test_lineage.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lineage.py
from datetime import UTC, datetime

import pytest

from pai3.enums import FlagCode, ProvenanceOrigin, RecordStatus, Severity
from pai3.ids import CanonicalRef, new_id
from pai3.lineage import DepthTooGreat, compute_depth, retraction_cascade
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
CLINICIAN = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")


def _prov(depth: int = 0, parents: list[CanonicalRef] | None = None) -> Provenance:
    parents = parents or []
    return Provenance(
        origin=ProvenanceOrigin.HUMAN if not parents else ProvenanceOrigin.AI_INFERENCE,
        asserted_by=CLINICIAN,
        asserted_at=NOW,
        derived_from=parents,
        depth=depth,
    )


def test_no_parents_means_depth_zero():
    assert compute_depth([]) == 0


def test_one_root_parent_means_depth_one():
    assert compute_depth([_prov(0)]) == 1


def test_depth_follows_the_deepest_parent():
    assert compute_depth([_prov(0), _prov(1, [CanonicalRef(entity_type="C", entity_id="x", version=1)])]) == 2


def test_inference_beyond_the_cap_is_refused_at_computation():
    deep = _prov(1, [CanonicalRef(entity_type="C", entity_id="x", version=1)])
    with pytest.raises(DepthTooGreat):
        compute_depth([deep], origin=ProvenanceOrigin.AI_INFERENCE)


def test_a_human_may_assert_from_a_deep_parent():
    # The cap constrains AI inference, not a clinician reading the chart.
    deep = _prov(1, [CanonicalRef(entity_type="C", entity_id="x", version=1)])
    assert compute_depth([deep], origin=ProvenanceOrigin.HUMAN) == 2


def test_cascade_flags_every_child_of_a_retracted_record():
    parent_id = new_id("cond")
    children = [
        ("Condition", new_id("cond"), [CanonicalRef(entity_type="Condition", entity_id=parent_id, version=1)]),
        ("LabResult", new_id("lab"), [CanonicalRef(entity_type="Condition", entity_id=parent_id, version=1)]),
    ]
    flags = retraction_cascade(
        retracted_id=parent_id,
        children=children,
        patient_id=new_id("pat"),
        actor=CLINICIAN,
        now=NOW,
    )
    assert len(flags) == 2
    assert all(f.code is FlagCode.PARENT_RETRACTED for f in flags)
    assert all(f.severity is Severity.BLOCKING for f in flags)


def test_cascade_ignores_records_that_name_a_different_parent():
    flags = retraction_cascade(
        retracted_id=new_id("cond"),
        children=[
            ("Condition", new_id("cond"), [CanonicalRef(entity_type="Condition", entity_id=new_id("cond"), version=1)])
        ],
        patient_id=new_id("pat"),
        actor=CLINICIAN,
        now=NOW,
    )
    assert flags == []


def test_cascade_flag_targets_the_child_not_the_parent():
    parent_id, child_id = new_id("cond"), new_id("lab")
    flags = retraction_cascade(
        retracted_id=parent_id,
        children=[("LabResult", child_id, [CanonicalRef(entity_type="Condition", entity_id=parent_id, version=1)])],
        patient_id=new_id("pat"),
        actor=CLINICIAN,
        now=NOW,
    )
    assert flags[0].targets[0].entity_id == child_id


def test_retracted_status_is_what_triggers_a_cascade():
    assert RecordStatus.ENTERED_IN_ERROR.value == "entered_in_error"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_lineage.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.lineage'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/lineage.py
"""Depth and retraction, the two halves of §6.19 that need to see the parents.

`depth` is stored rather than derived on read, and that does not contradict §6.13's
refusal to store derived values: it is computed once from parents named *by version*,
and a named version never changes, so it cannot go stale. The gain is that "everything
deeper than one, pending review" is a single filter rather than a recursive walk.
"""

from datetime import datetime

from pai3.entities.infrastructure import DataQualityFlag, FlagTarget
from pai3.enums import FlagCode, ProvenanceOrigin, Severity
from pai3.ids import CanonicalRef, new_id
from pai3.values.actor import Actor
from pai3.values.provenance import AI_INFERENCE_MAX_DEPTH, Provenance


class DepthTooGreat(ValueError):
    """Raised when an ai_inference would exceed the §6.19 cap."""


def compute_depth(
    parents: list[Provenance],
    origin: ProvenanceOrigin = ProvenanceOrigin.HUMAN,
) -> int:
    """`0` with no parents, otherwise one past the deepest parent.

    The cap applies only to AI inference. A clinician reading the chart and asserting
    something from it is `human`, and no ceiling applies to a person's judgement.
    """
    if not parents:
        return 0
    depth = 1 + max(p.depth for p in parents)
    if origin is ProvenanceOrigin.AI_INFERENCE and depth > AI_INFERENCE_MAX_DEPTH:
        raise DepthTooGreat(
            f"ai_inference would reach depth {depth}; the cap is {AI_INFERENCE_MAX_DEPTH}. "
            "AI may reason from documents and first-generation facts, not from inferences."
        )
    return depth


def retraction_cascade(
    retracted_id: str,
    children: list[tuple[str, str, list[CanonicalRef]]],
    patient_id: str,
    actor: Actor,
    now: datetime,
) -> list[DataQualityFlag]:
    """Flag every record that reasoned from a record just marked entered_in_error.

    `children` is `(entity_type, entity_id, derived_from)` for the candidate records —
    passed in rather than queried, so this stays a pure function the caller can test.

    Severity is BLOCKING on §9.1's meaning: the derived fact may still be true, but its
    basis is gone, so no autonomous conclusion may rest on it until a human has looked.
    """
    flags: list[DataQualityFlag] = []
    for entity_type, entity_id, parents in children:
        if not any(ref.entity_id == retracted_id for ref in parents):
            continue
        flags.append(
            DataQualityFlag(
                id=new_id("flag"),
                provenance=Provenance(
                    origin=ProvenanceOrigin.SYSTEM_DERIVED,
                    asserted_by=actor,
                    asserted_at=now,
                ),
                created_at=now,
                updated_at=now,
                updated_by=actor,
                patient_id=patient_id,
                code=FlagCode.PARENT_RETRACTED,
                severity=Severity.BLOCKING,
                message=(
                    f"{entity_type} {entity_id} was derived from {retracted_id}, "
                    "which has been marked entered_in_error"
                ),
                targets=[FlagTarget(entity_type=entity_type, entity_id=entity_id)],
            )
        )
    return flags
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/test_lineage.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/lineage.py tests/test_lineage.py
git commit -m "feat: depth computation and retraction cascade"
```

---

### Task 14: `Patient` (§6.12)

`identifiers` is a list, not `mrn: str` — a concierge practice pulls from several EMRs
and one patient has several MRNs, which §6.12 names as the primary cause of duplicate
patient records. Contacts and addresses are embedded: read with the patient every time,
never queried alone.

**Files:**
- Create: `src/pai3/entities/people.py`
- Test: `tests/entities/test_patient.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_patient.py
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.people import CareTeamMembership, Patient
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.people import Address, ContactPoint, HumanName, PatientIdentifier
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
STAFF = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="M. Chen")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=STAFF, asserted_at=NOW)


def _patient(**over) -> Patient:
    kwargs = {
        "id": new_id("pat"),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": STAFF,
        "names": [HumanName(given=["Dana"], family="Okafor")],
        "birth_date": date(1979, 4, 2),
        "sex_at_birth": "female",
        "identifiers": [PatientIdentifier(system="emr-west", value="MRN-4471")],
    }
    return Patient(**(kwargs | over))


def test_patient_holds_several_identifiers():
    patient = _patient(
        identifiers=[
            PatientIdentifier(system="emr-west", value="MRN-4471"),
            PatientIdentifier(system="lab-portal", value="LP-99812"),
        ]
    )
    assert len(patient.identifiers) == 2


def test_at_least_one_identifier_is_required():
    # D5: "Patient must have a durable patient identifier" — a layer-1 invariant.
    with pytest.raises(ValidationError, match="identifier"):
        _patient(identifiers=[])


def test_at_least_one_name_is_required():
    with pytest.raises(ValidationError):
        _patient(names=[])


def test_patient_is_not_patient_scoped():
    # Its own id is the scope (§2.4).
    assert "patient_id" not in Patient.model_fields


def test_age_is_derived_not_stored():
    # §10.4 gives the AI projection age and not date of birth.
    patient = _patient(birth_date=date(1979, 4, 2))
    assert patient.age_years(datetime(2026, 4, 1, tzinfo=UTC).date()) == 46
    assert patient.age_years(datetime(2026, 4, 2, tzinfo=UTC).date()) == 47


def test_contacts_and_addresses_are_embedded_lists():
    patient = _patient(
        contacts=[ContactPoint(system="phone", value="+1-555-0100")],
        addresses=[Address(lines=["12 Rue Haute"], city="Lyon", country="FR")],
    )
    assert patient.contacts and patient.addresses


def test_care_team_membership_marks_the_primary():
    patient = _patient(
        care_team=[
            CareTeamMembership(provider_id=new_id("prov"), role="internist", is_primary=True)
        ]
    )
    assert patient.care_team[0].is_primary
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_patient.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.entities.people'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/entities/people.py
"""Patient and Provider.

Patient inherits CanonicalRecord rather than PatientScoped because its own id is the
scope. Provider does too, for a reason that is governance and not tidiness: a provider
record is not covered by any patient's consent scope and is not part of a patient data
export (§2.4).
"""

from datetime import date

from pydantic import BaseModel, Field, model_validator

from pai3.base import CanonicalRecord
from pai3.values.people import (
    Address,
    ContactPoint,
    HumanName,
    PatientIdentifier,
    Preferences,
)


class CareTeamMembership(BaseModel):
    """Embedded on Patient: a membership is read with the patient, never alone (§5)."""

    provider_id: str
    role: str
    since: date | None = None
    is_primary: bool = False


class Patient(CanonicalRecord):
    identifiers: list[PatientIdentifier] = Field(min_length=1)
    names: list[HumanName] = Field(min_length=1)
    birth_date: date | None = None
    sex_at_birth: str | None = None
    gender_identity: str | None = None
    contacts: list[ContactPoint] = Field(default_factory=list)
    addresses: list[Address] = Field(default_factory=list)
    preferences: Preferences | None = None
    care_team: list[CareTeamMembership] = Field(default_factory=list)

    @model_validator(mode="after")
    def _identifier_values_are_present(self) -> "Patient":
        if any(not i.value.strip() for i in self.identifiers):
            raise ValueError("every patient identifier needs a value")
        return self

    def age_years(self, on: date) -> int | None:
        """Derived, never stored. §10.4's projection carries this and not birth_date."""
        if self.birth_date is None:
            return None
        had_birthday = (on.month, on.day) >= (self.birth_date.month, self.birth_date.day)
        return on.year - self.birth_date.year - (0 if had_birthday else 1)


class Provider(CanonicalRecord):
    """Practice reference data: prescriber, note author, lab orderer.

    Normalised rather than a free-text name on each record, so that "every medication
    prescribed by Dr X" is answerable and names do not drift into
    "J. Smith" / "John Smith MD" (§5).
    """

    name: HumanName
    identifiers: list[PatientIdentifier] = Field(default_factory=list)
    specialty: str | None = None
    is_external: bool = False
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_patient.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities/people.py tests/entities/test_patient.py
git commit -m "feat: Patient with multiple identifiers, and Provider"
```

---

### Task 15: `Condition` and `AllergyIntolerance` (§6.4)

One `Condition` entity for both medical history and current diagnoses: they differ by
`clinical_status` alone, and two entities would let the same diabetes exist as a history
row and a current row that diverge at the first update. `verification_status` is
independent, so that "suspected lupus" cannot enter a summary as "has lupus".

**Files:**
- Create: `src/pai3/entities/clinical.py`
- Test: `tests/entities/test_clinical.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_clinical.py
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.clinical import AllergyIntolerance, Condition, Criticality, Reaction
from pai3.enums import ClinicalStatus, ProvenanceOrigin, VerificationStatus
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)
PATIENT = new_id("pat")


def _base(prefix: str) -> dict:
    return {
        "id": new_id(prefix),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": DOC,
        "patient_id": PATIENT,
    }


def test_history_and_current_differ_only_by_clinical_status():
    current = Condition(
        **_base("cond"),
        code=CodeableConcept(raw_text="type 2 diabetes", system="ICD-10", code="E11"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    past = current.model_copy(update={"clinical_status": ClinicalStatus.RESOLVED})
    assert current.code == past.code


def test_verification_status_is_independent_of_clinical_status():
    suspected = Condition(
        **_base("cond"),
        code=CodeableConcept(raw_text="lupus"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.PROVISIONAL,
    )
    assert suspected.clinical_status is ClinicalStatus.ACTIVE
    assert not suspected.is_assertable


def test_a_confirmed_active_condition_is_assertable():
    condition = Condition(
        **_base("cond"),
        code=CodeableConcept(raw_text="hypertension", system="ICD-10", code="I10"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    assert condition.is_assertable


def test_a_refuted_condition_is_never_assertable():
    condition = Condition(
        **_base("cond"),
        code=CodeableConcept(raw_text="lupus"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.REFUTED,
    )
    assert not condition.is_assertable


def test_abatement_before_onset_is_refused():
    with pytest.raises(ValidationError, match="abatement"):
        Condition(
            **_base("cond"),
            code=CodeableConcept(raw_text="flu"),
            clinical_status=ClinicalStatus.RESOLVED,
            verification_status=VerificationStatus.CONFIRMED,
            onset=date(2026, 2, 1),
            abatement=date(2026, 1, 1),
        )


def test_condition_whitelists_clinical_status_for_field_provenance():
    # §6.2: this is exactly where conditions conflict — resolved in the EMR
    # against active in the intake form.
    assert Condition.FIELD_PROVENANCE_WHITELIST == frozenset({"clinical_status"})


def test_criticality_is_separate_from_reaction_severity():
    # §6: "is it life-threatening" is not "how bad was the last reaction".
    allergy = AllergyIntolerance(
        **_base("alg"),
        substance=CodeableConcept(raw_text="penicillin", system="RxNorm", code="7980"),
        criticality=Criticality.HIGH,
        verification_status=VerificationStatus.CONFIRMED,
        reactions=[Reaction(manifestation=CodeableConcept(raw_text="hives"), severity="mild")],
    )
    assert allergy.criticality is Criticality.HIGH
    assert allergy.reactions[0].severity == "mild"


def test_allergy_requires_a_substance():
    with pytest.raises(ValidationError):
        AllergyIntolerance(
            **_base("alg"),
            criticality=Criticality.LOW,
            verification_status=VerificationStatus.CONFIRMED,
        )


def test_an_unconfirmed_allergy_is_not_assertable_but_is_never_dropped():
    # §10.6 makes allergies non-droppable regardless of verification status.
    allergy = AllergyIntolerance(
        **_base("alg"),
        substance=CodeableConcept(raw_text="sulfa"),
        criticality=Criticality.UNABLE_TO_ASSESS,
        verification_status=VerificationStatus.UNCONFIRMED,
    )
    assert not allergy.is_assertable
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_clinical.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.entities.clinical'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/entities/clinical.py
"""Coded clinical statements, and the small entities that sit beside them.

Encounter, Procedure, Goal and SocialFactor arrive in Phases 2 and 3; this file holds
them all because they change together as the coding approach changes.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from pai3.base import ClinicalRecord
from pai3.enums import ClinicalStatus, VerificationStatus
from pai3.values.codeable import CodeableConcept

_NOT_ASSERTABLE = {VerificationStatus.REFUTED, VerificationStatus.PROVISIONAL,
                   VerificationStatus.DIFFERENTIAL, VerificationStatus.UNCONFIRMED}


class Condition(ClinicalRecord):
    """Medical history and current diagnoses in one entity (§6.4)."""

    FIELD_PROVENANCE_WHITELIST = frozenset({"clinical_status"})

    code: CodeableConcept
    clinical_status: ClinicalStatus
    verification_status: VerificationStatus
    onset: date | None = None
    abatement: date | None = None
    recorded_by: str | None = Field(default=None, description="Provider id")

    @model_validator(mode="after")
    def _abatement_follows_onset(self) -> "Condition":
        if self.onset and self.abatement and self.abatement < self.onset:
            raise ValueError("abatement precedes onset")
        return self

    @property
    def is_assertable(self) -> bool:
        """Whether a summary may state this as fact.

        Only a confirmed condition qualifies. Everything else is a hypothesis, and
        §6.4 exists so that a hypothesis cannot be rendered as a diagnosis.
        """
        return self.verification_status not in _NOT_ASSERTABLE


class Criticality(StrEnum):
    """Potential for a life-threatening reaction — not the severity of a past one."""

    LOW = "low"
    HIGH = "high"
    UNABLE_TO_ASSESS = "unable_to_assess"


class Reaction(BaseModel):
    manifestation: CodeableConcept
    severity: str | None = None
    occurred: date | None = None


class AllergyIntolerance(ClinicalRecord):
    """Never embedded on Patient.

    The most safety-critical list in the model needs its own audit trail, and §10.6
    makes it non-droppable from any projection regardless of verification status.
    """

    substance: CodeableConcept
    criticality: Criticality
    verification_status: VerificationStatus
    reactions: list[Reaction] = Field(default_factory=list)
    recorded_by: str | None = None

    @property
    def is_assertable(self) -> bool:
        return self.verification_status not in _NOT_ASSERTABLE
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_clinical.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities/clinical.py tests/entities/test_clinical.py
git commit -m "feat: Condition and AllergyIntolerance"
```

---

### Task 16: `Medication` (§6.7)

Split from `Supplement` on trust presumption: a drug was asserted by a prescriber, a
supplement is self-reported. `status` and `dose` are the field-provenance whitelist,
because the EMR and the intake form disagree about exactly those two.

**Files:**
- Create: `src/pai3/entities/therapy.py`
- Test: `tests/entities/test_therapy.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_therapy.py
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.therapy import Medication, MedicationStatus
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)


def _med(**over) -> Medication:
    kwargs = {
        "id": new_id("med"),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": DOC,
        "patient_id": new_id("pat"),
        "drug": CodeableConcept(raw_text="metformin", system="RxNorm", code="6809"),
        "dosage": Dosage(text="500 mg BID", amount=500.0, unit="mg", frequency="BID"),
        "status": MedicationStatus.ACTIVE,
    }
    return Medication(**(kwargs | over))


def test_an_active_medication_is_current():
    assert _med().is_current


def test_a_stopped_medication_is_not_current():
    # D5: discontinued medications must not be treated as active without review.
    assert not _med(status=MedicationStatus.STOPPED, stopped_on=date(2026, 1, 9)).is_current


def test_a_stopped_medication_needs_a_stop_date():
    with pytest.raises(ValidationError, match="stopped_on"):
        _med(status=MedicationStatus.STOPPED)


def test_a_stop_date_on_an_active_medication_is_refused():
    # This is exactly the "discontinued shown as active" defect, caught at layer 1.
    with pytest.raises(ValidationError, match="stopped_on"):
        _med(status=MedicationStatus.ACTIVE, stopped_on=date(2026, 1, 9))


def test_stop_before_start_is_refused():
    with pytest.raises(ValidationError, match="stopped_on"):
        _med(
            status=MedicationStatus.STOPPED,
            started_on=date(2026, 2, 1),
            stopped_on=date(2026, 1, 1),
        )


def test_dose_and_status_are_the_whitelist():
    assert Medication.FIELD_PROVENANCE_WHITELIST == frozenset({"dose", "status"})


def test_prescriber_is_a_provider_reference_not_a_name():
    med = _med(prescriber_id=new_id("prov"))
    assert med.prescriber_id.startswith("prov_")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_therapy.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.entities.therapy'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/entities/therapy.py
"""Medication, Supplement and TreatmentPlan.

Medication and Supplement are separate entities on an axis of trust rather than field
overlap (§6.7): a drug was asserted by a prescriber, a supplement is self-reported, has
no reliable numeric dose, usually has no RxNorm code, and is checked for interactions
against a different knowledge base. Supplement and TreatmentPlan arrive in Phase 2.
"""

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from pai3.base import ClinicalRecord
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage


class MedicationStatus(StrEnum):
    ACTIVE = "active"
    HELD = "held"
    STOPPED = "stopped"
    COMPLETED = "completed"


class Medication(ClinicalRecord):
    FIELD_PROVENANCE_WHITELIST = frozenset({"dose", "status"})

    drug: CodeableConcept
    dosage: Dosage
    status: MedicationStatus
    started_on: date | None = None
    stopped_on: date | None = None
    prescriber_id: str | None = Field(default=None, description="Provider id")
    indication: str | None = None

    @model_validator(mode="after")
    def _stop_date_agrees_with_status(self) -> "Medication":
        ended = self.status in (MedicationStatus.STOPPED, MedicationStatus.COMPLETED)
        if ended and self.stopped_on is None:
            raise ValueError(f"status {self.status} requires stopped_on")
        if not ended and self.stopped_on is not None:
            raise ValueError(
                f"stopped_on is set but status is {self.status}; "
                "a discontinued medication must not present as active"
            )
        if self.started_on and self.stopped_on and self.stopped_on < self.started_on:
            raise ValueError("stopped_on precedes started_on")
        return self

    @property
    def is_current(self) -> bool:
        """§10.6 makes a current medication non-droppable from any projection."""
        return self.status in (MedicationStatus.ACTIVE, MedicationStatus.HELD)
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_therapy.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities/therapy.py tests/entities/test_therapy.py
git commit -m "feat: Medication with status and stop-date invariants"
```

---

### Task 17: `LabResult` (§6.9)

Two parallel value slots, at most one populated. Not a union: making it discriminated
would need a literal tag on both `Quantity` and `CodeableConcept`, which are shared by
six other entities — the tail wagging the dog. `biomarker.raw_text` and
`collection_date` are layer-1 invariants; `quantity` and `unit` are layer 2, so an
unresolved conflict leaves the slot empty with a flag rather than losing the record
(§9.2).

**Files:**
- Create: `src/pai3/entities/results.py`
- Test: `tests/entities/test_results.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_results.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.results import LabResult
from pai3.enums import Interpretation, ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity, ReferenceRange

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")
PROV = Provenance(origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=LAB, asserted_at=NOW)


def _lab(**over) -> LabResult:
    kwargs = {
        "id": new_id("lab"),
        "provenance": PROV,
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": LAB,
        "patient_id": new_id("pat"),
        "biomarker": CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3"),
        "collection_date": NOW,
    }
    return LabResult(**(kwargs | over))


def test_biomarker_is_a_layer_one_invariant():
    # A measurement with no analyte name is not a lab result (§9.2).
    with pytest.raises(ValidationError):
        LabResult(
            id=new_id("lab"), provenance=PROV, created_at=NOW, updated_at=NOW,
            updated_by=LAB, patient_id=new_id("pat"), collection_date=NOW,
        )


def test_collection_date_is_a_layer_one_invariant():
    # Without a date it cannot be placed on a timeline or trended.
    with pytest.raises(ValidationError):
        LabResult(
            id=new_id("lab"), provenance=PROV, created_at=NOW, updated_at=NOW,
            updated_by=LAB, patient_id=new_id("pat"),
            biomarker=CodeableConcept(raw_text="TSH"),
        )


def test_an_empty_value_slot_is_legal():
    # An unresolved conflict leaves the slot empty with a blocking flag (§9.3).
    result = _lab()
    assert result.quantity is None and result.coded_value is None
    assert not result.has_value


def test_a_quantity_alone_is_legal():
    assert _lab(quantity=Quantity(value=2.1, unit="mIU/L")).has_value


def test_a_coded_value_alone_is_legal():
    assert _lab(coded_value=CodeableConcept(raw_text="positive")).has_value


def test_both_slots_populated_is_refused():
    with pytest.raises(ValidationError, match="at most one"):
        _lab(
            quantity=Quantity(value=2.1, unit="mIU/L"),
            coded_value=CodeableConcept(raw_text="positive"),
        )


def test_a_missing_unit_is_accepted_and_left_for_layer_two():
    # D5 says review, not reject.
    assert _lab(quantity=Quantity(value=2.1)).quantity.unit is None


def test_reported_interpretation_is_kept_as_the_lab_sent_it():
    result = _lab(
        quantity=Quantity(value=9.0, unit="mIU/L"),
        reported_interpretation=CodeableConcept(raw_text="H"),
    )
    assert result.reported_interpretation.raw_text == "H"


def test_computed_interpretation_uses_the_comparator_table():
    result = _lab(
        quantity=Quantity(value=0.01, unit="mIU/L", comparator="<"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
    )
    assert result.computed_interpretation is Interpretation.LOW


def test_computed_interpretation_is_indeterminate_without_a_value():
    assert _lab().computed_interpretation is Interpretation.INDETERMINATE


def test_display_interpretation_prefers_what_the_lab_said():
    # §9.5: the lab vouched for its H; ours depends on the range we stored.
    result = _lab(
        quantity=Quantity(value=2.1, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
        reported_interpretation=CodeableConcept(raw_text="H"),
    )
    assert result.display_interpretation == ("H", "reported")


def test_display_interpretation_falls_back_to_computed_and_says_so():
    result = _lab(
        quantity=Quantity(value=2.1, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
    )
    assert result.display_interpretation == ("normal", "computed")


def test_quantity_is_the_whitelisted_field():
    # §6.2: keys are top-level field names, so it is `quantity`, not `quantity.value`.
    assert LabResult.FIELD_PROVENANCE_WHITELIST == frozenset({"quantity"})
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_results.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.entities.results'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/entities/results.py
"""DiagnosticReport, LabResult and VitalSign.

Labs and vitals stay separate (§6.6) because their validation severities genuinely
differ — a lab without a unit is a layer-2 flag, a blood pressure without a cuff size is
an acceptable missing value — and merging would make the validator branch on category to
decide that. DiagnosticReport and VitalSign arrive in Phase 2.
"""

from pydantic import AwareDatetime, Field, model_validator

from pai3.base import ClinicalRecord
from pai3.enums import Interpretation
from pai3.interpretation import interpret
from pai3.values.codeable import CodeableConcept
from pai3.values.quantity import Quantity, ReferenceRange


class LabResult(ClinicalRecord):
    """One analyte.

    The value lives in one of two parallel slots rather than a union, because a
    discriminated union would require a literal tag field on both `Quantity` and
    `CodeableConcept`, which six other entities share (§6.9).
    """

    FIELD_PROVENANCE_WHITELIST = frozenset({"quantity"})

    biomarker: CodeableConcept
    collection_date: AwareDatetime
    quantity: Quantity | None = None
    coded_value: CodeableConcept | None = Field(
        default=None, description="positive, negative, trace"
    )
    reference_range: ReferenceRange | None = None
    reported_interpretation: CodeableConcept | None = Field(
        default=None, description="The lab's own H / L / HH / A — a source fact (§9.5)"
    )
    specimen: str | None = None
    performing_lab: str | None = None
    ordering_provider_id: str | None = None
    report_id: str | None = Field(default=None, description="DiagnosticReport id (§6.8)")

    @model_validator(mode="after")
    def _at_most_one_value_slot(self) -> "LabResult":
        if self.quantity is not None and self.coded_value is not None:
            raise ValueError("at most one of quantity and coded_value may be populated")
        return self

    @property
    def has_value(self) -> bool:
        """False for an unresolved conflict or a failed extraction — the flag says which."""
        return self.quantity is not None or self.coded_value is not None

    @property
    def computed_interpretation(self) -> Interpretation:
        """Ours, derived from the stored range (§9.5). Never overwrites the lab's."""
        if self.quantity is None:
            return Interpretation.INDETERMINATE
        return interpret(self.quantity, self.reference_range)

    @property
    def display_interpretation(self) -> tuple[str, str] | None:
        """What a read-model shows, and where it came from.

        The lab's reading wins when present: ours depends on which reference range we
        stored, which is exactly what a disagreement puts in doubt (§9.5).
        """
        if self.reported_interpretation is not None:
            return (self.reported_interpretation.raw_text, "reported")
        computed = self.computed_interpretation
        if computed is Interpretation.INDETERMINATE:
            return None
        return (computed.value, "computed")
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_results.py -q`
Expected: `13 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities/results.py tests/entities/test_results.py
git commit -m "feat: LabResult with two parallel value slots"
```

---

### Task 18: Layer-2 validation — the checks that raise flags (§9.1)

Layer 1 is the Pydantic validators already written: the record is never created. Layer 2
runs over records that *do* exist and marks them, so the lab stays visible in canonical
while the defect is actionable.

**Files:**
- Create: `src/pai3/validation.py`
- Test: `tests/test_validation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_validation.py
from datetime import UTC, date, datetime

from pai3.entities.clinical import Condition
from pai3.entities.results import LabResult
from pai3.entities.therapy import Medication, MedicationStatus
from pai3.enums import (
    ClinicalStatus,
    FlagCode,
    ProvenanceOrigin,
    Severity,
    VerificationStatus,
)
from pai3.ids import new_id
from pai3.validation import check_condition, check_lab_result, check_medication
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity, ReferenceRange

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": DOC}


def _lab(**over) -> LabResult:
    kwargs = {
        "id": new_id("lab"), **BASE, "patient_id": new_id("pat"),
        "biomarker": CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3"),
        "collection_date": NOW,
    }
    return LabResult(**(kwargs | over))


def _codes(flags) -> set[FlagCode]:
    return {f.code for f in flags}


def test_a_complete_lab_raises_nothing():
    lab = _lab(
        quantity=Quantity(value=2.1, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
    )
    assert check_lab_result(lab, DOC, NOW) == []


def test_a_missing_unit_is_human_review_required():
    flags = check_lab_result(_lab(quantity=Quantity(value=2.1)), DOC, NOW)
    assert FlagCode.MISSING_UNIT in _codes(flags)
    assert all(f.severity is Severity.HUMAN_REVIEW_REQUIRED for f in flags
               if f.code is FlagCode.MISSING_UNIT)


def test_a_missing_reference_range_is_a_warning():
    flags = check_lab_result(_lab(quantity=Quantity(value=2.1, unit="mIU/L")), DOC, NOW)
    missing = [f for f in flags if f.code is FlagCode.MISSING_REFERENCE_RANGE]
    assert missing and missing[0].severity is Severity.WARNING


def test_an_uncoded_biomarker_is_human_review_required():
    lab = _lab(
        biomarker=CodeableConcept(raw_text="thyroid thing"),
        quantity=Quantity(value=2.1, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
    )
    assert FlagCode.UNCODED_CONCEPT in _codes(check_lab_result(lab, DOC, NOW))


def test_interpretation_disagreement_is_flagged():
    lab = _lab(
        quantity=Quantity(value=2.1, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
        reported_interpretation=CodeableConcept(raw_text="H"),
    )
    assert FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE in _codes(
        check_lab_result(lab, DOC, NOW)
    )


def test_agreement_is_not_flagged():
    lab = _lab(
        quantity=Quantity(value=9.0, unit="mIU/L"),
        reference_range=ReferenceRange(low=0.4, high=4.0),
        reported_interpretation=CodeableConcept(raw_text="H"),
    )
    assert FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE not in _codes(
        check_lab_result(lab, DOC, NOW)
    )


def test_an_empty_value_slot_is_not_itself_flagged_here():
    # The flag for an unresolved conflict is raised by the normaliser that found the
    # conflict, with both candidates attached (§9.3). Absence alone proves nothing.
    assert FlagCode.CONFLICTING_VALUES not in _codes(check_lab_result(_lab(), DOC, NOW))


def test_an_uncoded_condition_is_flagged():
    condition = Condition(
        id=new_id("cond"), **BASE, patient_id=new_id("pat"),
        code=CodeableConcept(raw_text="high bp"),
        clinical_status=ClinicalStatus.ACTIVE,
        verification_status=VerificationStatus.CONFIRMED,
    )
    assert FlagCode.UNCODED_CONCEPT in _codes(check_condition(condition, DOC, NOW))


def test_a_stopped_medication_with_no_prescriber_is_not_flagged_as_active():
    med = Medication(
        id=new_id("med"), **BASE, patient_id=new_id("pat"),
        drug=CodeableConcept(raw_text="metformin", system="RxNorm", code="6809"),
        dosage=Dosage(text="500 mg BID"),
        status=MedicationStatus.STOPPED, stopped_on=date(2026, 1, 9),
    )
    assert FlagCode.DISCONTINUED_SHOWN_ACTIVE not in _codes(check_medication(med, DOC, NOW))


def test_an_active_medication_with_an_unparsed_dose_is_flagged_for_review():
    med = Medication(
        id=new_id("med"), **BASE, patient_id=new_id("pat"),
        drug=CodeableConcept(raw_text="metformin", system="RxNorm", code="6809"),
        dosage=Dosage(text="as directed"),
        status=MedicationStatus.ACTIVE,
    )
    flags = check_medication(med, DOC, NOW)
    assert FlagCode.MISSING_UNIT in _codes(flags)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_validation.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.validation'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/validation.py
"""Layer-2 checks: the record exists, and these mark what is wrong with it (§9.1).

Layer 1 is the Pydantic validators on each entity — a structurally invalid record is
never created and the flag attaches to the source document instead (§9.7). Layer 2 runs
here, so that a lab with no unit stays visible in canonical rather than vanishing from
every brief and trend.

These functions are pure: they take a record and return flags. Persisting the flags and
closing them is the caller's job.
"""

from datetime import datetime

from pai3.entities.clinical import Condition
from pai3.entities.infrastructure import DataQualityFlag, FlagTarget
from pai3.entities.results import LabResult
from pai3.entities.therapy import Medication
from pai3.enums import FlagCode, ProvenanceOrigin, Severity
from pai3.ids import new_id
from pai3.interpretation import interpretation_disagrees
from pai3.values.actor import Actor
from pai3.values.provenance import Provenance


def _flag(
    code: FlagCode,
    severity: Severity,
    message: str,
    entity_type: str,
    entity_id: str,
    patient_id: str,
    actor: Actor,
    now: datetime,
    field_path: str | None = None,
) -> DataQualityFlag:
    return DataQualityFlag(
        id=new_id("flag"),
        provenance=Provenance(
            origin=ProvenanceOrigin.SYSTEM_DERIVED, asserted_by=actor, asserted_at=now
        ),
        created_at=now,
        updated_at=now,
        updated_by=actor,
        patient_id=patient_id,
        code=code,
        severity=severity,
        message=message,
        targets=[
            FlagTarget(entity_type=entity_type, entity_id=entity_id, field_path=field_path)
        ],
    )


def check_lab_result(lab: LabResult, actor: Actor, now: datetime) -> list[DataQualityFlag]:
    """D5's lab rules, as layer-2 checks.

    An empty value slot is not flagged here. Three different situations present as an
    empty slot, and only the normaliser that produced the record knows which — so the
    flag with its candidates is raised there (§9.3). Absence alone proves nothing.
    """
    out: list[DataQualityFlag] = []
    args = ("LabResult", lab.id, lab.patient_id, actor, now)

    if lab.quantity is not None and lab.quantity.unit is None:
        out.append(
            _flag(
                FlagCode.MISSING_UNIT,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"{lab.biomarker.raw_text}: value {lab.quantity.value} has no unit",
                *args,
                field_path="quantity",
            )
        )
    if lab.quantity is not None and lab.reference_range is None:
        out.append(
            _flag(
                FlagCode.MISSING_REFERENCE_RANGE,
                Severity.WARNING,
                f"{lab.biomarker.raw_text}: no reference range from the performing lab",
                *args,
                field_path="reference_range",
            )
        )
    if not lab.biomarker.is_coded:
        out.append(
            _flag(
                FlagCode.UNCODED_CONCEPT,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"analyte {lab.biomarker.raw_text!r} is not coded",
                *args,
                field_path="biomarker",
            )
        )
    if interpretation_disagrees(lab.reported_interpretation, lab.computed_interpretation):
        out.append(
            _flag(
                FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE,
                Severity.HUMAN_REVIEW_REQUIRED,
                (
                    f"{lab.biomarker.raw_text}: lab reported "
                    f"{lab.reported_interpretation.raw_text!r} but the stored range gives "
                    f"{lab.computed_interpretation.value!r} — the stored range is suspect"
                ),
                *args,
                field_path="reported_interpretation",
            )
        )
    return out


def check_condition(
    condition: Condition, actor: Actor, now: datetime
) -> list[DataQualityFlag]:
    if condition.code.is_coded:
        return []
    return [
        _flag(
            FlagCode.UNCODED_CONCEPT,
            Severity.HUMAN_REVIEW_REQUIRED,
            f"condition {condition.code.raw_text!r} is not coded",
            "Condition",
            condition.id,
            condition.patient_id,
            actor,
            now,
            field_path="code",
        )
    ]


def check_medication(med: Medication, actor: Actor, now: datetime) -> list[DataQualityFlag]:
    """A current medication with no parsed dose cannot be reconciled safely."""
    out: list[DataQualityFlag] = []
    args = ("Medication", med.id, med.patient_id, actor, now)

    if med.is_current and (med.dosage.amount is None or med.dosage.unit is None):
        out.append(
            _flag(
                FlagCode.MISSING_UNIT,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"{med.drug.raw_text}: dose {med.dosage.text!r} has no parsed amount and unit",
                *args,
                field_path="dose",
            )
        )
    if not med.drug.is_coded:
        out.append(
            _flag(
                FlagCode.UNCODED_CONCEPT,
                Severity.HUMAN_REVIEW_REQUIRED,
                f"drug {med.drug.raw_text!r} is not coded",
                *args,
                field_path="drug",
            )
        )
    return out
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/test_validation.py -q`
Expected: `10 passed`

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/pytest -q`
Expected: all tests pass, no errors.

```bash
git add src/pai3/validation.py tests/test_validation.py
git commit -m "feat: layer-2 validation raising data quality flags"
```

**Phase 1 is complete.** The canonical spine exists: identifiers, enums, every value
object, the three tiers, the eight highest-risk entities, provenance lineage with the
inference cap and retraction cascade, comparator-aware interpretation, and layer-2
validation.

---

## Phase 2 — the remaining full-depth entities

`Provider` was built alongside `Patient` in Task 14 because they share a file. The
remaining seven are grouped by the file they live in.

### Task 19: `Encounter` and `Consent`

`Consent` is `PatientScoped` and the gate for the whole AI layer. It carries `revoked_at`
because withdrawal differs from expiry and from `superseded`, and the audit trail has to
tell them apart (§6.11).

**Files:**
- Modify: `src/pai3/entities/clinical.py` (add `Encounter`)
- Create: `src/pai3/entities/administrative.py`
- Test: `tests/entities/test_administrative.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_administrative.py
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from pai3.entities.administrative import Consent
from pai3.entities.clinical import Encounter
from pai3.enums import ConsentScope, ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
STAFF = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="M. Chen")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=STAFF, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": STAFF}


def _consent(**over) -> Consent:
    kwargs = {
        "id": new_id("cons"), **BASE, "patient_id": new_id("pat"),
        "scope": ConsentScope.AI_PROCESSING,
        "effective_from": NOW - timedelta(days=30),
    }
    return Consent(**(kwargs | over))


def test_an_open_ended_consent_is_active():
    assert _consent().is_active_at(NOW)


def test_a_consent_not_yet_in_force_is_inactive():
    assert not _consent(effective_from=NOW + timedelta(days=1)).is_active_at(NOW)


def test_an_expired_consent_is_inactive():
    assert not _consent(effective_until=NOW - timedelta(days=1)).is_active_at(NOW)


def test_a_revoked_consent_is_inactive_even_inside_its_window():
    consent = _consent(revoked_at=NOW - timedelta(days=1), revoked_by=STAFF)
    assert not consent.is_active_at(NOW)


def test_revocation_requires_who_revoked_it():
    with pytest.raises(ValidationError, match="revoked_by"):
        _consent(revoked_at=NOW)


def test_revocation_before_the_window_opens_is_refused():
    with pytest.raises(ValidationError, match="revoked_at"):
        _consent(effective_from=NOW, revoked_at=NOW - timedelta(days=5), revoked_by=STAFF)


def test_consent_has_no_encounter_field():
    # §2.4: Consent is PatientScoped, not ClinicalRecord.
    assert "encounter_id" not in Consent.model_fields


def test_encounter_is_patient_scoped_not_clinical():
    # It *is* the encounter; it does not reference itself.
    assert "encounter_id" not in Encounter.model_fields


def test_encounter_period_must_not_end_before_it_starts():
    with pytest.raises(ValidationError, match="ended_at"):
        Encounter(
            id=new_id("enc"), **BASE, patient_id=new_id("pat"), encounter_type="office visit",
            started_at=NOW, ended_at=NOW - timedelta(hours=1),
        )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_administrative.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.entities.administrative'`

- [ ] **Step 3: Write the implementations**

```python
# src/pai3/entities/administrative.py
"""Consent and Coverage.

Consent is a separate entity rather than a field on Patient because it is an enforcement
point: an agent asks for it before doing anything, and §10.3 turns that question into a
capability token. Embedded, a revocation would bump the patient version and "whose
AI-processing consent expires this month" would be unanswerable. Coverage arrives in
Phase 3.
"""

from datetime import datetime

from pydantic import AwareDatetime, model_validator

from pai3.base import PatientScoped
from pai3.enums import ConsentScope
from pai3.values.actor import Actor


class Consent(PatientScoped):
    scope: ConsentScope
    effective_from: AwareDatetime
    effective_until: AwareDatetime | None = None
    revoked_at: AwareDatetime | None = None
    revoked_by: Actor | None = None
    document_ref: str | None = None

    @model_validator(mode="after")
    def _revocation_is_attributable(self) -> "Consent":
        if self.revoked_at is not None and self.revoked_by is None:
            raise ValueError("revoked_at requires revoked_by")
        if self.revoked_at is not None and self.revoked_at < self.effective_from:
            raise ValueError("revoked_at precedes effective_from")
        if (
            self.effective_until is not None
            and self.effective_until < self.effective_from
        ):
            raise ValueError("effective_until precedes effective_from")
        return self

    def is_active_at(self, moment: datetime) -> bool:
        """Revocation beats the window: a withdrawn consent is inactive at once."""
        if self.revoked_at is not None and moment >= self.revoked_at:
            return False
        if moment < self.effective_from:
            return False
        if self.effective_until is not None and moment > self.effective_until:
            return False
        return True
```

Append to `src/pai3/entities/clinical.py`:

```python
class Encounter(PatientScoped):
    """A visit or contact — the grouping anchor for the pre-visit brief (§4).

    PatientScoped rather than ClinicalRecord: it is the encounter (§2.4).
    """

    encounter_type: str
    started_at: AwareDatetime
    ended_at: AwareDatetime | None = None
    participant_ids: list[str] = Field(default_factory=list)
    reason: CodeableConcept | None = None

    @model_validator(mode="after")
    def _period_is_ordered(self) -> "Encounter":
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at precedes started_at")
        return self
```

Add to the imports at the top of `src/pai3/entities/clinical.py`:

```python
from pydantic import AwareDatetime
from pai3.base import ClinicalRecord, PatientScoped
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_administrative.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities tests/entities/test_administrative.py
git commit -m "feat: Consent with revocation, and Encounter"
```

---

### Task 20: `Supplement` and `TreatmentPlan`

`Supplement` mirrors `Medication` but has no prescriber and no reliable numeric dose.
`TreatmentPlan` embeds its items: they have no lifecycle of their own and are revised as
part of the plan (§5).

**Files:**
- Modify: `src/pai3/entities/therapy.py`
- Test: `tests/entities/test_therapy_phase2.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_therapy_phase2.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.therapy import Supplement, SupplementStatus, TreatmentPlan
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.plan import PlanItem
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
PATIENT_ACTOR = Actor(kind=ActorKind.HUMAN, ref=new_id("pat"), label="Dana Okafor")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=PATIENT_ACTOR, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": PATIENT_ACTOR}


def test_a_supplement_accepts_an_unparseable_dose():
    # "one dropper" has no mg. Refusing it loses the fact that it is being taken.
    supp = Supplement(
        id=new_id("supp"), **BASE, patient_id=new_id("pat"),
        substance=CodeableConcept(raw_text="vitamin D3"),
        dosage=Dosage(text="one dropper daily"),
        status=SupplementStatus.ACTIVE,
    )
    assert supp.dosage.amount is None


def test_a_supplement_has_no_prescriber_field():
    # §6.7: the trust presumption differs — a supplement is self-reported.
    assert "prescriber_id" not in Supplement.model_fields


def test_treatment_plan_embeds_its_items():
    plan = TreatmentPlan(
        id=new_id("plan"), **BASE, patient_id=new_id("pat"), title="Q2 metabolic plan",
        items=[PlanItem(description="Titrate metformin", targets=[new_id("med")])],
    )
    assert plan.items[0].description == "Titrate metformin"


def test_a_plan_needs_at_least_one_item():
    with pytest.raises(ValidationError):
        TreatmentPlan(
            id=new_id("plan"), **BASE, patient_id=new_id("pat"), title="empty", items=[]
        )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_therapy_phase2.py -q`
Expected: `ImportError: cannot import name 'Supplement'`

- [ ] **Step 3: Append to `src/pai3/entities/therapy.py`**

```python
class SupplementStatus(StrEnum):
    ACTIVE = "active"
    STOPPED = "stopped"


class Supplement(ClinicalRecord):
    """Almost always patient-reported (§6.7).

    No prescriber, no reliable numeric dose, usually no RxNorm code. Interaction
    checking against supplements uses a different knowledge base, so every consumer
    would branch on a `kind` discriminator anyway if this were merged with Medication.
    """

    FIELD_PROVENANCE_WHITELIST = frozenset({"dose", "status"})

    substance: CodeableConcept
    dosage: Dosage
    status: SupplementStatus
    started_on: date | None = None
    stopped_on: date | None = None
    reported_reason: str | None = None

    @property
    def is_current(self) -> bool:
        return self.status is SupplementStatus.ACTIVE


class TreatmentPlan(ClinicalRecord):
    """Items are embedded: no independent lifecycle, revised with the plan (§5)."""

    title: str = Field(min_length=1)
    items: list[PlanItem] = Field(min_length=1)
    authored_by: str | None = Field(default=None, description="Provider id")
```

Add to the imports at the top of `src/pai3/entities/therapy.py`:

```python
from pai3.values.plan import PlanItem
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_therapy_phase2.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities/therapy.py tests/entities/test_therapy_phase2.py
git commit -m "feat: Supplement and TreatmentPlan"
```

---

### Task 21: `DiagnosticReport` and `VitalSign`

`DiagnosticReport` groups a panel or an imaging study, so that a fourteen-analyte panel is
not fourteen orphan rows and "the CBC from 12 March" has something to cite (§6.8).
`VitalSign` carries a required `measurement_context`, and §6.6's hard rule is that trend
analysis must be able to filter on it.

**Files:**
- Modify: `src/pai3/entities/results.py`
- Test: `tests/entities/test_results_phase2.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_results_phase2.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.results import DiagnosticReport, VitalSign
from pai3.enums import MeasurementContext, ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity
from pai3.values.text import ClinicalText
from pai3.enums import TextOrigin

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")
PROV = Provenance(origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=LAB, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": LAB}


def test_a_panel_report_groups_its_results():
    report = DiagnosticReport(
        id=new_id("dxr"), **BASE, patient_id=new_id("pat"),
        report_type=CodeableConcept(raw_text="CBC", system="LOINC", code="58410-2"),
        issued_at=NOW, result_ids=[new_id("lab"), new_id("lab")],
    )
    assert len(report.result_ids) == 2


def test_an_imaging_report_carries_narrative_and_no_results():
    report = DiagnosticReport(
        id=new_id("dxr"), **BASE, patient_id=new_id("pat"),
        report_type=CodeableConcept(raw_text="chest X-ray"), issued_at=NOW,
        findings=ClinicalText(value="No focal consolidation.", origin=TextOrigin.EXTERNAL_DOCUMENT),
        impression=ClinicalText(value="Normal study.", origin=TextOrigin.EXTERNAL_DOCUMENT),
    )
    assert report.result_ids == []
    assert report.findings.crossed_perimeter


def test_a_report_with_neither_results_nor_narrative_is_refused():
    # An empty report cites nothing and groups nothing.
    with pytest.raises(ValidationError, match="result_ids"):
        DiagnosticReport(
            id=new_id("dxr"), **BASE, patient_id=new_id("pat"),
            report_type=CodeableConcept(raw_text="CBC"), issued_at=NOW,
        )


def test_narrative_text_must_carry_its_origin():
    with pytest.raises(ValidationError):
        DiagnosticReport(
            id=new_id("dxr"), **BASE, patient_id=new_id("pat"),
            report_type=CodeableConcept(raw_text="chest X-ray"), issued_at=NOW,
            findings="No focal consolidation.",
        )


def test_measurement_context_is_required_on_a_vital():
    with pytest.raises(ValidationError):
        VitalSign(
            id=new_id("vit"), **BASE, patient_id=new_id("pat"),
            kind=CodeableConcept(raw_text="body weight"), measured_at=NOW,
            quantity=Quantity(value=71.2, unit="kg"),
        )


def test_patient_reported_and_clinical_vitals_are_distinguishable():
    # §6.6: home weight and in-clinic weight are never silently averaged.
    home = VitalSign(
        id=new_id("vit"), **BASE, patient_id=new_id("pat"),
        kind=CodeableConcept(raw_text="body weight"), measured_at=NOW,
        quantity=Quantity(value=71.2, unit="kg"),
        measurement_context=MeasurementContext.PATIENT_REPORTED,
    )
    assert home.measurement_context is MeasurementContext.PATIENT_REPORTED
    assert not home.is_clinical


def test_a_vital_without_a_cuff_size_is_acceptable():
    # D5 classifies this as an acceptable missing value, not a defect (§6.6).
    vital = VitalSign(
        id=new_id("vit"), **BASE, patient_id=new_id("pat"),
        kind=CodeableConcept(raw_text="systolic blood pressure"), measured_at=NOW,
        quantity=Quantity(value=128.0, unit="mmHg"),
        measurement_context=MeasurementContext.CLINICAL,
    )
    assert vital.cuff_size is None and vital.is_clinical
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_results_phase2.py -q`
Expected: `ImportError: cannot import name 'DiagnosticReport'`

- [ ] **Step 3: Append to `src/pai3/entities/results.py`**

```python
class DiagnosticReport(ClinicalRecord):
    """A panel or an imaging study as one object (§6.8).

    Imaging is the same entity with narrative and no discrete values, so no separate
    imaging entity is needed.
    """

    report_type: CodeableConcept
    issued_at: AwareDatetime
    result_ids: list[str] = Field(default_factory=list, description="LabResult ids")
    findings: ClinicalText | None = None
    impression: ClinicalText | None = None
    performing_lab: str | None = None

    @model_validator(mode="after")
    def _report_carries_something(self) -> "DiagnosticReport":
        if not self.result_ids and self.findings is None and self.impression is None:
            raise ValueError("a report needs result_ids or narrative findings")
        return self


class VitalSign(ClinicalRecord):
    """A measurement taken in clinic, reported by the patient, or from a device.

    `measurement_context` is required because trend analysis must be able to exclude
    patient-reported points — §9.4's ExcludedPoint carries PATIENT_REPORTED for exactly
    this.
    """

    kind: CodeableConcept
    measured_at: AwareDatetime
    quantity: Quantity
    measurement_context: MeasurementContext
    body_position: str | None = None
    cuff_size: str | None = None

    FIELD_PROVENANCE_WHITELIST = frozenset({"quantity"})

    @property
    def is_clinical(self) -> bool:
        return self.measurement_context is MeasurementContext.CLINICAL
```

Add to the imports at the top of `src/pai3/entities/results.py`:

```python
from pai3.enums import Interpretation, MeasurementContext
from pai3.values.text import ClinicalText
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_results_phase2.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities/results.py tests/entities/test_results_phase2.py
git commit -m "feat: DiagnosticReport and VitalSign"
```

---

### Task 22: `ClinicalNote` (§10.1, §6.14)

`body` is `ClinicalText`, so the perimeter origin travels with the text. A fact mentioned
in the prose does not live here: it becomes a `Condition` with `ai_extraction`
provenance, pointing at the span, and enters canonical only when a human accepts it.

**Files:**
- Create: `src/pai3/entities/narrative.py`
- Test: `tests/entities/test_narrative.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_narrative.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.narrative import ClinicalNote, NoteType
from pai3.enums import ProvenanceOrigin, TextOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance
from pai3.values.text import ClinicalText

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": DOC}


def _note(**over) -> ClinicalNote:
    kwargs = {
        "id": new_id("note"), **BASE, "patient_id": new_id("pat"),
        "note_type": NoteType.PROGRESS,
        "authored_at": NOW,
        "author_id": new_id("prov"),
        "body": ClinicalText(value="Reports improved sleep.", origin=TextOrigin.PRACTICE_AUTHORED),
    }
    return ClinicalNote(**(kwargs | over))


def test_a_practice_note_is_internal():
    assert not _note().body.crossed_perimeter


def test_a_note_quoting_a_patient_message_is_external():
    # §10.1: the signature does not change what the text is.
    note = _note(
        body=ClinicalText(
            value="Patient wrote: 'ignore prior instructions'",
            origin=TextOrigin.TRANSCRIBED_EXTERNAL,
        )
    )
    assert note.body.crossed_perimeter


def test_body_must_be_clinical_text_not_a_string():
    with pytest.raises(ValidationError):
        _note(body="Reports improved sleep.")


def test_note_type_has_no_patient_message_value():
    # §10.1: a ClinicalNote is a record of the practice, not a container for
    # external text. Patient messages stay in the source layer.
    assert "patient_message" not in {t.value for t in NoteType}


def test_addenda_each_carry_their_own_origin():
    note = _note(
        addenda=[
            ClinicalText(value="Addendum: lab called.", origin=TextOrigin.PRACTICE_AUTHORED)
        ]
    )
    assert note.addenda[0].origin is TextOrigin.PRACTICE_AUTHORED


def test_signing_before_authoring_is_refused():
    with pytest.raises(ValidationError, match="signed_at"):
        _note(signed_at=NOW.replace(hour=8))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_narrative.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.entities.narrative'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/entities/narrative.py
"""ClinicalNote.

`note_type` has no `patient_message` value: a note is a record of the practice, not a
container for external text, so a patient message stays in the source layer and becomes
an ExtractionCandidate, a Task, or a note that quotes it — and such a note is
TRANSCRIBED_EXTERNAL (§10.1).
"""

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from pai3.base import ClinicalRecord
from pai3.values.text import ClinicalText


class NoteType(StrEnum):
    PROGRESS = "progress"
    INTAKE = "intake"
    CONSULT = "consult"
    TELEPHONE = "telephone"


class ClinicalNote(ClinicalRecord):
    note_type: NoteType
    authored_at: AwareDatetime
    author_id: str = Field(min_length=1, description="Provider id")
    body: ClinicalText
    addenda: list[ClinicalText] = Field(default_factory=list)
    signed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def _signature_follows_authoring(self) -> "ClinicalNote":
        if self.signed_at is not None and self.signed_at < self.authored_at:
            raise ValueError("signed_at precedes authored_at")
        return self
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_narrative.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/entities/narrative.py tests/entities/test_narrative.py
git commit -m "feat: ClinicalNote with perimeter-marked body"
```

---

## Phase 3 — the thin five

### Task 23: `Coverage`, `Procedure`, `Goal`, `SocialFactor`, `Task`

Four to six fields each. These are administrative dimensions where Phase 1 proves they are
modelled and they can be deepened later (§4). Two tier placements matter: `Goal` is
`PatientScoped` because a patient goal exists before any plan and before any visit, and
`SocialFactor` is `ClinicalRecord` because it is asserted at an encounter and its risk is
staleness — "smoker" recorded in 2019 and never revisited (§6.16).

**Files:**
- Modify: `src/pai3/entities/administrative.py` (add `Coverage`)
- Modify: `src/pai3/entities/clinical.py` (add `Procedure`, `Goal`, `SocialFactor`)
- Create: `src/pai3/entities/workflow.py` (`Task`)
- Test: `tests/entities/test_thin_five.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/entities/test_thin_five.py
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.administrative import Coverage
from pai3.entities.clinical import Goal, Procedure, SocialFactor
from pai3.entities.workflow import Task, TaskOrigin, TaskStatus
from pai3.enums import ProvenanceOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
STAFF = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="M. Chen")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=STAFF, asserted_at=NOW)
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": STAFF}
PATIENT = new_id("pat")


def test_coverage_carries_effective_dates():
    # Concierge practices bill labs through insurance even when membership is self-pay.
    coverage = Coverage(
        id=new_id("cov"), **BASE, patient_id=PATIENT, payer="Meridian Health",
        member_id="MH-88213", effective_from=date(2026, 1, 1),
    )
    assert coverage.payer == "Meridian Health"


def test_goal_is_patient_scoped_with_no_encounter():
    # A goal can exist before any plan and before any visit (§2.4).
    assert "encounter_id" not in Goal.model_fields
    goal = Goal(
        id=new_id("goal"), **BASE, patient_id=PATIENT,
        description="Come off metformin within a year",
    )
    assert goal.status == "active"


def test_social_factor_records_when_it_was_asserted():
    # Its risk is staleness, so a record with a date beats a mutable block (§6.16).
    factor = SocialFactor(
        id=new_id("soc"), **BASE, patient_id=PATIENT,
        factor=CodeableConcept(raw_text="smoking status"), value="former smoker",
        asserted_on=date(2019, 6, 1),
    )
    assert factor.asserted_on.year == 2019


def test_procedure_requires_a_performed_date():
    with pytest.raises(ValidationError):
        Procedure(
            id=new_id("proc"), **BASE, patient_id=PATIENT,
            code=CodeableConcept(raw_text="colonoscopy"),
        )


def test_an_ai_suggested_task_lands_proposed():
    # §4: AI-extracted tasks land proposed, never open and assigned.
    task = Task(
        id=new_id("task"), **BASE, patient_id=PATIENT,
        description="Repeat TSH in six weeks", origin=TaskOrigin.AI_SUGGESTED,
    )
    assert task.status is TaskStatus.PROPOSED


def test_an_ai_suggested_task_may_not_be_opened_and_assigned():
    with pytest.raises(ValidationError, match="ai_suggested"):
        Task(
            id=new_id("task"), **BASE, patient_id=PATIENT,
            description="Repeat TSH", origin=TaskOrigin.AI_SUGGESTED,
            status=TaskStatus.OPEN, assignee_id=new_id("prov"),
        )


def test_a_human_task_may_open_assigned():
    task = Task(
        id=new_id("task"), **BASE, patient_id=PATIENT, description="Call patient",
        origin=TaskOrigin.HUMAN, status=TaskStatus.OPEN, assignee_id=new_id("prov"),
    )
    assert task.status is TaskStatus.OPEN
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/entities/test_thin_five.py -q`
Expected: `ImportError: cannot import name 'Coverage'`

- [ ] **Step 3: Write the implementations**

Append to `src/pai3/entities/administrative.py`:

```python
class Coverage(PatientScoped):
    """Payment context. Thin by design (§4).

    Kept because a concierge practice commonly bills labs and procedures through
    insurance even when membership is self-pay, so "if relevant" in the brief is a scope
    call rather than permission to assume it away.
    """

    payer: str
    member_id: str | None = None
    effective_from: date | None = None
    effective_until: date | None = None
```

Add `from datetime import date` to that file's imports.

Append to `src/pai3/entities/clinical.py`:

```python
class Procedure(ClinicalRecord):
    """Thin (§4)."""

    code: CodeableConcept
    performed_on: date
    performer_id: str | None = None
    outcome: str | None = None


class Goal(PatientScoped):
    """Patient-owned, and outlives any single treatment plan (§2.4)."""

    description: str = Field(min_length=1)
    target_date: date | None = None
    status: str = "active"


class SocialFactor(ClinicalRecord):
    """Smoking, alcohol, sleep, occupation, living situation.

    A record with an assertion date rather than a mutable block on Patient, because the
    whole risk here is staleness and a block has no history (§6.16).
    """

    factor: CodeableConcept
    value: str
    asserted_on: date
```

Create `src/pai3/entities/workflow.py`:

```python
"""Task — follow-ups and workflow state.

An AI-extracted task lands PROPOSED and is never opened and assigned by the pipeline.
Assignment is the human approval step in §10.4's rights matrix.
"""

from datetime import date
from enum import StrEnum

from pydantic import Field, model_validator

from pai3.base import ClinicalRecord


class TaskStatus(StrEnum):
    PROPOSED = "proposed"
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


class TaskOrigin(StrEnum):
    HUMAN = "human"
    AI_SUGGESTED = "ai_suggested"


class Task(ClinicalRecord):
    description: str = Field(min_length=1)
    origin: TaskOrigin
    status: TaskStatus = TaskStatus.PROPOSED
    assignee_id: str | None = None
    due_on: date | None = None
    source_ref: str | None = Field(
        default=None, description="The note or lab this follow-up came from"
    )

    @model_validator(mode="after")
    def _ai_tasks_are_not_self_assigning(self) -> "Task":
        if self.origin is TaskOrigin.AI_SUGGESTED and self.status is not TaskStatus.PROPOSED:
            raise ValueError(
                "an ai_suggested task must stay proposed until a human assigns it"
            )
        return self
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/entities/test_thin_five.py -q`
Expected: `7 passed`

- [ ] **Step 5: Run the whole suite and commit**

Run: `.venv/bin/pytest -q`
Expected: all pass. All 21 canonical entities now exist.

```bash
git add src/pai3/entities tests/entities/test_thin_five.py
git commit -m "feat: the thin five — Coverage, Procedure, Goal, SocialFactor, Task"
```

---

## Phase 4 — AI layer schema

### Task 24: `AIArtifact` and its subtypes (§10.2, §10.5)

D7 requires an AI-generated summary object, so this precedes the deferrable work. Two
fields carry invariants that the type alone does not enforce — `execution` and
`consent_ref` — and both are set by the adapter in Task 27, never by a caller.

**Files:**
- Create: `src/pai3/ai/__init__.py`
- Create: `src/pai3/ai/artifact.py`
- Test: `tests/ai/test_artifact.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ai/test_artifact.py
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.ai.artifact import (
    AIClaim,
    AISummary,
    ArtifactReview,
    ClaimValue,
    Engine,
    ExtractionCandidate,
    GuardrailFailure,
    OmittedRecord,
    OmissionReason,
)
from pai3.ids import CanonicalRef, new_id

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB_REF = CanonicalRef(entity_type="LabResult", entity_id=new_id("lab"), version=1)


def _summary(**over) -> AISummary:
    kwargs = {
        "id": new_id("aia"),
        "patient_id": new_id("pat"),
        "trace_id": new_id("trc"),
        "created_at": NOW,
        "inputs": [LAB_REF],
        "prompt_digest": "sha256:" + "a" * 64,
        "model_id": "llama-3.3-70b-instruct",
        "engine": Engine.OLLAMA,
        "engine_version": "0.5.1",
        "consent_ref": new_id("cons"),
        "claims": [
            AIClaim(
                text="TSH is below the reference range.",
                cites=[LAB_REF],
                values=[ClaimValue(value=0.01, unit="mIU/L", cites=LAB_REF)],
            )
        ],
        "unresolved": [],
    }
    return AISummary(**(kwargs | over))


def test_execution_has_exactly_one_legal_value():
    # §10.2: a cloud run is unrepresentable, not merely discouraged.
    assert _summary().execution == "local"
    with pytest.raises(ValidationError):
        _summary(execution="cloud")


def test_inputs_carry_versions():
    # §10.2: prompt reconstruction holds only while the named versions are unchanged.
    assert _summary().inputs[0].version == 1


def test_the_prompt_itself_is_not_a_field():
    # §10.2: storing it would duplicate PHI outside canonical governance.
    assert "prompt" not in AISummary.model_fields
    assert "prompt_digest" in AISummary.model_fields


def test_model_digest_may_be_absent():
    # Not every engine reports one; None means unknown, on §6.3's semantics.
    assert _summary().model_digest is None


def test_a_claim_must_cite_something():
    with pytest.raises(ValidationError):
        AIClaim(text="TSH is low.", cites=[], values=[])


def test_review_starts_pending():
    assert _summary().review is ArtifactReview.PENDING


def test_a_guardrail_rejection_is_a_review_state():
    artifact = _summary(
        review=ArtifactReview.REJECTED_BY_GUARDRAIL,
        guardrail_failures=[
            GuardrailFailure(check="cites_in_inputs", detail="cited lab_x was never read")
        ],
    )
    assert artifact.guardrail_failures


def test_an_empty_failure_list_is_the_passing_state():
    # §10.5: there is deliberately no guardrails_passed boolean.
    assert _summary().guardrail_failures == []
    assert "guardrails_passed" not in AISummary.model_fields


def test_omitted_records_name_their_reason():
    artifact = _summary(
        omitted=[OmittedRecord(ref=LAB_REF, reason=OmissionReason.CONTEXT_BUDGET)]
    )
    assert artifact.omitted[0].reason is OmissionReason.CONTEXT_BUDGET


def test_an_extraction_candidate_records_what_it_produced():
    # §6.19: the link runs this way because canonical never references the AI layer.
    candidate = ExtractionCandidate(
        id=new_id("aia"), patient_id=new_id("pat"), trace_id=new_id("trc"),
        created_at=NOW, inputs=[LAB_REF], prompt_digest="sha256:" + "b" * 64,
        model_id="llama-3.3-70b-instruct", engine=Engine.LLAMA_CPP,
        engine_version="b4120", consent_ref=new_id("cons"),
        proposed_entity_type="Condition",
        proposed_payload={"code": {"raw_text": "hypothyroidism"}},
    )
    assert candidate.produced == []
    accepted = candidate.model_copy(
        update={"produced": [CanonicalRef(entity_type="Condition", entity_id=new_id("cond"), version=1)]}
    )
    assert accepted.produced[0].entity_type == "Condition"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/ai/test_artifact.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.ai'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/ai/__init__.py
```

```python
# src/pai3/ai/artifact.py
"""The AI layer's own records.

These reference canonical by id and version. Canonical never references back (§1), which
is why `produced` lives here and not as an `artifact_ref` on provenance — the lookup
"which artifact produced this fact" is a query against this layer (§6.19).

`execution` and `consent_ref` are set by the adapter (§10.2, §10.3) and never by a
caller. The type is not what holds those invariants; the absence of a public path that
takes them as arguments is.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from pai3.ids import CanonicalRef
from pai3.values.flags import FlagSummary


class Engine(StrEnum):
    OLLAMA = "ollama"
    LLAMA_CPP = "llama_cpp"
    VLLM = "vllm"
    TRANSFORMERS = "transformers"


class ArtifactReview(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REJECTED_BY_GUARDRAIL = "rejected_by_guardrail"
    SUPERSEDED = "superseded"


class OmissionReason(StrEnum):
    """Why a record in scope did not reach the prompt (§10.6)."""

    CONTEXT_BUDGET = "context_budget"
    OUT_OF_WINDOW = "out_of_window"
    SUPERSEDED = "superseded"
    TOO_LARGE_FOR_BUDGET = "too_large_for_budget"


class OmittedRecord(BaseModel):
    ref: CanonicalRef
    reason: OmissionReason


class GuardrailFailure(BaseModel):
    check: str
    detail: str


class ClaimValue(BaseModel):
    """A number appearing in a claim, structurally, so check 2 can compare it."""

    value: float
    unit: str | None = None
    cites: CanonicalRef


class AIClaim(BaseModel):
    """One assertion with its citations.

    The output is structured rather than prose because over prose none of §10.5's checks
    works: a number extractor that misses one produces a false pass, which is worse than
    no check at all.
    """

    text: str = Field(min_length=1)
    cites: list[CanonicalRef] = Field(min_length=1)
    values: list[ClaimValue] = Field(default_factory=list)


class AIArtifact(BaseModel):
    """What is recorded about one generation (§10.2)."""

    id: str
    patient_id: str
    trace_id: str = Field(min_length=1)
    created_at: AwareDatetime
    inputs: list[CanonicalRef]
    omitted: list[OmittedRecord] = Field(default_factory=list)
    produced: list[CanonicalRef] = Field(
        default_factory=list, description="What was accepted into canonical from this (§6.19)"
    )
    prompt_digest: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    model_digest: str | None = None
    engine: Engine
    engine_version: str = Field(min_length=1)
    execution: Literal["local"] = "local"
    consent_ref: str = Field(min_length=1)
    review: ArtifactReview = ArtifactReview.PENDING
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    guardrail_failures: list[GuardrailFailure] = Field(default_factory=list)


class AISummary(AIArtifact):
    """Generated narrative as a list of cited claims."""

    claims: list[AIClaim] = Field(default_factory=list)
    unresolved: list[FlagSummary] = Field(default_factory=list)


class ExtractionCandidate(AIArtifact):
    """A proposed canonical record, awaiting a human.

    Nothing here is canonical. Acceptance creates the canonical record and records it in
    `produced`.
    """

    proposed_entity_type: str
    proposed_payload: dict
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/ai/test_artifact.py -q`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/ai tests/ai
git commit -m "feat: AI layer artifacts with local-only execution"
```

---

## Phase 5 — the enforcement layer (mandatory, §11 step 5)

Nothing in this phase degrades. An unenforced consent gate is an open door rather than a
`None`; without the guardrails §10.5 is decorative; without `AIPatientView` §10.4 is a
table nothing obeys.

### Task 25: The consent gate as a capability (§10.3)

`AIReadScope` can only be produced by the consent check, and every projection takes one.
"Read a patient's data for a model without checking consent" becomes unexpressible rather
than discouraged.

**Files:**
- Create: `src/pai3/ai/scope.py`
- Test: `tests/ai/test_scope.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ai/test_scope.py
from datetime import UTC, datetime, timedelta

import pytest

from pai3.ai.scope import AIReadScope, ConsentDenied, authorize_ai_read
from pai3.entities.administrative import Consent
from pai3.enums import ConsentScope, ProvenanceOrigin, RecordStatus
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
STAFF = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="M. Chen")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=STAFF, asserted_at=NOW)
PATIENT = new_id("pat")


def _consent(**over) -> Consent:
    kwargs = {
        "id": new_id("cons"), "provenance": PROV, "created_at": NOW, "updated_at": NOW,
        "updated_by": STAFF, "patient_id": PATIENT, "scope": ConsentScope.AI_PROCESSING,
        "effective_from": NOW - timedelta(days=30),
    }
    return Consent(**(kwargs | over))


def test_an_active_ai_consent_yields_a_scope():
    scope = authorize_ai_read(PATIENT, [_consent()], NOW)
    assert scope.consent_id and scope.trace_id
    assert scope.scope == "ai_processing"


def test_no_consent_raises_rather_than_returning_none():
    # §10.3: None invites `if scope:` and the one caller who omits it.
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [], NOW)


def test_a_treatment_consent_does_not_authorise_ai():
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [_consent(scope=ConsentScope.TREATMENT)], NOW)


def test_a_revoked_consent_is_refused():
    revoked = _consent(revoked_at=NOW - timedelta(days=1), revoked_by=STAFF)
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [revoked], NOW)


def test_an_expired_consent_is_refused():
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [_consent(effective_until=NOW - timedelta(days=1))], NOW)


def test_another_patients_consent_is_refused():
    other = _consent(patient_id=new_id("pat"))
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [other], NOW)


def test_a_retracted_consent_record_is_refused():
    retracted = _consent(record_status=RecordStatus.ENTERED_IN_ERROR)
    with pytest.raises(ConsentDenied):
        authorize_ai_read(PATIENT, [retracted], NOW)


def test_the_scope_bounds_its_own_validity():
    scope = authorize_ai_read(PATIENT, [_consent(effective_until=NOW + timedelta(days=1))], NOW)
    assert scope.valid_until <= NOW + timedelta(days=1)


def test_an_open_ended_consent_still_bounds_the_scope():
    # A token good forever is a token nobody re-checks.
    scope = authorize_ai_read(PATIENT, [_consent()], NOW)
    assert scope.valid_until > NOW
    assert scope.valid_until <= NOW + timedelta(hours=1)


def test_the_scope_is_still_valid_helper():
    scope = authorize_ai_read(PATIENT, [_consent()], NOW)
    assert scope.is_valid_at(NOW)
    assert not scope.is_valid_at(NOW + timedelta(days=2))


def test_a_scope_cannot_be_built_for_a_patient_it_does_not_name():
    scope = authorize_ai_read(PATIENT, [_consent()], NOW)
    assert scope.patient_id == PATIENT
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/ai/test_scope.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.ai.scope'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/ai/scope.py
"""The consent gate (§10.3).

`AIReadScope` is a capability: every projection takes one, no overload takes a bare
`patient_id`, and the only way to obtain one is `authorize_ai_read`. That makes reading a
patient's data for a model without a consent check unexpressible rather than merely
discouraged.

It is deliberately not persisted — a stored capability is a forgeable and replayable one.

This gates the AI path only. A physician reading a chart needs `treatment` consent under
different rules including break-glass, and this model does not build general access
control (§10.3).
"""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel

from pai3.entities.administrative import Consent
from pai3.enums import ConsentScope, RecordStatus
from pai3.ids import new_id

MAX_SCOPE_LIFETIME = timedelta(hours=1)
"""A token good forever is a token nobody re-checks. §10.3's mid-flight limit."""


class ConsentDenied(PermissionError):
    """No active ai_processing consent. Refusal is the default path, not a return value."""


class AIReadScope(BaseModel):
    patient_id: str
    consent_id: str
    scope: Literal["ai_processing"] = "ai_processing"
    valid_until: AwareDatetime
    trace_id: str

    model_config = {"frozen": True}

    def is_valid_at(self, moment: datetime) -> bool:
        return moment <= self.valid_until


def authorize_ai_read(
    patient_id: str, consents: list[Consent], now: datetime
) -> AIReadScope:
    """Produce a scope, or refuse.

    `consents` is passed in rather than queried so this stays a pure function. The caller
    supplies the patient's consent records; filtering them is this function's job.
    """
    for consent in consents:
        if consent.patient_id != patient_id:
            continue
        if consent.scope is not ConsentScope.AI_PROCESSING:
            continue
        if consent.record_status is not RecordStatus.ACTIVE:
            continue
        if not consent.is_active_at(now):
            continue
        ceiling = now + MAX_SCOPE_LIFETIME
        valid_until = (
            min(ceiling, consent.effective_until)
            if consent.effective_until is not None
            else ceiling
        )
        return AIReadScope(
            patient_id=patient_id,
            consent_id=consent.id,
            valid_until=valid_until,
            trace_id=new_id("trc"),
        )
    raise ConsentDenied(
        f"no active ai_processing consent for patient {patient_id} at {now.isoformat()}"
    )
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/ai/test_scope.py -q`
Expected: `11 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/ai/scope.py tests/ai/test_scope.py
git commit -m "feat: consent gate as an unforgeable read capability"
```

---

### Task 26: The projection layer (§10.4, §10.6)

Four duties in one place: admit no caller without a scope, emit `AIPatientView` rather
than `Patient`, keep every text span's origin, and report what the budget left out. If a
non-droppable category does not fit, the budget is wrong — so the projection says so and
the generation is refused.

**Files:**
- Create: `src/pai3/ai/projection.py`
- Test: `tests/ai/test_projection.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ai/test_projection.py
from datetime import UTC, date, datetime, timedelta

import pytest

from pai3.ai.artifact import OmissionReason
from pai3.ai.projection import (
    AIPatientView,
    BudgetExceeded,
    ProjectionResult,
    project_patient,
    project_records,
)
from pai3.ai.scope import AIReadScope
from pai3.entities.clinical import AllergyIntolerance, Condition, Criticality
from pai3.entities.people import Patient
from pai3.enums import ClinicalStatus, ProvenanceOrigin, VerificationStatus
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.people import HumanName, PatientIdentifier
from pai3.values.provenance import Provenance

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
PROV = Provenance(origin=ProvenanceOrigin.HUMAN, asserted_by=DOC, asserted_at=NOW)
PATIENT_ID = new_id("pat")
BASE = {"provenance": PROV, "created_at": NOW, "updated_at": NOW, "updated_by": DOC}
SCOPE = AIReadScope(
    patient_id=PATIENT_ID, consent_id=new_id("cons"),
    valid_until=NOW + timedelta(minutes=30), trace_id=new_id("trc"),
)


def _patient() -> Patient:
    return Patient(
        id=PATIENT_ID, **BASE,
        identifiers=[PatientIdentifier(system="emr-west", value="MRN-4471")],
        names=[HumanName(given=["Dana"], family="Okafor")],
        birth_date=date(1979, 4, 2), sex_at_birth="female",
    )


def _condition(status: ClinicalStatus = ClinicalStatus.ACTIVE) -> Condition:
    return Condition(
        id=new_id("cond"), **BASE, patient_id=PATIENT_ID,
        code=CodeableConcept(raw_text="hypothyroidism", system="ICD-10", code="E03.9"),
        clinical_status=status, verification_status=VerificationStatus.CONFIRMED,
    )


def _allergy() -> AllergyIntolerance:
    return AllergyIntolerance(
        id=new_id("alg"), **BASE, patient_id=PATIENT_ID,
        substance=CodeableConcept(raw_text="penicillin", system="RxNorm", code="7980"),
        criticality=Criticality.HIGH, verification_status=VerificationStatus.CONFIRMED,
    )


def test_the_projection_carries_no_identity():
    view = project_patient(_patient(), SCOPE, on=date(2026, 4, 3))
    assert view.age_years == 47
    for forbidden in ("names", "identifiers", "birth_date", "contacts", "addresses"):
        assert forbidden not in AIPatientView.model_fields


def test_projecting_another_patient_through_this_scope_is_refused():
    other = _patient().model_copy(update={"id": new_id("pat")})
    with pytest.raises(PermissionError):
        project_patient(other, SCOPE, on=date(2026, 4, 3))


def test_an_expired_scope_is_refused():
    stale = SCOPE.model_copy(update={"valid_until": NOW - timedelta(minutes=1)})
    with pytest.raises(PermissionError):
        project_patient(_patient(), stale, on=date(2026, 4, 3), now=NOW)


def test_everything_fits_when_the_budget_is_ample():
    result = project_records([_condition(), _allergy()], SCOPE, budget=100)
    assert len(result.included) == 2
    assert result.omitted == []


def test_a_droppable_record_is_omitted_and_named():
    # Resolved conditions are droppable; the omission is reported, never silent.
    result = project_records(
        [_allergy(), _condition(ClinicalStatus.RESOLVED)], SCOPE, budget=1
    )
    assert len(result.omitted) == 1
    assert result.omitted[0].reason is OmissionReason.CONTEXT_BUDGET


def test_a_non_droppable_record_is_never_omitted():
    with pytest.raises(BudgetExceeded):
        project_records([_allergy(), _allergy()], SCOPE, budget=1)


def test_the_error_names_what_would_not_fit():
    with pytest.raises(BudgetExceeded, match="AllergyIntolerance"):
        project_records([_allergy(), _allergy()], SCOPE, budget=1)


def test_active_conditions_are_non_droppable():
    # A narrative without active diagnoses is a list of test results (§10.6).
    with pytest.raises(BudgetExceeded):
        project_records([_condition(), _condition()], SCOPE, budget=1)


def test_the_result_reports_its_budget_usage():
    result = project_records([_condition()], SCOPE, budget=10)
    assert result.budget.limit == 10
    assert result.budget.consumed == 1


def test_omitted_is_required_on_the_result():
    assert ProjectionResult.model_fields["omitted"].is_required()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/ai/test_projection.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.ai.projection'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/ai/projection.py
"""The only place canonical data becomes model context (§10.4, §10.6).

Four duties: refuse any caller without an `AIReadScope`, emit `AIPatientView` instead of
`Patient`, preserve each text span's origin, and report everything the budget left out.

Budget units here are records rather than tokens. A token count depends on the engine's
tokeniser, which belongs to the adapter; the shape of the decision — what is droppable,
what is reported — is the same either way, and keeping it countable keeps it testable.
"""

from datetime import date, datetime
from typing import Protocol

from pydantic import BaseModel, Field

from pai3.ai.artifact import OmissionReason, OmittedRecord
from pai3.ai.scope import AIReadScope
from pai3.entities.clinical import AllergyIntolerance, Condition
from pai3.entities.people import Patient
from pai3.entities.therapy import Medication
from pai3.enums import ClinicalStatus
from pai3.ids import CanonicalRef


class AIPatientView(BaseModel):
    """The only patient shape a projection emits (§10.4).

    No names, identifiers, contacts, addresses or date of birth. Age replaces the
    birthday because dosing and reference ranges need an age. Since the type has no
    identity fields, "the model saw the patient's name" is unexpressible.

    The deeper reason is that `fields_read` (§6.3) exists to measure exposure, and a
    default projection carrying identifiers makes that measurement meaningless.
    """

    patient_id: str
    age_years: int | None
    sex: str | None


class BudgetUsage(BaseModel):
    limit: int
    consumed: int


class ProjectionResult(BaseModel):
    included: list[CanonicalRef]
    omitted: list[OmittedRecord]
    budget: BudgetUsage


class BudgetExceeded(RuntimeError):
    """A non-droppable category did not fit, so the budget is wrong, not the allergies.

    §10.6: the generation is refused rather than truncated. The caller still writes an
    artifact with no output so that the refusal is visible.
    """


class _Record(Protocol):
    id: str
    version: int


def _is_non_droppable(record: object) -> bool:
    """§10.6's list: allergies, current medications, active conditions.

    Open blocking flags are the fourth member and are carried separately, on the
    read-model's required `unresolved` field (§9.4).
    """
    if isinstance(record, AllergyIntolerance):
        return True
    if isinstance(record, Medication):
        return record.is_current
    if isinstance(record, Condition):
        return record.clinical_status in (ClinicalStatus.ACTIVE, ClinicalStatus.RECURRENCE)
    return False


def _check(scope: AIReadScope, patient_id: str, now: datetime | None) -> None:
    if scope.patient_id != patient_id:
        raise PermissionError(
            f"scope authorises {scope.patient_id}, not {patient_id}"
        )
    if now is not None and not scope.is_valid_at(now):
        raise PermissionError(f"scope expired at {scope.valid_until.isoformat()}")


def project_patient(
    patient: Patient, scope: AIReadScope, on: date, now: datetime | None = None
) -> AIPatientView:
    _check(scope, patient.id, now)
    return AIPatientView(
        patient_id=patient.id,
        age_years=patient.age_years(on),
        sex=patient.sex_at_birth,
    )


def project_records(
    records: list[_Record],
    scope: AIReadScope,
    budget: int,
    now: datetime | None = None,
) -> ProjectionResult:
    """Select within the budget, non-droppable records first.

    Raises BudgetExceeded when the non-droppable set alone does not fit. Everything else
    that does not fit is included in `omitted` with a reason — nothing is dropped without
    being named.
    """
    for record in records:
        _check(scope, record.patient_id, now)

    required = [r for r in records if _is_non_droppable(r)]
    optional = [r for r in records if not _is_non_droppable(r)]

    if len(required) > budget:
        kinds = sorted({type(r).__name__ for r in required})
        raise BudgetExceeded(
            f"non-droppable records ({', '.join(kinds)}) need {len(required)} slots "
            f"but the budget is {budget}; the budget is wrong, not the records"
        )

    included = list(required)
    omitted: list[OmittedRecord] = []
    for record in optional:
        ref = CanonicalRef(
            entity_type=type(record).__name__, entity_id=record.id, version=record.version
        )
        if len(included) < budget:
            included.append(record)
        else:
            omitted.append(OmittedRecord(ref=ref, reason=OmissionReason.CONTEXT_BUDGET))

    return ProjectionResult(
        included=[
            CanonicalRef(
                entity_type=type(r).__name__, entity_id=r.id, version=r.version
            )
            for r in included
        ],
        omitted=omitted,
        budget=BudgetUsage(limit=budget, consumed=len(included)),
    )
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/ai/test_projection.py -q`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/ai/projection.py tests/ai/test_projection.py
git commit -m "feat: projection layer stripping identity and reporting omissions"
```

---

### Task 27: The five guardrail checks (§10.5)

These verify grounding, not judgement. A claim can cite the right record, carry the right
number, and still be a poor clinical inference — the only check on judgement is human
review. They are also asymmetric: they catch fabrication and never omission.

**Files:**
- Create: `src/pai3/ai/guardrails.py`
- Test: `tests/ai/test_guardrails.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/ai/test_guardrails.py
from datetime import UTC, datetime

from pai3.ai.artifact import (
    AIClaim,
    AISummary,
    ClaimValue,
    Engine,
    OmissionReason,
    OmittedRecord,
)
from pai3.ai.guardrails import Verdict, run_guardrails
from pai3.entities.results import LabResult
from pai3.enums import FlagCode, ProvenanceOrigin, Severity
from pai3.ids import CanonicalRef, new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.flags import FlagSummary
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB_ACTOR = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")
PROV = Provenance(origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=LAB_ACTOR, asserted_at=NOW)
PATIENT = new_id("pat")


def _lab(value: float | None, lab_id: str | None = None) -> LabResult:
    return LabResult(
        id=lab_id or new_id("lab"), provenance=PROV, created_at=NOW, updated_at=NOW,
        updated_by=LAB_ACTOR, patient_id=PATIENT,
        biomarker=CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3"),
        collection_date=NOW,
        quantity=None if value is None else Quantity(value=value, unit="mIU/L"),
    )


def _ref(lab: LabResult) -> CanonicalRef:
    return CanonicalRef(entity_type="LabResult", entity_id=lab.id, version=lab.version)


def _summary(claims, inputs, **over) -> AISummary:
    kwargs = {
        "id": new_id("aia"), "patient_id": PATIENT, "trace_id": new_id("trc"),
        "created_at": NOW, "inputs": inputs, "prompt_digest": "sha256:" + "a" * 64,
        "model_id": "llama-3.3-70b-instruct", "engine": Engine.OLLAMA,
        "engine_version": "0.5.1", "consent_ref": new_id("cons"),
        "claims": claims, "unresolved": [],
    }
    return AISummary(**(kwargs | over))


def test_a_grounded_summary_passes():
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.PASS and failures == []


def test_a_citation_the_model_never_read_is_a_hard_failure():
    lab, unread = _lab(2.1), _lab(9.9)
    summary = _summary([AIClaim(text="TSH high.", cites=[_ref(unread)])], [_ref(lab)])
    verdict, failures = run_guardrails(summary, {lab.id: lab, unread.id: unread}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "cites_in_inputs" for f in failures)


def test_a_value_that_does_not_match_the_record_is_a_hard_failure():
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 7.2.", cites=[_ref(lab)],
                 values=[ClaimValue(value=7.2, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "value_matches_source" for f in failures)


def test_asserting_a_value_where_the_slot_is_empty_is_a_hard_failure():
    # §9.6 as code: there is no value, so it can be neither asserted nor inferred.
    lab = _lab(None)
    summary = _summary(
        [AIClaim(text="TSH 2.1.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "no_claim_on_empty_slot" for f in failures)


def test_a_non_droppable_omission_is_a_hard_failure():
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
        omitted=[
            OmittedRecord(
                ref=CanonicalRef(entity_type="AllergyIntolerance", entity_id=new_id("alg"), version=1),
                reason=OmissionReason.CONTEXT_BUDGET,
            )
        ],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.HARD_FAIL
    assert any(f.check == "no_non_droppable_omitted" for f in failures)


def test_an_unsurfaced_blocking_flag_is_a_soft_failure():
    lab = _lab(2.1)
    flag = FlagSummary(
        flag_id=new_id("flag"), code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING, message="unresolved conflict",
    )
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, failures = run_guardrails(summary, {lab.id: lab}, [flag])
    assert verdict is Verdict.SOFT_FAIL
    assert any(f.check == "blocking_flags_surfaced" for f in failures)


def test_a_surfaced_blocking_flag_passes():
    lab = _lab(2.1)
    flag = FlagSummary(
        flag_id=new_id("flag"), code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING, message="unresolved conflict",
    )
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)], unresolved=[flag],
    )
    verdict, _ = run_guardrails(summary, {lab.id: lab}, [flag])
    assert verdict is Verdict.PASS


def test_a_hard_failure_outranks_a_soft_one():
    lab, unread = _lab(2.1), _lab(9.9)
    flag = FlagSummary(
        flag_id=new_id("flag"), code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING, message="x",
    )
    summary = _summary([AIClaim(text="x", cites=[_ref(unread)])], [_ref(lab)])
    verdict, failures = run_guardrails(summary, {lab.id: lab, unread.id: unread}, [flag])
    assert verdict is Verdict.HARD_FAIL
    assert len(failures) >= 2


def test_guardrails_cannot_detect_an_omission():
    # §10.5 and §7: a brief that omits a critical allergy passes every check. This test
    # pins the documented limit so nobody later believes the checks cover it.
    lab = _lab(2.1)
    summary = _summary(
        [AIClaim(text="TSH 2.1 mIU/L.", cites=[_ref(lab)],
                 values=[ClaimValue(value=2.1, unit="mIU/L", cites=_ref(lab))])],
        [_ref(lab)],
    )
    verdict, _ = run_guardrails(summary, {lab.id: lab}, [])
    assert verdict is Verdict.PASS
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/ai/test_guardrails.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.ai.guardrails'`

- [ ] **Step 3: Write the implementation**

```python
# src/pai3/ai/guardrails.py
"""What is checked before a generation becomes an artifact (§10.5).

These verify grounding, not judgement: a claim can cite the right record, carry the right
number, and still be a poor clinical inference. They are asymmetric — fabrication is
caught, omission is not, because there is nothing to diff a summary against that was
never written.
"""

from enum import Enum

from pai3.ai.artifact import AISummary, GuardrailFailure
from pai3.entities.results import LabResult
from pai3.enums import Severity
from pai3.values.flags import FlagSummary

NON_DROPPABLE_TYPES = frozenset(
    {"AllergyIntolerance", "Medication", "Condition", "DataQualityFlag"}
)
"""§10.6. A conservative test by entity type: a non-droppable record must never be
omitted, and the projection layer is what decides droppability per record."""

_HARD_CHECKS = frozenset(
    {"cites_in_inputs", "value_matches_source", "no_claim_on_empty_slot",
     "no_non_droppable_omitted"}
)


class Verdict(Enum):
    PASS = "pass"
    SOFT_FAIL = "soft_fail"
    HARD_FAIL = "hard_fail"


def run_guardrails(
    summary: AISummary,
    records: dict[str, object],
    open_blocking_flags: list[FlagSummary],
) -> tuple[Verdict, list[GuardrailFailure]]:
    """Run all five checks and classify the result.

    `records` maps canonical id to the record, for checks 2 and 3. `open_blocking_flags`
    are the flags on the records in `inputs`, which the caller gathers.
    """
    failures: list[GuardrailFailure] = []
    input_ids = {ref.entity_id for ref in summary.inputs}

    # 1 — every citation was actually read.
    for claim in summary.claims:
        for ref in claim.cites:
            if ref.entity_id not in input_ids:
                failures.append(
                    GuardrailFailure(
                        check="cites_in_inputs",
                        detail=f"claim cites {ref.entity_id}, which is not in inputs",
                    )
                )

    for claim in summary.claims:
        for value in claim.values:
            record = records.get(value.cites.entity_id)
            if not isinstance(record, LabResult):
                continue
            # 3 — nothing may be asserted about an empty slot.
            if record.quantity is None:
                failures.append(
                    GuardrailFailure(
                        check="no_claim_on_empty_slot",
                        detail=(
                            f"claim asserts {value.value} for {record.id}, "
                            "whose value slot is empty"
                        ),
                    )
                )
                continue
            # 2 — the number matches the record.
            if record.quantity.value != value.value:
                failures.append(
                    GuardrailFailure(
                        check="value_matches_source",
                        detail=(
                            f"claim says {value.value} but {record.id} holds "
                            f"{record.quantity.value}"
                        ),
                    )
                )

    # 4 — open blocking flags were carried to the output.
    surfaced = {flag.flag_id for flag in summary.unresolved}
    for flag in open_blocking_flags:
        if flag.severity is Severity.BLOCKING and flag.flag_id not in surfaced:
            failures.append(
                GuardrailFailure(
                    check="blocking_flags_surfaced",
                    detail=f"blocking flag {flag.flag_id} ({flag.code}) was not surfaced",
                )
            )

    # 5 — nothing non-droppable was omitted.
    for omission in summary.omitted:
        if omission.ref.entity_type in NON_DROPPABLE_TYPES:
            failures.append(
                GuardrailFailure(
                    check="no_non_droppable_omitted",
                    detail=(
                        f"{omission.ref.entity_type} {omission.ref.entity_id} was omitted "
                        f"({omission.reason}); the budget is wrong, not the record"
                    ),
                )
            )

    if any(f.check in _HARD_CHECKS for f in failures):
        return Verdict.HARD_FAIL, failures
    if failures:
        return Verdict.SOFT_FAIL, failures
    return Verdict.PASS, failures
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/ai/test_guardrails.py -q`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/ai/guardrails.py tests/ai/test_guardrails.py
git commit -m "feat: five output guardrails over structured claims"
```

---

### Task 28: Read-models — `LabTrend` and `PreVisitBrief` (§9.4, §10.4)

Both carry a required list of what the reader is not seeing, so a brief that quietly
dropped a flagged lab cannot be constructed. `LabTrend` keeps every point in the series and
excludes comparator values from the arithmetic only: three consecutive `TSH <0.01` are a
signal, and the physician sees them while the trend arrow abstains.

**Files:**
- Create: `src/pai3/readmodels/__init__.py`
- Create: `src/pai3/readmodels/trend.py`
- Create: `src/pai3/readmodels/brief.py`
- Test: `tests/readmodels/test_trend.py`
- Test: `tests/readmodels/test_brief.py`

- [ ] **Step 1: Write the failing trend tests**

```python
# tests/readmodels/test_trend.py
from datetime import UTC, datetime, timedelta

from pai3.enums import MeasurementContext, ProvenanceOrigin
from pai3.entities.results import LabResult
from pai3.ids import new_id
from pai3.readmodels.trend import Direction, ExclusionReason, build_lab_trend
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
LAB = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")
PROV = Provenance(origin=ProvenanceOrigin.SOURCE_SYSTEM, asserted_by=LAB, asserted_at=NOW)
TSH = CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3")


def _lab(value: float | None, days_ago: int, unit: str = "mIU/L", comparator=None) -> LabResult:
    return LabResult(
        id=new_id("lab"), provenance=PROV, created_at=NOW, updated_at=NOW, updated_by=LAB,
        patient_id=new_id("pat"), biomarker=TSH,
        collection_date=NOW - timedelta(days=days_ago),
        quantity=None if value is None else Quantity(value=value, unit=unit, comparator=comparator),
    )


def test_a_rising_series_is_detected():
    trend = build_lab_trend(TSH, [_lab(1.0, 60), _lab(2.0, 30), _lab(3.0, 0)])
    assert trend.direction is Direction.RISING
    assert len(trend.series) == 3
    assert trend.excluded == []


def test_a_falling_series_is_detected():
    trend = build_lab_trend(TSH, [_lab(3.0, 60), _lab(2.0, 30), _lab(1.0, 0)])
    assert trend.direction is Direction.FALLING


def test_comparator_points_stay_in_the_series_but_leave_the_arithmetic():
    # Three consecutive <0.01 are clinically meaningful; dropping them loses signal.
    labs = [_lab(0.01, 60, comparator="<"), _lab(0.01, 30, comparator="<"), _lab(0.01, 0, comparator="<")]
    trend = build_lab_trend(TSH, labs)
    assert len(trend.series) == 3
    assert trend.numeric_basis == []
    assert len(trend.excluded) == 3
    assert all(e.reason is ExclusionReason.LIMIT_OF_DETECTION for e in trend.excluded)
    assert trend.direction is Direction.INDETERMINATE


def test_a_mismatched_unit_is_excluded_and_named():
    # A trend that quietly adds 5.5 mmol/L to 99 mg/dL is the failure this prevents.
    trend = build_lab_trend(TSH, [_lab(2.0, 30), _lab(99.0, 0, unit="mg/dL")])
    assert any(e.reason is ExclusionReason.UNIT_MISMATCH for e in trend.excluded)


def test_an_empty_value_slot_is_excluded_as_no_value():
    trend = build_lab_trend(TSH, [_lab(2.0, 30), _lab(None, 0)])
    assert any(e.reason is ExclusionReason.NO_VALUE for e in trend.excluded)


def test_direction_needs_two_numeric_points():
    # Not a tuned threshold: two is the minimum at which a direction exists.
    trend = build_lab_trend(TSH, [_lab(2.0, 0)])
    assert trend.direction is Direction.INDETERMINATE


def test_excluded_is_a_required_field():
    from pai3.readmodels.trend import LabTrend

    assert LabTrend.model_fields["excluded"].is_required()
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/readmodels/test_trend.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.readmodels'`

- [ ] **Step 3: Write the trend implementation**

```python
# src/pai3/readmodels/__init__.py
```

```python
# src/pai3/readmodels/trend.py
"""Lab trends (§9.4).

A comparator point is excluded from the arithmetic and not from the series. The physician
sees `<0.01, <0.01, <0.01` on the chart while the arrow abstains, which is strictly better
than three points disappearing with a note that they did.

`direction` is INDETERMINATE when and only when fewer than two numeric points remain. That
is not a tuned number but the minimum at which a direction exists at all; whether an arrow
can be trusted when half the points were excluded is a clinical judgement, not a schema
rule. Do not insert a ratio here.
"""

from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, Field

from pai3.entities.results import LabResult
from pai3.values.codeable import CodeableConcept
from pai3.values.flags import FlagSummary
from pai3.values.quantity import Quantity

MIN_POINTS_FOR_DIRECTION = 2


class Direction(StrEnum):
    RISING = "rising"
    FALLING = "falling"
    FLAT = "flat"
    INDETERMINATE = "indeterminate"


class ExclusionReason(StrEnum):
    LIMIT_OF_DETECTION = "limit_of_detection"
    NO_VALUE = "no_value"
    CODED_RESULT = "coded_result"
    UNIT_MISMATCH = "unit_mismatch"
    PATIENT_REPORTED = "patient_reported"


class TrendPoint(BaseModel):
    result_id: str
    at: AwareDatetime
    quantity: Quantity | None


class ExcludedPoint(BaseModel):
    result_id: str
    at: AwareDatetime
    quantity: Quantity | None
    reason: ExclusionReason


class LabTrend(BaseModel):
    analyte: CodeableConcept
    series: list[TrendPoint]
    numeric_basis: list[str]
    excluded: list[ExcludedPoint]
    direction: Direction
    unresolved: list[FlagSummary]


def build_lab_trend(
    analyte: CodeableConcept,
    results: list[LabResult],
    unresolved: list[FlagSummary] | None = None,
) -> LabTrend:
    """Assemble a trend, naming every point that left the arithmetic.

    The unit of the earliest usable point sets the series unit; anything else is excluded
    as UNIT_MISMATCH rather than converted, because conversion needs UCUM plus a
    conversion table (§10.6 records that as out of scope).
    """
    ordered = sorted(results, key=lambda r: r.collection_date)
    series: list[TrendPoint] = []
    excluded: list[ExcludedPoint] = []
    basis: list[tuple[str, float]] = []
    series_unit: str | None = None

    for result in ordered:
        point = TrendPoint(
            result_id=result.id, at=result.collection_date, quantity=result.quantity
        )
        series.append(point)

        if result.quantity is None:
            reason = (
                ExclusionReason.CODED_RESULT
                if result.coded_value is not None
                else ExclusionReason.NO_VALUE
            )
            excluded.append(ExcludedPoint(**point.model_dump(), reason=reason))
            continue
        if result.quantity.is_bounded:
            excluded.append(
                ExcludedPoint(**point.model_dump(), reason=ExclusionReason.LIMIT_OF_DETECTION)
            )
            continue
        if series_unit is None:
            series_unit = result.quantity.unit
        elif result.quantity.unit != series_unit:
            excluded.append(
                ExcludedPoint(**point.model_dump(), reason=ExclusionReason.UNIT_MISMATCH)
            )
            continue
        basis.append((result.id, result.quantity.value))

    if len(basis) < MIN_POINTS_FOR_DIRECTION:
        direction = Direction.INDETERMINATE
    elif basis[-1][1] > basis[0][1]:
        direction = Direction.RISING
    elif basis[-1][1] < basis[0][1]:
        direction = Direction.FALLING
    else:
        direction = Direction.FLAT

    return LabTrend(
        analyte=analyte,
        series=series,
        numeric_basis=[rid for rid, _ in basis],
        excluded=excluded,
        direction=direction,
        unresolved=unresolved or [],
    )
```

- [ ] **Step 4: Run them to verify they pass**

Run: `.venv/bin/pytest tests/readmodels/test_trend.py -q`
Expected: `7 passed`

- [ ] **Step 5: Commit**

```bash
git add src/pai3/readmodels tests/readmodels/test_trend.py
git commit -m "feat: LabTrend keeping excluded points visible"
```

- [ ] **Step 6: Write the failing brief tests**

```python
# tests/readmodels/test_brief.py
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from pai3.enums import FlagCode, Severity
from pai3.ids import new_id
from pai3.readmodels.brief import PatientHeader, PreVisitBrief
from pai3.values.flags import FlagSummary

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
HEADER = PatientHeader(
    patient_id=new_id("pat"), display_name="Dana Okafor",
    primary_mrn="MRN-4471", birth_date=date(1979, 4, 2),
)


def test_identity_sits_on_the_deterministic_header():
    # §10.4: the practice assembles this; the narrative never receives it.
    assert HEADER.display_name == "Dana Okafor"
    assert HEADER.primary_mrn == "MRN-4471"


def test_unresolved_is_required_with_no_default():
    # §9.4: a brief that dropped a flagged lab must be impossible to construct.
    assert PreVisitBrief.model_fields["unresolved"].is_required()
    with pytest.raises(ValidationError):
        PreVisitBrief(header=HEADER, generated_at=NOW)


def test_an_empty_unresolved_list_must_be_passed_deliberately():
    brief = PreVisitBrief(header=HEADER, generated_at=NOW, unresolved=[])
    assert brief.unresolved == []
    assert brief.narrative is None


def test_a_brief_without_a_narrative_states_why():
    # §10.6: refusal rather than truncation, and the reason reaches the physician.
    brief = PreVisitBrief(
        header=HEADER, generated_at=NOW, unresolved=[],
        narrative_withheld_reason="non-droppable records exceed the context budget",
    )
    assert brief.narrative is None
    assert "budget" in brief.narrative_withheld_reason


def test_a_blocking_flag_is_carried_to_the_reader():
    flag = FlagSummary(
        flag_id=new_id("flag"), code=FlagCode.CONFLICTING_VALUES,
        severity=Severity.BLOCKING,
        message="glucose: EMR 5.5 against lab 7.2, unresolved",
    )
    brief = PreVisitBrief(header=HEADER, generated_at=NOW, unresolved=[flag])
    assert brief.has_blocking_flags
    assert "7.2" in brief.unresolved[0].message


def test_a_brief_with_no_flags_reports_none():
    assert not PreVisitBrief(header=HEADER, generated_at=NOW, unresolved=[]).has_blocking_flags


def test_the_brief_has_no_context_budget():
    # §10.6: the deterministic brief holds everything; only the narrative is bounded.
    assert "budget" not in PreVisitBrief.model_fields
```

- [ ] **Step 7: Run them to verify they fail**

Run: `.venv/bin/pytest tests/readmodels/test_brief.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.readmodels.brief'`

- [ ] **Step 8: Write the brief implementation**

```python
# src/pai3/readmodels/brief.py
"""The Physician Pre-Visit Brief — D8's workflow (§10.4).

Two objects with two shapes, deliberately. `PatientHeader` carries the identity the
physician needs and has no context budget: it holds everything. `narrative` is generated
from `AIPatientView`, so it cannot contain a name it never received — a type that cannot
carry identity rather than a sentence promising it will not.

`unresolved` is required with no default, so a brief that quietly dropped a flagged lab
cannot be constructed (§9.4).
"""

from datetime import date

from pydantic import AwareDatetime, BaseModel, Field

from pai3.ai.artifact import AISummary
from pai3.enums import Severity
from pai3.readmodels.trend import LabTrend
from pai3.values.flags import FlagSummary


class PatientHeader(BaseModel):
    """Identity, for the physician reading the brief. Never projected to a model."""

    patient_id: str
    display_name: str
    primary_mrn: str | None = None
    birth_date: date | None = None


class PreVisitBrief(BaseModel):
    header: PatientHeader
    generated_at: AwareDatetime
    unresolved: list[FlagSummary]
    active_conditions: list[str] = Field(default_factory=list)
    active_medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    trends: list[LabTrend] = Field(default_factory=list)
    narrative: AISummary | None = None
    narrative_withheld_reason: str | None = Field(
        default=None,
        description="Why no narrative: a refused generation, or a guardrail rejection",
    )

    @property
    def has_blocking_flags(self) -> bool:
        return any(f.severity is Severity.BLOCKING for f in self.unresolved)
```

- [ ] **Step 9: Run them to verify they pass**

Run: `.venv/bin/pytest tests/readmodels/test_brief.py -q`
Expected: `7 passed`

- [ ] **Step 10: Commit**

```bash
git add src/pai3/readmodels/brief.py tests/readmodels/test_brief.py
git commit -m "feat: PreVisitBrief with required unresolved and no context budget"
```

---

### Task 29: The adapter, the mock patient, and D8 end to end

The adapter is the only thing that constructs an `AIArtifact`, which is what makes
`execution="local"` and `consent_ref` hold — the type is not what enforces them. The
end-to-end test is D8's demonstration, and it must include a failing case, otherwise the
guardrails are decorative in the submission.

A stub generator stands in for a local model so the test is deterministic. Swapping it for
ollama changes one function and no invariant.

**Files:**
- Create: `src/pai3/ai/adapter.py`
- Create: `mock/__init__.py`
- Create: `mock/patient_fixture.py`
- Test: `tests/test_d8_previsit_brief.py`

- [ ] **Step 1: Write the failing end-to-end tests**

```python
# tests/test_d8_previsit_brief.py
"""D8 end to end: canonical records -> gate -> projection -> generation -> guardrails.

Every test here asserts an invariant the spec names, not an implementation detail.
"""

import pytest

from pai3.ai.adapter import LocalInferenceAdapter, NarrativeRefused
from pai3.ai.artifact import ArtifactReview, Engine
from pai3.ai.scope import ConsentDenied, authorize_ai_read
from pai3.enums import Severity
from mock.patient_fixture import build_fixture


def test_the_whole_brief_assembles_with_a_narrative():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct", engine=Engine.OLLAMA, engine_version="0.5.1"
    )
    brief = adapter.build_brief(fx, scope, budget=50)
    assert brief.narrative is not None
    assert brief.narrative.review is ArtifactReview.PENDING
    assert brief.narrative.execution == "local"


def test_without_consent_nothing_is_read_at_all():
    fx = build_fixture(with_ai_consent=False)
    with pytest.raises(ConsentDenied):
        authorize_ai_read(fx.patient.id, fx.consents, fx.now)


def test_the_narrative_never_receives_identity():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct", engine=Engine.OLLAMA, engine_version="0.5.1"
    )
    brief = adapter.build_brief(fx, scope, budget=50)
    rendered = " ".join(claim.text for claim in brief.narrative.claims)
    assert fx.patient.names[0].family not in rendered
    assert fx.patient.identifiers[0].value not in rendered


def test_a_blocking_flag_reaches_both_the_brief_and_the_narrative():
    fx = build_fixture(with_conflicting_glucose=True)
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct", engine=Engine.OLLAMA, engine_version="0.5.1"
    )
    brief = adapter.build_brief(fx, scope, budget=50)
    assert brief.has_blocking_flags
    assert any(f.severity is Severity.BLOCKING for f in brief.narrative.unresolved)


def test_a_fabricating_model_is_rejected_and_the_attempt_is_recorded():
    # The failing case D8 must show: the artifact exists, marked, and reaches no reader.
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct", engine=Engine.OLLAMA, engine_version="0.5.1",
        fabricate=True,
    )
    brief = adapter.build_brief(fx, scope, budget=50)
    assert brief.narrative is None
    assert brief.narrative_withheld_reason
    artifact = adapter.last_artifact
    assert artifact.review is ArtifactReview.REJECTED_BY_GUARDRAIL
    assert artifact.guardrail_failures


def test_a_budget_too_small_for_the_allergies_refuses_rather_than_truncating():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct", engine=Engine.OLLAMA, engine_version="0.5.1"
    )
    brief = adapter.build_brief(fx, scope, budget=1)
    assert brief.narrative is None
    assert "budget" in brief.narrative_withheld_reason
    # The data is still there: the deterministic brief has no budget (§10.6).
    assert brief.allergies


def test_the_artifact_joins_to_its_read_events_by_trace_id():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct", engine=Engine.OLLAMA, engine_version="0.5.1"
    )
    brief = adapter.build_brief(fx, scope, budget=50)
    assert brief.narrative.trace_id == scope.trace_id
    assert all(e.trace_id == scope.trace_id for e in adapter.audit_events)


def test_the_prompt_is_not_stored_only_its_digest():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct", engine=Engine.OLLAMA, engine_version="0.5.1"
    )
    brief = adapter.build_brief(fx, scope, budget=50)
    assert brief.narrative.prompt_digest.startswith("sha256:")


def test_an_expired_scope_cannot_be_reused():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    stale = scope.model_copy(update={"valid_until": fx.now})
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct", engine=Engine.OLLAMA, engine_version="0.5.1"
    )
    with pytest.raises(PermissionError):
        adapter.build_brief(fx, stale, budget=50, now=fx.now.replace(hour=23))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/pytest tests/test_d8_previsit_brief.py -q`
Expected: `ModuleNotFoundError: No module named 'pai3.ai.adapter'`

- [ ] **Step 3: Write the fixture (D3's mock patient)**

```python
# mock/__init__.py
```

```python
# mock/patient_fixture.py
"""One realistic, entirely fictional patient — D3.

Deliberately includes an active ai_processing consent, because without it the workflow
D8 demonstrates cannot run at all (§10.3). `with_conflicting_glucose` produces the
unresolved-conflict case from §9.3: the value slot is empty and a blocking flag names
both candidates.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from pai3.entities.administrative import Consent
from pai3.entities.clinical import AllergyIntolerance, Condition, Criticality
from pai3.entities.infrastructure import DataQualityFlag, FlagTarget, SourceReference
from pai3.entities.people import Patient
from pai3.entities.results import LabResult
from pai3.entities.therapy import Medication, MedicationStatus
from pai3.enums import (
    ClinicalStatus,
    ConsentScope,
    FlagCode,
    ProvenanceOrigin,
    Severity,
    VerificationStatus,
)
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.dosage import Dosage
from pai3.values.people import HumanName, PatientIdentifier
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity, ReferenceRange

NOW = datetime(2026, 3, 12, 9, 0, tzinfo=UTC)
DOC = Actor(kind=ActorKind.HUMAN, ref=new_id("prov"), label="Dr A. Reyes")
LAB_SYS = Actor(kind=ActorKind.SYSTEM, ref="lab-portal", label="lab-portal")


def _prov(actor: Actor = DOC, origin: ProvenanceOrigin = ProvenanceOrigin.HUMAN) -> Provenance:
    return Provenance(origin=origin, asserted_by=actor, asserted_at=NOW)


def _base(actor: Actor = DOC) -> dict:
    return {
        "provenance": _prov(actor),
        "created_at": NOW,
        "updated_at": NOW,
        "updated_by": actor,
    }


@dataclass
class Fixture:
    now: datetime
    patient: Patient
    consents: list[Consent]
    conditions: list[Condition]
    medications: list[Medication]
    allergies: list[AllergyIntolerance]
    labs: list[LabResult]
    flags: list[DataQualityFlag] = field(default_factory=list)
    source_refs: list[SourceReference] = field(default_factory=list)


def build_fixture(
    with_ai_consent: bool = True, with_conflicting_glucose: bool = False
) -> Fixture:
    patient_id = new_id("pat")
    patient = Patient(
        id=patient_id,
        **_base(),
        identifiers=[
            PatientIdentifier(system="emr-west", value="MRN-4471", assigner="West Clinic"),
            PatientIdentifier(system="lab-portal", value="LP-99812"),
        ],
        names=[HumanName(given=["Dana"], family="Okafor")],
        birth_date=date(1979, 4, 2),
        sex_at_birth="female",
    )

    consents: list[Consent] = [
        Consent(
            id=new_id("cons"), **_base(), patient_id=patient_id,
            scope=ConsentScope.TREATMENT, effective_from=NOW - timedelta(days=400),
        )
    ]
    if with_ai_consent:
        consents.append(
            Consent(
                id=new_id("cons"), **_base(), patient_id=patient_id,
                scope=ConsentScope.AI_PROCESSING, effective_from=NOW - timedelta(days=120),
            )
        )

    conditions = [
        Condition(
            id=new_id("cond"), **_base(), patient_id=patient_id,
            code=CodeableConcept(raw_text="hypothyroidism", system="ICD-10", code="E03.9"),
            clinical_status=ClinicalStatus.ACTIVE,
            verification_status=VerificationStatus.CONFIRMED,
            onset=date(2021, 5, 14),
        ),
        Condition(
            id=new_id("cond"), **_base(), patient_id=patient_id,
            code=CodeableConcept(raw_text="iron deficiency anaemia", system="ICD-10", code="D50.9"),
            clinical_status=ClinicalStatus.RESOLVED,
            verification_status=VerificationStatus.CONFIRMED,
            onset=date(2019, 2, 3), abatement=date(2019, 11, 20),
        ),
    ]

    medications = [
        Medication(
            id=new_id("med"), **_base(), patient_id=patient_id,
            drug=CodeableConcept(raw_text="levothyroxine", system="RxNorm", code="10582"),
            dosage=Dosage(text="75 mcg daily", amount=75.0, unit="mcg", frequency="daily"),
            status=MedicationStatus.ACTIVE, started_on=date(2021, 6, 1),
            prescriber_id=DOC.ref,
        )
    ]

    allergies = [
        AllergyIntolerance(
            id=new_id("alg"), **_base(), patient_id=patient_id,
            substance=CodeableConcept(raw_text="penicillin", system="RxNorm", code="7980"),
            criticality=Criticality.HIGH,
            verification_status=VerificationStatus.CONFIRMED,
        )
    ]

    tsh = CodeableConcept(raw_text="TSH", system="LOINC", code="3016-3")
    labs = [
        LabResult(
            id=new_id("lab"), **_base(LAB_SYS), patient_id=patient_id, biomarker=tsh,
            collection_date=NOW - timedelta(days=180),
            quantity=Quantity(value=3.8, unit="mIU/L"),
            reference_range=ReferenceRange(low=0.4, high=4.0),
            performing_lab="Meridian Labs",
        ),
        LabResult(
            id=new_id("lab"), **_base(LAB_SYS), patient_id=patient_id, biomarker=tsh,
            collection_date=NOW - timedelta(days=14),
            quantity=Quantity(value=5.6, unit="mIU/L"),
            reference_range=ReferenceRange(low=0.4, high=4.0),
            reported_interpretation=CodeableConcept(raw_text="H"),
            performing_lab="Meridian Labs",
        ),
    ]

    flags: list[DataQualityFlag] = []
    source_refs: list[SourceReference] = []

    if with_conflicting_glucose:
        glucose = CodeableConcept(raw_text="glucose, fasting", system="LOINC", code="1558-6")
        emr_ref = SourceReference(
            id=new_id("sref"), **_base(LAB_SYS), patient_id=patient_id,
            document_id=new_id("doc"), field_path="labs[3].value", quote="Glucose 5.5 mmol/L",
        )
        lab_ref = SourceReference(
            id=new_id("sref"), **_base(LAB_SYS), patient_id=patient_id,
            document_id=new_id("doc"), page=2, field_path="results[1].value",
            quote="Glucose 7.2 mmol/L",
        )
        source_refs.extend([emr_ref, lab_ref])
        # The slot stays empty: canonical never holds a value nobody vouched for (§9.3).
        unresolved_lab = LabResult(
            id=new_id("lab"), **_base(LAB_SYS), patient_id=patient_id, biomarker=glucose,
            collection_date=NOW - timedelta(days=14),
            quantity=None,
            reference_range=ReferenceRange(low=3.9, high=5.5),
            performing_lab="Meridian Labs",
        )
        labs.append(unresolved_lab)
        flags.append(
            DataQualityFlag(
                id=new_id("flag"),
                **_base(Actor(kind=ActorKind.PIPELINE, ref="normaliser", label="normaliser")),
                patient_id=patient_id,
                code=FlagCode.CONFLICTING_VALUES,
                severity=Severity.BLOCKING,
                message="fasting glucose: EMR 5.5 mmol/L against lab 7.2 mmol/L, unresolved",
                targets=[
                    FlagTarget(
                        entity_type="LabResult", entity_id=unresolved_lab.id,
                        field_path="quantity",
                    )
                ],
                candidates=[emr_ref.id, lab_ref.id],
            )
        )

    return Fixture(
        now=NOW, patient=patient, consents=consents, conditions=conditions,
        medications=medications, allergies=allergies, labs=labs, flags=flags,
        source_refs=source_refs,
    )
```

- [ ] **Step 4: Write the adapter**

```python
# src/pai3/ai/adapter.py
"""The only constructor of an AIArtifact (§10.2).

`execution="local"` and `consent_ref` are set here, from the scope the caller was given.
There is no public path that takes either as an argument, which is what makes those
invariants hold — the type alone does not. The same discipline as `fields_read` (§6.3) and
`TextOrigin` (§10.1): three invariants on a wrapper rather than on callers remembering.

`generate` stands in for a local model so the pipeline is deterministic under test.
Replacing it with an ollama call changes this one method and no invariant; `fabricate`
exists so D8 can demonstrate a guardrail rejection.
"""

import hashlib
import json
from datetime import datetime

from pai3.ai.artifact import (
    AIClaim,
    AISummary,
    ArtifactReview,
    ClaimValue,
    Engine,
    GuardrailFailure,
)
from pai3.ai.guardrails import Verdict, run_guardrails
from pai3.ai.projection import BudgetExceeded, project_patient, project_records
from pai3.ai.scope import AIReadScope
from pai3.entities.infrastructure import AuditAction, AuditEvent
from pai3.enums import ClinicalStatus, ProvenanceOrigin, Severity
from pai3.ids import CanonicalRef, new_id
from pai3.readmodels.brief import PatientHeader, PreVisitBrief
from pai3.readmodels.trend import build_lab_trend
from pai3.values.actor import Actor, ActorKind
from pai3.values.flags import FlagSummary
from pai3.values.provenance import Provenance

AGENT = Actor(kind=ActorKind.AGENT, ref="previsit-brief", label="previsit-brief")


class NarrativeRefused(RuntimeError):
    """The generation was refused before a model was called (§10.6)."""


class LocalInferenceAdapter:
    def __init__(
        self,
        model_id: str,
        engine: Engine,
        engine_version: str,
        model_digest: str | None = None,
        fabricate: bool = False,
    ) -> None:
        self.model_id = model_id
        self.engine = engine
        self.engine_version = engine_version
        self.model_digest = model_digest
        self.fabricate = fabricate
        self.audit_events: list[AuditEvent] = []
        self.last_artifact: AISummary | None = None

    # ---------------------------------------------------------------- audit

    def _audit_read(self, scope: AIReadScope, refs: list[CanonicalRef], now: datetime) -> None:
        """One batched event per entity type (§6.3).

        `fields_read` stays None: field-level recording is §11 step 6, and None is a legal
        value meaning "assume the whole record".
        """
        by_type: dict[str, list[str]] = {}
        for ref in refs:
            by_type.setdefault(ref.entity_type, []).append(ref.entity_id)
        for entity_type, ids in by_type.items():
            self.audit_events.append(
                AuditEvent(
                    id=new_id("aud"),
                    provenance=Provenance(
                        origin=ProvenanceOrigin.SYSTEM_DERIVED, asserted_by=AGENT, asserted_at=now
                    ),
                    created_at=now,
                    updated_at=now,
                    updated_by=AGENT,
                    patient_id=scope.patient_id,
                    action=AuditAction.READ,
                    trace_id=scope.trace_id,
                    actor=AGENT,
                    targets=ids,
                    fields_read=None,
                    inputs=[r for r in refs if r.entity_type == entity_type],
                )
            )

    # ------------------------------------------------------------- generate

    def generate(self, view, labs, trends) -> list[AIClaim]:
        """Stand-in for a local model, emitting structured claims (§10.5).

        Claims are the output shape because over free prose none of the five checks works.
        `fabricate` cites a value the record does not hold, so the rejection path is
        demonstrable.
        """
        claims: list[AIClaim] = []
        for lab in labs:
            if lab.quantity is None:
                continue
            ref = CanonicalRef(
                entity_type="LabResult", entity_id=lab.id, version=lab.version
            )
            reported = lab.quantity.value + (1.0 if self.fabricate else 0.0)
            claims.append(
                AIClaim(
                    text=(
                        f"{lab.biomarker.raw_text} measured {reported} "
                        f"{lab.quantity.unit or 'unknown unit'}."
                    ),
                    cites=[ref],
                    values=[ClaimValue(value=reported, unit=lab.quantity.unit, cites=ref)],
                )
            )
        for trend in trends:
            if trend.numeric_basis:
                claims.append(
                    AIClaim(
                        text=f"{trend.analyte.raw_text} trend is {trend.direction.value}.",
                        cites=[
                            CanonicalRef(
                                entity_type="LabResult", entity_id=rid, version=1
                            )
                            for rid in trend.numeric_basis
                        ],
                    )
                )
        return claims

    # ---------------------------------------------------------------- brief

    def build_brief(
        self, fx, scope: AIReadScope, budget: int, now: datetime | None = None
    ) -> PreVisitBrief:
        moment = now or fx.now
        header = PatientHeader(
            patient_id=fx.patient.id,
            display_name=f"{' '.join(fx.patient.names[0].given)} {fx.patient.names[0].family}",
            primary_mrn=fx.patient.identifiers[0].value,
            birth_date=fx.patient.birth_date,
        )
        unresolved = [
            FlagSummary(
                flag_id=f.id, code=f.code, severity=f.severity, message=f.message
            )
            for f in fx.flags
            if f.blocks_autonomous_use
        ]

        # The deterministic brief has no budget: it holds everything (§10.6).
        trends = [
            build_lab_trend(fx.labs[0].biomarker, [l for l in fx.labs if l.biomarker.code == fx.labs[0].biomarker.code], unresolved)
        ]
        brief_kwargs = {
            "header": header,
            "generated_at": moment,
            "unresolved": unresolved,
            "active_conditions": [
                c.code.raw_text for c in fx.conditions if c.clinical_status is ClinicalStatus.ACTIVE
            ],
            "active_medications": [m.drug.raw_text for m in fx.medications if m.is_current],
            "allergies": [a.substance.raw_text for a in fx.allergies],
            "trends": trends,
        }

        records = [*fx.conditions, *fx.medications, *fx.allergies, *fx.labs]
        try:
            view = project_patient(fx.patient, scope, on=moment.date(), now=moment)
            projection = project_records(records, scope, budget=budget, now=moment)
        except BudgetExceeded as exc:
            return PreVisitBrief(**brief_kwargs, narrative_withheld_reason=str(exc))

        self._audit_read(scope, projection.included, moment)

        included_ids = {ref.entity_id for ref in projection.included}
        labs_in_context = [l for l in fx.labs if l.id in included_ids]
        claims = self.generate(view, labs_in_context, trends)

        prompt = json.dumps(
            {"view": view.model_dump(), "inputs": [r.model_dump() for r in projection.included]},
            sort_keys=True,
            default=str,
        )
        artifact = AISummary(
            id=new_id("aia"),
            patient_id=fx.patient.id,
            trace_id=scope.trace_id,
            created_at=moment,
            inputs=projection.included,
            omitted=projection.omitted,
            prompt_digest="sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
            model_id=self.model_id,
            model_digest=self.model_digest,
            engine=self.engine,
            engine_version=self.engine_version,
            consent_ref=scope.consent_id,
            claims=claims,
            unresolved=unresolved,
        )

        verdict, failures = run_guardrails(
            artifact, {r.id: r for r in records}, unresolved
        )
        if verdict is Verdict.HARD_FAIL:
            artifact = artifact.model_copy(
                update={
                    "review": ArtifactReview.REJECTED_BY_GUARDRAIL,
                    "guardrail_failures": failures,
                    "claims": [],
                }
            )
            self.last_artifact = artifact
            return PreVisitBrief(
                **brief_kwargs,
                narrative_withheld_reason=(
                    "narrative rejected by guardrails: "
                    + "; ".join(f.check for f in failures)
                ),
            )

        artifact = artifact.model_copy(update={"guardrail_failures": failures})
        self.last_artifact = artifact
        return PreVisitBrief(**brief_kwargs, narrative=artifact)
```

- [ ] **Step 5: Run the end-to-end tests**

Run: `.venv/bin/pytest tests/test_d8_previsit_brief.py -q`
Expected: `9 passed`

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: every test passes.

- [ ] **Step 7: Lint**

Run: `.venv/bin/ruff check src tests mock`
Expected: no findings. Fix anything reported.

- [ ] **Step 8: Commit**

```bash
git add src/pai3/ai/adapter.py mock tests/test_d8_previsit_brief.py
git commit -m "feat: local inference adapter and D8 pre-visit brief end to end"
```

**Phase 5 is complete, and with it §11 steps 1–5.** The governance layer enforces itself:
no read without a consent capability, no identity in the projection, no narrative on
trimmed data, no fabricated number reaching a physician — and each refusal is recorded
rather than silent.

---

## Self-review

**Spec coverage.** Walked §§1–11 against the tasks.

| Spec | Task |
|---|---|
| §2 three tiers | 10 |
| §6.2 provenance whitelist | 8 (plus per-entity constants in 15–17, 20–21) |
| §6.3 audit correlation | 12 (schema), 29 (batched read events) |
| §6.4 Condition, verification_status | 15 |
| §6.5 flags as an entity, closed codes | 3, 12 |
| §6.6 labs/vitals split, measurement_context | 17, 21 |
| §6.7 Medication/Supplement split | 16, 20 |
| §6.8 DiagnosticReport | 21 |
| §6.9 two value slots, Quantity, comparator | 6, 17 |
| §6.10 CodeableConcept | 5 |
| §6.11 Consent | 19 |
| §6.12 identifiers as a list | 14 |
| §6.13 timeline derived | not built — a read-model with no D8 dependency; §11 does not require it before step 6 |
| §6.14 no AI fields on canonical | 24 (the AI layer references canonical, never the reverse) |
| §6.15 versioning | 10 (`version`), 12 (`field_delta`) |
| §6.16 SocialFactor | 23 |
| §6.17 SourceReference | 12 |
| §6.19 lineage, cap, cascade | 8, 13 |
| §8 prefixed ULIDs | 2 (registry is step 6, out of scope here) |
| §9.1 two layers | entity validators throughout, 18 |
| §9.2 the lab rule across layers | 17 (layer 1), 18 (layer 2) |
| §9.3 the invariant | 17, 18, fixture in 29 |
| §9.4 required `unresolved`, trends | 28 |
| §9.5 interpretation table | 11 |
| §9.6 AI read rule | 27 (check 3 is this rule as code) |
| §9.7 partial ingestion | 12 (`IngestSummary`); the pipeline that emits the events belongs to the optional normalization build, as §9.7 itself says |
| §10.1 ClinicalText | 7, 21, 22 |
| §10.2 AIArtifact | 24, 29 |
| §10.3 consent gate | 25 |
| §10.4 rights matrix, AIPatientView | 26 |
| §10.5 five guardrails | 27 |
| §10.6 budget, non-droppable, refusal | 26, 28, 29 |

Two deliberate gaps, both named rather than silent: `TimelineEvent` (§6.13) is a read-model
D8 does not use, and the ingestion pipeline (§9.7) rides with the optional normalization
build. Everything §11 marks mandatory has a task.

**Placeholders.** None. Every code step carries the code; no step says "add validation" or
"similar to Task N".

**Type consistency.** Checked across tasks: `FIELD_PROVENANCE_WHITELIST` is a
`frozenset` on Medication, Supplement, LabResult, VitalSign and Condition; `is_current` is
the name on both Medication and Supplement; `blocks_autonomous_use` on DataQualityFlag is
what Task 29 filters on; `AIReadScope.trace_id` is what both the artifact and the audit
events carry; `CanonicalRef(entity_type, entity_id, version)` is used identically in
`Provenance.derived_from`, `AIArtifact.inputs`, `OmittedRecord.ref` and `ClaimValue.cites`.

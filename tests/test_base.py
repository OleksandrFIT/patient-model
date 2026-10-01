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
    # DTZ001 is silenced deliberately: constructing a naive datetime is the input
    # under test, and ruff's rule enforces the same discipline AwareDatetime does.
    naive = datetime(2026, 3, 12, 9, 0)  # noqa: DTZ001
    with pytest.raises(ValidationError):
        CanonicalRecord(**_base_kwargs("prov") | {"created_at": naive})


def test_is_retracted_reports_entered_in_error():
    record = CanonicalRecord(
        **_base_kwargs("prov") | {"record_status": RecordStatus.ENTERED_IN_ERROR}
    )
    assert record.is_retracted

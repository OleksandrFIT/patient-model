from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.infrastructure import (
    AuditAction,
    AuditEvent,
    DataQualityFlag,
    FlagTarget,
    IngestSummary,
    SourceReference,
)
from pai3.enums import FlagCode, FlagStatus, ProvenanceOrigin, Severity
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

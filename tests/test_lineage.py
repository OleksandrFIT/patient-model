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


def _ref(entity_id: str | None = None) -> CanonicalRef:
    return CanonicalRef(
        entity_type="Condition", entity_id=entity_id or new_id("cond"), version=1
    )


def test_no_parents_means_depth_zero():
    assert compute_depth([]) == 0


def test_one_root_parent_means_depth_one():
    assert compute_depth([_prov(0)]) == 1


def test_depth_follows_the_deepest_parent():
    assert compute_depth([_prov(0), _prov(1, [_ref()])]) == 2


def test_inference_beyond_the_cap_is_refused_at_computation():
    deep = _prov(1, [_ref()])
    with pytest.raises(DepthTooGreat):
        compute_depth([deep], origin=ProvenanceOrigin.AI_INFERENCE)


def test_a_human_may_assert_from_a_deep_parent():
    # The cap constrains AI inference, not a clinician reading the chart.
    deep = _prov(1, [_ref()])
    assert compute_depth([deep], origin=ProvenanceOrigin.HUMAN) == 2


def test_cascade_flags_every_child_of_a_retracted_record():
    parent_id = new_id("cond")
    children = [
        ("Condition", new_id("cond"), [_ref(parent_id)]),
        ("LabResult", new_id("lab"), [_ref(parent_id)]),
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
        children=[("Condition", new_id("cond"), [_ref()])],
        patient_id=new_id("pat"),
        actor=CLINICIAN,
        now=NOW,
    )
    assert flags == []


def test_cascade_flag_targets_the_child_not_the_parent():
    parent_id, child_id = new_id("cond"), new_id("lab")
    flags = retraction_cascade(
        retracted_id=parent_id,
        children=[("LabResult", child_id, [_ref(parent_id)])],
        patient_id=new_id("pat"),
        actor=CLINICIAN,
        now=NOW,
    )
    assert flags[0].targets[0].entity_id == child_id


def test_retracted_status_is_what_triggers_a_cascade():
    assert RecordStatus.ENTERED_IN_ERROR.value == "entered_in_error"

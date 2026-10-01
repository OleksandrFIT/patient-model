"""D8 end to end: canonical records -> gate -> projection -> generation -> guardrails.

Every test asserts an invariant the spec names, not an implementation detail.
"""

import pytest

from mock.patient_fixture import build_fixture
from pai3.ai.adapter import LocalInferenceAdapter
from pai3.ai.artifact import ArtifactReview, Engine
from pai3.ai.generators import StubGenerator
from pai3.ai.scope import ConsentDenied, authorize_ai_read
from pai3.enums import Severity


def _adapter(fabricate: bool = False) -> LocalInferenceAdapter:
    # The stub, explicitly. A test that wrote engine=OLLAMA while nothing ran would be the
    # same untruth as the artifact, at a smaller scale.
    return LocalInferenceAdapter(StubGenerator(fabricate=fabricate))


def test_the_whole_brief_assembles_with_a_narrative():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    brief = _adapter().build_brief(fx, scope, budget=50)
    assert brief.narrative is not None
    assert brief.narrative.review is ArtifactReview.PENDING
    assert brief.narrative.execution == "local"
    # No inference happened, and the artifact says so rather than naming a real engine.
    assert brief.narrative.engine is Engine.STUB
    assert brief.narrative.model_id.startswith("stub:")


def test_without_consent_nothing_is_read_at_all():
    fx = build_fixture(with_ai_consent=False)
    with pytest.raises(ConsentDenied):
        authorize_ai_read(fx.patient.id, fx.consents, fx.now)


def test_the_narrative_never_receives_identity():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    brief = _adapter().build_brief(fx, scope, budget=50)
    rendered = " ".join(claim.text for claim in brief.narrative.claims)
    assert fx.patient.names[0].family not in rendered
    assert fx.patient.identifiers[0].value not in rendered


def test_a_blocking_flag_reaches_both_the_brief_and_the_narrative():
    fx = build_fixture(with_conflicting_glucose=True)
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    brief = _adapter().build_brief(fx, scope, budget=50)
    assert brief.has_blocking_flags
    assert any(f.severity is Severity.BLOCKING for f in brief.narrative.unresolved)


def test_a_fabricating_model_is_rejected_and_the_attempt_is_recorded():
    # The failing case D8 must show: the artifact exists, marked, and reaches no reader.
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = _adapter(fabricate=True)
    brief = adapter.build_brief(fx, scope, budget=50)
    assert brief.narrative is None
    assert brief.narrative_withheld_reason
    artifact = adapter.last_artifact
    assert artifact.review is ArtifactReview.REJECTED_BY_GUARDRAIL
    assert artifact.guardrail_failures


def test_a_budget_too_small_for_the_allergies_refuses_rather_than_truncating():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    brief = _adapter().build_brief(fx, scope, budget=1)
    assert brief.narrative is None
    assert "budget" in brief.narrative_withheld_reason
    # The data is still there: the deterministic brief has no budget (§10.6).
    assert brief.allergies


def test_the_artifact_joins_to_its_read_events_by_trace_id():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = _adapter()
    brief = adapter.build_brief(fx, scope, budget=50)
    assert brief.narrative.trace_id == scope.trace_id
    assert adapter.audit_events
    assert all(e.trace_id == scope.trace_id for e in adapter.audit_events)


def test_the_prompt_is_not_stored_only_its_digest():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    brief = _adapter().build_brief(fx, scope, budget=50)
    assert brief.narrative.prompt_digest.startswith("sha256:")


def test_an_expired_scope_cannot_be_reused():
    fx = build_fixture()
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    stale = scope.model_copy(update={"valid_until": fx.now})
    with pytest.raises(PermissionError):
        _adapter().build_brief(fx, stale, budget=50, now=fx.now.replace(hour=23))

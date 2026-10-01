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


def test_every_text_origin_is_classified_so_a_new_one_fails_closed():
    # Not in the plan. Without this, adding a sixth TextOrigin and forgetting to list
    # it in _EXTERNAL makes crossed_perimeter return False for it — the new value
    # would default to *trusted*, which is the opposite of §10.1's fail-closed rule,
    # and none of the tests above would notice.
    internal = {TextOrigin.PRACTICE_AUTHORED}
    for origin in TextOrigin:
        text = ClinicalText(value="x", origin=origin)
        expected_external = origin not in internal
        assert text.crossed_perimeter is expected_external, (
            f"{origin.value} is unclassified; a new origin must be added to _EXTERNAL "
            "or to this test's `internal` set deliberately"
        )

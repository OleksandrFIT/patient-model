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

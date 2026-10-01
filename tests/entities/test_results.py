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

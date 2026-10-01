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

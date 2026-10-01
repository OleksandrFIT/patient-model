from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pai3.entities.results import DiagnosticReport, VitalSign
from pai3.enums import MeasurementContext, ProvenanceOrigin, TextOrigin
from pai3.ids import new_id
from pai3.values.actor import Actor, ActorKind
from pai3.values.codeable import CodeableConcept
from pai3.values.provenance import Provenance
from pai3.values.quantity import Quantity
from pai3.values.text import ClinicalText

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
        findings=ClinicalText(
            value="No focal consolidation.", origin=TextOrigin.EXTERNAL_DOCUMENT
        ),
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

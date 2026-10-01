"""Generate deliverables/d3_example_patient.json from the fixture.

Generated rather than hand-written, so the example record cannot drift away from the
models it claims to be an instance of. Regenerate with:

    .venv/bin/python scripts_build_d3.py
"""

import json
from pathlib import Path

from mock.patient_fixture import build_fixture
from pai3.ai.adapter import LocalInferenceAdapter
from pai3.ai.artifact import Engine
from pai3.ai.scope import authorize_ai_read
from pai3.readmodels.timeline import build_timeline
from pai3.validation import check_condition, check_lab_result, check_medication

OUT = Path("deliverables/d3_example_patient.json")


def main() -> None:
    fx = build_fixture(with_conflicting_glucose=True)
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(
        model_id="llama-3.3-70b-instruct",
        engine=Engine.OLLAMA,
        engine_version="0.5.1",
        model_digest="sha256:8f4a1c…(illustrative)",
    )
    brief = adapter.build_brief(fx, scope, budget=50)

    # Layer-2 validation over the record, so the flags shown are the ones the validators
    # actually raise rather than a hand-picked selection.
    derived_flags = []
    for cond in fx.conditions:
        derived_flags += check_condition(cond, fx.provider_actor, fx.now)
    for med in fx.medications:
        derived_flags += check_medication(med, fx.provider_actor, fx.now)
    for lab in fx.labs:
        derived_flags += check_lab_result(lab, fx.provider_actor, fx.now)

    record = {
        "_note": (
            "Entirely fictional. Generated from mock/patient_fixture.py by "
            "scripts_build_d3.py so it cannot drift from the Pydantic models."
        ),
        "_sections": {
            "canonical": "accepted clinical fact; every value names who vouched for it",
            "derived": "read-models, never stored (model_design.md §6.13, §9.4)",
            "ai_layer": "generated, references canonical by id and version; never the reverse",
        },
        "canonical": {
            "patient": fx.patient.model_dump(mode="json"),
            "provider": fx.provider.model_dump(mode="json"),
            "consents": [c.model_dump(mode="json") for c in fx.consents],
            "encounters": [e.model_dump(mode="json") for e in fx.encounters],
            "conditions": [c.model_dump(mode="json") for c in fx.conditions],
            "medications": [m.model_dump(mode="json") for m in fx.medications],
            "supplements": [s.model_dump(mode="json") for s in fx.supplements],
            "allergies": [a.model_dump(mode="json") for a in fx.allergies],
            "lab_results": [lab.model_dump(mode="json") for lab in fx.labs],
            "vitals": [v.model_dump(mode="json") for v in fx.vitals],
            "clinical_notes": [n.model_dump(mode="json") for n in fx.notes],
            "treatment_plans": [p.model_dump(mode="json") for p in fx.plans],
            "source_references": [s.model_dump(mode="json") for s in fx.source_refs],
            "data_quality_flags": [
                f.model_dump(mode="json") for f in (*fx.flags, *derived_flags)
            ],
        },
        "derived": {
            "timeline": [
                e.model_dump(mode="json")
                for e in build_timeline(
                    encounters=fx.encounters, conditions=fx.conditions,
                    medications=fx.medications, supplements=fx.supplements,
                    labs=fx.labs, notes=fx.notes,
                )
            ],
            "lab_trends": [t.model_dump(mode="json") for t in brief.trends],
            "pre_visit_brief": brief.model_dump(mode="json", exclude={"narrative"}),
        },
        "ai_layer": {
            "summary": brief.narrative.model_dump(mode="json")
            if brief.narrative
            else None,
            "human_review_status": brief.narrative.review.value
            if brief.narrative
            else "no narrative produced",
        },
        "audit": [e.model_dump(mode="json") for e in adapter.audit_events],
    }

    OUT.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

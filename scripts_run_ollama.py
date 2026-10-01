"""Run D8's pre-visit brief against a real local model.

    ollama serve                      # if it is not already running
    ollama pull qwen2.5:7b            # or any instruct model
    .venv/bin/python scripts_run_ollama.py [model]

Writes deliverables/d8_real_inference/. Unlike every other generated artifact in this
repository, **this one is not reproducible**: a model's reply can differ between runs and
certainly between versions, even at temperature 0. It is evidence that a run happened, not a
fixture. Which is also why `deliverables/d3_example_patient.json` uses the stub — a
deliverable that has to be byte-stable cannot be produced by a model.

Nothing leaves this machine. The call goes to localhost, and the artifact records the engine
version and the weight digest the runtime reported.
"""

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from mock.patient_fixture import build_fixture
from pai3.ai.adapter import LocalInferenceAdapter
from pai3.ai.artifact import ArtifactReview
from pai3.ai.generators import OllamaGenerator, OllamaUnavailable
from pai3.ai.scope import authorize_ai_read

OUT = Path("deliverables/d8_real_inference")
DEFAULT_MODEL = "qwen2.5:7b"


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    try:
        generator = OllamaGenerator(model)
    except OllamaUnavailable as exc:
        print(f"ollama is not reachable: {exc}")
        print("start it with `ollama serve`, then re-run.")
        return 1

    print(f"  engine   ollama {generator.engine_version}")
    print(f"  model    {generator.model_id}")
    print(f"  digest   {generator.model_digest or '(not reported by the runtime)'}")

    fx = build_fixture(with_conflicting_glucose=True)
    scope = authorize_ai_read(fx.patient.id, fx.consents, fx.now)
    adapter = LocalInferenceAdapter(generator)

    started = datetime.now(UTC)
    brief = adapter.build_brief(fx, scope, budget=50)
    elapsed = (datetime.now(UTC) - started).total_seconds()

    # Read the verdict off the artifact the adapter produced. Re-running the guardrails here
    # would score a rejected artifact whose claims the adapter has already cleared, and report
    # a pass on it -- which the first version of this script did.
    artifact = adapter.last_artifact
    rejected = artifact.review is ArtifactReview.REJECTED_BY_GUARDRAIL
    failures = artifact.guardrail_failures

    print(f"\n  generated in {elapsed:.1f}s")
    print(f"  review     {artifact.review.value}")
    print(f"  claims     {len(artifact.claims)}" + (" (cleared on rejection)" if rejected else ""))
    for f in failures:
        print(f"    {f.check}: {f.detail}")
    for note in artifact.generation_notes:
        print(f"    note: {note}")
    print(f"  narrative reached the physician: {brief.narrative is not None}")
    if brief.narrative_withheld_reason:
        print(f"  withheld: {brief.narrative_withheld_reason}")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "artifact.json").write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    )
    (OUT / "prompt.txt").write_text(adapter.last_prompt or "")
    (OUT / "run.json").write_text(json.dumps({
        "ran_at": started.isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "engine": artifact.engine.value,
        "engine_version": artifact.engine_version,
        "model_id": artifact.model_id,
        "model_digest": artifact.model_digest,
        "execution": artifact.execution,
        "review": artifact.review.value,
        "guardrail_failures": [f.model_dump() for f in failures],
        "generation_notes": artifact.generation_notes,
        "narrative_delivered": brief.narrative is not None,
        "claims": len(artifact.claims),
        "_note": (
            "Not reproducible. A model's reply may differ between runs and between versions."
        ),
    }, indent=2) + "\n")
    print(f"\n  wrote {OUT}/artifact.json, prompt.txt, run.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

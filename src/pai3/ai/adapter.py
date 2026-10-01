"""The only constructor of an AIArtifact (§10.2).

`execution="local"` and `consent_ref` are set here, from the scope the caller was given.
No public path takes either as an argument, which is what makes those invariants hold —
the type alone does not. The same discipline as `fields_read` (§6.3) and `TextOrigin`
(§10.1): three invariants on a wrapper rather than on callers remembering.

Where the claims come from is a `Generator` (see `generators.py`): either a deterministic
stand-in that reports `engine=stub`, or a real local model. The adapter does not know which,
and records whichever actually answered. The prompt is built by the generator and handed
back, so the digest is of the exact string that was sent.
"""

import hashlib
from datetime import datetime

from pai3.ai.artifact import AISummary, ArtifactReview
from pai3.ai.generators import GenerationContext, Generator
from pai3.ai.guardrails import Verdict, run_guardrails
from pai3.ai.projection import BudgetExceeded, project_patient, project_records
from pai3.ai.scope import AIReadScope
from pai3.entities.infrastructure import AuditAction, AuditEvent
from pai3.entities.results import LabResult
from pai3.enums import ClinicalStatus, ProvenanceOrigin
from pai3.ids import CanonicalRef, new_id
from pai3.readmodels.brief import PatientHeader, PreVisitBrief
from pai3.readmodels.timeline import build_timeline
from pai3.readmodels.trend import LabTrend, build_lab_trend
from pai3.values.actor import Actor, ActorKind
from pai3.values.flags import FlagSummary
from pai3.values.provenance import Provenance

AGENT = Actor(kind=ActorKind.AGENT, ref="previsit-brief", label="previsit-brief")


def _trends_for(labs: list[LabResult], unresolved: list[FlagSummary]) -> list[LabTrend]:
    """One trend per analyte, keyed on the coded concept where there is one.

    Grouped rather than assuming a single analyte, so a panel does not collapse into one
    meaningless series.
    """
    groups: dict[str, list[LabResult]] = {}
    for lab in labs:
        key = lab.biomarker.code or lab.biomarker.raw_text
        groups.setdefault(key, []).append(lab)
    return [
        build_lab_trend(group[0].biomarker, group, unresolved) for group in groups.values()
    ]


class LocalInferenceAdapter:
    def __init__(self, generator: Generator) -> None:
        self.generator = generator
        self.audit_events: list[AuditEvent] = []
        self.last_artifact: AISummary | None = None
        self.last_prompt: str | None = None
        """Held for inspection after a run, never persisted: the prompt contains PHI and
        storing it would duplicate canonical data outside canonical governance (§10.2)."""

    # ---------------------------------------------------------------- audit

    def _audit_read(
        self, scope: AIReadScope, refs: list[CanonicalRef], now: datetime
    ) -> None:
        """One batched event per entity type (§6.3).

        `fields_read` stays None: field-level recording is §11 step 6, and None is a legal
        value meaning "assume the whole record".
        """
        by_type: dict[str, list[CanonicalRef]] = {}
        for ref in refs:
            by_type.setdefault(ref.entity_type, []).append(ref)
        for entity_type, grouped in by_type.items():
            self.audit_events.append(
                AuditEvent(
                    id=new_id("aud"),
                    provenance=Provenance(
                        origin=ProvenanceOrigin.SYSTEM_DERIVED,
                        asserted_by=AGENT,
                        asserted_at=now,
                    ),
                    created_at=now,
                    updated_at=now,
                    updated_by=AGENT,
                    patient_id=scope.patient_id,
                    action=AuditAction.READ,
                    trace_id=scope.trace_id,
                    actor=AGENT,
                    targets=[r.entity_id for r in grouped],
                    fields_read=None,
                    inputs=grouped,
                )
            )
            _ = entity_type

    # ---------------------------------------------------------------- brief

    def build_brief(
        self, fx, scope: AIReadScope, budget: int, now: datetime | None = None
    ) -> PreVisitBrief:
        moment = now or fx.now
        given = fx.patient.names[0].given
        header = PatientHeader(
            patient_id=fx.patient.id,
            display_name=f"{' '.join(given)} {fx.patient.names[0].family}".strip(),
            primary_mrn=fx.patient.identifiers[0].value,
            birth_date=fx.patient.birth_date,
        )
        unresolved = [
            FlagSummary(flag_id=f.id, code=f.code, severity=f.severity, message=f.message)
            for f in fx.flags
            if f.blocks_autonomous_use
        ]

        # The deterministic brief has no budget: it holds every lab (§10.6).
        brief_kwargs = {
            "header": header,
            "generated_at": moment,
            "unresolved": unresolved,
            "active_conditions": [
                c.code.raw_text
                for c in fx.conditions
                if c.clinical_status is ClinicalStatus.ACTIVE
            ],
            "active_symptoms": [
                f"{s.symptom.raw_text} ({s.severity.value}, {s.reported_by.value})"
                for s in fx.symptoms
                if s.is_current
            ],
            "active_medications": [m.drug.raw_text for m in fx.medications if m.is_current],
            "active_supplements": [
                s.substance.raw_text for s in fx.supplements if s.is_current
            ],
            "allergies": [a.substance.raw_text for a in fx.allergies],
            "recent_vitals": [
                f"{v.kind.raw_text} {v.quantity.value} {v.quantity.unit}"
                f" ({v.measurement_context.value})"
                for v in sorted(fx.vitals, key=lambda v: v.measured_at, reverse=True)
            ],
            "trends": _trends_for(fx.labs, unresolved),
            "timeline": build_timeline(
                encounters=fx.encounters,
                conditions=fx.conditions,
                symptoms=fx.symptoms,
                medications=fx.medications,
                supplements=fx.supplements,
                labs=fx.labs,
                reports=fx.reports,
                notes=fx.notes,
            ),
        }

        records = [
            *fx.conditions, *fx.symptoms, *fx.medications, *fx.supplements, *fx.allergies,
            *fx.labs, *fx.vitals, *fx.notes,
        ]
        try:
            view = project_patient(fx.patient, scope, on=moment.date(), now=moment)
            projection = project_records(records, scope, budget=budget, now=moment)
        except BudgetExceeded as exc:
            return PreVisitBrief(**brief_kwargs, narrative_withheld_reason=str(exc))

        self._audit_read(scope, projection.included, moment)

        # The narrative sees only what the projection admitted, so every id it cites is in
        # inputs. Building its trends from fx.labs instead would let a claim cite a lab the
        # budget omitted, which guardrail 1 would then reject as a fabricated citation.
        included_ids = {ref.entity_id for ref in projection.included}
        labs_in_context = [lab for lab in fx.labs if lab.id in included_ids]
        generated = self.generator.generate(GenerationContext(
            view=view,
            labs=labs_in_context,
            trends=_trends_for(labs_in_context, unresolved),
            unresolved=unresolved,
        ))

        self.last_prompt = generated.prompt
        artifact = AISummary(
            id=new_id("aia"),
            patient_id=fx.patient.id,
            trace_id=scope.trace_id,
            created_at=moment,
            inputs=projection.included,
            omitted=projection.omitted,
            prompt_digest=(
                "sha256:" + hashlib.sha256(generated.prompt.encode()).hexdigest()
            ),
            model_id=self.generator.model_id,
            model_digest=self.generator.model_digest,
            engine=self.generator.engine,
            engine_version=self.generator.engine_version,
            consent_ref=scope.consent_id,
            claims=generated.claims,
            unresolved=unresolved,
            generation_notes=generated.notes,
        )

        verdict, failures = run_guardrails(artifact, {r.id: r for r in records}, unresolved)
        if verdict is Verdict.HARD_FAIL:
            artifact = artifact.model_copy(
                update={
                    "review": ArtifactReview.REJECTED_BY_GUARDRAIL,
                    "guardrail_failures": failures,
                    "claims": [],
                }
            )
            self.last_artifact = artifact
            return PreVisitBrief(
                **brief_kwargs,
                narrative_withheld_reason=(
                    "narrative rejected by guardrails: "
                    + "; ".join(sorted({f.check for f in failures}))
                ),
            )

        artifact = artifact.model_copy(update={"guardrail_failures": failures})
        self.last_artifact = artifact
        return PreVisitBrief(**brief_kwargs, narrative=artifact)

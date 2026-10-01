"""The only constructor of an AIArtifact (§10.2).

`execution="local"` and `consent_ref` are set here, from the scope the caller was given.
No public path takes either as an argument, which is what makes those invariants hold —
the type alone does not. The same discipline as `fields_read` (§6.3) and `TextOrigin`
(§10.1): three invariants on a wrapper rather than on callers remembering.

`generate` stands in for a local model so the pipeline is deterministic under test.
Replacing it with an ollama call changes this one method and no invariant; `fabricate`
exists so D8 can demonstrate a guardrail rejection.
"""

import hashlib
import json
from datetime import datetime

from pai3.ai.artifact import (
    AIClaim,
    AISummary,
    ArtifactReview,
    ClaimValue,
    Engine,
)
from pai3.ai.guardrails import Verdict, run_guardrails
from pai3.ai.projection import (
    AIPatientView,
    BudgetExceeded,
    project_patient,
    project_records,
)
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
    def __init__(
        self,
        model_id: str,
        engine: Engine,
        engine_version: str,
        model_digest: str | None = None,
        fabricate: bool = False,
    ) -> None:
        self.model_id = model_id
        self.engine = engine
        self.engine_version = engine_version
        self.model_digest = model_digest
        self.fabricate = fabricate
        self.audit_events: list[AuditEvent] = []
        self.last_artifact: AISummary | None = None

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

    # ------------------------------------------------------------- generate

    def generate(
        self, view: AIPatientView, labs: list[LabResult], trends: list[LabTrend]
    ) -> list[AIClaim]:
        """Stand-in for a local model, emitting structured claims (§10.5).

        Claims are the output shape because over free prose none of the five checks works.
        `fabricate` cites a value the record does not hold, so the rejection path is
        demonstrable.

        `labs` and `trends` are already restricted to what the projection admitted, so
        every id cited here is in `inputs`.
        """
        _ = view
        claims: list[AIClaim] = []
        for lab in labs:
            if lab.quantity is None:
                continue
            ref = CanonicalRef(
                entity_type="LabResult", entity_id=lab.id, version=lab.version
            )
            reported = lab.quantity.value + (1.0 if self.fabricate else 0.0)
            claims.append(
                AIClaim(
                    text=(
                        f"{lab.biomarker.raw_text} measured {reported} "
                        f"{lab.quantity.unit or 'unknown unit'}."
                    ),
                    cites=[ref],
                    values=[ClaimValue(value=reported, unit=lab.quantity.unit, cites=ref)],
                )
            )
        for trend in trends:
            if not trend.numeric_basis:
                continue
            claims.append(
                AIClaim(
                    text=f"{trend.analyte.raw_text} trend is {trend.direction.value}.",
                    cites=[
                        CanonicalRef(entity_type="LabResult", entity_id=rid, version=1)
                        for rid in trend.numeric_basis
                    ],
                )
            )
        return claims

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
                medications=fx.medications,
                supplements=fx.supplements,
                labs=fx.labs,
                reports=fx.reports,
                notes=fx.notes,
            ),
        }

        records = [
            *fx.conditions, *fx.medications, *fx.supplements, *fx.allergies,
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
        narrative_trends = _trends_for(labs_in_context, unresolved)
        claims = self.generate(view, labs_in_context, narrative_trends)

        prompt = json.dumps(
            {
                "view": view.model_dump(),
                "inputs": [r.model_dump() for r in projection.included],
            },
            sort_keys=True,
            default=str,
        )
        artifact = AISummary(
            id=new_id("aia"),
            patient_id=fx.patient.id,
            trace_id=scope.trace_id,
            created_at=moment,
            inputs=projection.included,
            omitted=projection.omitted,
            prompt_digest="sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
            model_id=self.model_id,
            model_digest=self.model_digest,
            engine=self.engine,
            engine_version=self.engine_version,
            consent_ref=scope.consent_id,
            claims=claims,
            unresolved=unresolved,
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

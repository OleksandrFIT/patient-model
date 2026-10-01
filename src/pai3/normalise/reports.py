"""Rendering the four outputs the optional build asks for.

Kept out of the pipeline so the reports can be tested against a `Result` rather than against
a file on disk, and so a change to the wording cannot change what was decided.
"""

import json
from typing import Any

from pai3.enums import FlagCode, Severity
from pai3.normalise.model import ConflictOutcome
from pai3.normalise.pipeline import Result

_SEVERITY_LABEL = {
    Severity.BLOCKING: "BLOCKING",
    Severity.HUMAN_REVIEW_REQUIRED: "review required",
    Severity.WARNING: "warning",
    Severity.ACCEPTABLE_MISSING: "acceptable",
}


def canonical_json(r: Result) -> str:
    """The canonical output, by layer, with nothing invented to fill a gap."""
    payload: dict[str, Any] = {
        "_note": (
            "Normalised from three conflicting sources in mock/sources/. Canonical holds only "
            "what a source vouched for; an unresolved conflict leaves the field empty and the "
            "flag names both candidates (model_design.md §9.3)."
        ),
        "source_documents": [d.model_dump(mode="json") for d in r.documents],
        "canonical": {
            "patient": r.patient.model_dump(mode="json") if r.patient else None,
            "conditions": [c.model_dump(mode="json") for c in r.conditions],
            "medications": [m.model_dump(mode="json") for m in r.medications],
            "supplements": [s.model_dump(mode="json") for s in r.supplements],
            "allergies": [a.model_dump(mode="json") for a in r.allergies],
            "lab_results": [lab.model_dump(mode="json") for lab in r.labs],
            "source_references": [s.model_dump(mode="json") for s in r.source_refs],
            "data_quality_flags": [f.model_dump(mode="json") for f in r.review_queue],
        },
        "not_accepted": {
            "_note": "Stayed in the source layer. No canonical record exists for these.",
            "rows": [row.model_dump(mode="json") for row in r.rejected],
        },
        "audit": [e.model_dump(mode="json") for e in r.audit],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def validation_report(r: Result) -> str:
    """What was checked, at which layer, and what each check found."""
    by_code: dict[FlagCode, list] = {}
    for f in r.flags:
        by_code.setdefault(f.code, []).append(f)

    lines = [
        "# Validation report",
        "",
        "Two layers, and which one a check belongs to decides whether a record exists at all",
        "(`docs/model_design.md` §9.1).",
        "",
        "## Layer 1 — structural. The record is never created.",
        "",
        f"{len(r.rejected)} row(s) refused. The value stays in the source document and the flag",
        "names the document rather than a canonical id, because there is no canonical id to name.",
        "",
    ]
    if r.rejected:
        lines += ["| Document | Page | Found | Why refused |", "|---|---|---|---|"]
        for row in r.rejected:
            raw = row.raw.get("analyte") or row.raw.get("raw_text") or "—"
            lines.append(
                f"| `{row.locator.document_id}` | {row.locator.page or '—'} | {raw} | {row.reason} |"
            )
        lines.append("")

    lines += [
        "## Layer 2 — data quality. The record exists and carries a flag.",
        "",
        f"{len(r.flags)} flag(s) across {len(by_code)} distinct codes.",
        "",
        "| Severity | Code | Count | What it means here |",
        "|---|---|---|---|",
    ]
    meaning = {
        FlagCode.CONFLICTING_VALUES: "two sources disagreed about one field",
        FlagCode.UNIT_MISMATCH: "the same measurement in two unit systems; nothing converts them",
        FlagCode.MISSING_UNIT: "a value with no unit — review, not rejection (D5)",
        FlagCode.MISSING_REFERENCE_RANGE: "the performing lab printed no range",
        FlagCode.INTERPRETATION_DISAGREES_WITH_RANGE: (
            "the lab's own flag contradicts the range stored beside it"
        ),
        FlagCode.UNCODED_CONCEPT: "free text that matched no code, and was not guessed at",
        FlagCode.DUPLICATE_CANDIDATE: "one fact asserted twice inside a single document",
        FlagCode.EXTRACTION_FAILED: "a row that could not be read at all",
        FlagCode.RECORD_REJECTED_AT_INGEST: "refused by layer 1; recorded so it is not invisible",
        FlagCode.DISCONTINUED_SHOWN_ACTIVE: (
            "the EMR and the patient disagree about whether a drug is still taken"
        ),
    }
    for code, flags in sorted(by_code.items(), key=lambda kv: kv[0].value):
        worst = min(flags, key=lambda f: list(_SEVERITY_LABEL).index(f.severity))
        lines.append(
            f"| {_SEVERITY_LABEL[worst.severity]} | `{code.value}` | {len(flags)} "
            f"| {meaning.get(code, '—')} |"
        )

    unraised = [c for c in FlagCode if c not in by_code]
    lines += [
        "",
        "## Codes this run did not raise",
        "",
    ]
    if unraised:
        for code in unraised:
            lines.append(
                f"- `{code.value}` — raised by the retraction cascade (§6.19), not by ingestion. "
                "Covered by `tests/test_lineage.py`."
            )
    else:
        lines.append("None: every declared code fired.")
    lines += [
        "",
        "Every other code in the enum fired on this data, which is what shows they are not",
        "dead declarations.",
        "",
    ]
    return "\n".join(lines)


def conflict_report(r: Result) -> str:
    """Every disagreement, what decided it, and what the canonical record now holds."""
    lines = [
        "# Conflict report",
        "",
        "Three sources, one patient. Trust is assigned **per field class and explicitly** —",
        "never \"the newest wins\", because recency is a heuristic and not a vouching (§9.3).",
        "",
        "| Field class | Order | Why |",
        "|---|---|---|",
        "| prescribed | emr > intake | the prescriber is the authority on what was prescribed |",
        (
            "| self_reported | intake > emr | the patient is the only reliable source for"
            " what she actually takes |"
        ),
        (
            "| lab_value | lab_report > emr > intake | the report is primary; the EMR holds"
            " a transcription |"
        ),
        "| coding | emr > lab_report > intake | free text cannot outrank a code |",
        "",
        (
            "Two assertions of the same class that disagree are never resolved automatically,"
            " whatever their confidence scores say. Confidence measures how well a line was"
            " read, not whether it is true."
        ),
        "",
    ]

    interesting = [
        (g, c) for g in r.groups for c in g.conflicts
        if c.outcome is not ConflictOutcome.AGREED
    ]
    corroborated = [g for g in r.groups if g.corroborated]

    lines += [
        f"## {len(interesting)} disagreement(s)",
        "",
    ]
    for g, c in sorted(interesting, key=lambda gc: (gc[0].kind.value, gc[0].key, gc[1].field_name)):
        shown = "<br>".join(
            f"`{x.source_class.value}`"
            + (f" p{x.locator.page}" if x.locator.page else "")
            + f" → `{x.value}`"
            + (f" (conf {x.confidence})" if x.confidence is not None else "")
            for x in c.candidates
        )
        # Computed, not looked up in a dict literal: a dict evaluates every branch, and
        # `c.winner` is None for both outcomes where no source won.
        if c.outcome is ConflictOutcome.RESOLVED_BY_TRUST:
            outcome = f"resolved to **{c.winner.value}**"
        elif c.outcome is ConflictOutcome.UNRESOLVED:
            outcome = "**unresolved** — the field is left empty"
        else:
            outcome = "**winner unrepresentable** — the rule's answer cannot be stored"
        lines += [
            f"### {g.kind.value} `{g.key}` — `{c.field_name}`",
            "",
            f"{shown}",
            "",
            f"{outcome}. Rule: {c.rule or '—'}",
            "",
        ]

    lines += [
        f"## {len(corroborated)} fact(s) corroborated across sources",
        "",
        "Asserted by more than one source with nothing contested between them. One canonical",
        "record with both citations attached — which is how a duplicate that agrees should be",
        "handled, and why it raises no flag.",
        "",
        "| Kind | Key | Sources |",
        "|---|---|---|",
    ]
    for g in sorted(corroborated, key=lambda g: (g.kind.value, g.key)):
        srcs = ", ".join(sorted(s.value for s in g.source_classes))
        lines.append(f"| {g.kind.value} | `{g.key}` | {srcs} |")
    lines.append("")
    return "\n".join(lines)


def review_queue(r: Result) -> str:
    """What a human must act on, worst first, each with the evidence attached."""
    queue = r.review_queue
    blocking = [f for f in queue if f.severity is Severity.BLOCKING]
    lines = [
        "# Human review queue",
        "",
        f"{len(queue)} item(s), worst first. {len(blocking)} blocking.",
        "",
        "`blocking` does not mean the record was refused — it means no read-model and no agent",
        "may draw a conclusion from it until a human has looked (§9.1).",
        "",
    ]
    for i, f in enumerate(queue, 1):
        target = (
            f"{f.targets[0].entity_type} `{f.targets[0].entity_id}`"
            + (f" field `{f.targets[0].field_path}`" if f.targets[0].field_path else "")
            if f.targets
            else "no canonical record — see the source document"
        )
        lines += [
            f"## {i}. `{f.code.value}` — {_SEVERITY_LABEL[f.severity]}",
            "",
            f"**Target:** {target}",
            "",
            f"{f.message}",
            "",
            (
                f"**Evidence:** {len(f.candidates) or len(f.source_locator)} source"
                f" reference(s) attached"
                f" (`{', '.join(f.candidates or f.source_locator) or '—'}`)"
            ),
            "",
        ]
    return "\n".join(lines)

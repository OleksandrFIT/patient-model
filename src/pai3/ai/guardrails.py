"""What is checked before a generation becomes an artifact (§10.5).

These verify grounding, not judgement: a claim can cite the right record, carry the right
number, and still be a poor clinical inference. They are asymmetric — fabrication is
caught, omission is not, because there is nothing to diff a summary against that was
never written.

Every check fails closed. Where a cited or omitted record is not among the records handed
in, that is itself a failure rather than a skipped check: a checker that cannot see what
it is checking must not report a pass.
"""

from enum import Enum

from pai3.ai.artifact import AISummary, GuardrailFailure
from pai3.ai.projection import is_non_droppable
from pai3.enums import Severity
from pai3.values.flags import FlagSummary

_HARD_CHECKS = frozenset(
    {
        "cites_in_inputs",
        "value_matches_source",
        "no_claim_on_empty_slot",
        "no_non_droppable_omitted",
        "record_available_for_checking",
    }
)


class Verdict(Enum):
    PASS = "pass"
    SOFT_FAIL = "soft_fail"
    HARD_FAIL = "hard_fail"


def run_guardrails(
    summary: AISummary,
    records: dict[str, object],
    open_blocking_flags: list[FlagSummary],
) -> tuple[Verdict, list[GuardrailFailure]]:
    """Run all five checks and classify the result.

    `records` maps canonical id to the record, for checks 2, 3 and 5.
    `open_blocking_flags` are the flags on the records in `inputs`, gathered by the caller.
    """
    failures: list[GuardrailFailure] = []
    input_ids = {ref.entity_id for ref in summary.inputs}

    # 1 — every citation was actually read.
    for claim in summary.claims:
        for ref in claim.cites:
            if ref.entity_id not in input_ids:
                failures.append(
                    GuardrailFailure(
                        check="cites_in_inputs",
                        detail=f"claim cites {ref.entity_id}, which is not in inputs",
                    )
                )

    # 2 and 3 — every asserted number matches its record, and no record with an empty
    # value slot is asserted about. Applies to anything carrying a `quantity`, which is
    # LabResult and VitalSign: §10.5 says every ClaimValue, not every lab ClaimValue.
    for claim in summary.claims:
        for value in claim.values:
            record = records.get(value.cites.entity_id)
            if record is None:
                failures.append(
                    GuardrailFailure(
                        check="record_available_for_checking",
                        detail=(
                            f"claim asserts {value.value} for {value.cites.entity_id}, "
                            "which was not supplied to the checker"
                        ),
                    )
                )
                continue
            if not hasattr(record, "quantity"):
                continue
            quantity = record.quantity
            if quantity is None:
                failures.append(
                    GuardrailFailure(
                        check="no_claim_on_empty_slot",
                        detail=(
                            f"claim asserts {value.value} for {value.cites.entity_id}, "
                            "whose value slot is empty"
                        ),
                    )
                )
                continue
            if quantity.value != value.value:
                failures.append(
                    GuardrailFailure(
                        check="value_matches_source",
                        detail=(
                            f"claim says {value.value} but {value.cites.entity_id} holds "
                            f"{quantity.value}"
                        ),
                    )
                )

    # 4 — open blocking flags were carried to the output.
    surfaced = {flag.flag_id for flag in summary.unresolved}
    for flag in open_blocking_flags:
        if flag.severity is Severity.BLOCKING and flag.flag_id not in surfaced:
            failures.append(
                GuardrailFailure(
                    check="blocking_flags_surfaced",
                    detail=f"blocking flag {flag.flag_id} ({flag.code}) was not surfaced",
                )
            )

    # 5 — nothing non-droppable was omitted. Droppability comes from the same function
    # the projection used, so the two cannot disagree about a resolved condition.
    for omission in summary.omitted:
        record = records.get(omission.ref.entity_id)
        if record is None:
            failures.append(
                GuardrailFailure(
                    check="no_non_droppable_omitted",
                    detail=(
                        f"{omission.ref.entity_type} {omission.ref.entity_id} was omitted "
                        "and was not supplied to the checker, so droppability is unknown"
                    ),
                )
            )
            continue
        if is_non_droppable(record):
            failures.append(
                GuardrailFailure(
                    check="no_non_droppable_omitted",
                    detail=(
                        f"{omission.ref.entity_type} {omission.ref.entity_id} was omitted "
                        f"({omission.reason}); the budget is wrong, not the record"
                    ),
                )
            )

    if any(f.check in _HARD_CHECKS for f in failures):
        return Verdict.HARD_FAIL, failures
    if failures:
        return Verdict.SOFT_FAIL, failures
    return Verdict.PASS, failures

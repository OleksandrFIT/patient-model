# Validation report

Two layers, and which one a check belongs to decides whether a record exists at all
(`docs/model_design.md` §9.1).

## Layer 1 — structural. The record is never created.

1 row(s) refused. The value stays in the source document and the flag
names the document rather than a canonical id, because there is no canonical id to name.

| Document | Page | Found | Why refused |
|---|---|---|---|
| `doc_lab` | 3 | vitamin D, 25-OH | no collection date: the result cannot be trended or placed on a timeline |

## Layer 2 — data quality. The record exists and carries a flag.

16 flag(s) across 10 distinct codes.

| Severity | Code | Count | What it means here |
|---|---|---|---|
| BLOCKING | `CONFLICTING_VALUES` | 6 | two sources disagreed about one field |
| BLOCKING | `DISCONTINUED_SHOWN_ACTIVE` | 1 | the EMR and the patient disagree about whether a drug is still taken |
| review required | `DUPLICATE_CANDIDATE` | 1 | one fact asserted twice inside a single document |
| review required | `EXTRACTION_FAILED` | 1 | a row that could not be read at all |
| review required | `INTERPRETATION_DISAGREES_WITH_RANGE` | 1 | the lab's own flag contradicts the range stored beside it |
| warning | `MISSING_REFERENCE_RANGE` | 1 | the performing lab printed no range |
| review required | `MISSING_UNIT` | 1 | a value with no unit — review, not rejection (D5) |
| review required | `RECORD_REJECTED_AT_INGEST` | 1 | refused by layer 1; recorded so it is not invisible |
| review required | `UNCODED_CONCEPT` | 2 | free text that matched no code, and was not guessed at |
| review required | `UNIT_MISMATCH` | 1 | the same measurement in two unit systems; nothing converts them |

## Codes this run did not raise

- `PARENT_RETRACTED` — raised by the retraction cascade (§6.19), not by ingestion. Covered by `tests/test_lineage.py`.

Every other code in the enum fired on this data, which is what shows they are not
dead declarations.

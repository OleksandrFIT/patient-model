# Conflict report

Three sources, one patient. Trust is assigned **per field class and explicitly** —
never "the newest wins", because recency is a heuristic and not a vouching (§9.3).

| Field class | Order | Why |
|---|---|---|
| prescribed | emr > intake | the prescriber is the authority on what was prescribed |
| self_reported | intake > emr | the patient is the only reliable source for what she actually takes |
| lab_value | lab_report > emr > intake | the report is primary; the EMR holds a transcription |
| coding | emr > lab_report > intake | free text cannot outrank a code |

Two assertions of the same class that disagree are never resolved automatically, whatever their confidence scores say. Confidence measures how well a line was read, not whether it is true.

## 7 disagreement(s)

### lab `1558-6|2026-02-26` — `value`

`lab_report` p2 → `7.2` (conf 0.93)<br>`lab_report` p3 → `5.5` (conf 0.88)

**unresolved** — the field is left empty. Rule: lab_value: both candidates are lab_report, so no rule applies

### lab `4548-4|2026-02-26` — `ref_high`

`emr` → `42`<br>`lab_report` p2 → `5.6` (conf 0.95)

resolved to **lab_report**. Rule: lab_value: lab_report > emr > intake

### lab `4548-4|2026-02-26` — `ref_low`

`emr` → `20`<br>`lab_report` p2 → `4.0` (conf 0.95)

resolved to **lab_report**. Rule: lab_value: lab_report > emr > intake

### lab `4548-4|2026-02-26` — `unit`

`emr` → `mmol/mol`<br>`lab_report` p2 → `%` (conf 0.95)

resolved to **lab_report**. Rule: lab_value: lab_report > emr > intake

### lab `4548-4|2026-02-26` — `value`

`emr` → `54.0`<br>`lab_report` p2 → `7.1` (conf 0.95)

resolved to **lab_report**. Rule: lab_value: lab_report > emr > intake

### medication `6809` — `dose_amount`

`emr` → `500.0`<br>`intake` → `1000.0`

resolved to **emr**. Rule: prescribed: emr > intake

### medication `6809` — `status`

`emr` → `active`<br>`intake` → `stopped`

**winner unrepresentable** — the rule's answer cannot be stored. Rule: self_reported: intake > emr

## 7 fact(s) corroborated across sources

Asserted by more than one source with nothing contested between them. One canonical
record with both citations attached — which is how a duplicate that agrees should be
handled, and why it raises no flag.

| Kind | Key | Sources |
|---|---|---|
| allergy | `7980` | emr, intake |
| condition | `E03.9` | emr, intake |
| condition | `E11.9` | emr, intake |
| lab | `3016-3|2026-02-26` | emr, lab_report |
| medication | `10582` | emr, intake |
| patient | `MRN-4471` | emr, intake |
| supplement | `vitamin d` | emr, intake |

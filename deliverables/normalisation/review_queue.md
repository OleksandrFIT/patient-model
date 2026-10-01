# Human review queue

16 item(s), worst first. 2 blocking.

`blocking` does not mean the record was refused — it means no read-model and no agent
may draw a conclusion from it until a human has looked (§9.1).

## 1. `CONFLICTING_VALUES` — BLOCKING

**Target:** LabResult `lab_0004` field `value`

lab 1558-6|2026-02-26, field value: lab_report p2 = 7.2 vs lab_report p3 = 5.5. Unresolved — lab_value: both candidates are lab_report, so no rule applies. The field is left empty (§9.3).

**Evidence:** 2 source reference(s) attached (`sref_0036, sref_0037`)

## 2. `DISCONTINUED_SHOWN_ACTIVE` — BLOCKING

**Target:** Medication `med_0002` field `status`

metformin: the EMR shows it active and the patient reports stopping it ('around January, not sure of the date'). The trust rule gives the patient the status, but §9.8 requires a stop date for a stopped medication and she cannot name one. Canonical keeps 'active' and this flag blocks any autonomous use until the month is established.

**Evidence:** 2 source reference(s) attached (`sref_0013, sref_0014`)

## 3. `CONFLICTING_VALUES` — review required

**Target:** Medication `med_0002` field `dose_amount`

medication 6809, field dose_amount: emr = 500.0 vs intake = 1000.0. Resolved to emr by rule [prescribed: emr > intake]; a human should confirm the other source is wrong rather than newer.

**Evidence:** 2 source reference(s) attached (`sref_0011, sref_0012`)

## 4. `CONFLICTING_VALUES` — review required

**Target:** LabResult `lab_0002` field `ref_high`

lab 4548-4|2026-02-26, field ref_high: emr = 42 vs lab_report p2 = 5.6. Resolved to lab_report by rule [lab_value: lab_report > emr > intake]; a human should confirm the other source is wrong rather than newer.

**Evidence:** 2 source reference(s) attached (`sref_0023, sref_0024`)

## 5. `CONFLICTING_VALUES` — review required

**Target:** LabResult `lab_0002` field `ref_low`

lab 4548-4|2026-02-26, field ref_low: emr = 20 vs lab_report p2 = 4.0. Resolved to lab_report by rule [lab_value: lab_report > emr > intake]; a human should confirm the other source is wrong rather than newer.

**Evidence:** 2 source reference(s) attached (`sref_0025, sref_0026`)

## 6. `CONFLICTING_VALUES` — review required

**Target:** LabResult `lab_0002` field `value`

lab 4548-4|2026-02-26, field value: emr = 54.0 vs lab_report p2 = 7.1. Resolved to lab_report by rule [lab_value: lab_report > emr > intake]; a human should confirm the other source is wrong rather than newer.

**Evidence:** 2 source reference(s) attached (`sref_0029, sref_0030`)

## 7. `CONFLICTING_VALUES` — review required

**Target:** Supplement `supp_0002`

biotin 5000mcg: reported on the intake form and absent from the EMR supplement list. Kept, because the patient is the authority on what she takes — but the EMR list is now known to be incomplete.

**Evidence:** 1 source reference(s) attached (`sref_0043`)

## 8. `DUPLICATE_CANDIDATE` — review required

**Target:** LabResult `lab_0004`

glucose, fasting appears more than once in one document (2 rows). One is likely an amended result; the pages are attached so a human can see which supersedes which.

**Evidence:** 2 source reference(s) attached (`sref_0034, sref_0035`)

## 9. `EXTRACTION_FAILED` — review required

**Target:** no canonical record — see the source document

doc_lab page 3: analyte or value could not be read from the page. Read as '████ 1.9 ██/█  (band obscured by stamp)' with confidence 0.31. No canonical record was created.

**Evidence:** 1 source reference(s) attached (`sref_0044`)

## 10. `INTERPRETATION_DISAGREES_WITH_RANGE` — review required

**Target:** LabResult `lab_0005` field `reported_interpretation`

ferritin: lab reported 'N' but the stored range gives 'low' — the stored range is suspect

**Evidence:** 0 source reference(s) attached (`—`)

## 11. `MISSING_UNIT` — review required

**Target:** LabResult `lab_0003` field `quantity`

free T4: value 11.2 has no unit

**Evidence:** 0 source reference(s) attached (`—`)

## 12. `RECORD_REJECTED_AT_INGEST` — review required

**Target:** no canonical record — see the source document

vitamin D, 25-OH: rejected at ingest — no collection date. The value stays in the source document; re-read the page or request a reissue.

**Evidence:** 1 source reference(s) attached (`sref_0039`)

## 13. `UNCODED_CONCEPT` — review required

**Target:** Condition `cond_0003`

'fibromyalgia': asserted on the intake form only, so it is UNCONFIRMED and not assertable in a summary. No code was matched, so the term was not guessed at — a clinician should confirm and code it.

**Evidence:** 1 source reference(s) attached (`sref_0041`)

## 14. `UNCODED_CONCEPT` — review required

**Target:** Condition `cond_0003` field `code`

condition 'fibromyalgia' is not coded

**Evidence:** 0 source reference(s) attached (`—`)

## 15. `UNIT_MISMATCH` — review required

**Target:** LabResult `lab_0002` field `unit`

lab 4548-4|2026-02-26, field unit: emr = 'mmol/mol' vs lab_report p2 = '%'. Resolved to lab_report by rule [lab_value: lab_report > emr > intake]; a human should confirm the other source is wrong rather than newer.

**Evidence:** 2 source reference(s) attached (`sref_0027, sref_0028`)

## 16. `MISSING_REFERENCE_RANGE` — warning

**Target:** LabResult `lab_0003` field `reference_range`

free T4: no reference range from the performing lab

**Evidence:** 0 source reference(s) attached (`—`)

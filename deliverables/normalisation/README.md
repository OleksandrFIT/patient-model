# Optional build — normalising three conflicting sources

Three source documents for one patient, reconciled into canonical records.

```bash
.venv/bin/python scripts_normalise.py        # regenerate; git diff should be empty
.venv/bin/pytest tests/normalise -q          # 25 tests
```

| Input | Class | What it is |
|---|---|---|
| `mock/sources/emr_export.json` | `emr` | A structured export. Authoritative for what was prescribed |
| `mock/sources/lab_report_extraction.json` | `lab_report` | AI-extracted PDF rows, each with a confidence and the text it came from |
| `mock/sources/intake_form.csv` | `intake` | A spreadsheet the patient filled in at reception. Free text throughout |

| Output | What it holds |
|---|---|
| `canonical.json` | The canonical records, their citations, their flags, and the rows that did not become records |
| `validation_report.md` | What was checked, at which layer, and what each check found |
| `conflict_report.md` | Every disagreement, what decided it, and what canonical now holds |
| `review_queue.md` | What a human must act on, worst first, each with its evidence |

---

## What was automated

**Reading all three formats, and keying across them.** Nested JSON, extracted rows and a CSV
of free text become one kind of intermediate object. The keying is what makes two sources meet:
`Hypothyroidism` with ICD-10 `E03.9` from the EMR and the word `hypothyroid` typed on an intake
form resolve to the same canonical condition rather than two active diagnoses for one thyroid.

**Deciding which source wins, by an explicit rule per field class.** Not by recency, which §9.3
forbids as a heuristic rather than a vouching, and not by confidence.

| Field class | Order | Why |
|---|---|---|
| prescribed — dose, prescriber, start date | `emr > intake` | the prescriber is the authority on what was prescribed |
| self_reported — status, supplements | `intake > emr` | the patient is the only reliable source for what she actually takes |
| lab_value — value, unit, range | `lab_report > emr > intake` | the report is primary; the EMR holds a transcription |
| coding | `emr > lab_report > intake` | free text cannot outrank a code |

**Detecting and classifying ten kinds of defect.** Every flag code the model declares fired on
this data except `PARENT_RETRACTED`, which belongs to the retraction cascade rather than to
ingestion. Six of them had no caller anywhere before this build, which is what shows they were
declarations rather than dead code.

**Refusing a record where layer 1 says it cannot exist**, and recording the refusal against the
document so it is not merely absent. A lab result with an illegible collection date stays in the
source layer; the flag names the page.

**Counting what each document claimed.** The EMR declares a row count, so completeness is
checkable. The PDF declares none, so `expected` is `None` — not flagged, because one flag per
ingested PDF is noise, but queryable, because "which documents have unverifiable completeness"
has to be answerable.

---

## What was not automated, and why

**Choosing between two readings of the same page.** Fasting glucose appears twice in one lab
report: `7.2` on page 2 and `5.5` on page 3, where page 3 is marked amended. Both are
`lab_report`, so no trust rule can separate them. The canonical record keeps the analyte, the
date and the reference range, and the **value slot stays empty** with a blocking flag naming both
pages. A system that picked one would be guessing, and the guess would be invisible.

Confidence was available — 0.93 against 0.88 — and was deliberately not used. Confidence measures
how well a line was read, not whether it is true. Letting it decide would reintroduce the silent
winner through the back door.

**Flipping a medication to stopped on an undated self-report.** The trust rule gives the patient
the status: she says she is no longer taking metformin. §9.8 requires a stop date for a stopped
medication, and she cannot name the month — *"around January, not sure of the date"*. Neither
side gives way, so canonical keeps the EMR's `active` and a **blocking** flag records the dispute.

This was not anticipated when the model was designed. The invariant that makes "discontinued shown
as active" unrepresentable also prevents the normaliser from acting on an undated self-report — so
the conflict stays visible instead of being resolved in either direction. A new outcome,
`WINNER_UNREPRESENTABLE`, exists because the data produced it.

**Converting between unit systems.** HbA1c arrives as `54 mmol/mol` from the EMR and `7.1 %` from
the report. These are the same measurement. Nothing in the model converts them (§10.6 names
conversion as out of scope), so the report's value is kept, the mismatch is flagged, and a human
decides which system the practice stores. A trend will not mix them.

**Guessing at an unmatched term.** The synonym table that maps `hypothyroid` to `E03.9` is
deliberately tiny, and a real deployment resolves free text against a terminology service. A term
it does not know — the patient wrote `fibromyalgia`, which the practice's coded problem list does
not carry — becomes its own record, **uncoded** and **`UNCONFIRMED`**, and §6.4 keeps it out of any
summary. The alternative is a guessed code, which is a fabricated diagnosis.

**Deciding whether the EMR's supplement list is simply incomplete.** The patient reports biotin;
the EMR does not list it. It is kept, because she is the authority on what she takes — and the flag
says the EMR list is now known to be incomplete, which is a different and more useful statement
than "conflict".

**Reviewing anything.** 16 flags, 2 blocking, each with its source references attached. The
pipeline surfaces; it does not resolve.

---

## One thing worth saying about bulk acceptance

§1 permits a canonical record with `origin=ai_extraction` only once a human has accepted it. A
migration run accepts in bulk, and bulk acceptance is a rubber stamp unless two things hold: a
named person is accountable for the run, and everything that needed a decision reaches a queue.

Both hold here — `asserted_by` on every extracted record names the data steward, and the queue is
one of the four outputs. Nobody hand-reviews ten thousand lab rows, and a submission that implied
otherwise would be the dishonest part. What makes it not a rubber stamp is that the queue is short
*because* most rows were uncontested, and the contested ones are all in it.

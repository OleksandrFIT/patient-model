# Phase 1: a governed foundation for your patient data

## What a canonical patient model is

Your patient data lives in several places at once — your EMR, lab portals, PDFs from outside
specialists, intake forms, spreadsheets, and messages. Each holds a version of the same
patient, and none of them agrees entirely with the others.

A canonical model is the single agreed description of a patient that sits above all of them.
Not a copy of your EMR and not a replacement for it: a definition of what a condition, a
medication, a lab result and an allergy *are* in your practice, so that one patient assembled
from four sources comes out as one record rather than four overlapping ones.

The important part is what it refuses to do. It will not quietly pick a winner when two
sources disagree. If your EMR says a glucose of 5.5 and the lab report says 7.2, the
canonical record holds **neither** value and shows the physician both, labelled as
unresolved. A system that guesses is more dangerous than one that admits it does not know,
because the guess is invisible.

## Why the data foundation matters

Every downstream thing you want — summaries, trends, follow-up lists, risk review — is built
on the same substrate. If that substrate treats a discontinued medication as active, every
tool built on it does too, and each one looks confident.

Most of the risk is not dramatic failure. It is a condition resolved in 2019 that still reads
as current. A supplement mentioned once by phone that nobody wrote down. Two lab results in
different units averaged into a trend that means nothing. Each is small, each is routine, and
each changes what a physician does.

## Why source traceability is required

Every value in the record names where it came from and who stood behind it: which document,
which page, which field, and whether a person, a source system, or an extraction put it
there.

A physician who distrusts a value sees its origin in one step instead of hunting for the fax.
A disagreement between two sources is settled by looking at both, rather than by deciding
which system to trust in general. And every sentence a tool produces can be traced back to
the record that justified it.

Without traceability a summary is an assertion. With it, the summary is evidence that can be
checked.

## Why AI needs structured, validated data

AI is good at synthesis and poor at knowing what it does not know. Given clean structure, it
turns twelve records into four readable sentences. Given a free-text dump, it fills gaps with
plausible text, and plausible text is indistinguishable from fact at a glance.

So the foundation does three things. It validates: a lab value arriving without a unit is
flagged for review, not silently accepted. It restricts: the model receives clinical facts
plus age and sex, never names or record numbers. And it checks the output: every number a
summary asserts is compared against the record it cites, and a summary that cannot be
grounded is withheld with the reason shown.

One limit we state plainly: these checks catch invented content. They cannot catch what a
summary left out. The brief shortens preparation; it does not replace reading the chart.

## What you would need to provide

- **Read access to each source**: EMR export, lab feeds, and a sample of the PDFs and intake
  forms as they actually arrive — including the messy ones.
- **Twenty to thirty real patients' worth of data**, de-identified if you prefer. The
  conflicts between your sources are the design input; we cannot guess them.
- **A few hours of clinical time** to settle questions only you can answer: which source wins
  for a medication dose, how long a social history stays current, what belongs in a brief.
- **Someone to own the review queue.** The system will surface conflicts; it will not resolve
  them.
- **Your consent records**, in whatever form they exist. Automated processing is gated on
  them.

## What success looks like at the end of Phase 1

A working model of your patients, with real records loaded through it. A report naming every
conflict and gap it found in your actual data — usually the most immediately useful output,
independent of anything AI. One workflow running end to end: a pre-visit brief assembled from
the record, sources cited, unresolved items visible. And a clear account of what the system
refuses to do, so the Phase 2 decision rests on evidence rather than on a demonstration.

# Project context

PAI3 practical test — canonical patient data model for a concierge medical practice.
Full requirements are in ASSIGNMENT.md. Read it before proposing anything.

## Decisions I have already made

**Stack: Python + Pydantic v2.**
Runtime validation at ingestion, not compile-time. TypeScript types disappear after
compilation — a lab PDF arriving without a unit would pass through unnoticed.
Pydantic rejects or flags it at the boundary. Second reason: local inference
(ollama, llama.cpp) is a Python-first ecosystem.

**AI never writes to the canonical layer.**
Not because AI output is low quality — because once written, an AI value is
indistinguishable from what a physician entered. There is nothing to roll back to
and nothing to show in an audit. Canonical stays the source of truth; AI output
lives in its own layer next to it, carrying its review status.

**Workflow for D8: Physician Pre-Visit Brief.**
It exercises almost the entire model — conditions, medications, labs, allergies,
notes — so it demonstrates the model in operation rather than one entity in isolation.
D8 asks which parts of the patient model are used; this workflow has a real answer.

**Doing the optional normalization build.**
Three conflicting source records into canonical JSON plus a conflict report and
human review queue. Only after the 11 core deliverables are complete.

## How I want to work

- One file per step. Stop after each and wait for my review.
- Use plan mode before any non-trivial step. I want to see the plan before code exists.
- No speculative fields. If I did not ask for it, do not add it.
- Docstrings explain why a field exists, not what it holds.
- Do not resolve design questions on your own — ask me.

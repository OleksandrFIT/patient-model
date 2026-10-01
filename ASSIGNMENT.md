# PAI3 Practical Candidate Test — AI Systems Engineer

*Designing and defending a real-world patient data foundation for AI systems.*

The engineer role is focused on correctness, reliability, agent systems, APIs, and local AI execution.

---

## Purpose

This practical test evaluates whether candidates can design and defend a real-world patient data
foundation for AI systems.

PAI3 does not need people who simply ask AI for answers. We need people who can use AI
intelligently, critique the output, defend their decisions, and produce work that can survive
real client complexity.

The central assignment is to design and, where appropriate, implement a canonical patient data
model that represents a patient across multiple dimensions of clinical, operational, workflow,
and AI-readiness data.

---

## Universal Rules

Candidates may use AI tools, including ChatGPT, Claude, Cursor, Gemini, Perplexity, or similar.

AI use is allowed, but full transparency is required.

Each candidate must submit:

- All prompts used
- A summary of what AI produced
- Their critique of the AI output
- What they accepted
- What they rejected
- What they changed
- Why they made those changes
- Total time spent on the assignment

The candidate must be able to explain and defend every major design choice.

Submitting polished AI output without understanding it is a failure condition.

---

## Scenario

PAI3 Labs is beginning discovery for a concierge medical practice.

The client has patient data spread across:

- EMR records
- Lab reports
- Intake forms
- PDF documents
- Spreadsheets
- Patient messages
- Physician notes
- Treatment plans
- Supplements and medications
- Wearable or patient-reported data
- Staff tasks and follow-up workflows

The client wants a governed data foundation that can support:

- Accurate physician review
- AI-assisted patient summaries
- Clinical timeline construction
- Lab trend analysis
- Follow-up task extraction
- Risk and compliance review
- Human-in-the-loop clinical workflows
- Future AI agents operating on local/private infrastructure

The first phase is not to build a full production product. The first phase is to define a
practical canonical patient data model, identify source data issues, create validation logic,
and demonstrate how AI systems can safely operate on structured, source-linked patient information.

---

## Central Assignment

### Design a Canonical Patient Data Model

The candidate must design a canonical patient data model that encompasses multiple dimensions
of patient data.

The model must not be limited to demographics or clinical notes. It must represent the patient
as a multidimensional object that can support clinical review, operational workflows,
AI-assisted reasoning, source traceability, and governance.

The candidate must explain each major element of the model, what it contains, why it is
necessary, and what risks arise if that element is missing, stale, duplicated, or incorrect.

### Required Patient Data Dimensions

The model should address, at minimum, the following areas:

- Patient identity and demographics
- Contact information
- Consent and authorization
- Care team and provider relationships
- Insurance or payment context, if relevant
- Medical history
- Current conditions and diagnoses
- Symptoms and patient concerns
- Medications
- Supplements
- Allergies and contraindications
- Lab results and biomarkers
- Vitals and measurements
- Imaging and diagnostic reports
- Clinical notes
- Treatment plans
- Procedures and interventions
- Patient goals and preferences
- Lifestyle and social factors
- Timeline of clinical events
- Documents and source references
- Tasks, follow-ups, and workflow state
- Data provenance and audit trail
- Data quality flags
- AI-generated summaries and human review status

Candidates may add, merge, rename, or reorganize these dimensions if they can defend their choices.

---

## Required Deliverables

### Deliverable 1: Canonical Patient Data Model

Submit a structured model that includes:

- Main entities
- Fields within each entity
- Data types
- Required vs optional fields
- Relationships between entities
- Normalized vs embedded design choices
- Unique identifiers
- Versioning approach
- Source system references
- Audit and provenance fields

The model may be presented as:

- Entity relationship diagram
- JSON schema
- TypeScript interfaces
- Python/Pydantic models
- SQL schema
- Structured tables
- A combination of the above

### Deliverable 2: Explanation of Each Model Element

For every major section of the model, explain:

- What this element contains
- Why it is necessary
- Which source systems may provide it
- How physicians, staff, or AI agents may use it
- What risks exist if the data is missing, stale, duplicated, conflicting, or incorrect

Suggested table format:

| Model Element | What It Contains | Why It Matters | Source Systems | AI/Workflow Use | Risks |
|---|---|---|---|---|---|
| Lab Results | Biomarker name, value, unit, reference range, collection date, source lab, abnormal flag | Enables trend analysis and clinical interpretation | Lab PDFs, EMR, uploads | Lab summaries, trend detection | Unit mismatch, missing range, duplicate reports |
| Medications | Drug, dose, route, frequency, start date, stop date, status, prescriber | Prevents unsafe recommendations and supports accurate summaries | EMR, notes, patient intake | Medication reconciliation, safety checks | Conflicting doses, discontinued meds shown as active |
| Source References | Original system, document, page, field, import date, confidence, reviewer | Preserves evidence and auditability | All systems | Citations, review, dispute resolution | AI cannot prove where a claim came from |

### Deliverable 3: Example Patient Record

Create one realistic mock patient record using the model.

The example must be fake and must not contain real patient information.

It should include:

- Demographics
- Conditions
- Medications
- Supplements
- Allergies
- Labs
- Vitals
- Notes
- Treatment plan
- Timeline events
- Source references
- Data quality flags
- AI-generated summary with human review status

### Deliverable 4: Data Provenance and Auditability Design

Explain how the model tracks:

- Source system
- Source document
- Source field
- Date imported
- Date last updated
- Who or what changed the record
- Whether a field came from a human, source system, or AI extraction
- Confidence level, if AI extraction was used
- Human review status
- Version history

The candidate must explain why provenance is essential for clinical AI systems.

The model should preserve source evidence and should not allow AI-generated conclusions
to overwrite source truth.

### Deliverable 5: Data Quality and Validation Rules

Define validation rules for the model.

Examples:

- Patient must have a durable patient identifier.
- Lab value must include biomarker name, value, unit, and collection date.
- Medication should include dose, route, frequency, status, and source when known.
- AI-generated summaries must be marked as AI-generated.
- Clinical assertions must link back to source evidence.
- Duplicate records must be detected.
- Conflicting records must be flagged, not silently overwritten.
- Discontinued medications must not be treated as active without review.
- Abnormal lab flags must preserve the lab-specific reference range.
- Missing units must trigger review.
- Extracted PDF data must carry extraction confidence and source document reference.

Classify validation issues as:

- Blocking error
- Warning
- Human review required
- Acceptable missing value

### Deliverable 6: AI Readiness and Governance

Explain how this model supports safe AI use.

The answer should include:

- Which fields AI can read
- Which fields AI can write
- Which fields AI can suggest but not finalize
- Which fields require human approval
- How AI-generated content is labeled
- How hallucination risk is reduced
- How source citations are preserved
- How conflicts are handled
- How the model prevents AI from overwriting clinical truth
- How the model supports local/private AI execution

### Deliverable 7: Implementation Component

Candidates should implement a small version of the model.

Acceptable implementation formats include:

- JSON schema
- TypeScript interfaces
- Python/Pydantic models
- SQL DDL
- A small normalization script
- A mock API contract

The implementation must include at least:

- Patient
- Encounter or clinical event
- Condition
- Medication
- Supplement
- Lab result
- Clinical note
- Treatment plan
- Source reference
- Audit/provenance object
- Data quality flag
- AI-generated summary object

### Deliverable 8: Workflow Application

Choose one workflow that would use the canonical patient model.

Examples:

- New patient intake
- Lab review
- Physician pre-visit brief
- Patient timeline generation
- Follow-up task extraction
- Medication reconciliation
- Patient message triage

For the selected workflow, document:

- Current-state workflow
- Pain points
- Future-state workflow
- Which parts of the patient model are used
- Where AI can assist
- Where human review is required
- What could go wrong
- What should be out of scope for Phase 1

### Deliverable 9: Client-Ready Summary

Write a short client-facing summary explaining:

- What a canonical patient model is
- Why the data foundation matters
- Why source traceability is required
- Why AI needs structured, validated patient data
- What the client must provide
- What success looks like at the end of Phase 1

Expected length: 500–700 words.

### Deliverable 10: AI Prompt Log and Critique

Submit a complete AI prompt log.

For each prompt, include:

- Tool used
- Exact prompt
- Output summary
- What was useful
- What was wrong, generic, unsafe, or incomplete
- What was accepted
- What was rejected
- What was changed
- Why the candidate made the final decision

### Deliverable 11: Time Log

Submit total time spent.

Suggested format:

| Activity | Time Spent |
|---|---|
| Reading assignment | |
| Planning | |
| AI prompting | |
| Model design | |
| Implementation | |
| Workflow analysis | |
| Final documentation | |
| Review | |
| Total | |

---

## Role-Specific Expectations: AI Systems Engineer

The AI Systems Engineer is expected to focus on system correctness, performance, reliability,
implementation, API readiness, local execution, and agent interaction.

The engineer's submission should emphasize:

- Implementable schema design
- Clean entity relationships
- Validation logic
- Provenance and audit architecture
- Versioning
- API or integration readiness
- Agent-readiness
- Local/private execution constraints
- Error handling
- Reliability under messy data conditions
- Separation of source data, canonical data, and AI-generated data
- How agents safely consume the model without corrupting it

The engineer should produce a lightweight technical implementation.

### Engineer-Specific Deliverable

In addition to the deliverables above, the engineer must submit one of the following:

- TypeScript interfaces plus validation examples
- Python/Pydantic models plus validation examples
- JSON schema plus sample valid and invalid records
- SQL DDL plus example inserts and constraints
- A small normalization script that converts messy mock source data into the canonical format

The engineer must include a README explaining:

- How the model is structured
- How validation works
- How provenance is represented
- How an AI agent would safely read from the model
- What the agent is not allowed to modify directly

---

## Optional Advanced Engineer Build

For stronger technical screening, provide a small mock dataset and ask the engineer to
normalize it.

### Input

Provide three mock source records for the same patient:

- EMR export
- Lab PDF extraction
- Intake spreadsheet row

The records should intentionally contain conflicts, such as:

- Different medication dose
- Missing lab units
- Different spelling of condition
- Conflicting supplement list
- Discontinued medication appearing as active
- Duplicate lab result

### Required Output

The engineer must produce:

- Canonical JSON output
- Validation report
- Conflict report
- Human review queue
- Short explanation of what was automated and what was not

---

## Recommended Time Limit

### AI Systems Engineer

Recommended time: 4 to 5 hours

Expected output should include documentation plus a lightweight implementation of the model.

If assigning the optional normalization build, allow an additional 2 hours.

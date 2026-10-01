"""Audit the brief's required dimensions against the code and the example record.

    .venv/bin/python scripts_audit_dimensions.py

Three independent things are checked, and the point is that none of them is a restatement of
the others:

1. **The brief against D2.** Every dimension in `ASSIGNMENT.md` has a row in D2's map, and the
   wording matches verbatim, so a reviewer walking the list with a pencil finds every line.
2. **D2 against the code.** Every identifier D2 names in backticks resolves — a class that
   exists, or a field on the entity named in the same row.
3. **D2 against the example record.** Every entity D2 names is actually instantiated in
   `deliverables/d3_example_patient.json`. A dimension covered in code but absent from the
   example is a claim a reviewer cannot verify.

The first version of this audit compared a hand-written mapping to itself, which proved nothing,
and guessed JSON keys from class names with a string heuristic that got four of them wrong. Both
mistakes are the same mistake: checking a claim against another copy of the claim.

Exits non-zero on any problem, so it can gate a submission.
"""

import importlib
import inspect
import json
import pathlib
import re

from pai3.base import CanonicalRecord, ClinicalRecord, PatientScoped

BASES = {"CanonicalRecord", "PatientScoped", "ClinicalRecord"}

# Where each entity appears in the example record. Written out rather than derived from the
# class name, because a heuristic that turns "AllergyIntolerance" into "allergies" will also
# turn something else into the wrong key and pass.
EXAMPLE_KEY = {
    "Patient": "canonical.patient", "Provider": "canonical.provider",
    "Consent": "canonical.consents", "Coverage": "canonical.coverage",
    "Encounter": "canonical.encounters", "Condition": "canonical.conditions",
    "Symptom": "canonical.symptoms", "AllergyIntolerance": "canonical.allergies",
    "Medication": "canonical.medications", "Supplement": "canonical.supplements",
    "DiagnosticReport": "canonical.diagnostic_reports",
    "LabResult": "canonical.lab_results", "VitalSign": "canonical.vitals",
    "Procedure": "canonical.procedures", "ClinicalNote": "canonical.clinical_notes",
    "TreatmentPlan": "canonical.treatment_plans", "Goal": "canonical.goals",
    "SocialFactor": "canonical.social_factors", "Task": "canonical.tasks",
    "SourceReference": "canonical.source_references",
    "DataQualityFlag": "canonical.data_quality_flags", "AuditEvent": "audit",
    "TimelineEvent": "derived.timeline", "LabTrend": "derived.lab_trends",
    "AISummary": "ai_layer.summary",
    "Provenance": None,       # embedded on every record, has no section of its own
    "SourceDocument": None,   # source layer, deliberately not canonical
}


def load_classes() -> tuple[dict, dict]:
    classes, fields = {}, {}
    for f in sorted(pathlib.Path("src/pai3").rglob("*.py")):
        name = str(f.with_suffix("")).replace("/", ".").replace("src.", "")
        mod = importlib.import_module(name)
        for cls_name, obj in vars(mod).items():
            if inspect.isclass(obj) and obj.__module__ == mod.__name__:
                classes[cls_name] = obj
                if hasattr(obj, "model_fields"):
                    fields[cls_name] = set(obj.model_fields)
    return classes, fields


def main() -> int:
    problems: list[str] = []

    dims = [
        line.strip("- ").strip()
        for line in pathlib.Path("ASSIGNMENT.md").read_text()
        .split("### Required Patient Data Dimensions")[1]
        .split("Candidates may add")[0]
        .splitlines()
        if line.strip().startswith("- ")
    ]
    d2 = pathlib.Path("deliverables/d2_model_elements.md").read_text()
    claims = {
        int(m[0]): (m[1].strip().strip("*"), m[2].strip())
        for m in re.findall(r"^\| (\d+) \| (.+?) \| (.+?) \|$", d2, re.MULTILINE)
    }
    classes, fields = load_classes()

    with pathlib.Path("deliverables/d3_example_patient.json").open() as fh:
        d3 = json.load(fh)
    flat = {
        f"{section}.{k}": (len(v) if isinstance(v, list) else (1 if v else 0))
        for section in ("canonical", "derived", "ai_layer")
        for k, v in d3[section].items()
    }
    flat["audit"] = len(d3.get("audit", []))

    print(f"{'#':>3}  {'dimension':46} code      example")
    print("─" * 92)
    for i, dim in enumerate(dims, 1):
        if i not in claims:
            problems.append(f"dimension {i} ({dim}) has no row in D2")
            print(f"{i:>3}. {dim[:45]:46} {'—':9} {'—'}")
            continue
        claimed, where = claims[i]
        if claimed.lower() != dim.lower():
            problems.append(f"{i}: D2 says {claimed!r}, the brief says {dim!r}")

        # the entity this row is about, for resolving bare field names
        entities_here = [
            n for n in re.findall(r"`([A-Za-z_][\w.]*)`", where)
            if n.split(".")[0] in classes
        ]
        owner = entities_here[0].split(".")[0] if entities_here else None

        code, example = "ok", "ok"
        for ident in re.findall(r"`([A-Za-z_][\w.]*)`", where):
            head, _, attr = ident.partition(".")
            if head in classes:
                if attr and attr not in fields.get(head, set()):
                    code = "FAIL"
                    problems.append(f"{i}: {head} has no field {attr!r}")
                    continue
                key = EXAMPLE_KEY.get(head, "UNMAPPED")
                if key == "UNMAPPED":
                    problems.append(f"{i}: {head} is not in EXAMPLE_KEY — extend this script")
                elif key and not flat.get(key):
                    example = "ABSENT"
                    problems.append(f"{i}: {head} is not instantiated in the example record")
            elif owner and head in fields.get(owner, set()):
                pass  # a bare field name, resolved against the entity named in the same row
            else:
                code = "FAIL"
                problems.append(f"{i}: cannot resolve `{ident}` as a class or a field of {owner}")
        print(f"{i:>3}. {dim[:45]:46} {code:9} {example}")

    print("─" * 92)
    entities = {
        n: c for n, c in classes.items()
        if issubclass(c, CanonicalRecord) and n not in BASES
    }
    tiers = {"Canonical": 0, "PatientScoped": 0, "Clinical": 0}
    for cls in entities.values():
        tiers[
            "Clinical" if issubclass(cls, ClinicalRecord)
            else "PatientScoped" if issubclass(cls, PatientScoped) else "Canonical"
        ] += 1
    for name in sorted(entities):
        key = EXAMPLE_KEY.get(name, "UNMAPPED")
        if key == "UNMAPPED":
            problems.append(f"entity {name} is not in EXAMPLE_KEY — extend this script")
        elif key and not flat.get(key):
            problems.append(f"entity {name} is not instantiated in the example record")

    print(f"dimensions {len(dims)}  |  D2 rows {len(claims)}  |  entities {len(entities)} {tiers}")
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nno problems: every dimension has a row, every identifier resolves, every entity")
    print("named by D2 is instantiated in the example record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

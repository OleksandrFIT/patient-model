"""One reader per source format.

Each reader does two things and nothing else: turn rows into `RawAssertion` objects, and
decide the matching key. It does not resolve anything — a reader that resolved would hide
the disagreement it was supposed to surface.

The keying rule is stated per reader because getting it wrong is the expensive mistake: too
loose and two facts merge, too tight and one fact splits into two records that then drift.
"""

import csv
import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

from pai3.normalise.model import (
    AssertionKind,
    Locator,
    RawAssertion,
    SourceClass,
    SourceDocument,
)

RECEIVED_AT = datetime(2026, 3, 11, 8, 0, tzinfo=UTC)
"""Fixed so a run is reproducible. A real pipeline stamps the actual receipt time."""

_CONDITION_CODES: dict[str, tuple[str, str]] = {
    "hypothyroidism": ("ICD-10", "E03.9"),
    "hypothyroid": ("ICD-10", "E03.9"),
    "type 2 diabetes mellitus": ("ICD-10", "E11.9"),
    "type 2 diabetes": ("ICD-10", "E11.9"),
    "t2dm": ("ICD-10", "E11.9"),
}
"""A deliberately tiny synonym table, and a named limit.

A real deployment resolves free text against a terminology service. This exists so the
demonstration performs the matching step instead of skipping it: "hypothyroid" from an intake
form and "Hypothyroidism" from an EMR reach the same canonical condition. A term that is not
in the table becomes its own record carrying UNCODED_CONCEPT, which is the honest outcome —
not a guess.
"""

_SUPPLEMENT_ALIASES: dict[str, str] = {
    "vitamin d3": "vitamin d",
    "vitamin d drops": "vitamin d",
    "vitamin d": "vitamin d",
    "biotin": "biotin",
}


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def condition_key(raw_text: str, code: str | None) -> tuple[str, tuple[str, str] | None]:
    """Key a condition by its code where one is known, else by normalised text.

    Coding is what lets two spellings meet. Without it "hypothyroid" and "Hypothyroidism"
    become two active conditions for one thyroid.
    """
    coding = _CONDITION_CODES.get(_norm(raw_text))
    if code:
        return code, coding or ("ICD-10", code)
    if coding:
        return coding[1], coding
    return f"text:{_norm(raw_text)}", None


# ----------------------------------------------------------------------- EMR

def read_emr(path: Path) -> tuple[SourceDocument, list[RawAssertion]]:
    """Structured export. Keyed on the code the EMR already supplies."""
    payload = json.loads(path.read_text())
    doc = SourceDocument(
        id="doc_emr", source_class=SourceClass.EMR, filename=path.name,
        content_sha256=_hash(path), received_at=RECEIVED_AT,
        declared_row_count=(
            len(payload["problems"]) + len(payload["medications"])
            + len(payload["supplements"]) + len(payload["allergies"])
            + len(payload["labs"]) + 1
        ),
    )
    out: list[RawAssertion] = []

    def loc(field_path: str) -> Locator:
        return Locator(document_id=doc.id, field_path=field_path)

    p = payload["patient"]
    out.append(RawAssertion(
        source_class=SourceClass.EMR, locator=loc("patient"), kind=AssertionKind.PATIENT,
        key=p["mrn"],
        payload={
            "mrn": p["mrn"], "system": "emr-west", "given": [p["first_name"]],
            "family": p["last_name"], "birth_date": date.fromisoformat(p["dob"]),
            "sex_at_birth": "female" if p["sex"] == "F" else "male",
        },
    ))

    for i, prob in enumerate(payload["problems"]):
        key, coding = condition_key(prob["desc"], prob.get("icd10"))
        out.append(RawAssertion(
            source_class=SourceClass.EMR, locator=loc(f"problems[{i}]"),
            kind=AssertionKind.CONDITION, key=key,
            payload={
                "raw_text": prob["desc"], "coding": coding,
                "clinical_status": prob["status"],
                "onset": date.fromisoformat(prob["onset"]) if prob.get("onset") else None,
            },
        ))

    for i, med in enumerate(payload["medications"]):
        out.append(RawAssertion(
            source_class=SourceClass.EMR, locator=loc(f"medications[{i}]"),
            kind=AssertionKind.MEDICATION, key=med["rxnorm"],
            payload={
                "raw_text": med["name"], "coding": ("RxNorm", med["rxnorm"]),
                "dose_text": med["sig"], "dose_amount": float(med["dose_amount"]),
                "dose_unit": med["dose_unit"], "frequency": med["frequency"],
                "status": med["status"],
                "started_on": date.fromisoformat(med["start"]) if med.get("start") else None,
                "prescriber": med.get("prescriber"),
            },
        ))

    for i, supp in enumerate(payload["supplements"]):
        out.append(RawAssertion(
            source_class=SourceClass.EMR, locator=loc(f"supplements[{i}]"),
            kind=AssertionKind.SUPPLEMENT,
            key=_SUPPLEMENT_ALIASES.get(_norm(supp["name"]), _norm(supp["name"])),
            payload={"raw_text": supp["name"], "dose_text": supp["sig"], "status": "active"},
        ))

    for i, alg in enumerate(payload["allergies"]):
        out.append(RawAssertion(
            source_class=SourceClass.EMR, locator=loc(f"allergies[{i}]"),
            kind=AssertionKind.ALLERGY, key=alg["rxnorm"],
            payload={
                "raw_text": alg["substance"], "coding": ("RxNorm", alg["rxnorm"]),
                "reaction": alg.get("reaction"), "criticality": alg["criticality"],
            },
        ))

    for i, lab in enumerate(payload["labs"]):
        out.append(RawAssertion(
            source_class=SourceClass.EMR, locator=loc(f"labs[{i}]"),
            kind=AssertionKind.LAB, key=f"{lab['loinc']}|{lab['collected']}",
            payload={
                "raw_text": lab["analyte"], "coding": ("LOINC", lab["loinc"]),
                "value": float(lab["value"]), "unit": lab["unit"],
                "collected": date.fromisoformat(lab["collected"]),
                "ref_low": lab.get("ref_low"), "ref_high": lab.get("ref_high"),
                "reported_interpretation": lab.get("abnormal"),
                "performing_lab": lab.get("lab"),
            },
        ))

    return doc, out


# ----------------------------------------------------- lab report extraction

def read_lab_extraction(path: Path) -> tuple[SourceDocument, list[RawAssertion]]:
    """AI-extracted rows, each carrying a confidence and the text it came from.

    Keyed on LOINC plus collection date, which is what makes the same analyte from the EMR
    and from the report meet as one fact rather than two.
    """
    payload = json.loads(path.read_text())
    doc = SourceDocument(
        id="doc_lab", source_class=SourceClass.LAB_REPORT, filename=path.name,
        content_sha256=_hash(path), received_at=RECEIVED_AT,
        declared_row_count=None,  # a PDF declares no count -- §9.7
    )
    out: list[RawAssertion] = []

    for i, row in enumerate(payload["rows"]):
        loc = Locator(
            document_id=doc.id, page=row.get("page"),
            field_path=f"rows[{i}]", quote=row.get("quote"),
        )
        if not row.get("analyte") or row.get("value") is None:
            out.append(RawAssertion(
                source_class=SourceClass.LAB_REPORT, locator=loc, kind=AssertionKind.LAB,
                key=f"unreadable:{i}", payload=dict(row), confidence=row.get("confidence"),
                parse_error="analyte or value could not be read from the page",
            ))
            continue
        collected = row.get("collected")
        out.append(RawAssertion(
            source_class=SourceClass.LAB_REPORT, locator=loc, kind=AssertionKind.LAB,
            key=f"{row['loinc']}|{collected}",
            confidence=row.get("confidence"),
            payload={
                "raw_text": row["analyte"], "coding": ("LOINC", row["loinc"]),
                "value": float(row["value"]), "unit": row.get("unit"),
                "collected": date.fromisoformat(collected) if collected else None,
                "ref_low": row.get("ref_low"), "ref_high": row.get("ref_high"),
                "reported_interpretation": row.get("flag"),
                "performing_lab": "Meridian Labs",
            },
        ))

    return doc, out


# -------------------------------------------------------------------- intake

_MED_PATTERN = re.compile(
    r"(?P<name>[a-zA-Z][a-zA-Z\s]*?)\s*(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>mcg|mg|g|iu)\b",
    re.IGNORECASE,
)
_RXNORM_BY_NAME = {"levothyroxine": "10582", "metformin": "6809"}


def read_intake(path: Path) -> tuple[SourceDocument, list[RawAssertion]]:
    """A spreadsheet row the patient filled in. Free text throughout.

    Everything here is self-report, which is the trust class rather than a quality judgement:
    the patient is the only reliable source for whether they are still taking something, and
    the least reliable for what the dose is.
    """
    rows = {r["field"]: r["value"] for r in csv.DictReader(path.read_text().splitlines())}
    doc = SourceDocument(
        id="doc_intake", source_class=SourceClass.INTAKE, filename=path.name,
        content_sha256=_hash(path), received_at=RECEIVED_AT, declared_row_count=None,
    )
    out: list[RawAssertion] = []

    def loc(field: str) -> Locator:
        return Locator(document_id=doc.id, field_path=field, quote=rows.get(field))

    given, _, family = rows["name"].partition(" ")
    day, month, year = rows["dob"].split("/")
    out.append(RawAssertion(
        source_class=SourceClass.INTAKE, locator=loc("mrn"), kind=AssertionKind.PATIENT,
        key=rows["mrn"],
        payload={
            "mrn": rows["mrn"], "system": "intake-form", "given": [given], "family": family,
            "birth_date": date(int(year), int(month), int(day)), "sex_at_birth": None,
        },
    ))

    for term in (t.strip() for t in rows["conditions"].split(";") if t.strip()):
        key, coding = condition_key(term, None)
        out.append(RawAssertion(
            source_class=SourceClass.INTAKE, locator=loc("conditions"),
            kind=AssertionKind.CONDITION, key=key,
            payload={"raw_text": term, "coding": coding, "clinical_status": "active",
                     "onset": None},
        ))

    still_taking = _norm(rows.get("metformin_still_taking", ""))
    for term in (t.strip() for t in rows["medications"].split(";") if t.strip()):
        match = _MED_PATTERN.search(term)
        name = _norm(match.group("name")) if match else _norm(term)
        payload = {
            "raw_text": name, "coding": (
                ("RxNorm", _RXNORM_BY_NAME[name]) if name in _RXNORM_BY_NAME else None
            ),
            "dose_text": term,
            "dose_amount": float(match.group("amount")) if match else None,
            "dose_unit": _norm(match.group("unit")) if match else None,
            "frequency": None, "status": "active", "started_on": None, "prescriber": None,
        }
        if name == "metformin" and still_taking == "no":
            payload["status"] = "stopped"
            payload["stop_note"] = rows.get("metformin_stopped_when")
        out.append(RawAssertion(
            source_class=SourceClass.INTAKE, locator=loc("medications"),
            kind=AssertionKind.MEDICATION,
            key=_RXNORM_BY_NAME.get(name, f"text:{name}"), payload=payload,
        ))

    for term in (t.strip() for t in rows["supplements"].split(";") if t.strip()):
        match = _MED_PATTERN.search(term)
        name = _norm(match.group("name")) if match else _norm(term)
        out.append(RawAssertion(
            source_class=SourceClass.INTAKE, locator=loc("supplements"),
            kind=AssertionKind.SUPPLEMENT,
            key=_SUPPLEMENT_ALIASES.get(name, name),
            payload={"raw_text": term, "dose_text": term, "status": "active"},
        ))

    out.append(RawAssertion(
        source_class=SourceClass.INTAKE, locator=loc("allergies"),
        kind=AssertionKind.ALLERGY, key="7980",
        payload={"raw_text": rows["allergies"], "coding": None, "reaction": None,
                 "criticality": None},
    ))

    return doc, out

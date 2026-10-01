"""Run the normalisation build and write its four outputs.

    .venv/bin/python scripts_normalise.py

Identifiers are made deterministic here for the same reason as in `scripts_build_d3.py`:
regenerating must produce no diff, which is what proves the outputs are generated. Production
uses ULIDs.
"""

import itertools
from pathlib import Path

import pai3.ids

_COUNTERS: dict[str, itertools.count] = {}


def _deterministic_new_id(prefix: str) -> str:
    counter = _COUNTERS.setdefault(prefix, itertools.count(1))
    return f"{prefix}_{next(counter):04d}"


pai3.ids.new_id = _deterministic_new_id  # must precede the imports below

from pai3.normalise import reports
from pai3.normalise.pipeline import normalise

SOURCES = Path("mock/sources")
OUT = Path("deliverables/normalisation")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    result = normalise(SOURCES)

    for name, body in (
        ("canonical.json", reports.canonical_json(result)),
        ("validation_report.md", reports.validation_report(result)),
        ("conflict_report.md", reports.conflict_report(result)),
        ("review_queue.md", reports.review_queue(result)),
    ):
        path = OUT / name
        path.write_text(body)
        print(f"  wrote {path} ({path.stat().st_size:,} bytes)")

    blocking = sum(1 for f in result.flags if f.severity.value == "blocking")
    print(
        f"\n  {len(result.flags)} flags ({blocking} blocking), "
        f"{len(result.rejected)} rows refused at layer 1, "
        f"{len(result.labs)} lab results built"
    )


if __name__ == "__main__":
    main()

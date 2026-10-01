"""Audit every number D9, D10 and D11 assert against the repository they describe.

    .venv/bin/python scripts_audit_figures.py

This script exists because of a specific failure. D10 and D11 were written at one commit with
figures that were correct at that commit — 271 tests, 10 defects, 2,684 lines of `src/` — and
then stood unchanged through four feature commits that moved every one of them. Nothing was
invented; the numbers simply stopped being re-checked, and a reader cannot tell the difference
between a figure that went stale and one that was never true.

The check is deliberately shaped so there is no second copy of the claim to drift with it. Each
figure is recomputed from the repository, rendered into the exact string the document should
contain, and that string is searched for. A number that moves breaks the match rather than
agreeing with a stale constant kept alongside it — the mistake the first dimension audit made.

Historical figures are excluded on purpose. D10's prompt log says the implementation closed at
264 tests, which is a statement about commit 6c9e024 and cannot drift; the gate covers only
claims about the repository as it stands.

D9's length is the one figure here that is a bound rather than a measurement to match, and it was
the last one outside this gate -- which it had the least right to be, having been stated wrongly
three times running: 714 words claimed as fitting the limit, then 701 claimed as 697, then 699
verified (26f5fdc, 945c7c7, c5fba67). The bound itself is read out of ASSIGNMENT.md rather than
written in here, for the same reason the dimension audit reads its list from there: a constant
copied beside the claim is a second copy to drift with it.

Exits non-zero on any drift, so it can gate a submission.
"""

import pathlib
import re
import subprocess

WORDS = {
    10: "Ten", 11: "Eleven", 12: "Twelve", 13: "Thirteen", 14: "Fourteen", 15: "Fifteen",
    16: "Sixteen", 17: "Seventeen", 18: "Eighteen", 19: "Nineteen", 20: "Twenty",
    21: "Twenty-one", 22: "Twenty-two", 23: "Twenty-three", 24: "Twenty-four",
}

D9 = pathlib.Path("deliverables/d9_client_summary.md")
D10 = pathlib.Path("deliverables/d10_ai_log.md")
D11 = pathlib.Path("deliverables/d11_time_log.md")
README = pathlib.Path("README.md")
ASSIGNMENT = pathlib.Path("ASSIGNMENT.md")


def lines_in(*globs: str) -> int:
    return sum(
        len(p.read_text().splitlines())
        for g in globs
        for p in pathlib.Path().glob(g)
    )


def d9_words() -> int:
    """D9's length, counted the way D9 says it is counted.

    Prose only: a heading line and the note at the top are not part of the summary a client
    reads. The basis has to be stated in the document and enforced here from the same rule,
    because the two plausible ways of counting disagree by 54 words -- `wc -w` on the file
    returns the headings as well -- and a limit that depends on which one a reader picks is
    not a limit.
    """
    return sum(
        len(re.findall(r"\S+", line))
        for line in D9.read_text().splitlines()
        if not line.startswith(("#", ">"))
    )


def d9_bound() -> tuple[int, int]:
    """The word limit, read from the brief rather than kept as a constant here."""
    found = re.search(r"Expected length: (\d+)[-\u2013](\d+) words", ASSIGNMENT.read_text())
    if not found:
        raise SystemExit("could not read D9's word limit out of ASSIGNMENT.md")
    return int(found.group(1)), int(found.group(2))


ACTIVITY_ROW = re.compile(r"^\| (?!\*\*Total)(?!Activity)(?!---)(?:.+?) \| (\d+):(\d\d) \|$")
ACTIVITY_TOTAL = re.compile(r"^\| \*\*Total\*\* \| \*\*(\d+):(\d\d)\*\* \|$")


def hhmm(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def activity_tables(text: str) -> tuple[list[tuple[list[int], int]], int]:
    """Each activity table in D11, as its row minutes and the total it states.

    D11 gives the same total twice, under two breakdowns of the same work, and the first
    version of this check summed every row in the section against the first total — reporting
    30 rows summing to 11:00 against a stated 5:30, which was the check double counting rather
    than the document disagreeing with itself. A table therefore closes at its own `Total` row
    and is compared only against that. Rows left over after the last total are returned so a
    table that lost its total is a problem rather than a silence.
    """
    tables: list[tuple[list[int], int]] = []
    rows: list[int] = []
    for line in text.splitlines():
        row = ACTIVITY_ROW.match(line)
        if row:
            rows.append(int(row.group(1)) * 60 + int(row.group(2)))
            continue
        total = ACTIVITY_TOTAL.match(line)
        if total:
            tables.append((rows, int(total.group(1)) * 60 + int(total.group(2))))
            rows = []
    return tables, len(rows)


def collected_tests(target: str) -> int:
    out = subprocess.run(
        [".venv/bin/pytest", target, "-q", "--collect-only"],
        capture_output=True, text=True, check=False,
    ).stdout
    found = re.search(r"(\d+) tests collected", out)
    if not found:
        raise SystemExit(f"could not collect tests for {target}; is the venv present?")
    return int(found.group(1))


def facts() -> dict[str, int]:
    """Recompute from the repository. Every value here is a measurement, not a record."""
    spec = pathlib.Path("docs/model_design.md").read_text()
    plan = pathlib.Path("docs/implementation_plan.md").read_text()
    defects = pathlib.Path("docs/plan_defects.md").read_text()
    return {
        "spec_lines": len(spec.splitlines()),
        # D11 states the section count beside the line count, so it drifts the same way.
        "spec_sections": len(re.findall(r"^## \d+\.", spec, re.MULTILINE)),
        "d9_words": d9_words(),
        "claude_md_lines": len(pathlib.Path("CLAUDE.md").read_text().splitlines()),
        "src_lines": lines_in("src/**/*.py"),
        "test_lines": lines_in("tests/**/*.py", "mock/**/*.py"),
        "tests": collected_tests("tests"),
        "norm_tests": collected_tests("tests/normalise"),
        "plan_tasks": len(re.findall(r"^### Task ", plan, re.MULTILINE)),
        "plan_steps": len(re.findall(r"^- \[ \] \*\*Step", plan, re.MULTILINE)),
        # The tier table in §4 is the one place every entity is listed with its base class.
        "entities": len(re.findall(r"^\| `\w+` \| (?:Canonical|PatientScoped|Clinical) \|", spec, re.MULTILINE)),
        # Numbered defect sections and the summary tables that carry the rest.
        "defects": max(
            {int(n) for n in re.findall(r"^## (\d+)\.", defects, re.MULTILINE)}
            | {int(n) for n in re.findall(r"^\| (\d+) \| \d+ \|", defects, re.MULTILINE)}
            | {int(n) for n in re.findall(r"^## (\d+) and (\d+)\.", defects, re.MULTILINE)[0]}
        ),
    }


def expected(f: dict[str, int]) -> list[tuple[pathlib.Path, str, str]]:
    """The exact strings the documents must contain, built from the measurements above."""
    return [
        (D10, "design document size",
         f"| `docs/model_design.md` | {f['spec_lines']:,} lines |"),
        (D10, "implementation plan size",
         f"| {f['plan_tasks']} tasks, {f['plan_steps']} TDD steps |"),
        (D10, "code size and test count",
         f"| {f['src_lines']:,} + {f['test_lines']:,} lines, {f['tests']} tests |"),
        (D10, "defect count in the critique heading",
         f"### {WORDS[f['defects']]} defects in AI-written code"),
        # The four decisions taken before any prompt in this repository.
        (D10, "size of the hand-written CLAUDE.md",
         f"a {f['claude_md_lines']}-line `CLAUDE.md`"),
        (D9, "the word count D9 states about itself",
         f"> {f['d9_words']} words."),
        (D11, "design document size",
         f"`docs/model_design.md`, {f['spec_lines']:,} lines, {f['spec_sections']} sections"),
        (D11, "implementation plan size",
         f"{f['plan_tasks']} tasks, {f['plan_steps']} steps"),
        (D11, "code size",
         f"| Code | {f['src_lines']:,} lines in `src/`, {f['test_lines']:,} in `tests/` and `mock/` |"),
        (D11, "test count",
         f"| Tests | {f['tests']}, all passing; ruff clean |"),
        (D11, "entity count",
         f"| Canonical entities | {f['entities']} of {f['entities']},"),
        (D11, "normalisation build test count",
         f"`deliverables/normalisation/`, {f['norm_tests']} tests"),
        (D11, "defect count",
         f"| Defects found in AI-written code | {f['defects']},"),
        # The first command a reviewer runs. It carried the stale count too.
        (README, "test count in the quickstart",
         f".venv/bin/pytest -q          # {f['tests']} tests"),
        (README, "entity count in the opening sentence",
         f"{WORDS[f['entities']].lower()} canonical"),
    ]


def main() -> int:
    f = facts()
    problems = []

    for path, what, literal in expected(f):
        if literal not in path.read_text():
            problems.append(f"{path.name}: {what} is stale — expected to find {literal!r}")

    # The instrument table attributes every defect to how it was found, so it must account for
    # all of them. A defect added to the log and not to the table leaves the table quietly short.
    table = D10.read_text().split("defects in AI-written code")[-1].split("The second row")[0]
    counted = sum(
        int(n) for n in re.findall(r"^\| .+? \| (?:\*\*)?(\d+)(?:\*\*)? \|", table, re.MULTILINE)
    )
    if counted != f["defects"]:
        problems.append(
            f"d10_ai_log.md: the instrument table accounts for {counted} defects, "
            f"the log records {f['defects']}"
        )

    # D11's activity rows must account for the total it states. The same shape as the
    # instrument table above: a document whose own figures have to add up. Each table is
    # checked against its own total, and the totals against each other — the two breakdowns
    # are the same 5:30 twice, so they have to agree as well as add up.
    breakdown = D11.read_text().split("## What the repository can attest to")[0]
    tables, orphans = activity_tables(breakdown)
    if not tables:
        problems.append("d11_time_log.md: could not read the activity breakdown or its total")
    if orphans:
        problems.append(
            f"d11_time_log.md: {orphans} activity row(s) after the last total — "
            "a table lost its Total row"
        )
    for n, (rows, claimed) in enumerate(tables, start=1):
        counted = sum(rows)
        if counted != claimed:
            problems.append(
                f"d11_time_log.md: breakdown {n}'s {len(rows)} activity rows sum to "
                f"{hhmm(counted)}, its total states {hhmm(claimed)}"
            )
    stated_totals = {claimed for _, claimed in tables}
    if len(stated_totals) > 1:
        problems.append(
            "d11_time_log.md: the breakdowns state different totals — "
            + ", ".join(hhmm(t) for t in sorted(stated_totals))
            + " — and each is presented as the same work"
        )

    # D9 against the brief's own limit. The check above only holds D9's stated count to the
    # file; this one holds the file to the assignment, and both are needed: a wrong count
    # inside the range and a right count outside it are different failures.
    lo, hi = d9_bound()
    if not lo <= f["d9_words"] <= hi:
        problems.append(
            f"d9_client_summary.md: {f['d9_words']} words of prose, outside the {lo}-{hi} "
            "ASSIGNMENT.md sets (headings and the opening note excluded, as D9 states)"
        )

    # The claim this gate was built after. Kept as a named check rather than left to the
    # figures above, because it was prose and no number would have caught it.
    if "normalisation build was not started" in D11.read_text():
        problems.append("d11_time_log.md: still says the normalisation build was not started")

    print(
        f"spec {f['spec_lines']:,} lines / {f['spec_sections']} sections  |  src "
        f"{f['src_lines']:,}  |  tests+mock {f['test_lines']:,}  |  {f['tests']} tests  |  "
        f"{f['entities']} entities  |  {f['defects']} defects  |  CLAUDE.md "
        f"{f['claude_md_lines']}  |  D9 {f['d9_words']} words ({lo}-{hi})"
    )
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nno drift: every figure D9, D10 and D11 assert matches the repository, D9 is")
    print("inside the brief's limit, and the instrument table accounts for every defect.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

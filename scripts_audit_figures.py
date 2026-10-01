"""Audit every number D10 and D11 assert against the repository they describe.

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

D10 = pathlib.Path("deliverables/d10_ai_log.md")
D11 = pathlib.Path("deliverables/d11_time_log.md")
README = pathlib.Path("README.md")


def lines_in(*globs: str) -> int:
    return sum(
        len(p.read_text().splitlines())
        for g in globs
        for p in pathlib.Path().glob(g)
    )


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
        (D11, "design document size",
         f"`docs/model_design.md`, {f['spec_lines']:,} lines"),
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

    # The claim this gate was built after. Kept as a named check rather than left to the
    # figures above, because it was prose and no number would have caught it.
    if "normalisation build was not started" in D11.read_text():
        problems.append("d11_time_log.md: still says the normalisation build was not started")

    print(
        f"spec {f['spec_lines']:,} lines  |  src {f['src_lines']:,}  |  tests+mock "
        f"{f['test_lines']:,}  |  {f['tests']} tests  |  {f['entities']} entities  |  "
        f"{f['defects']} defects"
    )
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("\nno drift: every figure D10 and D11 assert matches the repository, and the")
    print("instrument table accounts for every defect in the log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Where claims come from.

Two implementations behind one protocol. `StubGenerator` produces claims deterministically
and reports `engine=stub`, so a run with no inference in it is self-evidently that.
`OllamaGenerator` calls a local model over HTTP and reports what actually ran.

Each generator builds its own prompt and hands it back, so the digest the adapter records is
of the exact string that was sent (§10.2). The earlier design built the prompt in the adapter
*after* generation, purely to be hashed — which was fine for a stub and wrong the moment
anything real was wired in.
"""

import json
import re
import urllib.error
import urllib.request
from typing import NamedTuple, Protocol

from pydantic import BaseModel

from pai3.ai.artifact import AIClaim, ClaimValue, Engine
from pai3.ai.projection import AIPatientView
from pai3.entities.results import LabResult
from pai3.ids import CanonicalRef
from pai3.readmodels.trend import LabTrend
from pai3.values.flags import FlagSummary

OLLAMA_HOST = "http://localhost:11434"

CLAIM_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "cites": {"type": "array", "items": {"type": "string"}},
                    "values": {
                        "description": (
                            "Every number appearing in `text`, with the id it came from."
                            " A claim stating a number and declaring none is rejected."
                        ),
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "value": {"type": "number"},
                                "unit": {"type": "string"},
                                "cites": {"type": "string"},
                            },
                            "required": ["value", "cites"],
                        },
                    },
                },
                "required": ["text", "cites"],
            },
        }
    },
    "required": ["claims"],
}
"""Constrained decoding, per §10.5. Free prose would make every output check unworkable."""


class RenderedPrompt(NamedTuple):
    """The prompt and the index map that decodes a reply to it.

    They are returned together because they must come from one pass over the same labs. A
    second function deriving the ordering separately is how two components end up with
    parallel definitions of the same thing, which is the defect class this build has hit
    three times. The map is local to one call: the caller renders, sends, decodes, and drops
    it. Nothing persists an index, and the artifact carries the real ids the map resolves to.
    """

    text: str
    by_index: dict[str, CanonicalRef]


_FIGURE = re.compile(r"\d[\d.,]*")
"""Any figure in a flag message, deliberately broader than guardrail 6's decimal pattern.

The two are allowed to differ, and unifying them would reopen a hole. Check 6 is narrow
because it reads a *claim*, where "type 2 diabetes" must not be mistaken for a measurement.
This reads a *flag message*, where no number is one the model may use: the values a conflict
names are the competing readings, and canonical holds neither of them. An integer left in
would be restated and would pass every check, because check 6 ignores integers by design.
"""


def _without_figures(message: str) -> str:
    """A flag message with its competing values removed.

    The model is told which analyte is disputed and by whom, and not the figures, because
    there is no legal way for it to use them. They belong to no citable record — an
    unresolved conflict leaves the canonical value empty (§9.3) — so declaring one fails
    check 2 or 3 and stating one undeclared fails check 6. Printing them made the context a
    trap: every run restated them and every run was rejected.
    """
    return _FIGURE.sub("(withheld)", message)


def resolve_citation(token: str, by_index: dict[str, CanonicalRef]) -> CanonicalRef:
    """Turn what the model wrote into a ref, or into one that cannot resolve.

    Lenient about the form — `[2]`, `2` and ` [2] ` are the same citation — because the
    brackets are presentation and a model that drops them has still cited the second result.
    Strict about existence: `[9]` where three results were offered, a ULID the prompt never
    contained, or anything that is not an index returns a ref carrying the token verbatim, so
    guardrail 1 reports it as a citation that is not in inputs. Resolution never invents an
    id, which is what keeps the check that catches fabrication unchanged by the switch.
    """
    index = token.strip().strip("[]").strip()
    if index.isdigit() and index in by_index:
        return by_index[index]
    return CanonicalRef(entity_type="LabResult", entity_id=token, version=1)


class GenerationContext(BaseModel):
    """Exactly what the model is allowed to see. No identity — §10.4."""

    view: AIPatientView
    labs: list[LabResult]
    trends: list[LabTrend]
    unresolved: list[FlagSummary]

    def refs(self) -> dict[str, CanonicalRef]:
        return {
            lab.id: CanonicalRef(
                entity_type="LabResult", entity_id=lab.id, version=lab.version
            )
            for lab in self.labs
        }

    def render(self) -> RenderedPrompt:
        """The prompt, labelling each result `[1]`, `[2]`, … instead of its id.

        A model asked to echo a 26-character ULID will sometimes return one that is right in
        its prefix and wrong in its tail. That is indistinguishable from a real id by eye, so
        the only thing standing between it and a physician is guardrail 1. A single digit is
        short enough to copy correctly and short enough for a reviewer to check, which
        removes the cause rather than relying on the catch. An index the context never
        offered still resolves to nothing and still fails as a fabricated citation.
        """
        by_index: dict[str, CanonicalRef] = {}
        lines = [
            "Patient context (no identifying detail is available to you):",
            f"  age {self.view.age_years}, sex {self.view.sex}",
            "",
            "Lab results. Cite a result by its bracketed index, exactly as shown — [2], not",
            "the analyte name. Do not state a value for a result whose value is absent.",
        ]
        for position, lab in enumerate(self.labs, start=1):
            tag = f"[{position}]"
            by_index[str(position)] = CanonicalRef(
                entity_type="LabResult", entity_id=lab.id, version=lab.version
            )
            if lab.quantity is None:
                lines.append(
                    f"  {tag} {lab.biomarker.raw_text} — VALUE ABSENT (unresolved conflict)"
                )
                continue
            rng = (
                f", reference {lab.reference_range.low}-{lab.reference_range.high}"
                if lab.reference_range
                else ""
            )
            lines.append(
                f"  {tag} {lab.biomarker.raw_text} "
                f"{lab.quantity.value} {lab.quantity.unit or '(no unit recorded)'}{rng}"
            )
        if self.trends:
            lines += ["", "Trends already computed for you. Do not recompute them."]
            for t in self.trends:
                lines.append(
                    f"  {t.analyte.raw_text}: {t.direction.value} "
                    f"over {len(t.numeric_basis)} measurement(s)"
                    + (f", {len(t.excluded)} excluded" if t.excluded else "")
                )
        if self.unresolved:
            lines += [
                "",
                "Unresolved data problems you must not reason past. The competing figures are",
                "withheld because no record holds them — name the disagreement, not numbers:",
            ]
            for f in self.unresolved:
                lines.append(f"  {f.code.value}: {_without_figures(f.message)}")
        lines += [
            "",
            "Write one short claim per fact worth a physician's attention. Every claim cites",
            "at least one index, written as it appears above.",
            "",
            "If a claim states a number, that number MUST also appear in that claim's",
            "`values`, with the index it came from. A claim that states a number in its text",
            "and declares none is rejected outright, because nothing can then be checked",
            "against the record. Prefer describing a direction to restating a figure.",
        ]
        return RenderedPrompt(text="\n".join(lines), by_index=by_index)


class Generated(NamedTuple):
    claims: list[AIClaim]
    prompt: str
    notes: list[str]
    """Parse problems, recorded rather than swallowed: a generator that quietly drops a
    malformed claim hides the failure the guardrails exist to surface."""


class Generator(Protocol):
    engine: Engine
    model_id: str
    engine_version: str
    model_digest: str | None

    def generate(self, ctx: GenerationContext) -> Generated: ...


class StubGenerator:
    """Deterministic claims. No inference of any kind happens here.

    Reports `engine=stub` and a `model_id` that says what it is, so neither the artifact nor
    a test can be read as evidence that a model ran. `fabricate` offsets every value by one,
    which is how D8 demonstrates a guardrail rejection without needing a model to misbehave
    on cue.
    """

    def __init__(self, fabricate: bool = False) -> None:
        self.engine = Engine.STUB
        self.model_id = "stub:deterministic-claim-builder"
        self.engine_version = "n/a"
        self.model_digest = None
        self.fabricate = fabricate

    def generate(self, ctx: GenerationContext) -> Generated:
        refs = ctx.refs()
        claims: list[AIClaim] = []
        for lab in ctx.labs:
            if lab.quantity is None:
                continue
            ref = refs[lab.id]
            value = lab.quantity.value + (1.0 if self.fabricate else 0.0)
            claims.append(AIClaim(
                text=(
                    f"{lab.biomarker.raw_text} measured {value} "
                    f"{lab.quantity.unit or 'unknown unit'}."
                ),
                cites=[ref],
                values=[ClaimValue(value=value, unit=lab.quantity.unit, cites=ref)],
            ))
        for trend in ctx.trends:
            if not trend.numeric_basis:
                continue
            claims.append(AIClaim(
                text=f"{trend.analyte.raw_text} trend is {trend.direction.value}.",
                cites=[
                    refs.get(
                        rid,
                        CanonicalRef(entity_type="LabResult", entity_id=rid, version=1),
                    )
                    for rid in trend.numeric_basis
                ],
            ))
        return Generated(claims=claims, prompt=ctx.render().text, notes=[])


class OllamaUnavailable(RuntimeError):
    """The local runtime did not answer. Not a guardrail failure — nothing was generated."""


class OllamaGenerator:
    """A real call to a model running on this machine.

    Structured output via a JSON schema, temperature 0 so a run is repeatable, and nothing
    leaves localhost. `model_digest` is read from the runtime rather than written by hand, so
    the artifact records which weights actually answered.
    """

    def __init__(
        self, model: str, host: str = OLLAMA_HOST, timeout: int = 180,
    ) -> None:
        self.engine = Engine.OLLAMA
        self.model_id = model
        self.host = host
        self.timeout = timeout
        self.engine_version = self._version()
        self.model_digest = self._digest()

    # ------------------------------------------------------------------ http

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{self.host}{path}", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OllamaUnavailable(f"{self.host}{path}: {exc}") from exc

    def _get(self, path: str) -> dict:
        try:
            with urllib.request.urlopen(f"{self.host}{path}", timeout=10) as response:
                return json.loads(response.read())
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OllamaUnavailable(f"{self.host}{path}: {exc}") from exc

    def _version(self) -> str:
        return str(self._get("/api/version").get("version", "unknown"))

    def _digest(self) -> str | None:
        """Which weights answered. None when the runtime does not report it (§6.3)."""
        try:
            shown = self._post("/api/show", {"model": self.model_id})
        except OllamaUnavailable:
            return None
        digest = shown.get("digest") or (shown.get("details") or {}).get("digest")
        return str(digest) if digest else None

    # ------------------------------------------------------------- generation

    def generate(self, ctx: GenerationContext) -> Generated:
        rendered = ctx.render()
        reply = self._post("/api/chat", {
            "model": self.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You summarise clinical data for a physician. State only what the "
                        "context contains. Never state a value for a result marked VALUE "
                        "ABSENT. Every claim cites at least one bracketed index from the "
                        "context, copied exactly, and every number you write in `text` must "
                        "also be listed in that claim's `values` with the index it came from."
                    ),
                },
                {"role": "user", "content": rendered.text},
            ],
            "stream": False,
            "format": CLAIM_SCHEMA,
            "options": {"temperature": 0, "num_predict": 600},
        })
        return Generated(
            claims=self._parse(reply["message"]["content"], rendered.by_index),
            prompt=rendered.text,
            notes=self._notes,
        )

    def _parse(self, content: str, by_index: dict[str, CanonicalRef]) -> list[AIClaim]:
        """Turn the reply into claims, resolving indices back to ids.

        A citation the context never offered is passed through rather than dropped. That is a
        hallucinated citation and guardrail 1 is what must catch it — a parser that silently
        discarded it would hide exactly the failure the guardrails exist for. `[9]` where the
        prompt offered three results resolves to nothing and fails the same way a wrong id
        did, as does anything that is not an index at all, so the check is unchanged by the
        switch. The unresolved token is kept verbatim in `entity_id` so the failure names what
        the model actually wrote.
        """
        self._notes: list[str] = []

        def ref_for(token: str) -> CanonicalRef:
            return resolve_citation(token, by_index)

        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            self._notes.append(f"reply was not JSON despite a schema being supplied: {exc}")
            return []

        claims: list[AIClaim] = []
        for i, raw in enumerate(payload.get("claims", [])):
            cites = [ref_for(c) for c in raw.get("cites", []) if isinstance(c, str)]
            if not raw.get("text") or not cites:
                self._notes.append(f"claim {i} dropped: it cited nothing or had no text")
                continue
            values = [
                ClaimValue(
                    value=float(v["value"]), unit=v.get("unit"), cites=ref_for(v["cites"])
                )
                for v in raw.get("values", [])
                if isinstance(v, dict) and "value" in v and "cites" in v
            ]
            claims.append(AIClaim(text=raw["text"], cites=cites, values=values))
        return claims

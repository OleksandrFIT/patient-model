"""Free text with its origin attached.

The trust boundary is whether the text crossed the practice perimeter, not who signed
the record holding it (§10.1). This does not make text safe, and there is
deliberately no `sanitized` field: declining to act on instructions found in an
external span is a policy of the AI layer, not a property of the schema.
"""

from pydantic import BaseModel, Field

from pai3.enums import TextOrigin
from pai3.values.actor import Actor

_EXTERNAL = {
    TextOrigin.PATIENT_SUBMITTED,
    TextOrigin.EXTERNAL_DOCUMENT,
    TextOrigin.TRANSCRIBED_EXTERNAL,
    TextOrigin.UNKNOWN,
}


class ClinicalText(BaseModel):
    value: str
    origin: TextOrigin
    captured_by: Actor | None = Field(
        default=None, description="Who entered this into the practice system"
    )

    @property
    def crossed_perimeter(self) -> bool:
        """True for anything that did not originate inside the practice.

        UNKNOWN is included: the default fails closed.
        """
        return self.origin in _EXTERNAL

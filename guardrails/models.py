from dataclasses import dataclass
from typing import Literal

DecisionType = Literal["allow", "block", "warn", "sanitize"]


@dataclass
class GuardrailDecision:
    correlation_id: str
    stage: str
    decision: DecisionType
    reason_code: str
    message: str

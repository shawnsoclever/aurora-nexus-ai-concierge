from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(description="Machine-readable error code")
    message: str = Field(description="Human-readable error message")
    reason_code: str | None = Field(default=None, description="Guardrail or policy reason code")


class ErrorResponse(BaseModel):
    status: str = Field(default="error")
    correlation_id: str
    error: ErrorDetail

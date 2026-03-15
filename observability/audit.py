from loguru import logger


def audit_event(
    *,
    correlation_id: str,
    stage: str,
    action: str,
    reason_code: str | None = None,
    details: dict | None = None,
) -> None:
    logger.bind(correlation_id=correlation_id, stage=stage).info(
        "audit_action={action} reason_code={reason_code} details={details}",
        action=action,
        reason_code=reason_code,
        details=details or {},
    )

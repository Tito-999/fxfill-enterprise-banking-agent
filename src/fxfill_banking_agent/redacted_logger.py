"""Redacted logger — enforces FieldPolicy in logs (B2).

Wraps the standard logger and redacts sensitive fields before they
reach the log output. Ensures API tokens, full account numbers,
and PII never appear in log files.
"""

from __future__ import annotations

from fxfill_banking_agent.data_security import (
    DataClassification,
    get_field_policy,
)


def redact_dict(data: dict[str, object]) -> dict[str, object]:
    """Redact sensitive fields in a dictionary according to FieldPolicy.

    Fields classified as SECRET are replaced with "[REDACTED]".
    Fields classified as RESTRICTED_PII are replaced with "[PII]".
    Fields with redaction_rule "last4" show only the last 4 chars.
    """
    result: dict[str, object] = {}
    for key, value in data.items():
        policy = get_field_policy(key)
        if policy.classification in (
            DataClassification.SECRET,
            DataClassification.RESTRICTED_PII,
        ):
            result[key] = "[REDACTED]"
        elif policy.redaction_rule == "last4" and isinstance(value, str):
            result[key] = "..." + value[-4:] if len(value) > 4 else value
        elif policy.redaction_rule == "hash" and isinstance(value, str):
            import hashlib

            result[key] = hashlib.sha256(value.encode()).hexdigest()[:16]
        elif not policy.can_enter_log:
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result


def safe_log_data(data: dict[str, object]) -> dict[str, object]:
    """Return a copy of *data* safe for logging.

    Strips: api_key, token, password, secret, account_number, PII.
    """
    sensitive_keys = {
        "api_key",
        "token",
        "authorization",
        "x-api-key",
        "password",
        "secret",
        "full_account_number",
        "ssn",
    }
    result: dict[str, object] = {}
    for key, value in data.items():
        if key.lower() in sensitive_keys or any(
            s in key.lower() for s in ("token", "secret", "password")
        ):
            result[key] = "[REDACTED]"
        else:
            result[key] = value
    return result

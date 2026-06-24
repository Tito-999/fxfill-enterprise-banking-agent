"""Structured error codes for the banking agent.

Every error exposed through the API must use a machine-readable
error code from this module. Internal exception messages must never
be leaked to clients — they may contain paths, SQL, tokens, or
provider internals.
"""

from __future__ import annotations

from enum import Enum


class AgentErrorCode(str, Enum):
    """Machine-readable error codes for API responses.

    These codes are stable and can be used by clients for programmatic
    error handling. The numeric HTTP status code is a separate concern.
    """

    # Provider errors
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_AUTHENTICATION_FAILED = "PROVIDER_AUTHENTICATION_FAILED"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    PROVIDER_INTERNAL_ERROR = "PROVIDER_INTERNAL_ERROR"

    # Tool errors
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    INVALID_TOOL_ARGUMENTS = "INVALID_TOOL_ARGUMENTS"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    TOOL_OUTCOME_UNKNOWN = "TOOL_OUTCOME_UNKNOWN"
    TOOL_TIMEOUT = "TOOL_TIMEOUT"

    # Authorization errors
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    APPROVAL_ALREADY_CONSUMED = "APPROVAL_ALREADY_CONSUMED"

    # Identity errors
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    CROSS_TENANT_ACCESS_DENIED = "CROSS_TENANT_ACCESS_DENIED"
    CROSS_ACCOUNT_ACCESS_DENIED = "CROSS_ACCOUNT_ACCESS_DENIED"

    # State errors
    CHECKPOINT_CONFLICT = "CHECKPOINT_CONFLICT"
    THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
    THREAD_ALREADY_EXISTS = "THREAD_ALREADY_EXISTS"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"

    # System errors
    AGENT_STEP_LIMIT_EXCEEDED = "AGENT_STEP_LIMIT_EXCEEDED"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


# Mapping from error code to safe client-facing message
_ERROR_MESSAGES: dict[AgentErrorCode, str] = {
    AgentErrorCode.PROVIDER_TIMEOUT: "The AI service timed out. Please try again.",
    AgentErrorCode.PROVIDER_AUTHENTICATION_FAILED: "AI service configuration error.",
    AgentErrorCode.PROVIDER_RATE_LIMITED: "The service is busy. Please try again shortly.",
    AgentErrorCode.PROVIDER_INTERNAL_ERROR: "The AI service encountered an error. Please try again.",
    AgentErrorCode.UNKNOWN_TOOL: "The requested operation is not available.",
    AgentErrorCode.INVALID_TOOL_ARGUMENTS: "Invalid operation parameters.",
    AgentErrorCode.TOOL_EXECUTION_FAILED: "The operation could not be completed.",
    AgentErrorCode.TOOL_OUTCOME_UNKNOWN: "The operation outcome is uncertain. Please contact support.",
    AgentErrorCode.TOOL_TIMEOUT: "The operation timed out. Please try again.",
    AgentErrorCode.AUTHORIZATION_DENIED: "You are not authorized to perform this operation.",
    AgentErrorCode.APPROVAL_REQUIRED: "This operation requires human approval.",
    AgentErrorCode.APPROVAL_EXPIRED: "The approval window has expired. Please request again.",
    AgentErrorCode.APPROVAL_ALREADY_CONSUMED: "This approval has already been used.",
    AgentErrorCode.AUTHENTICATION_REQUIRED: "Authentication is required.",
    AgentErrorCode.INSUFFICIENT_PERMISSIONS: "You do not have sufficient permissions.",
    AgentErrorCode.CROSS_TENANT_ACCESS_DENIED: "Access denied.",
    AgentErrorCode.CROSS_ACCOUNT_ACCESS_DENIED: "Access denied.",
    AgentErrorCode.CHECKPOINT_CONFLICT: "A conflict occurred. Please retry.",
    AgentErrorCode.THREAD_NOT_FOUND: "Conversation not found.",
    AgentErrorCode.THREAD_ALREADY_EXISTS: "A conversation with this ID already exists.",
    AgentErrorCode.RECONCILIATION_REQUIRED: "This operation requires manual review.",
    AgentErrorCode.AGENT_STEP_LIMIT_EXCEEDED: "The request was too complex. Please simplify and try again.",
    AgentErrorCode.CONFIGURATION_ERROR: "Service configuration error.",
    AgentErrorCode.INTERNAL_ERROR: "An unexpected error occurred. Please try again.",
}


def safe_error_message(code: AgentErrorCode) -> str:
    """Return a safe, client-facing message for an error code.

    These messages never contain internal paths, SQL, tokens, or
    provider-specific details.
    """
    return _ERROR_MESSAGES.get(code, "An unexpected error occurred.")

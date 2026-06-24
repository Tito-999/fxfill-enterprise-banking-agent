"""Intent classifier — deterministic keyword matching with LLM fallback.

Classification is fast and explainable. Simple queries are matched by
keyword rules (HIGH confidence). Ambiguous or complex messages fall
through to a lightweight LLM classifier (LOW confidence).

The classifier never authorizes actions — it only suggests intent.
"""

from __future__ import annotations

import re
from typing import Any

from fxfill_banking_agent.routing.intent import Intent, IntentConfidence, IntentResult

# ── Keyword → Intent mapping (HIGH confidence, prioritised) ────────
_KEYWORD_RULES: list[tuple[list[str], Intent, str]] = [
    # Transfer workflows (checked before generic reads)
    (
        ["submit draft", "execute transfer", "finalize transfer", "confirm transfer"],
        Intent.TRANSFER_SUBMIT,
        "Transfer submission intent",
    ),
    (
        ["cancel", "void", "stop transfer"],
        Intent.TRANSFER_CANCEL,
        "Transfer cancellation intent",
    ),
    (
        ["transfer status", "where is my transfer", "track transfer", "status of transfer"],
        Intent.TRANSFER_STATUS,
        "Transfer status inquiry",
    ),
    (
        [
            "send money",
            "send $",
            "transfer $",
            "pay ",
            "make a transfer",
            "create transfer",
            "draft transfer",
            "send a transfer",
            "new transfer",
        ],
        Intent.TRANSFER_CREATE,
        "Transfer creation intent",
    ),
    # Suspicious activity (check before generic transaction queries)
    (
        ["fraud", "suspicious", "scam", "unauthorized", "phishing", "report suspicious"],
        Intent.SUSPICIOUS_ACTIVITY_REPORT,
        "Suspicious activity report",
    ),
    # Account queries
    (
        ["balance", "how much", "account summary", "my account", "show account"],
        Intent.ACCOUNT_QUERY,
        "Account balance/summary query",
    ),
    # Transaction queries
    (
        [
            "transactions",
            "transaction",
            "recent",
            "history",
            "last payment",
            "what did I spend",
            "statement",
        ],
        Intent.TRANSACTION_QUERY,
        "Transaction history query",
    ),
    # Beneficiary queries
    (
        ["beneficiary", "payee", "recipient", "who can I send"],
        Intent.BENEFICIARY_QUERY,
        "Beneficiary lookup",
    ),
    # Knowledge / policy questions
    (
        [
            "fee",
            "charge",
            "rate",
            "policy",
            "rule",
            "limit",
            "how long",
            "how much does it cost",
            "what is the",
            "how do I",
            "form",
            "account type",
            "offer",
            "product",
        ],
        Intent.POLICY_QUESTION,
        "Policy/product knowledge question",
    ),
    # Complex multi-step (detected by presence of multiple action verbs)
    (
        ["and then", "also", "additionally", "after that", "schedule recurring"],
        Intent.COMPLEX_TASK,
        "Multi-step task detected",
    ),
]


def classify(message: str, llm: Any | None = None) -> IntentResult:
    """Classify a user message into an intent category.

    Args:
        message: The user's natural language message.
        llm: Optional LLM provider for fallback classification. When
            None, only keyword matching is used.

    Returns:
        An ``IntentResult`` with the classified intent and confidence.
    """
    message_lower = message.lower().strip()

    # ── Phase 1: Deterministic keyword matching ──────────────────
    for keywords, intent, reason in _KEYWORD_RULES:
        for kw in keywords:
            if kw in message_lower:
                # Check that it's a word match, not a substring false positive
                if _is_word_match(kw, message_lower):
                    return IntentResult(
                        intent=intent,
                        confidence=IntentConfidence.HIGH,
                        reason=reason,
                        suggested_tools=_suggest_tools(intent),
                    )

    # ── Phase 2: Pattern heuristics ──────────────────────────────
    # Multiple question marks or action verbs → complex
    action_verbs = re.findall(
        r"\b(send|pay|transfer|check|find|show|get|cancel|report)\b", message_lower
    )
    if len(action_verbs) >= 2:
        return IntentResult(
            intent=Intent.COMPLEX_TASK,
            confidence=IntentConfidence.MEDIUM,
            reason="Multiple action verbs detected",
            suggested_tools=_suggest_tools(Intent.COMPLEX_TASK),
        )

    # Contains question words → could be policy or account
    if any(q in message_lower for q in ("what", "how", "why", "when", "where", "can i", "do i")):
        # Heuristic: if it mentions numbers/amounts → likely account query
        if re.search(r"\$|dollar|amount|balance|money", message_lower):
            return IntentResult(
                intent=Intent.ACCOUNT_QUERY,
                confidence=IntentConfidence.MEDIUM,
                reason="Financial question pattern",
                suggested_tools=_suggest_tools(Intent.ACCOUNT_QUERY),
            )
        return IntentResult(
            intent=Intent.POLICY_QUESTION,
            confidence=IntentConfidence.MEDIUM,
            reason="General question pattern",
            suggested_tools=_suggest_tools(Intent.POLICY_QUESTION),
        )

    # ── Phase 3: LLM fallback (if available) ─────────────────────
    if llm is not None:
        return _llm_classify(message, llm)

    # ── Phase 4: Give up ─────────────────────────────────────────
    return IntentResult(
        intent=Intent.GENERAL_UNSUPPORTED,
        confidence=IntentConfidence.LOW,
        reason="No keyword or pattern match",
    )


def _is_word_match(keyword: str, text: str) -> bool:
    """Check that *keyword* appears as a word/phrase boundary in *text*."""
    # For multi-word keywords, do substring check
    if " " in keyword:
        return keyword in text
    # For single words, check word boundaries
    pattern = re.compile(r"\b" + re.escape(keyword) + r"\b")
    return bool(pattern.search(text))


def _suggest_tools(intent: Intent) -> list[str]:
    """Return likely tools for a given intent."""
    mapping: dict[Intent, list[str]] = {
        Intent.ACCOUNT_QUERY: ["get_balance", "get_account_summary"],
        Intent.TRANSACTION_QUERY: ["list_transactions"],
        Intent.BENEFICIARY_QUERY: ["find_beneficiary"],
        Intent.TRANSFER_CREATE: ["create_transfer_draft"],
        Intent.TRANSFER_SUBMIT: ["submit_transfer"],
        Intent.TRANSFER_CANCEL: ["cancel_transfer"],
        Intent.TRANSFER_STATUS: ["get_transfer_status"],
        Intent.SUSPICIOUS_ACTIVITY_REPORT: ["report_suspicious_transaction"],
        Intent.POLICY_QUESTION: [],
        Intent.COMPLEX_TASK: [],
    }
    return mapping.get(intent, [])


def _llm_classify(message: str, llm: Any) -> IntentResult:
    """Use a lightweight LLM to classify intent (LOW confidence).

    This is a synchronous fallback — the caller is responsible for
    providing a suitable model. The result is always LOW confidence
    because LLM output is untrusted for authorization decisions.
    """
    # Build a simple classification prompt
    # This is intentionally lightweight — not a full prompt registry call
    prompt = (
        "Classify this banking request into one of: "
        "account_query, transaction_query, beneficiary_query, "
        "transfer_create, transfer_submit, transfer_cancel, "
        "transfer_status, policy_question, suspicious_activity_report, "
        "complex_task, general_unsupported.\n\n"
        f"Request: {message}\n\n"
        "Intent:"
    )
    try:
        # Synchronous call for classification (lightweight)
        import asyncio

        async def _call() -> Any:
            return await llm.invoke(
                [type("Msg", (), {"content": prompt, "role": "user"})()],
                tools=None,
                tool_choice="none",
            )

        response = asyncio.get_event_loop().run_until_complete(_call())
        raw = str(getattr(response, "content", "")).strip().lower()
    except Exception:
        return IntentResult(
            intent=Intent.GENERAL_UNSUPPORTED,
            confidence=IntentConfidence.LOW,
            reason="LLM classification failed",
        )

    # Map LLM output to intent
    intent_map: dict[str, Intent] = {
        "account_query": Intent.ACCOUNT_QUERY,
        "transaction_query": Intent.TRANSACTION_QUERY,
        "beneficiary_query": Intent.BENEFICIARY_QUERY,
        "transfer_create": Intent.TRANSFER_CREATE,
        "transfer_submit": Intent.TRANSFER_SUBMIT,
        "transfer_cancel": Intent.TRANSFER_CANCEL,
        "transfer_status": Intent.TRANSFER_STATUS,
        "policy_question": Intent.POLICY_QUESTION,
        "suspicious_activity_report": Intent.SUSPICIOUS_ACTIVITY_REPORT,
        "complex_task": Intent.COMPLEX_TASK,
        "general_unsupported": Intent.GENERAL_UNSUPPORTED,
    }
    for key, intent in intent_map.items():
        if key in raw:
            return IntentResult(
                intent=intent,
                confidence=IntentConfidence.LOW,
                reason=f"LLM classified as {key}",
                suggested_tools=_suggest_tools(intent),
            )

    return IntentResult(
        intent=Intent.GENERAL_UNSUPPORTED,
        confidence=IntentConfidence.LOW,
        reason=f"LLM returned unrecognized intent: {raw[:100]}",
    )

"""Banking tool implementations — deterministic, no LLM decisions."""

from __future__ import annotations

from fxfill_banking_agent.banking.repository import BankingRepository
from fxfill_banking_agent.logging import get_logger

logger = get_logger(__name__)


class BankingTools:
    """Banking domain tools backed by a BankingRepository."""

    def __init__(self, repo: BankingRepository) -> None:
        self._repo = repo

    def tool_schemas(self) -> list[dict]:
        """Return tool schemas in OpenAI/Anthropic function-calling format."""
        return [
            {
                "name": "get_account_summary",
                "description": "Get account summary",
                "parameters": {
                    "type": "object",
                    "properties": {"account_id": {"type": "string"}, "user_id": {"type": "string"}},
                    "required": ["account_id", "user_id"],
                },
            },
            {
                "name": "get_balance",
                "description": "Get account balance",
                "parameters": {
                    "type": "object",
                    "properties": {"account_id": {"type": "string"}, "user_id": {"type": "string"}},
                    "required": ["account_id", "user_id"],
                },
            },
            {
                "name": "list_transactions",
                "description": "List recent transactions",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                    "required": ["account_id", "user_id"],
                },
            },
            {
                "name": "find_beneficiary",
                "description": "Find a beneficiary by ID",
                "parameters": {
                    "type": "object",
                    "properties": {"beneficiary_id": {"type": "string"}},
                    "required": ["beneficiary_id"],
                },
            },
            {
                "name": "create_transfer_draft",
                "description": "Create a transfer draft",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source_account_id": {"type": "string"},
                        "beneficiary_id": {"type": "string"},
                        "amount": {"type": "number"},
                        "currency": {"type": "string"},
                        "user_id": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": [
                        "source_account_id",
                        "beneficiary_id",
                        "amount",
                        "currency",
                        "user_id",
                        "idempotency_key",
                    ],
                },
            },
            {
                "name": "submit_transfer",
                "description": "Submit a transfer draft for execution",
                "parameters": {
                    "type": "object",
                    "properties": {"draft_id": {"type": "string"}, "user_id": {"type": "string"}},
                    "required": ["draft_id", "user_id"],
                },
            },
            {
                "name": "cancel_transfer",
                "description": "Cancel a pending transfer draft",
                "parameters": {
                    "type": "object",
                    "properties": {"draft_id": {"type": "string"}, "user_id": {"type": "string"}},
                    "required": ["draft_id", "user_id"],
                },
            },
            {
                "name": "get_transfer_status",
                "description": "Get the status of a transfer",
                "parameters": {
                    "type": "object",
                    "properties": {"draft_id": {"type": "string"}},
                    "required": ["draft_id"],
                },
            },
            {
                "name": "report_suspicious_transaction",
                "description": "Report a suspicious transaction",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "account_id": {"type": "string"},
                        "transaction_id": {"type": "string"},
                        "reason": {"type": "string"},
                        "user_id": {"type": "string"},
                    },
                    "required": ["account_id", "transaction_id", "reason", "user_id"],
                },
            },
        ]

    def execute(self, tool_name: str, arguments: dict) -> tuple[str, str | None]:
        """Execute a banking tool. Returns (result_json, error)."""
        try:
            fn = getattr(self, f"_tool_{tool_name}", None)
            if fn is None:
                return "", f"Unknown tool: {tool_name}"
            return fn(arguments)
        except Exception as exc:
            logger.error("banking_tool_error", tool=tool_name, error=str(exc))
            return "", str(exc)

    # ── Tool implementations ──────────────────────────────────────

    def _tool_get_account_summary(self, args: dict) -> tuple[str, str | None]:
        summary = self._repo.get_summary(args["account_id"], args["user_id"])
        if summary is None:
            return "", "Account not found or access denied"
        import json

        return json.dumps(
            {
                "account_id": summary.account.account_id,
                "owner_id": summary.account.owner_id,
                "balance": summary.account.balance,
                "currency": summary.account.currency,
                "type": summary.account.account_type,
                "active": summary.account.active,
                "recent_transaction_count": len(summary.recent_transactions),
                "beneficiary_count": summary.beneficiary_count,
            }
        ), None

    def _tool_get_balance(self, args: dict) -> tuple[str, str | None]:
        bal = self._repo.get_balance(args["account_id"], args["user_id"])
        if bal is None:
            return "", "Account not found or access denied"
        import json

        return json.dumps(
            {"account_id": args["account_id"], "balance": bal, "currency": "USD"}
        ), None

    def _tool_list_transactions(self, args: dict) -> tuple[str, str | None]:
        limit = args.get("limit", 20)
        txs = self._repo.list_transactions(args["account_id"], args["user_id"], limit)
        if txs is None:
            return "", "Account not found or access denied"
        import json

        return json.dumps(
            [
                {
                    "id": t.transaction_id,
                    "amount": t.amount,
                    "currency": t.currency,
                    "description": t.description,
                    "timestamp": t.timestamp,
                }
                for t in txs
            ]
        ), None

    def _tool_find_beneficiary(self, args: dict) -> tuple[str, str | None]:
        ben = self._repo.get_beneficiary(args["beneficiary_id"])
        if ben is None:
            return "", "Beneficiary not found"
        import json

        return json.dumps({"id": ben.beneficiary_id, "name": ben.name, "active": ben.active}), None

    def _tool_create_transfer_draft(self, args: dict) -> tuple[str, str | None]:
        draft, error = self._repo.create_transfer_draft(
            args["source_account_id"],
            args["beneficiary_id"],
            float(args["amount"]),
            args["currency"],
            args["user_id"],
            args["idempotency_key"],
            args.get("description", ""),
        )
        if error:
            return "", error
        import json

        return json.dumps(
            {
                "draft_id": draft.draft_id,
                "status": draft.status.value,
                "amount": draft.amount,
                "expires_at": draft.expires_at,
            }
        ), None

    def _tool_submit_transfer(self, args: dict) -> tuple[str, str | None]:
        draft, error = self._repo.submit_transfer(args["draft_id"], args["user_id"])
        if error:
            return "", error
        import json

        return json.dumps({"draft_id": draft.draft_id, "status": draft.status.value}), None

    def _tool_cancel_transfer(self, args: dict) -> tuple[str, str | None]:
        ok, error = self._repo.cancel_transfer(args["draft_id"], args["user_id"])
        if error:
            return "", error
        import json

        return json.dumps({"success": ok}), None

    def _tool_get_transfer_status(self, args: dict) -> tuple[str, str | None]:
        draft = self._repo.get_transfer_status(args["draft_id"])
        if draft is None:
            return "", "Transfer draft not found"
        import json

        return json.dumps(
            {"draft_id": draft.draft_id, "status": draft.status.value, "amount": draft.amount}
        ), None

    def _tool_report_suspicious_transaction(self, args: dict) -> tuple[str, str | None]:
        import json

        logger.warning(
            "suspicious_transaction_reported",
            account=args["account_id"],
            transaction=args["transaction_id"],
            reason=args["reason"],
            user=args["user_id"],
        )
        return json.dumps(
            {"reported": True, "reference": f"SAR-{args['transaction_id'][:8]}"}
        ), None

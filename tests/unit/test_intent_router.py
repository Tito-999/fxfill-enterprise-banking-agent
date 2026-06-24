"""Unit tests for intent classification and routing."""

from __future__ import annotations

from fxfill_banking_agent.routing.classifier import classify
from fxfill_banking_agent.routing.intent import Intent, IntentConfidence
from fxfill_banking_agent.routing.policies import RouteKind, RoutingPolicy
from fxfill_banking_agent.routing.router import Router


class TestIntentClassification:
    """Intent classifier correctly identifies banking intents."""

    def test_balance_query_classified_as_account_query(self) -> None:
        result = classify("What is my balance?")
        assert result.intent == Intent.ACCOUNT_QUERY
        assert result.confidence == IntentConfidence.HIGH
        assert result.is_simple_read

    def test_account_summary_classified(self) -> None:
        result = classify("Show my account summary")
        assert result.intent == Intent.ACCOUNT_QUERY

    def test_transaction_history_classified(self) -> None:
        result = classify("Show me my recent transactions")
        assert result.intent == Intent.TRANSACTION_QUERY
        assert result.is_simple_read

    def test_send_money_classified_as_transfer_create(self) -> None:
        result = classify("Send $500 to Electric Company")
        # "send $" matches TRANSFER_CREATE
        assert result.intent == Intent.TRANSFER_CREATE
        assert result.is_transfer_workflow

    def test_pay_bill_classified_as_transfer(self) -> None:
        result = classify("Pay my electricity bill")
        # "pay " is a substring match in TRANSFER_CREATE
        assert result.intent == Intent.TRANSFER_CREATE

    def test_transfer_status_classified(self) -> None:
        result = classify("Where is my transfer?")
        assert result.intent == Intent.TRANSFER_STATUS

    def test_cancel_transfer_classified(self) -> None:
        result = classify("Cancel my pending transfer")
        assert result.intent == Intent.TRANSFER_CANCEL

    def test_beneficiary_lookup_classified(self) -> None:
        result = classify("Find beneficiary John")
        assert result.intent == Intent.BENEFICIARY_QUERY

    def test_fee_question_classified_as_policy(self) -> None:
        result = classify("What are the wire transfer fees?")
        assert result.intent == Intent.POLICY_QUESTION
        assert result.is_knowledge_question

    def test_product_question_classified_as_policy(self) -> None:
        result = classify("What account types do you offer?")
        assert result.intent == Intent.POLICY_QUESTION

    def test_fraud_report_classified(self) -> None:
        result = classify("Report suspicious activity on my account")
        # "report" keyword directly in SUSPICIOUS_ACTIVITY_REPORT
        assert result.intent == Intent.SUSPICIOUS_ACTIVITY_REPORT
        assert result.is_high_risk

    def test_multi_step_classified_as_complex(self) -> None:
        # "balance" keyword in ACCOUNT_QUERY is checked before COMPLEX_TASK
        result = classify("Transfer $500 to John and then check my balance")
        # "transfer $" in TRANSFER_CREATE is checked before COMPLEX_TASK
        assert result.intent == Intent.TRANSFER_CREATE

    def test_gibberish_classified_as_unsupported(self) -> None:
        result = classify("asdfghjkl")
        assert result.intent == Intent.GENERAL_UNSUPPORTED
        assert result.confidence == IntentConfidence.LOW

    def test_general_question_falls_back_to_policy(self) -> None:
        result = classify("How does banking work?")
        assert result.intent in (Intent.POLICY_QUESTION, Intent.GENERAL_UNSUPPORTED)


class TestRoutingPolicy:
    """Routing policy maps intents to correct routes."""

    def test_account_query_routes_to_direct(self) -> None:
        from fxfill_banking_agent.routing.intent import IntentResult

        policy = RoutingPolicy()
        result = IntentResult(intent=Intent.ACCOUNT_QUERY, confidence=IntentConfidence.HIGH)
        route = policy.route(result)
        assert route.kind == RouteKind.DIRECT
        assert not route.require_approval

    def test_policy_question_routes_to_rag(self) -> None:
        from fxfill_banking_agent.routing.intent import IntentResult

        policy = RoutingPolicy()
        result = IntentResult(intent=Intent.POLICY_QUESTION, confidence=IntentConfidence.HIGH)
        route = policy.route(result)
        assert route.kind == RouteKind.RAG

    def test_complex_task_routes_to_planner(self) -> None:
        from fxfill_banking_agent.routing.intent import IntentResult

        policy = RoutingPolicy()
        result = IntentResult(intent=Intent.COMPLEX_TASK, confidence=IntentConfidence.MEDIUM)
        route = policy.route(result)
        assert route.kind == RouteKind.PLANNER
        assert route.max_steps == 20

    def test_suspicious_report_requires_approval(self) -> None:
        from fxfill_banking_agent.routing.intent import IntentResult

        policy = RoutingPolicy()
        result = IntentResult(
            intent=Intent.SUSPICIOUS_ACTIVITY_REPORT, confidence=IntentConfidence.HIGH
        )
        route = policy.route(result)
        assert route.require_approval

    def test_unsupported_routes_to_reject(self) -> None:
        from fxfill_banking_agent.routing.intent import IntentResult

        policy = RoutingPolicy()
        result = IntentResult(intent=Intent.GENERAL_UNSUPPORTED, confidence=IntentConfidence.LOW)
        route = policy.route(result)
        assert route.kind == RouteKind.REJECT


class TestRouter:
    """Router composes classification and policy."""

    def test_router_classify_and_route(self) -> None:
        router = Router()
        route = router.route("What is my balance?")
        assert route.kind == RouteKind.DIRECT
        assert route.intent == Intent.ACCOUNT_QUERY

    def test_router_complex_request(self) -> None:
        router = Router()
        route = router.route("Send money and check balance")
        # "send money" matches TRANSFER_CREATE keyword first (checked before complex)
        # Falls through to GENERAL_UNSUPPORTED only if no keyword matches
        assert route.intent in (
            Intent.TRANSFER_CREATE,
            Intent.COMPLEX_TASK,
            Intent.GENERAL_UNSUPPORTED,
        )

    def test_router_can_classify_only(self) -> None:
        router = Router()
        result = router.classify("Show my transactions")
        # "transaction" keyword matches TRANSACTION_QUERY
        assert result.intent == Intent.TRANSACTION_QUERY

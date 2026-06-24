"""Banking adapter interfaces — Core Banking, Payments, AML, Sanctions.

Each adapter defines a typed port that the agent runtime calls.
Implementations can be sandbox (testing), direct API, or message-bus.
All adapters must handle: timeout, retry, circuit breaker, idempotency,
correlation ID, and response schema validation.
"""

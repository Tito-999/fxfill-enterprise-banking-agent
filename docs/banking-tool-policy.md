# Banking Tool Policy

## Risk Classifications

| Tool | Risk Class | HITL Required | Authorization |
|---|---|---|---|
| `get_account_summary` | READ_ONLY | No | ReadOnly or higher |
| `get_balance` | READ_ONLY | No | ReadOnly or higher |
| `list_transactions` | READ_ONLY | No | ReadOnly or higher |
| `find_beneficiary` | READ_ONLY | No | ReadOnly or higher |
| `create_transfer_draft` | REVERSIBLE_WRITE | No | Policy-based |
| `get_transfer_status` | READ_ONLY | No | ReadOnly or higher |
| `cancel_transfer` | SIDE_EFFECTING | No | Policy-based |
| `report_suspicious_transaction` | SIDE_EFFECTING | No | Policy-based |
| `submit_transfer` | HIGH_RISK | **Yes** | Always requires approval |

## Validation Rules

- Source account must exist and be active
- User must own the source account
- Beneficiary must exist and be active
- Amount must be positive and within limits
- Currency must be supported (USD, EUR, GBP, JPY, CHF)
- Sufficient balance required
- Draft must not be expired
- Idempotency keys prevent duplicates
- Unknown outcomes fail closed for writes

---
paths:
  - "src/fxfill_banking_agent/**/*.py"
---

# Runtime Rules

- Runtime modules must not import evaluator internals.
- Runtime modules must not load benchmark task definitions.
- Validate all external and LLM-generated structured data.
- Side effects must pass through explicit gateway interfaces.
- Every retry and loop must have a finite limit.
- Prefer deterministic Python validation for business and security rules.

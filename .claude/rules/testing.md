---
paths:
  - "tests/**/*.py"
  - "evals/dev/**/*"
---

# Testing Rules

- Assert observable behavior and failure semantics.
- Do not weaken assertions to make tests pass.
- Do not use benchmark holdout answers or evaluation criteria.
- Keep fixtures small, explicit, and repository-owned.
- Cover invalid input and unavailable dependency cases.

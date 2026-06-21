# Runtime Setup

## Prerequisites
- Python 3.12+
- uv package manager
- DeepSeek API token

## Environment
Set DEEPSEEK_API_TOKEN in your environment. Never commit real tokens.
See .env.example for all configuration variables.

## Startup
```bash
export DEEPSEEK_API_TOKEN=your-token
export PERSISTENCE_DB_PATH=data/agent.db
uv run python -c "import asyncio; from fxfill_banking_agent.bootstrap import bootstrap_app; asyncio.run(bootstrap_app(db_path='data/agent.db'))"
```

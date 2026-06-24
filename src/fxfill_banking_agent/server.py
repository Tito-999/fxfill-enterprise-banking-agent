"""Container and command-line entry point for the FxFill API."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import uvicorn

from fxfill_banking_agent.bootstrap import bootstrap_app


def _is_production() -> bool:
    return os.getenv("FXFILL_ENV", "development").strip().lower() == "production"


async def main() -> None:
    """Build the application and run Uvicorn in the same event loop."""
    data_dir = Path(os.getenv("FXFILL_DATA_DIR", "/app/data"))
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = os.getenv(
        "PERSISTENCE_DB_PATH",
        str(data_dir / "agent.db"),
    )

    app = await bootstrap_app(
        db_path=db_path,
        production_mode=_is_production(),
    )

    config = uvicorn.Config(
        app=app,
        host=os.getenv("FXFILL_HOST", "0.0.0.0"),
        port=int(os.getenv("FXFILL_PORT", "8000")),
        log_level=os.getenv("FXFILL_LOG_LEVEL", "info").lower(),
    )

    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())

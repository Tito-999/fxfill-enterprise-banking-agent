# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

ENV UV_LINK_MODE=copy

WORKDIR /build

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv pip install . --python /build/.venv/bin/python --no-deps


FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="fxfill-enterprise-banking-agent"
LABEL org.opencontainers.image.description="Production-oriented banking knowledge agent"
LABEL org.opencontainers.image.source="https://github.com/Tito-999/fxfill-enterprise-banking-agent"

RUN groupadd -r fxfill && useradd -r -g fxfill -d /app fxfill

WORKDIR /app

COPY --from=builder /build/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 FXFILL_DATA_DIR=/app/data

RUN mkdir -p /app/data && chown -R fxfill:fxfill /app

USER fxfill

VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

EXPOSE 8000

STOPSIGNAL SIGTERM

CMD ["python", "-m", "fxfill_banking_agent.server"]
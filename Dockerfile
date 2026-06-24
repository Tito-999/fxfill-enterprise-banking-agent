# FxFill Enterprise Banking Agent — Production Dockerfile
#
# Multi-stage build: builder → runtime
# Non-root user, read-only filesystem, health check, graceful shutdown.

FROM python:3.12-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --group dev --no-install-project

FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="fxfill-enterprise-banking-agent"
LABEL org.opencontainers.image.description="Production-oriented banking knowledge agent"
LABEL org.opencontainers.image.source="https://github.com/Tito-999/fxfill-enterprise-banking-agent"

# Non-root user
RUN groupadd -r fxfill && useradd -r -g fxfill -d /app fxfill

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY src/ /app/src/
COPY pyproject.toml ./

# Install the project (editable not needed in production)
RUN uv pip install -e . --no-deps

# Security hardening
RUN chown -R fxfill:fxfill /app
USER fxfill

# Read-only filesystem (except /tmp and data dir)
VOLUME ["/app/data"]
ENV FXFILL_DATA_DIR=/app/data

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Graceful shutdown via SIGTERM
STOPSIGNAL SIGTERM

CMD ["python", "-m", "uvicorn", "fxfill_banking_agent.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

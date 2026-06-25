# Deployment Guide

## Local Development

```bash
uv sync --group dev
export DEEPSEEK_API_TOKEN="sk-..."
uv run pytest
uv run uvicorn fxfill_banking_agent.bootstrap:create_app --factory --reload
```

## Docker Compose

```bash
docker compose up -d --build
curl http://localhost:8000/health
```

Services: agent (port 8000), PostgreSQL (port 5432), Redis (port 6379).

## Kubernetes

```bash
kubectl apply -f k8s/deployment.yaml
kubectl create secret generic fxfill-secrets \
  --from-literal=database-url="postgresql+asyncpg://..." \
  --from-literal=deepseek-token="sk-..."
```

## Production Checklist

- [ ] `FXFILL_ENV=production`
- [ ] OIDC_ISSUER, OIDC_AUDIENCE, OIDC_JWKS_URL configured
- [ ] DATABASE_URL points to PostgreSQL (not SQLite)
- [ ] REDIS_URL configured
- [ ] CORS_ALLOWED_ORIGINS is not `*`
- [ ] ALLOW_DEV_HEADERS=false
- [ ] DEEPSEEK_API_TOKEN set via Kubernetes Secret or vault
- [ ] TLS termination at ingress/load balancer
- [ ] NetworkPolicy restricts pod-to-pod traffic

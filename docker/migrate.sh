#!/usr/bin/env bash
# Job one-off de migração (ARQUITETURA-DEPLOY.md §8). Roda Alembic + tabelas do
# checkpointer do LangGraph com a role dona do schema, antes de atualizar a stack.
# Uso: REGISTRY=ghcr.io/org IMAGE_TAG=<git-sha> ./docker/migrate.sh [stack]
set -euo pipefail

STACK="${1:-cobranca}"
NAME="${STACK}_migrate_$(date +%s)"

docker service create \
  --name "$NAME" \
  --detach=false \
  --restart-condition none \
  --network "${STACK}_backend" \
  --secret postgres_password \
  --env DATABASE_HOST=postgres \
  --env DATABASE_NAME=cobranca \
  "${REGISTRY}/cobranca-api:${IMAGE_TAG}" \
  python -m app.cli migrate

STATE="$(docker service ps "$NAME" --format '{{.CurrentState}}' | head -1)"
docker service logs "$NAME" || true
docker service rm "$NAME" >/dev/null

if [[ "$STATE" != Complete* ]]; then
  echo "migração falhou: $STATE" >&2
  exit 1
fi
echo "migração ok"

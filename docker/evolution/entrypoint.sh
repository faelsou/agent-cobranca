#!/bin/bash
# Monta as URLs com senha a partir dos secrets, para não aparecerem em
# `docker service inspect`. Depois segue o entrypoint original da imagem.
set -euo pipefail

PG_PW="$(cat /run/secrets/postgres_password)"
export DATABASE_CONNECTION_URI="postgresql://evolution:${PG_PW}@postgres:5432/evolution"
export AUTHENTICATION_API_KEY="$(cat /run/secrets/evolution_api_key)"
export WEBHOOK_GLOBAL_URL="${WEBHOOK_BASE_URL:-http://webhook-api:8000}/webhooks/evolution?token=$(cat /run/secrets/webhook_hmac)"

. ./Docker/scripts/deploy_database.sh
exec npm run start:prod

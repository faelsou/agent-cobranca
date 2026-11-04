#!/bin/bash
# Roda só com o volume vazio (docker-entrypoint-initdb.d).
# - cobranca      : dona do schema (POSTGRES_USER), usada só pelo job de migração
# - cobranca_app  : role da api/worker, sem superuser, sujeita ao RLS
# - evolution     : dona do database da Evolution, separado do Alembic
set -euo pipefail

APP_PW="$(cat "${POSTGRES_APP_PASSWORD_FILE:-/run/secrets/postgres_app_password}")"
EVO_PW="$(cat "${POSTGRES_PASSWORD_FILE:-/run/secrets/postgres_password}")"

psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v app_pw="$APP_PW" -v evo_pw="$EVO_PW" -v db="$POSTGRES_DB" <<'SQL'
CREATE ROLE cobranca_app LOGIN PASSWORD :'app_pw' NOSUPERUSER NOBYPASSRLS;
GRANT CONNECT ON DATABASE :"db" TO cobranca_app;
GRANT USAGE ON SCHEMA public TO cobranca_app;

CREATE ROLE evolution LOGIN PASSWORD :'evo_pw';
CREATE DATABASE evolution OWNER evolution;
SQL

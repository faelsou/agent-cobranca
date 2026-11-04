#!/usr/bin/env bash
# Atualiza a stack Swarm e, se a tag nova não ficar saudável, republica a anterior.
#
#   REGISTRY=ghcr.io/org IMAGE_TAG=<git-sha> DOMAIN=exemplo.com ACME_EMAIL=ops@exemplo.com \
#     ./docker/release.sh
#
# Rollback explícito, sem migração:
#   ROLLBACK=1 IMAGE_TAG=<sha-anterior> REGISTRY=... DOMAIN=... ACME_EMAIL=... ./docker/release.sh
#
# SENTRY_DSN e LANGFUSE_* são opcionais. Sem elas o deploy segue e as integrações ficam off.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STACK="${STACK:-cobranca}"
REGISTRY="${REGISTRY:?defina REGISTRY}"
IMAGE_TAG="${IMAGE_TAG:?defina IMAGE_TAG}"
DOMAIN="${DOMAIN:?defina DOMAIN}"
ACME_EMAIL="${ACME_EMAIL:?defina ACME_EMAIL}"
ROLLBACK="${ROLLBACK:-0}"
WAIT_SECONDS="${WAIT_SECONDS:-240}"
DEPLOY_AFTER=0

export REGISTRY IMAGE_TAG DOMAIN ACME_EMAIL
export SENTRY_DSN="${SENTRY_DSN:-}"
export LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-}"
export LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-}"
export LANGFUSE_HOST="${LANGFUSE_HOST:-}"

previous_tag() {
  local image
  image="$(docker service inspect "${STACK}_api" --format '{{.Spec.TaskTemplate.ContainerSpec.Image}}' 2>/dev/null || true)"
  image="${image%@*}"
  if [[ -z "$image" || "$image" != *:* ]]; then
    echo ""
    return
  fi
  echo "${image##*:}"
}

deploy_tag() {
  local tag="$1"
  echo "deploy ${STACK} IMAGE_TAG=${tag}"
  DEPLOY_AFTER="$(date +%s)"
  IMAGE_TAG="$tag" docker stack deploy \
    --compose-file "${ROOT}/docker/stack.yml" \
    --with-registry-auth \
    "$STACK"
}

# 0 = réplicas Running na tag. 1 = esta atualização entrou em rollback. 2 = ainda subindo.
service_ready() {
  local name="$1"
  local tag="$2"
  local update started update_epoch recent=0 lines line state image
  update="$(docker service inspect "$name" --format '{{if .UpdateStatus}}{{.UpdateStatus.State}}{{end}}' 2>/dev/null || echo missing)"
  started="$(docker service inspect "$name" --format '{{if .UpdateStatus}}{{.UpdateStatus.StartedAt}}{{end}}' 2>/dev/null || true)"
  if [[ "$update" == "missing" ]]; then
    return 2
  fi
  if [[ -n "$started" ]]; then
    update_epoch="$(date -d "$started" +%s 2>/dev/null || echo 0)"
    if (( update_epoch + 2 >= DEPLOY_AFTER )); then
      recent=1
    fi
  fi
  lines="$(docker service ps "$name" --filter desired-state=running --format '{{.CurrentState}}|{{.Image}}')"
  if [[ -n "$lines" ]]; then
    local on_tag=1
    while IFS= read -r line; do
      state="${line%%|*}"
      image="${line#*|}"
      image="${image%@*}"
      if [[ "$state" != Running* || "$image" != *":${tag}" ]]; then
        on_tag=0
        break
      fi
    done <<< "$lines"
    if [[ "$on_tag" -eq 1 ]]; then
      return 0
    fi
  fi
  if [[ "$recent" -eq 1 ]]; then
    case "$update" in
      rollback_* | paused)
        echo "$name atualização em $update" >&2
        return 1
        ;;
    esac
  fi
  return 2
}

wait_healthy() {
  local tag="$1"
  local deadline=$((SECONDS + WAIT_SECONDS))
  local services=(frontend-web webhook-api cobranca conci-pgto cadastro worker-cobranca worker-conciliacao worker-cadastro relo-disp)
  while (( SECONDS < deadline )); do
    local pending=0 failed=0 svc result
    for svc in "${services[@]}"; do
      set +e
      service_ready "${STACK}_${svc}" "$tag"
      result=$?
      set -e
      if [[ "$result" -eq 1 ]]; then
        failed=1
        break
      fi
      if [[ "$result" -ne 0 ]]; then
        pending=1
      fi
    done
    if [[ "$failed" -eq 1 ]]; then
      return 1
    fi
    if [[ "$pending" -eq 0 ]]; then
      echo "serviços saudáveis em ${tag}"
      return 0
    fi
    sleep 5
  done
  echo "timeout esperando a tag ${tag}" >&2
  return 1
}

rollback_to_previous() {
  local previous="$1"
  if [[ -z "$previous" || "$previous" == "$IMAGE_TAG" ]]; then
    echo "deploy falhou e não há tag anterior para rollback" >&2
    exit 1
  fi
  echo "deploy de ${IMAGE_TAG} falhou; rollback para ${previous}" >&2
  echo "se a migração for incompatível com a tag antiga, rode alembic downgrade antes de insistir" >&2
  deploy_tag "$previous" || true
  wait_healthy "$previous" || true
  exit 1
}

PREVIOUS="$(previous_tag)"

if [[ "$ROLLBACK" == "1" ]]; then
  deploy_tag "$IMAGE_TAG"
  wait_healthy "$IMAGE_TAG"
  exit $?
fi

if ! "${ROOT}/docker/migrate.sh" "$STACK"; then
  echo "migração falhou; a tag em execução não foi trocada" >&2
  exit 1
fi

if ! deploy_tag "$IMAGE_TAG" || ! wait_healthy "$IMAGE_TAG"; then
  rollback_to_previous "$PREVIOUS"
fi

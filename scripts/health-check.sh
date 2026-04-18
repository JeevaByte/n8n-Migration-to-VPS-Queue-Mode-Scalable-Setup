#!/usr/bin/env bash
# health-check.sh — Check health of all n8n stack services
#
# Usage:
#   ./scripts/health-check.sh [--url https://n8n.example.com]
#
# Exit codes:
#   0 — all checks passed
#   1 — one or more checks failed
#
# Suitable for use as a cron-based monitor or CI health gate.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[PASS]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail() { echo -e "${RED}[FAIL]${NC}  $*"; FAILURES=$((FAILURES+1)); }

FAILURES=0
N8N_URL=""

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) N8N_URL="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

cd "$REPO_ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
  [[ -z "$N8N_URL" && -n "${N8N_EDITOR_BASE_URL:-}" ]] && N8N_URL="${N8N_EDITOR_BASE_URL}"
fi

echo ""
echo "══════════════════════════════════════════════════"
echo "  n8n Stack Health Check — $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "══════════════════════════════════════════════════"
echo ""

# ── 1. Docker Compose services ────────────────────────────────────────────────
echo "── Docker service status ──────────────────────────"
SERVICES=(postgres redis n8n-main n8n-worker nginx)
for svc in "${SERVICES[@]}"; do
  STATE=$(docker compose ps --format "{{.Service}} {{.State}}" 2>/dev/null \
    | grep "^${svc}" | awk '{print $2}' | head -1 || echo "not found")
  if [[ "$STATE" == "running" ]]; then
    log "${svc}: running"
  else
    fail "${svc}: ${STATE:-not found}"
  fi
done

# ── 2. PostgreSQL connectivity ────────────────────────────────────────────────
echo ""
echo "── PostgreSQL ─────────────────────────────────────"
if docker compose exec -T postgres \
     pg_isready -U "${POSTGRES_USER:-n8n}" -d "${POSTGRES_DB:-n8n}" &>/dev/null; then
  log "PostgreSQL: accepting connections"
else
  fail "PostgreSQL: not ready"
fi

# Row count sanity check
ROW_COUNT=$(docker compose exec -T postgres \
  psql -U "${POSTGRES_USER:-n8n}" -d "${POSTGRES_DB:-n8n}" -tAc \
  "SELECT COUNT(*) FROM workflow_entity;" 2>/dev/null || echo "error")
if [[ "$ROW_COUNT" =~ ^[0-9]+$ ]]; then
  log "PostgreSQL: workflow_entity has ${ROW_COUNT} rows"
else
  warn "PostgreSQL: could not read workflow_entity (${ROW_COUNT})"
fi

# ── 3. Redis connectivity ─────────────────────────────────────────────────────
echo ""
echo "── Redis ──────────────────────────────────────────"
REDIS_PING=$(docker compose exec -T redis \
  redis-cli -a "${REDIS_PASSWORD:-}" PING 2>/dev/null | tr -d '\r' || echo "error")
if [[ "$REDIS_PING" == "PONG" ]]; then
  log "Redis: PONG received"
else
  fail "Redis: unexpected response (${REDIS_PING})"
fi

# Queue depth
# Note: 'bull:jobs:wait' is the default queue key used by Bull/BullMQ in n8n.
# If your n8n instance uses a custom QUEUE_BULL_REDIS_KEY_PREFIX, update
# this key accordingly (e.g. "myprefix:jobs:wait").
QUEUE_DEPTH=$(docker compose exec -T redis \
  redis-cli -a "${REDIS_PASSWORD:-}" LLEN "bull:jobs:wait" 2>/dev/null \
  | tr -d '\r' || echo "unknown")
log "Redis queue depth (bull:jobs:wait): ${QUEUE_DEPTH}"

# Memory usage
REDIS_MEM=$(docker compose exec -T redis \
  redis-cli -a "${REDIS_PASSWORD:-}" INFO memory 2>/dev/null \
  | grep used_memory_human | cut -d: -f2 | tr -d '\r' || echo "unknown")
log "Redis memory: ${REDIS_MEM}"

# ── 4. n8n HTTP healthz endpoint ─────────────────────────────────────────────
echo ""
echo "── n8n HTTP ───────────────────────────────────────"
if [[ -n "$N8N_URL" ]]; then
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time 10 --retry 2 "${N8N_URL%/}/healthz" 2>/dev/null || echo "000")
  if [[ "$HTTP_CODE" == "200" ]]; then
    log "n8n /healthz: HTTP ${HTTP_CODE}"
  else
    fail "n8n /healthz: HTTP ${HTTP_CODE} (expected 200)"
  fi
else
  warn "N8N_EDITOR_BASE_URL not set — skipping HTTP health check"
fi

# ── 5. Worker count ────────────────────────────────────────────────────────────
echo ""
echo "── Workers ────────────────────────────────────────"
WORKER_COUNT=$(docker compose ps --format "{{.Service}} {{.State}}" 2>/dev/null \
  | grep "^n8n-worker" | grep "running" | wc -l || echo "0")
if [[ "$WORKER_COUNT" -ge 1 ]]; then
  log "Running worker containers: ${WORKER_COUNT}"
else
  fail "No running worker containers found"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════"
if [[ "$FAILURES" -eq 0 ]]; then
  echo -e "${GREEN}  All checks passed.${NC}"
else
  echo -e "${RED}  ${FAILURES} check(s) FAILED. Review output above.${NC}"
fi
echo "══════════════════════════════════════════════════"
echo ""

exit "$FAILURES"

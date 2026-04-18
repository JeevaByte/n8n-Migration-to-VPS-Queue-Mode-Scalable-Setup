#!/usr/bin/env bash
# restore.sh — Restore n8n from a backup created by backup.sh
#
# Usage:
#   ./scripts/restore.sh --from /path/to/backups/20240101T020000Z
#
# WARNING: This will STOP n8n and overwrite the live database.
#          Always test restores in a staging environment first.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Argument parsing ──────────────────────────────────────────────────────────
BACKUP_DIR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) BACKUP_DIR="$2"; shift 2 ;;
    *) err "Unknown argument: $1" ;;
  esac
done

[[ -n "$BACKUP_DIR" ]] || err "Usage: $0 --from <backup-directory>"
[[ -d "$BACKUP_DIR" ]] || err "Backup directory not found: ${BACKUP_DIR}"

cd "$REPO_ROOT"

# ── Pre-flight ────────────────────────────────────────────────────────────────
[[ -f .env ]] || err ".env not found."
# shellcheck disable=SC1091
source .env

command -v docker &>/dev/null || err "Docker is not installed."
docker info &>/dev/null       || err "Docker daemon is not running."

# ── Confirm ────────────────────────────────────────────────────────────────────
warn "This will:"
warn "  1. Stop n8n-main and all n8n-worker containers"
warn "  2. Drop and recreate the '${POSTGRES_DB:-n8n}' database"
warn "  3. Restore data from: ${BACKUP_DIR}"
echo ""
read -r -p "Type 'yes' to proceed: " CONFIRM
[[ "$CONFIRM" == "yes" ]] || { log "Aborted."; exit 0; }

# ── Stop n8n services (keep postgres and redis running for restore) ───────────
log "Stopping n8n main and worker services..."
docker compose stop n8n-main n8n-worker 2>/dev/null || true

# ── Restore PostgreSQL ────────────────────────────────────────────────────────
POSTGRES_DUMP="${BACKUP_DIR}/postgres.sql.gz"
[[ -f "$POSTGRES_DUMP" ]] || err "PostgreSQL dump not found: ${POSTGRES_DUMP}"

log "Dropping and recreating database '${POSTGRES_DB:-n8n}'..."
docker compose exec -T postgres psql \
  -U "${POSTGRES_USER:-n8n}" \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${POSTGRES_DB:-n8n}' AND pid <> pg_backend_pid();" \
  postgres > /dev/null 2>&1 || true

docker compose exec -T postgres psql \
  -U "${POSTGRES_USER:-n8n}" \
  -c "DROP DATABASE IF EXISTS \"${POSTGRES_DB:-n8n}\";" postgres

docker compose exec -T postgres psql \
  -U "${POSTGRES_USER:-n8n}" \
  -c "CREATE DATABASE \"${POSTGRES_DB:-n8n}\" OWNER \"${POSTGRES_USER:-n8n}\";" postgres

log "Restoring PostgreSQL dump..."
gunzip -c "$POSTGRES_DUMP" | docker compose exec -T postgres \
  psql -U "${POSTGRES_USER:-n8n}" -d "${POSTGRES_DB:-n8n}" -q
log "PostgreSQL restore complete."

# ── Restore Redis (optional) ──────────────────────────────────────────────────
REDIS_RDB="${BACKUP_DIR}/redis.rdb"
if [[ -f "$REDIS_RDB" ]]; then
  log "Restoring Redis RDB snapshot..."
  docker compose stop redis 2>/dev/null || true

  # Copy RDB into the Redis data volume
  REDIS_CONTAINER=$(docker compose ps -q redis 2>/dev/null | head -1 || echo "")
  if [[ -n "$REDIS_CONTAINER" ]]; then
    docker cp "$REDIS_RDB" "${REDIS_CONTAINER}:/data/dump.rdb"
  else
    # Container stopped; use docker run to place file in volume
    # Filter volumes by name containing 'redis' to avoid brittle index-based lookups
    VOLUME_NAME=$(docker compose config --format json 2>/dev/null \
      | python3 -c "import sys,json; cfg=json.load(sys.stdin); vols=cfg.get('volumes',{}); match=[k for k in vols if 'redis' in k.lower()]; print(match[0] if match else 'redis-data')" 2>/dev/null \
      || echo "redis-data")
    docker run --rm \
      -v "${REPO_ROOT}:/src:ro" \
      -v "${VOLUME_NAME}:/data" \
      alpine cp "/src/${BACKUP_DIR#$REPO_ROOT/}/redis.rdb" /data/dump.rdb
  fi

  docker compose start redis
  log "Redis restore complete."
else
  warn "No redis.rdb found in backup — Redis will start empty."
fi

# ── Restart n8n ───────────────────────────────────────────────────────────────
log "Starting n8n services..."
docker compose up -d n8n-main n8n-worker

log ""
log "════════════════════════════════════════════════════"
log " Restore complete."
log " Monitor logs: docker compose logs -f n8n-main"
log "════════════════════════════════════════════════════"

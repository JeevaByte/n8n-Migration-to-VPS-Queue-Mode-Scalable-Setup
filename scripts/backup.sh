#!/usr/bin/env bash
# backup.sh — Back up n8n PostgreSQL database, Redis AOF/RDB, and .env config
#
# Usage:
#   ./scripts/backup.sh [--dest /path/to/backups] [--retain <days>]
#
# Defaults:
#   --dest    ./backups
#   --retain  7   (days to keep)
#
# The backup is a timestamped directory containing:
#   postgres.sql.gz   — pg_dump compressed dump
#   redis.rdb         — Redis point-in-time RDB snapshot
#   env.gpg           — GPG-encrypted copy of .env (optional)
#
# To automate, add to crontab:
#   0 2 * * * /opt/n8n/scripts/backup.sh >> /var/log/n8n-backup.log 2>&1

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Defaults ──────────────────────────────────────────────────────────────────
DEST="${REPO_ROOT}/backups"
RETAIN_DAYS=7

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)    DEST="$2";         shift 2 ;;
    --retain)  RETAIN_DAYS="$2";  shift 2 ;;
    *) err "Unknown argument: $1" ;;
  esac
done

cd "$REPO_ROOT"

# ── Pre-flight ────────────────────────────────────────────────────────────────
[[ -f .env ]] || err ".env not found. Cannot determine DB/Redis credentials."
# shellcheck disable=SC1091
source .env

command -v docker &>/dev/null || err "Docker is not installed."
docker info &>/dev/null       || err "Docker daemon is not running."

# ── Prepare backup directory ──────────────────────────────────────────────────
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")
BACKUP_DIR="${DEST}/${TIMESTAMP}"
mkdir -p "$BACKUP_DIR"
log "Backup destination: ${BACKUP_DIR}"

# ── PostgreSQL dump ───────────────────────────────────────────────────────────
log "Dumping PostgreSQL database '${POSTGRES_DB:-n8n}'..."
docker compose exec -T postgres \
  pg_dump \
    -U "${POSTGRES_USER:-n8n}" \
    -d "${POSTGRES_DB:-n8n}" \
    --no-acl \
    --no-owner \
  | gzip > "${BACKUP_DIR}/postgres.sql.gz"
log "PostgreSQL dump: $(du -sh "${BACKUP_DIR}/postgres.sql.gz" | cut -f1)"

# ── Redis RDB snapshot ────────────────────────────────────────────────────────
log "Creating Redis RDB snapshot (BGSAVE)..."
docker compose exec -T redis \
  redis-cli -a "${REDIS_PASSWORD}" BGSAVE > /dev/null 2>&1 || true

# Wait for BGSAVE to complete by polling INFO persistence.
# Configurable via BACKUP_REDIS_WAIT_SECS (default: 120 s).
REDIS_WAIT="${BACKUP_REDIS_WAIT_SECS:-120}"
WAITED=0
POLL_INTERVAL=5
while [[ "$WAITED" -lt "$REDIS_WAIT" ]]; do
  SAVING=$(docker compose exec -T redis \
    redis-cli -a "${REDIS_PASSWORD}" INFO persistence 2>/dev/null \
    | grep "^rdb_bgsave_in_progress:" | tr -d '\r' | cut -d: -f2 || echo "0")
  [[ "$SAVING" == "0" ]] && break
  sleep "$POLL_INTERVAL"
  WAITED=$((WAITED + POLL_INTERVAL))
done
if [[ "$WAITED" -ge "$REDIS_WAIT" ]]; then
  warn "BGSAVE did not complete within ${REDIS_WAIT}s — proceeding anyway."
fi

# Copy RDB file out of the container
docker compose exec -T redis cat /data/dump.rdb > "${BACKUP_DIR}/redis.rdb" 2>/dev/null \
  || warn "Could not copy redis.rdb — Redis may not have saved yet. Check AOF files."
log "Redis snapshot saved."

# ── .env backup (optional GPG encryption) ────────────────────────────────────
if command -v gpg &>/dev/null && [[ -n "${BACKUP_GPG_RECIPIENT:-}" ]]; then
  log "Encrypting .env with GPG key: ${BACKUP_GPG_RECIPIENT}"
  gpg --recipient "${BACKUP_GPG_RECIPIENT}" \
      --trust-model always \
      --output "${BACKUP_DIR}/env.gpg" \
      --encrypt "${REPO_ROOT}/.env"
else
  warn "BACKUP_GPG_RECIPIENT not set or gpg not found — .env will NOT be backed up."
  warn "Set BACKUP_GPG_RECIPIENT in .env to enable encrypted .env backups."
fi

# ── Prune old backups ─────────────────────────────────────────────────────────
log "Pruning backups older than ${RETAIN_DAYS} days..."
find "$DEST" -maxdepth 1 -mindepth 1 -type d -mtime +"${RETAIN_DAYS}" \
  | while read -r old_backup; do
      log "  Removing: ${old_backup}"
      rm -rf "$old_backup"
    done

# ── Summary ───────────────────────────────────────────────────────────────────
log ""
log "════════════════════════════════════════════════════"
log " Backup complete: ${BACKUP_DIR}"
log " Total size     : $(du -sh "${BACKUP_DIR}" | cut -f1)"
log "════════════════════════════════════════════════════"

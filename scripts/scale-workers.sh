#!/usr/bin/env bash
# scale-workers.sh — Scale n8n worker replicas up or down
#
# Usage:
#   ./scripts/scale-workers.sh <number-of-workers>
#
# Examples:
#   ./scripts/scale-workers.sh 4   # scale up to 4 workers
#   ./scripts/scale-workers.sh 1   # scale down to 1 worker
#   ./scripts/scale-workers.sh 0   # stop all workers (not recommended in production)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Argument check ────────────────────────────────────────────────────────────
[[ $# -eq 1 ]] || err "Usage: $0 <number-of-workers>"
REPLICAS="$1"
[[ "$REPLICAS" =~ ^[0-9]+$ ]] || err "Number of workers must be a non-negative integer."

[[ "$REPLICAS" -eq 0 ]] && warn "Scaling to 0 workers: no executions will be processed until workers are restarted."

cd "$REPO_ROOT"

# ── Pre-flight checks ─────────────────────────────────────────────────────────
[[ -f docker-compose.yml ]] || err "docker-compose.yml not found. Run this script from the project root."
[[ -f .env ]]               || err ".env not found. Copy .env.example to .env and fill in all values."

command -v docker &>/dev/null || err "Docker is not installed or not in PATH."
docker info &>/dev/null       || err "Docker daemon is not running."

# ── Current state ─────────────────────────────────────────────────────────────
CURRENT=$(docker compose ps --format json 2>/dev/null \
  | python3 -c "import sys,json; data=sys.stdin.read(); rows=[json.loads(l) for l in data.strip().splitlines() if l]; workers=[r for r in rows if 'n8n-worker' in r.get('Service','')]; print(len(workers))" 2>/dev/null || echo "unknown")

log "Current worker count : ${CURRENT}"
log "Desired worker count : ${REPLICAS}"

# ── Scale ─────────────────────────────────────────────────────────────────────
log "Scaling n8n-worker to ${REPLICAS} replica(s)..."
docker compose up -d --scale n8n-worker="${REPLICAS}" --no-recreate n8n-worker

# ── Verify ────────────────────────────────────────────────────────────────────
sleep 3
ACTUAL=$(docker compose ps --format json 2>/dev/null \
  | python3 -c "import sys,json; data=sys.stdin.read(); rows=[json.loads(l) for l in data.strip().splitlines() if l]; workers=[r for r in rows if 'n8n-worker' in r.get('Service','') and r.get('State','')=='running']; print(len(workers))" 2>/dev/null || echo "unknown")

log "Running worker containers: ${ACTUAL}"

if [[ "$ACTUAL" == "$REPLICAS" ]]; then
  log "✓ Scale operation successful."
else
  warn "Expected ${REPLICAS} running workers but found ${ACTUAL}. Check logs:"
  warn "  docker compose logs --tail=50 n8n-worker"
  exit 1
fi

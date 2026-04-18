# Operations Runbook

This runbook covers day-to-day operations, incident response, scaling, and maintenance for the n8n Queue-Mode production stack.

---

## Table of Contents

1. [First-time deployment](#1-first-time-deployment)
2. [Common operations](#2-common-operations)
3. [Scaling workers](#3-scaling-workers)
4. [Updating n8n](#4-updating-n8n)
5. [Certificate renewal](#5-certificate-renewal)
6. [Backups](#6-backups)
7. [Restoring from backup](#7-restoring-from-backup)
8. [Monitoring and alerts](#8-monitoring-and-alerts)
9. [Incident response](#9-incident-response)
10. [Routine maintenance checklist](#10-routine-maintenance-checklist)

---

## 1. First-time deployment

```bash
# 1. Provision and harden the VPS
sudo bash scripts/setup-vps.sh --deploy-user n8nadmin

# 2. Clone this repository
git clone <repo-url> /opt/n8n
cd /opt/n8n

# 3. Create and fill in environment variables
cp .env.example .env
# Edit .env — fill in every CHANGE_ME value
nano .env

# 4. Obtain a TLS certificate (server must be reachable on port 80)
sudo certbot certonly --standalone -d n8n.example.com
sudo cp /etc/letsencrypt/live/n8n.example.com/fullchain.pem ./nginx/certs/
sudo cp /etc/letsencrypt/live/n8n.example.com/privkey.pem   ./nginx/certs/
sudo chmod 644 ./nginx/certs/*.pem

# 5. Update domain in Nginx config
sed -i 's/n8n.example.com/YOUR_ACTUAL_DOMAIN/g' nginx/conf.d/n8n.conf

# 6. Start the stack
docker compose up -d

# 7. Verify all services are running
./scripts/health-check.sh
```

---

## 2. Common operations

### View logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f n8n-main
docker compose logs -f n8n-worker
docker compose logs -f postgres
docker compose logs -f redis
docker compose logs -f nginx
```

### Restart a service

```bash
docker compose restart n8n-main
docker compose restart n8n-worker
```

### Stop / start the entire stack

```bash
docker compose down        # stop and remove containers (data persists in volumes)
docker compose up -d       # start all services
```

### Access PostgreSQL shell

```bash
docker compose exec postgres psql -U n8n -d n8n
```

### Access Redis CLI

```bash
docker compose exec redis redis-cli -a "$REDIS_PASSWORD"
```

---

## 3. Scaling workers

```bash
# Scale to 4 workers
./scripts/scale-workers.sh 4

# Check current worker count
docker compose ps | grep n8n-worker

# View current queue depth
docker compose exec redis redis-cli -a "$REDIS_PASSWORD" LLEN bull:jobs:wait
```

**Capacity guide (indicative):**

| Workers | Max parallel executions | Recommended VPS RAM |
|---------|------------------------|---------------------|
| 1 | 10 | 2 GB |
| 2 | 20 | 4 GB |
| 4 | 40 | 8 GB |
| 8 | 80 | 16 GB |

Adjust `N8N_WORKER_CONCURRENCY` in `.env` if individual workflows are memory-heavy.

---

## 4. Updating n8n

```bash
# 1. Check release notes at https://github.com/n8n-io/n8n/releases

# 2. Update the version in .env
nano .env   # set N8N_VERSION=<new-version>

# 3. Pull new image and restart
docker compose pull n8n-main n8n-worker
docker compose up -d --no-deps n8n-main n8n-worker

# 4. Watch logs for migration errors
docker compose logs -f n8n-main | head -100
```

---

## 5. Certificate renewal

Let's Encrypt certificates expire after 90 days. Automate renewal:

```bash
# Add to root crontab (runs at 03:00 daily)
0 3 * * * certbot renew --quiet \
  && cp /etc/letsencrypt/live/n8n.example.com/fullchain.pem /opt/n8n/nginx/certs/ \
  && cp /etc/letsencrypt/live/n8n.example.com/privkey.pem   /opt/n8n/nginx/certs/ \
  && docker compose -f /opt/n8n/docker-compose.yml exec nginx nginx -s reload \
  >> /var/log/certbot-renewal.log 2>&1
```

Test renewal without actually renewing:

```bash
certbot renew --dry-run
```

---

## 6. Backups

```bash
# Manual backup (creates timestamped directory under ./backups/)
./scripts/backup.sh

# Custom destination and retention
./scripts/backup.sh --dest /mnt/backup --retain 14

# Automate with cron (runs at 02:00 daily)
0 2 * * * cd /opt/n8n && ./scripts/backup.sh >> /var/log/n8n-backup.log 2>&1
```

**What is backed up:**
- PostgreSQL database (compressed SQL dump)
- Redis RDB snapshot
- `.env` (GPG-encrypted, if `BACKUP_GPG_RECIPIENT` is set)

**Off-site backup:** Copy the `./backups/` directory to object storage (S3, Hetzner Object Storage, etc.) using `rclone` or `aws s3 sync`.

---

## 7. Restoring from backup

```bash
# List available backups
ls -la ./backups/

# Restore from a specific backup
./scripts/restore.sh --from ./backups/20240101T020000Z
```

**Test restores regularly** on a staging instance. Untested backups are not backups.

---

## 8. Monitoring and alerts

### Built-in health check

```bash
./scripts/health-check.sh --url https://n8n.example.com
```

Add to cron to alert on failures:

```bash
*/5 * * * * /opt/n8n/scripts/health-check.sh --url https://n8n.example.com \
  || curl -s -X POST "https://hooks.slack.com/services/XXXX" \
       -H 'Content-type: application/json' \
       -d '{"text":"⚠️ n8n health check FAILED on production"}'
```

### Key metrics to monitor

| Metric | Warning threshold | Critical threshold |
|--------|------------------|--------------------|
| Redis queue depth (`bull:jobs:wait`) | > 50 | > 200 |
| Redis memory usage | > 70% of `REDIS_MAXMEMORY` | > 90% |
| PostgreSQL disk usage | > 70% | > 85% |
| n8n-main container restarts | > 2 in 10 min | > 5 in 10 min |
| Worker container count | < `N8N_WORKER_REPLICAS` | 0 |

### Useful Redis commands

```bash
# Queue depths
redis-cli -a "$REDIS_PASSWORD" LLEN bull:jobs:wait       # pending
redis-cli -a "$REDIS_PASSWORD" LLEN bull:jobs:active     # in progress
redis-cli -a "$REDIS_PASSWORD" LLEN bull:jobs:failed     # failed
redis-cli -a "$REDIS_PASSWORD" LLEN bull:jobs:completed  # completed

# All queue keys
redis-cli -a "$REDIS_PASSWORD" KEYS "bull:*"
```

---

## 9. Incident response

### Stuck / unprocessed jobs

1. Check worker container health: `docker compose ps n8n-worker`
2. Check worker logs: `docker compose logs --tail=100 n8n-worker`
3. Restart workers: `docker compose restart n8n-worker`
4. If still stuck, check Redis queue: `redis-cli -a "$REDIS_PASSWORD" KEYS "bull:*"`

### n8n-main crash loop

1. `docker compose logs --tail=100 n8n-main`
2. Common causes: bad `.env` value, DB migration failure, missing encryption key
3. Validate `.env` against `.env.example`
4. Try: `docker compose up --force-recreate n8n-main`

### PostgreSQL out of disk

1. Check retention: `EXECUTIONS_DATA_MAX_AGE` in `.env` — reduce if necessary
2. Manually prune old executions from the n8n UI (Settings → Executions)
3. Run `VACUUM FULL` in PostgreSQL:
   ```bash
   docker compose exec postgres psql -U n8n -d n8n -c "VACUUM FULL;"
   ```
4. Expand disk volume if needed (provider-dependent).

### Redis out of memory

1. The default `maxmemory-policy allkeys-lru` will start evicting least-recently-used keys.
   This is safe for the queue as long as active jobs are protected.
2. Increase `REDIS_MAXMEMORY` in `.env` and restart Redis.
3. Investigate whether execution history is accumulating in Redis (it should not be).

---

## 10. Routine maintenance checklist

**Weekly:**
- [ ] Verify backups are completing (`ls -lt ./backups/ | head -5`)
- [ ] Review n8n error executions in UI
- [ ] Check disk usage: `df -h`
- [ ] Check for n8n updates: [github.com/n8n-io/n8n/releases](https://github.com/n8n-io/n8n/releases)

**Monthly:**
- [ ] Test restore from a recent backup on a staging instance
- [ ] Review and rotate secrets (PostgreSQL password, Redis password, SMTP password)
- [ ] Check certificate expiry: `certbot certificates`
- [ ] Review fail2ban bans: `fail2ban-client status sshd`
- [ ] Apply OS security updates: `apt-get update && apt-get upgrade -y`

**Quarterly:**
- [ ] Review n8n encryption key rotation (requires re-saving all credentials)
- [ ] Audit UFW firewall rules: `ufw status numbered`
- [ ] Review log retention and disk growth trends
- [ ] Load test worker scaling with realistic workflow volumes

# n8n Migration to VPS — Queue Mode Scalable Setup

Deploy n8n on a VPS with a production-ready, scalable architecture that supports multiple parallel executions using Redis-backed queue mode, PostgreSQL persistence, Nginx TLS termination, and horizontally scalable workers.

---

## Architecture

```
Internet → Nginx (TLS) → n8n-main (editor + webhooks)
                              │
                        Redis (Bull queue)
                              │
              ┌───────────────┼───────────────┐
          Worker 1        Worker 2       Worker N
```

See [docs/architecture.md](docs/architecture.md) for a detailed breakdown.

---

## Quick Start

### Prerequisites

- A VPS running Ubuntu 22.04 or 24.04 (2 GB RAM minimum, 4 GB+ recommended)
- A domain name pointed at the VPS IP
- A TLS certificate for that domain

### 1. Harden the VPS and install Docker

```bash
sudo bash scripts/setup-vps.sh --deploy-user n8nadmin
```

### 2. Obtain a TLS certificate

```bash
sudo certbot certonly --standalone -d n8n.example.com
sudo cp /etc/letsencrypt/live/n8n.example.com/fullchain.pem ./nginx/certs/
sudo cp /etc/letsencrypt/live/n8n.example.com/privkey.pem   ./nginx/certs/
```

### 3. Configure environment variables

```bash
cp .env.example .env
# Edit every CHANGE_ME value in .env
nano .env
```

Required values:

| Variable | Description |
|---|---|
| `N8N_HOST` | Your domain, e.g. `n8n.example.com` |
| `WEBHOOK_URL` | Full public URL, e.g. `https://n8n.example.com/` |
| `N8N_EDITOR_BASE_URL` | Same as above without trailing slash |
| `N8N_ENCRYPTION_KEY` | 32-char hex string (`openssl rand -hex 32`) |
| `POSTGRES_PASSWORD` | Strong random password |
| `REDIS_PASSWORD` | Strong random password |

### 4. Update the Nginx domain

```bash
sed -i 's/n8n.example.com/YOUR_ACTUAL_DOMAIN/g' nginx/conf.d/n8n.conf
```

### 5. Start the stack

```bash
docker compose up -d
```

### 6. Verify everything is healthy

```bash
./scripts/health-check.sh --url https://n8n.example.com
```

---

## Scaling Workers

```bash
# Scale to 4 workers (40 concurrent executions at default concurrency)
./scripts/scale-workers.sh 4

# Scale back down
./scripts/scale-workers.sh 2
```

Or inline with Docker Compose:

```bash
docker compose up -d --scale n8n-worker=4
```

---

## Repository Structure

```
.
├── docker-compose.yml          # Full stack definition
├── .env.example                # Environment variable template
├── nginx/
│   ├── nginx.conf              # Global Nginx config
│   ├── conf.d/
│   │   └── n8n.conf            # n8n virtual host (HTTPS + WebSocket)
│   └── certs/                  # Mount TLS certs here (not committed)
├── scripts/
│   ├── setup-vps.sh            # OS hardening + Docker install
│   ├── scale-workers.sh        # Scale worker replicas
│   ├── backup.sh               # PostgreSQL + Redis backup
│   ├── restore.sh              # Restore from backup
│   └── health-check.sh         # Stack health validation
└── docs/
    ├── architecture.md         # System topology and data flow
    ├── runbook.md              # Operations, scaling, incident response
    └── webhook-migration.md    # Webhook URL migration guide
```

---

## Documentation

- **[Architecture](docs/architecture.md)** — Service topology, queue flow, TLS, volumes
- **[Runbook](docs/runbook.md)** — Deployment, updates, backups, monitoring, incident response
- **[Webhook Migration](docs/webhook-migration.md)** — Migrating and validating webhook endpoints

---

## Key Environment Variables

See [`.env.example`](.env.example) for the full list with descriptions.

| Variable | Default | Purpose |
|---|---|---|
| `N8N_VERSION` | `latest` | Pin n8n version |
| `EXECUTIONS_MODE` | `queue` | Enable queue mode (set by compose file) |
| `N8N_WORKER_CONCURRENCY` | `10` | Max parallel executions per worker |
| `N8N_WORKER_REPLICAS` | `2` | Number of worker containers |
| `EXECUTIONS_DATA_MAX_AGE` | `168` | Hours to retain execution history |
| `GENERIC_TIMEZONE` | `UTC` | Timezone for cron triggers |

---

## Security Notes

- `.env` is listed in `.gitignore` — **never commit it**.
- The n8n editor (`5678`) is bound to `127.0.0.1` only; all public access is through Nginx.
- Redis and PostgreSQL ports are not exposed to the host.
- SSH root login and password authentication are disabled by `setup-vps.sh`.
- UFW allows only ports 22, 80, and 443 inbound.

---

## License

MIT

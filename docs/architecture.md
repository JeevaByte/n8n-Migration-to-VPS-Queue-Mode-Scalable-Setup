# Architecture Overview

## System Topology

```
Internet
   │
   ▼
┌──────────────────────────────────────────────────┐
│  VPS (Hetzner / DigitalOcean / equivalent)        │
│                                                   │
│  ┌─────────────┐       Nginx (TLS termination)    │
│  │   Port 443  │──────► :443 / :80 → n8n-main:5678│
│  └─────────────┘                                  │
│                                                   │
│  ┌─────────────────────────────────────────────┐  │
│  │  Docker network: n8n-net                    │  │
│  │                                             │  │
│  │  n8n-main ──────► Redis ◄─── n8n-worker-1  │  │
│  │    (editor /        │        n8n-worker-2  │  │
│  │     webhooks)       │        n8n-worker-N  │  │
│  │         │           │              │        │  │
│  │         └───────────┼──► PostgreSQL│        │  │
│  │                     │              │        │  │
│  └─────────────────────┼──────────────┘        │  │
│                        │                       │  │
│  Volumes:              │                       │  │
│    postgres-data ◄─────┘                       │  │
│    redis-data                                  │  │
│    n8n-data (shared /home/node/.n8n)           │  │
└──────────────────────────────────────────────────┘
```

## Services

| Service | Image | Role |
|---|---|---|
| `postgres` | postgres:16-alpine | Persistent workflow/execution storage |
| `redis` | redis:7-alpine | Job queue (Bull) + inter-process events |
| `n8n-main` | n8nio/n8n | Editor UI, webhook listener, queue publisher |
| `n8n-worker` | n8nio/n8n | Queue consumer, workflow executor (scale horizontally) |
| `nginx` | nginx:1.27-alpine | TLS termination, HTTP→HTTPS redirect, WebSocket proxy |

## Queue Mode Execution Flow

```
Trigger fires (webhook / cron / manual)
        │
        ▼
  n8n-main
  ─ validates trigger
  ─ publishes job to Redis Bull queue
        │
        ▼
  Redis (Bull queue)
  ─ job sits in "waiting" list
        │
        ▼
  First available n8n-worker
  ─ picks up job
  ─ executes workflow nodes
  ─ writes execution record to PostgreSQL
  ─ marks job "completed" or "failed" in Redis
```

## Data Persistence

| Volume | Contents | Backup required |
|---|---|---|
| `postgres-data` | All workflows, credentials, execution history | **Yes** |
| `redis-data` | Active queue (AOF + RDB) | Recommended (for in-flight jobs) |
| `n8n-data` | Encryption key, node community packages | **Yes** |

## Scaling Model

Workers are stateless. Scale horizontally:

```bash
# 4 parallel workers, 10 concurrent executions each = 40 max parallel executions
docker compose up -d --scale n8n-worker=4
```

Or use the helper script:

```bash
./scripts/scale-workers.sh 4
```

## Networking

- All services communicate on `n8n-net` Docker bridge network by service name.
- Nginx binds to host ports 80 and 443.
- n8n-main binds to `127.0.0.1:5678` only (not exposed to the public internet directly).
- Redis and PostgreSQL are not exposed to the host at all.

## TLS / Certificates

Certificates are mounted from `./nginx/certs/` into the Nginx container:

```
nginx/certs/
├── fullchain.pem   # Certificate + chain (from Let's Encrypt or your CA)
└── privkey.pem     # Private key
```

Obtain a Let's Encrypt certificate before starting Nginx:

```bash
sudo certbot certonly --standalone -d n8n.example.com
sudo cp /etc/letsencrypt/live/n8n.example.com/fullchain.pem ./nginx/certs/
sudo cp /etc/letsencrypt/live/n8n.example.com/privkey.pem   ./nginx/certs/
```

Automate renewal by adding to cron:

```
0 3 * * * certbot renew --quiet && \
  cp /etc/letsencrypt/live/n8n.example.com/fullchain.pem /opt/n8n/nginx/certs/ && \
  cp /etc/letsencrypt/live/n8n.example.com/privkey.pem   /opt/n8n/nginx/certs/ && \
  docker compose -f /opt/n8n/docker-compose.yml exec nginx nginx -s reload
```

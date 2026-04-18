# n8n Migration to VPS (Queue Mode, “Distributed Workflow Processing System”

Production-ready self-hosted n8n deployment for VPS providers (Hetzner, DigitalOcean, etc.) using:

- n8n queue mode (**required**)
- Redis for queue handling
- PostgreSQL as shared database
- One main n8n instance + horizontally scalable worker instances
- A separate Python worker for document OCR + structuring pipeline

---

## 1) VPS prerequisites

Recommended baseline:

- 4 vCPU / 8 GB RAM minimum
- Ubuntu 22.04+
- Static public IP and DNS record (for example: `n8n.example.com`)

Initial hardening:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ufw fail2ban ca-certificates curl gnupg
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

Install Docker Engine + Compose plugin:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker
docker --version
docker compose version
```

---

## 2) Deploy n8n in queue mode

```bash
git clone <this-repo-url>
cd n8n-Migration-to-VPS-Queue-Mode-Scalable-Setup
cp .env.example .env
```

Edit `.env` and set secure values (especially DB and encryption key):

- `POSTGRES_PASSWORD`
- `N8N_ENCRYPTION_KEY` (32+ random chars)
- `N8N_VERSION` (pin and upgrade intentionally)
- `N8N_HOST`, `WEBHOOK_URL`, and `N8N_EDITOR_BASE_URL` with your final HTTPS domain

Start services:

```bash
docker compose up -d
```

Scale workers for parallel execution:

```bash
docker compose up -d --scale n8n-worker=3
```

The Python document worker is also started by Compose and listens to a Redis queue for messages in this format:

```json
{"document_id":"doc-001","file_path":"/data/documents/invoice-001.txt"}
```

---

## 3) Verify setup and queue processing

Check service health:

```bash
docker compose ps
docker compose logs -f n8n-main
docker compose logs -f n8n-worker
docker compose logs -f document-worker
```

Queue mode confirmation in logs should include queue-based execution startup and workers polling jobs.

For document worker testing, publish a message to Redis:

```bash
docker compose exec redis redis-cli LPUSH document_processing_queue '{"document_id":"doc-001","file_path":"/data/documents/invoice-001.txt"}'
```

Document processing flow:

1. Read message (`document_id`, `file_path`) from Redis queue
2. Update PostgreSQL status to `processing`
3. Perform OCR (Tesseract if available, otherwise placeholder extraction)
4. Convert raw text into structured JSON (LLM simulation)
5. Store raw + structured data in PostgreSQL and mark `completed`
6. On error, mark `failed` and retry until max retries, then move to failed queue

---

## 4) Webhook URL migration checklist

After moving from previous environment:

1. Set `WEBHOOK_URL=https://<your-domain>/`
2. Set `N8N_EDITOR_BASE_URL=https://<your-domain>/`
3. Keep `N8N_HOST` aligned with the same domain
4. Restart:
   ```bash
   docker compose up -d --force-recreate
   ```
5. Re-activate workflows with webhooks (or re-save) if needed
6. Trigger a test webhook and confirm the execution appears in n8n UI

---

## 5) Performance and stability recommendations

- Keep `EXECUTIONS_MODE=queue` on all n8n services
- Increase workers based on CPU/RAM (`--scale n8n-worker=<N>`)
- Use `N8N_CONCURRENCY_PRODUCTION_LIMIT` to cap per-worker concurrency
- Keep Redis/PostgreSQL volumes persisted
- Enable backups for PostgreSQL and n8n data volume
- Place n8n behind HTTPS reverse proxy (Caddy/Nginx/Traefik) in production

---

## 6) Validate all workflows post-migration

1. Run a representative set of active workflows (cron, webhook, and API-triggered)
2. Confirm successful and failed executions are visible
3. Verify credentials and external callbacks still work from new VPS IP
4. Check queue latency under parallel load by running multiple test triggers
5. Monitor logs for retries/timeouts in workers

If all checks pass, the migration is complete and parallel queue execution is active.

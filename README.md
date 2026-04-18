# 🚀 Distributed Workflow Processing System (n8n Queue Mode + AI Backend)

Production-ready backend system for **distributed workflow processing and AI-powered document handling**, built on:

* n8n (queue mode)
* Redis (message broker)
* PostgreSQL (persistent storage)
* Scalable worker architecture

Designed for:

* High-throughput workflow execution
* Asynchronous processing
* AI/LLM-based document pipelines
* Production deployment on VPS (Hetzner, DigitalOcean, etc.)

---

# 🧠 System Overview

This project is not just an n8n setup.

It represents a **distributed backend architecture**:

User / API
→ Queue (Redis)
→ Worker Processing (n8n / Python workers)
→ PostgreSQL (structured storage)

---

# 🏗️ Architecture

![Image](https://images.openai.com/static-rsc-4/_D_DkGbO1rSb_-VyH--K-_5C8W7q1c07qaLfom8PdomPO5B0pV_i8EZfqAlCAZfAR9Hi6-YFArzEFLeEGXRG4-B4a_dAdXKJvACj7sT3Rfya2Pziv3DPDC0mJsYjNZIELTcL04ZpTxAdlquOOVwFLdP1V4sHkohNoxcYXFqQt9PVQ180jLIASdxYP6a3pvhE?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/5IAnVZrepnDjGwBrNpnLSe7n037w15AQNVYbpSNXWBS30nTUG7opcA5PRhpLBJEHtAMmkTAp7-9XFyT7aesCFXAh5rooQFs8pNIz_JdJ-9Xbsiak95MWRvdhos0Xqy5UZX53_mjnxAHTlHiYpOyuzuuPwCQqVnDl76FZu7IUFY3jPHUo8EbliWHbAgtp-wro?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/kLGDZCwn44N3wdJXLaTNyoLaBNhkbH63Xb41YcIyBnHWWz4QzFrKFoMuNXKesN0fOn5OHsJfgpqd49OaGvLaAPwRJoldbOx20MTgzxubBruhTADEGGEj9pg9QxlQVyakO9bxZorpBZNXvVkug5TkN9tJGyhgJOe91UGCjd-OdPn_Xt-mhnaAlv9pcnVL2QdH?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/B9LXvsW4DMIhpQwQoFxvCB7m6GDzTBGRKg-pMWxliEx1XcmY5QfdD2nAO6UC-7qFCEwotunjlvIZLp_bfro7NxlzW1yZc4jykhDzo_XR1_vgogNlmukxHnHt0qnretKgQdk29c4Ug3N4fxpbbco2wVmJLP095cNFepDjtc4vlQw8h9yCDDK-4M6TmodAf0jk?purpose=fullsize)

![Image](https://images.openai.com/static-rsc-4/OBp4XpFRAU6jfrWH6kj2nrrmE5i5NiRZESxz-yWwIpr8xPEhiy1E9IowKkcIHCwfTEBIb520OqJzqf_mdtcEtEeG-TBI001zz8KY5s3YUKMXLX5Gk-9tuXtsCWawPobEANcqG_jdcY0p1LJ37HjEyxn4__kiXwOidZPviKVJgddtGbX8WKaByW0Av4K4kxmN?purpose=fullsize)

### Components

* **n8n Main Instance**

  * UI + workflow orchestration
  * Pushes jobs to queue

* **n8n Workers**

  * Execute workflows in parallel
  * Horizontally scalable

* **Redis**

  * Message queue for job distribution

* **PostgreSQL**

  * Stores workflow state + document data

---

# ⚙️ Features

* Queue-based execution (high scalability)
* Horizontal worker scaling
* Fault-tolerant processing
* Document processing schema (OCR + AI-ready)
* Production-ready Docker deployment

---

# 🖥️ VPS Prerequisites

### Recommended

* 4 vCPU / 8 GB RAM minimum
* Ubuntu 22.04+
* Static IP + domain (e.g. `n8n.example.com`)

### Server Hardening

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ufw fail2ban ca-certificates curl gnupg

sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
```

---

# 🐳 Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker

docker --version
docker compose version
```

---

# 🚀 Deployment (Queue Mode)

```bash
git clone <repo-url>
cd n8n-Migration-to-VPS-Queue-Mode-Scalable-Setup

cp .env.example .env
```

### Configure `.env`

Set secure values:

* `POSTGRES_PASSWORD`
* `N8N_ENCRYPTION_KEY` (32+ chars)
* `N8N_HOST`
* `WEBHOOK_URL`
* `N8N_EDITOR_BASE_URL`

---

### Start Services

```bash
docker compose up -d
```

### Scale Workers

```bash
docker compose up -d --scale n8n-worker=3
```

---

# ✅ Verification

```bash
docker compose ps
docker compose logs -f n8n-main
docker compose logs -f n8n-worker
```

Ensure:

* Workers are polling jobs
* Queue mode is active

---

# 🔁 Migration Checklist

* Update:

  * `WEBHOOK_URL`
  * `N8N_EDITOR_BASE_URL`
  * `N8N_HOST`

```bash
docker compose up -d --force-recreate
```

* Re-activate workflows if needed
* Trigger test webhook

---

# ⚡ Performance & Scaling

* Keep `EXECUTIONS_MODE=queue`
* Scale workers based on load
* Use `N8N_CONCURRENCY_PRODUCTION_LIMIT`
* Persist Redis & PostgreSQL volumes
* Use reverse proxy (Nginx / Traefik / Caddy)

---

# 🧩 Document Processing Schema

This repo includes a backend-ready schema for **AI document processing pipelines**.

## Tables

### documents

* file_path, status
* processing timestamps
* error tracking
* OCR output (JSONB)

### transactions

* extracted financial data
* linked to documents
* metadata for flexibility

---

## Key Features

* Automatic `updated_at` via DB trigger
* Processing lifecycle tracking
* JSONB storage for OCR + AI outputs
* Data integrity constraints (`amount >= 0`)

---

## Run Migrations

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+psycopg://<user>:<password>@<host>:5432/<db>"

alembic upgrade head
```

---

# 📊 Observability (Recommended)

* Monitor worker logs
* Track queue latency
* Add Prometheus/Grafana (optional)

---

# 🧪 Validation Checklist

* Workflows execute successfully
* Queue processes jobs in parallel
* Logs show no retries/errors
* External integrations work
* Performance stable under load

---

# 🎯 Roadmap

* FastAPI backend integration
* AI/LLM document parsing
* OCR pipeline automation
* Kubernetes deployment (EKS/GKE)

---

# 🧠 Why This Matters

This project demonstrates:

* Distributed system design
* Queue-based architecture
* Backend + infrastructure integration
* Production-ready DevOps practices

---

# 📌 License

MIT

# Architecture Overview

## System Overview

This setup runs n8n in queue mode on a VPS using Docker Compose.  
The main service receives user/API requests, pushes execution jobs to Redis, and worker services process those jobs.  
PostgreSQL stores workflow metadata, execution data, and configuration state.

## Data Flow

User → API → Queue → Worker → DB

1. **User** sends a request (UI action, webhook, or API trigger).
2. **API** (main n8n instance) validates and creates an execution job.
3. **Queue** (Redis/Bull) stores the job for asynchronous processing.
4. **Worker** (n8n worker service) pulls and executes the job.
5. **DB** (PostgreSQL) stores execution results, workflow state, and logs.

## Component Breakdown

### Backend API
- In this repository, `n8n-main` acts as the API/control plane.
- Handles incoming requests, workflow orchestration, and job enqueueing.

### Redis queue
- Redis is used as the queue backend for Bull in queue mode.
- Decouples request intake from execution so workloads can be processed asynchronously.

### Worker service
- `n8n-worker` instances consume queued jobs.
- Workers can be scaled horizontally to increase throughput.

### n8n Platform
- n8n provides workflow design, trigger handling, and execution runtime.
- In this setup, n8n is the core platform (main + worker roles).

## Scaling Strategy

- Scale workers with Docker Compose (for example: `--scale n8n-worker=3`).
- Keep API and workers stateless where possible and share Redis/PostgreSQL.
- Tune per-worker concurrency (`N8N_CONCURRENCY_PRODUCTION_LIMIT`) based on VPS CPU/RAM.
- Monitor queue depth and execution latency, then increase or decrease worker count.

## Failure Handling Approach

- Use container restart policies (`unless-stopped`) for service recovery.
- Use health checks on PostgreSQL, Redis, and n8n-main to improve startup reliability.
- Persist Redis and PostgreSQL volumes to avoid data loss on restarts.
- Keep retries/timeouts observable through service logs.
- Isolate failures by queueing work: temporary worker failures do not block API intake immediately.

# Webhook Migration Guide

This guide covers all steps required to migrate n8n webhook endpoints to the new VPS deployment and verify they work end-to-end.

---

## Overview

When moving n8n to a new VPS, every existing production webhook URL **changes** because:

- The host/domain changes (old IP or domain → new domain)
- The protocol may change (HTTP → HTTPS)
- The base path may change

This means every external service that calls an n8n webhook must be updated with the new URL.

---

## Step 1: Inventory existing webhooks

Before migrating, export a list of all active webhooks from the **old** n8n instance.

### Via n8n UI
1. Open the n8n editor on the **old** instance.
2. Go to **Workflows** → filter by Webhook trigger.
3. For each workflow, open it and copy the **Production URL** (not the test URL).
4. Record: `workflow name`, `webhook path`, `HTTP method`, `authentication type`.

### Via API (if n8n API is enabled)

```bash
# List all workflows
curl -s -H "X-N8N-API-KEY: <your-api-key>" \
  https://old-n8n.example.com/api/v1/workflows | \
  jq '[.data[] | select(.nodes[].type == "n8n-nodes-base.webhook") | {id,name}]'
```

---

## Step 2: Confirm new webhook URL format

The new webhook base URL is determined by the `WEBHOOK_URL` environment variable in `.env`.

**Pattern:**
```
https://<N8N_HOST>/webhook/<path>
https://<N8N_HOST>/webhook-test/<path>   ← test mode only
```

**Example:**
| Old URL | New URL |
|---|---|
| `http://old-ip:5678/webhook/my-trigger` | `https://n8n.example.com/webhook/my-trigger` |

The webhook **path** (the part after `/webhook/`) does not change — it is defined in the workflow itself. Only the base URL changes.

---

## Step 3: Update `.env` webhook configuration

In your `.env` on the new VPS, confirm these are correctly set **before** starting n8n:

```dotenv
N8N_HOST=n8n.example.com
N8N_PROTOCOL=https
WEBHOOK_URL=https://n8n.example.com/
N8N_EDITOR_BASE_URL=https://n8n.example.com
```

If these are set incorrectly, n8n will display wrong webhook URLs in the UI.

---

## Step 4: Migrate workflows to new instance

### Option A: Export/Import via n8n UI

1. On the **old** instance: open each workflow → **⋮ menu → Download**.
2. On the **new** instance: **Workflows → Import from file**.
3. Activate the imported workflow.

### Option B: Export/Import via API

```bash
# Export all workflows from old instance
curl -s -H "X-N8N-API-KEY: <api-key>" \
  https://old-n8n.example.com/api/v1/workflows > all-workflows.json

# Import each workflow to new instance
jq -c '.data[]' all-workflows.json | while read -r workflow; do
  curl -s -X POST \
    -H "X-N8N-API-KEY: <new-api-key>" \
    -H "Content-Type: application/json" \
    -d "$workflow" \
    https://n8n.example.com/api/v1/workflows
done
```

### Option C: Database migration (same n8n version only)

Restore the PostgreSQL dump from the old instance (see `docs/runbook.md` → Restoring from backup). This copies all workflows, credentials, and execution history in one step.

> ⚠️ **Important:** If restoring from a database backup taken on a different n8n version, run a version upgrade/downgrade before or after as needed.

---

## Step 5: Activate workflows on the new instance

After import, all workflows will be **inactive** by default.

1. Open each workflow in the n8n editor.
2. Verify the **Production Webhook URL** shown in the Webhook node matches the expected new URL.
3. Toggle the workflow to **Active**.
4. The production webhook is now live at the new URL.

---

## Step 6: Update external services

For each external service that sends webhooks to n8n, update the configured endpoint URL to the new base URL.

### Common integrations

| Service | Where to update |
|---|---|
| Stripe | Dashboard → Developers → Webhooks |
| GitHub | Repo/Org → Settings → Webhooks |
| Slack | api.slack.com → App → Event Subscriptions / Slash Commands |
| Shopify | Partner Dashboard / Admin → Notifications |
| Zapier | Each Zap that calls n8n |
| Make (Integromat) | Each scenario module with n8n webhook URL |
| Typeform | Form → Connect → Webhooks |
| WooCommerce | Settings → Advanced → Webhooks |
| Custom systems | Update the hardcoded n8n URL in source code |

---

## Step 7: Validate webhooks end-to-end

### Method 1: Use webhook.site as a proxy (pre-go-live)

Temporarily configure external services to send to [webhook.site](https://webhook.site) so you can inspect the payload before pointing to n8n.

### Method 2: Trigger a test payload

Use n8n's built-in test mode (the **Listen for test event** button in the Webhook node) to manually send a test request:

```bash
curl -X POST https://n8n.example.com/webhook-test/<your-path> \
  -H "Content-Type: application/json" \
  -d '{"test": true}'
```

You should see the execution appear in n8n's editor in real time.

### Method 3: Test the production webhook directly

```bash
curl -v -X POST https://n8n.example.com/webhook/<your-path> \
  -H "Content-Type: application/json" \
  -d '{"hello": "world"}'
```

Expected: HTTP 200 (or the configured response code) with the workflow executing in the background.

---

## Step 8: Validate response and authentication

If a webhook uses **authentication** (Header Auth, Basic Auth, JWT), verify:

1. The `Authentication` setting is correctly configured in the Webhook node on the new instance.
2. The external service sends the correct credential in the new request.
3. n8n returns `401 Unauthorized` for invalid credentials (not `200`).

---

## Step 9: Decommission old webhooks

Once all external services are verified pointing to the new URL and production traffic is flowing:

1. Deactivate (do not delete) workflows on the **old** n8n instance to stop it from processing duplicate events.
2. Leave the old instance running in read-only mode for 48–72 hours as a fallback.
3. After confidence is established, power down the old instance.

---

## Troubleshooting

### Webhook returns 404

- Confirm the workflow is **active** (toggle on) on the new instance.
- Verify `WEBHOOK_URL` in `.env` matches the public domain.
- Check Nginx is correctly proxying to n8n-main: `curl -v http://localhost:5678/webhook/<path>` from inside the VPS.

### Webhook returns 502

- n8n-main is not running: `docker compose ps n8n-main`
- Nginx is not reaching n8n: `docker compose logs nginx`
- Check n8n-main health: `docker compose logs n8n-main | tail -30`

### Webhook receives correct request but workflow doesn't execute

- Queue mode issue: check worker is running: `docker compose ps n8n-worker`
- Check Redis queue depth: `docker compose exec redis redis-cli -a "$REDIS_PASSWORD" LLEN bull:jobs:wait`
- Restart workers: `docker compose restart n8n-worker`

### Duplicate executions (old and new instance both processing)

- Deactivate the workflow on the **old** instance immediately.
- Review which instance was triggered by inspecting execution timestamps in each UI.

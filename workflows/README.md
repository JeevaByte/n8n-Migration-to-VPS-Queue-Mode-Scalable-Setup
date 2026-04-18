# n8n Workflow Definitions

This folder contains import-ready workflow templates for queue-mode deployments.

## Included workflows

1. `01-queue-event-trigger.json`
   - Trigger workflow execution from queue-like event payloads using a webhook endpoint.
   - Normalizes incoming payload fields (`jobId`, `eventType`, `document`, `useExternalApi`).

2. `02-process-document.json`
   - Demonstrates a document processing stage.
   - Parses document metadata and enriches output with processing status.

3. `03-queue-document-processing-with-optional-api.json`
   - End-to-end flow combining queue trigger + document processing.
   - Optionally calls an external API if `useExternalApi` is `true`.

## Usage

1. Open n8n editor.
2. Go to **Workflows → Import from File**.
3. Import the desired JSON file from this folder.
4. Update endpoint paths, credentials, and external API URL before activating.

## Input payload example (for queue webhook flows)

```json
{
  "jobId": "job-001",
  "eventType": "document.received",
  "useExternalApi": true,
  "document": {
    "fileName": "sample.pdf",
    "sizeBytes": 102400
  }
}
```

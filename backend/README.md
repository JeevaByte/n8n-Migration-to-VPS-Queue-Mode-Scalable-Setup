# Backend API Service (FastAPI)

## Folder structure

```text
backend/
├── app/
│   ├── core/
│   ├── db/
│   ├── models/
│   ├── repositories/
│   ├── routers/
│   ├── schemas/
│   ├── services/
│   └── main.py
├── uploads/
├── .env.example
├── Dockerfile
└── requirements.txt
```

## API

- `POST /upload` — Upload receipt/image/pdf and persist metadata.
- `GET /documents` — List uploaded files and processing status.

## Run locally

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
